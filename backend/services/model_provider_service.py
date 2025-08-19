import logging
import httpx
from consts.provider import SILICON_GET_URL
from consts.model import ModelConnectStatusEnum, ModelRequest
from utils.model_name_utils import split_repo_name, split_display_name
from services.model_health_service import embedding_dimension_check
# Added standard library and third-party dependencies
from abc import ABC, abstractmethod
from typing import List, Dict

logger = logging.getLogger("model_provider_service")


class AbstractModelProvider(ABC):
    """Common interface that all model provider integrations must implement."""

    @abstractmethod
    async def get_models(self, provider_config: Dict) -> List[Dict]:
        """Return a list of models provided by the concrete provider."""
        raise NotImplementedError


class SiliconModelProvider(AbstractModelProvider):
    """Concrete implementation for SiliconFlow provider."""

    async def get_models(self, provider_config: Dict) -> List[Dict]:
        try:
            model_type: str = provider_config["model_type"]
            model_api_key: str = provider_config["api_key"]

            headers = {"Authorization": f"Bearer {model_api_key}"}

            # Choose endpoint by model type
            if model_type in ("llm", "vlm"):
                silicon_url = f"{SILICON_GET_URL}?sub_type=chat"
            elif model_type in ("embedding", "multi_embedding"):
                silicon_url = f"{SILICON_GET_URL}?sub_type=embedding"
            else:
                silicon_url = SILICON_GET_URL

            async with httpx.AsyncClient(verify=False) as client:
                response = await client.get(silicon_url, headers=headers)
                response.raise_for_status()
                model_list: List[Dict] = response.json()["data"]

            # Annotate models with canonical fields expected downstream
            if model_type in ("llm", "vlm"):
                for item in model_list:
                    item["model_tag"] = "chat"
                    item["model_type"] = model_type
            elif model_type in ("embedding", "multi_embedding"):
                for item in model_list:
                    item["model_tag"] = "embedding"
                    item["model_type"] = model_type

            return model_list
        except Exception as e:
            logger.error(f"Error getting models from silicon: {e}")
            return []



async def prepare_model_dict(provider: str, model: dict, model_url: str, model_api_key: str, max_tokens: int) -> dict:
    """
    Construct a model configuration dictionary that is ready to be stored in the
    database. This utility centralises the logic that was previously embedded in
    the *batch_create_models* route so that it can be reused elsewhere and keep
    the router implementation concise.

    Args:
        provider: Name of the model provider (e.g. "silicon", "openai").
        model:      A single model item coming from the provider list.
        model_url:  Base URL for the provider API.
        model_api_key: API key that should be saved together with the model.
        max_tokens: User-supplied max token / embedding dimension upper-bound.

    Returns:
        A dictionary ready to be passed to *create_model_record*.
    """

    # Split repo/name once so it can be reused multiple times.
    model_repo, model_name = split_repo_name(model["id"])
    model_display_name = split_display_name(model["id"])


    # Build the canonical representation using the existing Pydantic schema for
    # consistency of validation and default handling.
    model_obj = ModelRequest(
        model_factory=provider,
        model_name=model_name,
        model_type=model["model_type"],
        api_key=model_api_key,
        max_tokens=max_tokens,
        display_name=f"{provider}/{model_display_name}"
    )

    model_dict = model_obj.model_dump()
    model_dict["model_repo"] = model_repo or ""

    # Determine the correct base_url and, for embeddings, update the actual
    # dimension by performing a real connectivity check.
    if model["model_type"] in ["embedding", "multi_embedding"]:
        model_dict["base_url"] = f"{model_url}embeddings"
        # The embedding dimension might differ from the provided max_tokens.
        model_dict["max_tokens"] = await embedding_dimension_check(model_dict)
    else:
        model_dict["base_url"] = model_url

    # All newly created models start in NOT_DETECTED status.
    model_dict["connect_status"] = ModelConnectStatusEnum.NOT_DETECTED.value

    return model_dict