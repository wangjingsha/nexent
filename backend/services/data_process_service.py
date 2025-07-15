import logging
import io
import time
import base64
import aiohttp
import os
import redis
import warnings
import tempfile
from typing import Optional, List, Dict, Any

from PIL import Image
import torch
from transformers import CLIPProcessor, CLIPModel
from data_process.app import app as celery_app

from consts.const import CLIP_MODEL_PATH, IMAGE_FILTER

# Configure logging
logger = logging.getLogger("data_process.service")


class DataProcessService:
    def __init__(self):
        """Initialize the DataProcessService

        Args:
            num_workers: Number of worker processes for data processing
        """
        # Initialize components in a modular way
        self._init_redis_client()
        
        # Don't init clip model here, otherwise it will drastically slow down the first call from data process.
        # self._init_clip_model()

        # Suppress PIL warning about palette images
        warnings.filterwarnings('ignore', category=UserWarning, module='PIL.Image')

        self._inspector = None
        self._inspector_last_time = 0
        self._inspector_ttl = 60  # inspector缓存时间，秒
        self._inspector_lock = None
        import threading
        self._inspector_lock = threading.Lock()

    def _init_redis_client(self):
        """Initializes the Redis client and connection pool."""
        self.redis_pool = None
        self.redis_client = None
        try:
            redis_url = os.environ.get('REDIS_BACKEND_URL')
            if redis_url:
                self.redis_pool = redis.ConnectionPool.from_url(
                    redis_url,
                    max_connections=50,
                    decode_responses=True
                )
                self.redis_client = redis.Redis(connection_pool=self.redis_pool)
                logger.info("Redis client initialized successfully.")
            else:
                logger.warning("REDIS_BACKEND_URL not set, Redis client not initialized.")
        except Exception as e:
            logger.error(f"Failed to initialize Redis client: {str(e)}")

    def _init_clip_model(self):
        """Initializes the CLIP model and processor."""
        if getattr(self, 'clip_available', False):
            return
        self.model = None
        self.processor = None
        self.clip_available = False
        try:
            self.model = CLIPModel.from_pretrained(CLIP_MODEL_PATH)
            self.processor = CLIPProcessor.from_pretrained(CLIP_MODEL_PATH)
            self.clip_available = True
            logger.info("CLIP model loaded successfully")
        except Exception as e:
            logger.warning(f"Failed to load CLIP model, size-only filtering will be used: {str(e)}")
            self.clip_available = False

    async def start(self):
        """Start the data processing service"""
        logger.info("Data processing service started")

    async def stop(self):
        """Stop the data processing service"""
        logger.info("Data processing service stopped")

    def _get_celery_inspector(self):
        """Get Celery inspector"""
        with self._inspector_lock:
            now = time.time()
            if self._inspector and now - self._inspector_last_time < self._inspector_ttl:
                return self._inspector
            # 确保当前应用配置正确
            if not celery_app.conf.broker_url or not celery_app.conf.result_backend:
                celery_app.conf.broker_url = os.environ.get('REDIS_URL')
                celery_app.conf.result_backend = os.environ.get('REDIS_BACKEND_URL')
                logger.warning(f"Celery broker URL is not configured properly, reconfiguring to {celery_app.conf.broker_url}")
            try:
                inspector = celery_app.control.inspect()
                inspector.ping()
                self._inspector = inspector
                self._inspector_last_time = now
                return inspector
            except Exception as e:
                self._inspector = None
                raise Exception(f"Failed to create inspector with celery_app: {str(e)}")

    async def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get task by ID (async)"""
        from data_process.utils import get_task_info
        return await get_task_info(task_id)

    async def get_all_tasks(self, filter: bool=True) -> List[Dict[str, Any]]:
        """Get all tasks

        Args:
            filter: Whether to filter out useless task (i.e. process_and_forward) with no index_name and tast_name

        Returns:
            List[Dict[str, Any]]: List of all tasks
        """
        from data_process.utils import get_task_info, get_all_task_ids_from_redis
        import concurrent.futures
        import asyncio
        all_tasks = []
        try:
            start_time = time.time()
            logger.debug("Getting inspector to check for active and reserved tasks (concurrent)")
            inspector = self._get_celery_inspector()
            logger.debug(f"⏰ Inspector initialization took {time.time() - start_time}s")
            
            # Collect task IDs from different sources
            task_ids = set()
            def get_active():
                return inspector.active()
            def get_reserved():
                return inspector.reserved()
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                future_active = executor.submit(get_active)
                future_reserved = executor.submit(get_reserved)
                active_tasks_dict = future_active.result()
                reserved_tasks_dict = future_reserved.result()
            logger.debug(f"⏰ Get active and reserved tasks (concurrent) took {time.time() - start_time}s")
            if active_tasks_dict:
                for worker, tasks in active_tasks_dict.items():
                    for task in tasks:
                        task_id = task.get('id')
                        if task_id:
                            task_ids.add(task_id)
            if reserved_tasks_dict:
                for worker, tasks in reserved_tasks_dict.items():
                    for task in tasks:
                        task_id = task.get('id')
                        if task_id:
                            task_ids.add(task_id)

            # Currently, we don't have scheduled tasks, so skip getting scheduled tasks here
            start_time = time.time()
            logger.debug("Getting task IDs from Redis backend")
            # Also get task IDs from Redis backend (covers completed/failed tasks within expiry)
            try:
                redis_task_ids = get_all_task_ids_from_redis(self.redis_client)
                logger.debug(f"⏰ Get Redis task IDs took {time.time() - start_time}s")
                for task_id in redis_task_ids:
                    # Add to the set, duplicates will be handled
                    task_ids.add(task_id)
                
            except Exception as redis_error:
                logger.warning(f"Failed to query Redis for stored task IDs: {str(redis_error)}")
            logger.debug(f"Total unique task IDs collected (inspector + Redis): {len(task_ids)}")
            # 并发异步获取所有任务详情
            tasks = [get_task_info(task_id) for task_id in task_ids]
            all_task_infos = await asyncio.gather(*tasks, return_exceptions=True)
            for task_info in all_task_infos:
                if isinstance(task_info, Exception):
                    logger.warning(f"Failed to get status for a task: {task_info}")
                    continue
                if filter and not (task_info.get('index_name') and task_info.get('task_name')):
                    continue
                all_tasks.append(task_info)
            logger.info(f"Retrieved {len(all_tasks)} tasks.")
        except Exception as e:
            logger.error(f"Error retrieving all tasks: {str(e)}")
            all_tasks = []
        
        return all_tasks

    async def get_index_tasks(self, index_name: str, filter: bool=True) -> List[Dict[str, Any]]:
        """Get all active tasks for a specific index

        Args:
            index_name: Name of the index to filter tasks for

        Returns:
            List[Dict[str, Any]]: Tasks for the specified index
        """
        task_list = await self.get_all_tasks(filter)
        # May got multiple tasks for the same index
        return [task for task in task_list if task.get('index_name') == index_name]

    def check_image_size(self, width: int, height: int, min_width: int = 200, min_height: int = 200) -> bool:
        """Check if the image dimensions meet the minimum requirements

        Args:
            width: Image width
            height: Image height
            min_width: Minimum width requirement
            min_height: Minimum height requirement

        Returns:
            bool: Returns True if image dimensions meet requirements, False otherwise
        """
        if width < min_width or height < min_height:
            return False
        return True

    async def load_image(self, image_url: str) -> Optional[Image.Image]:
        """Asynchronously load an image from URL, local file path, or base64 string

        Args:
            image_url: URL, file path, or base64 encoded image

        Returns:
            Optional[Image.Image]: PIL Image object if successful, None otherwise
        """
        connector = aiohttp.TCPConnector()
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(connector=connector, trust_env=True, timeout=timeout) as session:
            return await self._load_image(session, image_url)

    async def _load_image(self, session: aiohttp.ClientSession, path: str) -> Optional[Image.Image]:
        """Internal method to load an image from various sources"""
        try:
            # Check if input is base64 encoded
            if path.startswith('data:image'):
                # Extract the base64 data after the comma
                base64_data = path.split(',')[1]
                image_data = base64.b64decode(base64_data)
                image = Image.open(io.BytesIO(image_data))

                # Convert RGBA to RGB if necessary
                if image.mode == 'RGBA':
                    background = Image.new('RGB', image.size, (255, 255, 255))
                    background.paste(image, mask=image.split()[3])
                    image = background
                elif image.mode != 'RGB':
                    image = image.convert('RGB')

                return image

            # Check if the path is a local file
            if os.path.isfile(path):
                try:
                    image = Image.open(path)

                    # Convert RGBA to RGB if necessary
                    if image.mode == 'RGBA':
                        background = Image.new(
                            'RGB', image.size, (255, 255, 255))
                        background.paste(image, mask=image.split()[3])
                        image = background
                    elif image.mode != 'RGB':
                        image = image.convert('RGB')

                    return image
                except Exception as e:
                    logger.info(f"Failed to load local image: {str(e)}")
                    return None

            # If not a local file or base64, treat as URL
            # If the file ends in SVG, filter it.
            if path.lower().endswith('.svg'):
                return None

            async with session.get(path) as response:
                if response.status != 200:
                    return None

                image_data = await response.read()

                try:
                    # For other formats, try direct loading
                    image = Image.open(io.BytesIO(image_data))

                    # Convert RGBA to RGB if necessary
                    if image.mode == 'RGBA':
                        background = Image.new(
                            'RGB', image.size, (255, 255, 255))
                        background.paste(image, mask=image.split()[3])
                        image = background
                    elif image.mode != 'RGB':
                        image = image.convert('RGB')

                    return image
                except Exception:
                    # If direct loading fails, try downloading to a temporary file first
                    with tempfile.NamedTemporaryFile(suffix=os.path.splitext(path)[1], delete=False) as temp_file:
                        temp_file.write(image_data)
                        temp_file.flush()
                        try:
                            image = Image.open(temp_file.name)

                            if image.mode == 'RGBA':
                                background = Image.new(
                                    'RGB', image.size, (255, 255, 255))
                                background.paste(image, mask=image.split()[3])
                                image = background
                            elif image.mode != 'RGB':
                                image = image.convert('RGB')
                            return image
                        finally:
                            os.unlink(temp_file.name)

        except Exception as e:
            logger.info(f"Error loading {path}: {str(e)}")
            return None

    async def filter_important_image(self, image_url: str, positive_prompt: str = "an important image",
                                     negative_prompt: str = "an unimportant image") -> Dict[str, Any]:
        """Filter whether an image is important using CLIP model

        Args:
            image_url: URL to the image
            positive_prompt: Text describing an important image
            negative_prompt: Text describing an unimportant image

        Returns:
            Dict[str, Any]: JSON object with is_important boolean and confidence score
        """
        try:
            # Process image from URL
            img = await self.load_image(image_url)

            if img is None or not self.check_image_size(img.width, img.height):
                logger.info(
                    f"Image not loaded or does not meet minimum size requirements (200x200 pixels): {image_url}")
                return {
                    "is_important": False,
                    "confidence": 0.0,
                    "probabilities": {
                        "positive": 0.0,
                        "negative": 0.0
                    }
                }

            # If IMAGE_FILTER is False, or CLIP model is not available, skip CLIP calculation and return as important
            if not IMAGE_FILTER:
                logger.info(
                    f"IMAGE_FILTER is disabled, returning image as important: {image_url}")
                return {
                    "is_important": True,
                    "confidence": 1.0,
                    "probabilities": {
                        "positive": 1.0,
                        "negative": 0.0
                    }
                }

            # 延迟加载CLIP模型
            if not self.clip_available:
                self._init_clip_model()

            if not self.clip_available:
                logger.warning(
                    f"CLIP model not available, returning image as important: {image_url}")
                return {
                    "is_important": True,
                    "confidence": 1.0,
                    "probabilities": {
                        "positive": 1.0,
                        "negative": 0.0
                    }
                }

            # Convert RGBA to RGB if necessary
            if img.mode == 'RGBA':
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[3])
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')

            # Try to use CLIP model with fallback to size-only filter
            try:
                # Prepare inputs for CLIP
                inputs = self.processor(
                    text=[negative_prompt, positive_prompt],
                    images=img,
                    return_tensors="pt",
                    padding=True
                )

                # Get model outputs
                with torch.no_grad():
                    outputs = self.model(**inputs)

                # Get image-text similarity scores
                logits_per_image = outputs.logits_per_image
                probs = logits_per_image.softmax(dim=1)

                # Extract probabilities
                neg_prob, pos_prob = probs[0].tolist()

                # Determine if image is important based on probability
                is_important = pos_prob > 0.6 and neg_prob < 0.5

                return {
                    "is_important": bool(is_important),
                    "confidence": float(pos_prob),
                    "probabilities": {
                        "positive": float(pos_prob),
                        "negative": float(neg_prob)
                    }
                }
            except Exception as e:
                # CLIP model processing failed, fall back to size-only filtering
                logger.warning(f"CLIP processing failed, using size-only filter: {str(e)}")
                return {
                    "is_important": True,
                    "confidence": 0.8,  # Arbitrary high confidence value
                    "probabilities": {
                        "positive": 0.8,
                        "negative": 0.2
                    }
                }

        except Exception as e:
            logger.error(f"Error processing image: {str(e)}")
            raise Exception(f"Error processing image: {str(e)}")


# Global instance to be shared across modules
# This avoids creating multiple instances and loading CLIP model multiple times
_data_process_service = None

def get_data_process_service():
    """Get or create the global DataProcessService instance (lazy initialization)"""
    global _data_process_service
    if _data_process_service is None:
        _data_process_service = DataProcessService()
    return _data_process_service
