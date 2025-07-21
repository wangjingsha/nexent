import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Union, Optional

import requests


class BaseEmbedding(ABC):
    """
    Abstract base class for embedding models, defining methods that all embedding models should implement.
    """

    @abstractmethod
    def __init__(self, model_name: str = None, base_url: str = None, api_key: str = None, embedding_dim: int = None):
        """
        Initialize the embedding model.

        Args:
            model_name: Name of the embedding model
            base_url: Base URL of the embedding API
            api_key: API key for the embedding API
            embedding_dim: Dimension of the embedding vector
        """
        pass

    @abstractmethod
    def get_embeddings(self, inputs: Union[str, List[str]], with_metadata: bool = False, timeout: Optional[float] = None) -> Union[List[List[float]], Dict[str, Any]]:
        """
        Get the embedding vectors for the input.
        
        Args:
            inputs: Objects to be embedded
            with_metadata: Whether to return the full response with metadata
            timeout: Request timeout in seconds
            
        Returns:
            If with_metadata is False, returns a list of embedding vectors; otherwise, returns a dictionary containing embeddings and metadata
        """
        pass

    @abstractmethod
    def check_connectivity(self, timeout: float = 5.0) -> bool:
        """
        Test the connectivity to the embedding API, supporting timeout detection.
        
        Args:
            timeout: Timeout in seconds
            
        Returns:
            bool: Returns True if the connection is successful, False if it fails or times out
        """
        pass


class TextEmbedding(BaseEmbedding):
    """
    Abstract class for text embedding models, specifically handling the task of vectorizing text.
    Input format is a string or an array of strings.
    """
    
    @abstractmethod
    def __init__(self, model_name: str = None, base_url: str = None, api_key: str = None, embedding_dim: int = None):
        super().__init__(model_name, base_url, api_key, embedding_dim)
    
    @abstractmethod
    def get_embeddings(self, inputs: Union[str, List[str]], with_metadata: bool = False, timeout: Optional[float] = None) -> Union[List[List[float]], Dict[str, Any]]:
        """
        Get the embedding vectors for text inputs.
        
        Args:
            inputs: A text string or a list of text strings
            with_metadata: Whether to return the full response with metadata
            timeout: Request timeout in seconds
            
        Returns:
            If with_metadata is False, returns a list of embedding vectors; otherwise, returns a dictionary containing embeddings and metadata
        """
        pass


class MultimodalEmbedding(BaseEmbedding):
    """
    Abstract class for multimodal embedding models, capable of handling vectorization tasks for text, images, videos, etc.
    Input format is a list of dictionaries containing type information List[Dict[str, str]].
    """
    
    @abstractmethod
    def __init__(self, model_name: str = None, base_url: str = None, api_key: str = None, embedding_dim: int = None):
        super().__init__(model_name, base_url, api_key, embedding_dim)
    
    @abstractmethod
    def get_multimodal_embeddings(self, inputs: List[Dict[str, str]], with_metadata: bool = False, timeout: Optional[float] = None) -> Union[List[List[float]], Dict[str, Any]]:
        """
        Get the embedding vectors for multimodal inputs.
        
        Args:
            inputs: A list of dictionaries containing type information, e.g., [{"text": "content"}, {"image": "image URL"}]
            with_metadata: Whether to return the full response with metadata
            timeout: Request timeout in seconds
            
        Returns:
            If with_metadata is False, returns a list of embedding vectors; otherwise, returns a dictionary containing embeddings and metadata
        """
        pass


class JinaEmbedding(MultimodalEmbedding):
    def __init__(self, api_key: str, base_url: str = "https://api.jina.ai/v1/embeddings", model_name: str = "jina-clip-v2", embedding_dim: int = 1024):
        """Initialize JinaEmbedding with configuration."""
        self.api_key = api_key
        self.api_url = base_url
        self.model = model_name
        self.embedding_dim = embedding_dim

        self.headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"}

    def _prepare_multimodal_input(self, inputs: List[Dict[str, str]]) -> Dict[str, Any]:
        """Prepare the input data for the API request."""
        return {"model": self.model, "input": inputs}

    def _make_request(self, data: Dict[str, Any], timeout: Optional[float] = None) -> Dict[str, Any]:
        """
        Make the API request and return the response.
        
        Args:
            data: Request data
            timeout: Timeout in seconds
            
        Returns:
            Dict[str, Any]: API response
        """
        response = requests.post(self.api_url, headers=self.headers, json=data, timeout=timeout)
        response.raise_for_status()
        return response.json()

    def get_embeddings(self, inputs: Union[str, List[str]], with_metadata: bool = False, timeout: Optional[float] = None) -> Union[
        List[List[float]], Dict[str, Any]]:
        """
        Get embeddings for text inputs.
        Args:
            inputs: A single text string or a list of text strings.
            with_metadata: Whether to return the full response with metadata.
            timeout: Request timeout in seconds.
        Returns:
            A list of embedding vectors, or a dictionary with metadata if with_metadata is True.
        """
        if isinstance(inputs, str):
            multimodal_inputs = [{"text": inputs}]
        else:
            multimodal_inputs = [{"text": item} for item in inputs]

        return self.get_multimodal_embeddings(multimodal_inputs, with_metadata=with_metadata, timeout=timeout)

    def get_multimodal_embeddings(self, inputs: List[Dict[str, str]], with_metadata: bool = False, timeout: Optional[float] = None) -> Union[
        List[List[float]], Dict[str, Any]]:
        """
        Get embeddings for a list of inputs (text or image URLs).
        
        Args:
            inputs: List of dictionaries containing either 'text' or 'image' keys
            with_metadata: Whether to return the full response with metadata or just a list of embedding vectors
            timeout: Request timeout in seconds
            
        Returns:
            List of embedding vectors
            
        Example:
            >>> jina = JinaEmbedding()
            >>> inputs = [
            ...     {"text": "A beautiful sunset over the beach"},
            ...     {"image": "https://example.com/image.jpg"}
            ... ]
            >>> embeddings = jina.get_multimodal_embeddings(inputs)
        """
        data = self._prepare_multimodal_input(inputs)
        response = self._make_request(data, timeout=timeout)

        if with_metadata:
            return response

        # Extract embeddings from response
        embeddings = [item["embedding"] for item in response["data"]]
        return embeddings

    def check_connectivity(self, timeout: float = 5.0) -> bool:
        """
        Test the connectivity to the remote Jina Embedding API, supporting timeout detection
        
        Args:
            timeout: Timeout in seconds, default is 5 seconds
            
        Returns:
            bool: Returns True if the connection is successful, False if it fails or times out
        """
        try:
            # Create a simple test input
            test_input = "Hello, nexent!"

            # Try to get embedding vectors, setting a timeout
            embeddings = self.get_embeddings(test_input, timeout=timeout)

            # If embedding vectors are successfully obtained, the connection is normal
            return len(embeddings) > 0

        except requests.exceptions.Timeout:
            logging.error(f"Embedding API connection test timed out ({timeout} seconds)")
            return False
        except requests.exceptions.ConnectionError:
            logging.error("Embedding API connection error, unable to establish connection")
            return False
        except Exception as e:
            logging.error(f"Embedding API connection test failed: {str(e)}")
            return False


class OpenAICompatibleEmbedding(TextEmbedding):
    def __init__(self, model_name: str, base_url: str, api_key: str, embedding_dim: int):
        """Initialize OpenAICompatibleEmbedding with configuration from environment variables or provided parameters."""
        self.api_key = api_key
        self.api_url = base_url
        self.model = model_name
        self.embedding_dim = embedding_dim

        self.headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"}

    def _prepare_input(self, inputs: Union[str, List[str]]) -> Dict[str, Any]:
        """Prepare the input data for the API request."""
        if isinstance(inputs, str):
            inputs = [inputs]
        return {"model": self.model, "input": inputs}

    def _make_request(self, data: Dict[str, Any], timeout: Optional[float] = None) -> Dict[str, Any]:
        """
        Make the API request and return the response.
        
        Args:
            data: Request data
            timeout: Timeout in seconds
            
        Returns:
            Dict[str, Any]: API response
        """
        response = requests.post(self.api_url, headers=self.headers, json=data, timeout=timeout)
        response.raise_for_status()
        return response.json()

    def get_embeddings(self, inputs: Union[str, List[str]], with_metadata: bool = False, timeout: Optional[float] = None) -> Union[
        List[List[float]], Dict[str, Any]]:
        """
        Get embeddings for text inputs.
        
        Args:
            inputs: A single text string or a list of text strings
            with_metadata: Whether to return the full response with metadata or just a list of embedding vectors
            timeout: Request timeout in seconds
            
        Returns:
            List of embedding vectors
        """
        data = self._prepare_input(inputs)
        response = self._make_request(data, timeout=timeout)

        if with_metadata:
            return response

        # Extract embeddings from response
        embeddings = [item["embedding"] for item in response["data"]]
        return embeddings

    def check_connectivity(self, timeout: float = 5.0) -> bool:
        """
        Test the connectivity to the remote OpenAI API, supporting timeout detection
        
        Args:
            timeout: Timeout in seconds, default is 5 seconds
            
        Returns:
            bool: Returns True if the connection is successful, False if it fails or times out
        """
        try:
            test_input = "Hello, nexent!"

            # Try to get embedding vectors, setting a timeout
            embeddings = self.get_embeddings(test_input, timeout=timeout)

            # If embedding vectors are successfully obtained, the connection is normal
            return len(embeddings) > 0

        except requests.exceptions.Timeout:
            logging.error(f"OpenAI API connection test timed out ({timeout} seconds)")
            return False
        except requests.exceptions.ConnectionError:
            logging.error("OpenAI API connection error, unable to establish connection")
            return False
        except Exception as e:
            logging.error(f"OpenAI API connection test failed: {str(e)}")
            return False
