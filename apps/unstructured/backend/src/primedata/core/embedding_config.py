"""
Embedding model configuration for PrimeData.

This module provides centralized configuration for all available embedding models,
their properties, and metadata. This ensures consistency across the application
and makes it easy to add new models or modify existing ones.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

from primedata.utils.log_utils import get_logger

logger = get_logger(__name__)


# Azure OpenAI deployment names that are recognized directly
AZURE_OPENAI_DEPLOYMENT_NAMES = [
    "text-embedding-3-small",
    "text-embedding-3-large",
    "text-embedding-3-large-2",  # Alternative naming convention
    "text-embedding-ada-002",
]


class EmbeddingModelType(str, Enum):
    """Types of embedding models."""

    SENTENCE_TRANSFORMERS = "sentence_transformers"
    OPENAI = "openai"
    AZURE_OPENAI = "azure_openai"
    HUGGINGFACE = "huggingface"
    CUSTOM = "custom"


@dataclass
class EmbeddingModelConfig:
    """Configuration for an embedding model."""

    id: str
    name: str
    description: str
    model_type: EmbeddingModelType
    dimension: int
    model_path: str
    is_available: bool = True
    requires_api_key: bool = False
    cost_per_token: Optional[float] = None
    max_tokens: Optional[int] = None
    metadata: Optional[Dict] = None


class EmbeddingModelRegistry:
    """Registry for all available embedding models."""

    # Default models configuration
    MODELS: Dict[str, EmbeddingModelConfig] = {
        "mpnet": EmbeddingModelConfig(
            id="mpnet",
            name="MPNet",
            description="Microsoft's MPNet model for high-quality embeddings",
            model_type=EmbeddingModelType.SENTENCE_TRANSFORMERS,
            dimension=768,
            model_path="all-mpnet-base-v2",
            is_available=True,
            requires_api_key=False,
            metadata={
                "provider": "sentence-transformers",
                "license": "apache-2.0",
                "performance": "slower",
                "quality": "excellent",
            },
        ),
        "openai-ada-002": EmbeddingModelConfig(
            id="openai-ada-002",
            name="OpenAI Ada-002",
            description="OpenAI's text-embedding-ada-002 model",
            model_type=EmbeddingModelType.OPENAI,
            dimension=1536,
            model_path="text-embedding-ada-002",
            is_available=True,
            requires_api_key=True,
            cost_per_token=0.0001,  # $0.0001 per 1K tokens
            max_tokens=8191,
            metadata={"provider": "openai", "license": "commercial", "performance": "fast", "quality": "excellent"},
        ),
        "openai-3-small": EmbeddingModelConfig(
            id="openai-3-small",
            name="OpenAI Text-3-Small",
            description="OpenAI's latest small embedding model",
            model_type=EmbeddingModelType.OPENAI,
            dimension=1536,
            model_path="text-embedding-3-small",
            is_available=True,
            requires_api_key=True,
            cost_per_token=0.00002,  # $0.00002 per 1K tokens
            max_tokens=8191,
            metadata={"provider": "openai", "license": "commercial", "performance": "fast", "quality": "excellent"},
        ),
        "openai-3-large": EmbeddingModelConfig(
            id="openai-3-large",
            name="OpenAI Text-3-Large",
            description="OpenAI's latest large embedding model with higher dimensions",
            model_type=EmbeddingModelType.OPENAI,
            dimension=3072,
            model_path="text-embedding-3-large",
            is_available=True,
            requires_api_key=True,
            cost_per_token=0.00013,  # $0.00013 per 1K tokens
            max_tokens=8191,
            metadata={"provider": "openai", "license": "commercial", "performance": "medium", "quality": "excellent"},
        ),
        # Open-source models with 768 dimensions
        "e5-base": EmbeddingModelConfig(
            id="e5-base",
            name="E5 Base",
            description="Microsoft E5 base model for general-purpose embeddings",
            model_type=EmbeddingModelType.SENTENCE_TRANSFORMERS,
            dimension=768,
            model_path="intfloat/e5-base",
            is_available=True,
            requires_api_key=False,
            metadata={
                "provider": "microsoft",
                "license": "mit",
                "performance": "medium",
                "quality": "excellent",
                "multilingual": False,
            },
        ),
        "bge-base-en": EmbeddingModelConfig(
            id="bge-base-en",
            name="BGE Base (English)",
            description="BAAI General Embedding base model optimized for English",
            model_type=EmbeddingModelType.SENTENCE_TRANSFORMERS,
            dimension=768,
            model_path="BAAI/bge-base-en-v1.5",
            is_available=True,
            requires_api_key=False,
            metadata={
                "provider": "baai",
                "license": "mit",
                "performance": "medium",
                "quality": "excellent",
                "multilingual": False,
            },
        ),
        "instructor-base": EmbeddingModelConfig(
            id="instructor-base",
            name="Instructor Base",
            description="Instructor model for instruction-following embeddings",
            model_type=EmbeddingModelType.SENTENCE_TRANSFORMERS,
            dimension=768,
            model_path="hkunlp/instructor-base",
            is_available=True,
            requires_api_key=False,
            metadata={
                "provider": "hkunlp",
                "license": "apache-2.0",
                "performance": "medium",
                "quality": "excellent",
                "instruction_tuned": True,
            },
        ),
        # Open-source models with 1024 dimensions
        "e5-large": EmbeddingModelConfig(
            id="e5-large",
            name="E5 Large",
            description="Microsoft E5 large model with 1024 dimensions for high-quality embeddings",
            model_type=EmbeddingModelType.SENTENCE_TRANSFORMERS,
            dimension=1024,
            model_path="intfloat/e5-large",
            is_available=True,
            requires_api_key=False,
            metadata={
                "provider": "microsoft",
                "license": "mit",
                "performance": "slower",
                "quality": "excellent",
                "multilingual": False,
            },
        ),
        "bge-large-en": EmbeddingModelConfig(
            id="bge-large-en",
            name="BGE Large (English)",
            description="BAAI General Embedding large model with 1024 dimensions for English",
            model_type=EmbeddingModelType.SENTENCE_TRANSFORMERS,
            dimension=1024,
            model_path="BAAI/bge-large-en-v1.5",
            is_available=True,
            requires_api_key=False,
            metadata={
                "provider": "baai",
                "license": "mit",
                "performance": "slower",
                "quality": "excellent",
                "multilingual": False,
            },
        ),
        "gte-large": EmbeddingModelConfig(
            id="gte-large",
            name="GTE Large",
            description="General Text Embeddings large model with 1024 dimensions",
            model_type=EmbeddingModelType.SENTENCE_TRANSFORMERS,
            dimension=1024,
            model_path="thenlper/gte-large",
            is_available=True,
            requires_api_key=False,
            metadata={
                "provider": "thenlper",
                "license": "apache-2.0",
                "performance": "slower",
                "quality": "excellent",
                "multilingual": False,
            },
        ),
        "instructor-large": EmbeddingModelConfig(
            id="instructor-large",
            name="Instructor Large",
            description="Instructor large model with 1024 dimensions for instruction-following",
            model_type=EmbeddingModelType.SENTENCE_TRANSFORMERS,
            dimension=1024,
            model_path="hkunlp/instructor-large",
            is_available=True,
            requires_api_key=False,
            metadata={
                "provider": "hkunlp",
                "license": "apache-2.0",
                "performance": "slower",
                "quality": "excellent",
                "instruction_tuned": True,
            },
        ),
        # Additional open-source models with other dimensions
        "e5-small": EmbeddingModelConfig(
            id="e5-small",
            name="E5 Small",
            description="Microsoft E5 small model optimized for speed",
            model_type=EmbeddingModelType.SENTENCE_TRANSFORMERS,
            dimension=384,
            model_path="intfloat/e5-small",
            is_available=True,
            requires_api_key=False,
            metadata={
                "provider": "microsoft",
                "license": "mit",
                "performance": "fast",
                "quality": "good",
                "multilingual": False,
            },
        ),
        "bge-small-en": EmbeddingModelConfig(
            id="bge-small-en",
            name="BGE Small (English)",
            description="BAAI General Embedding small model for fast embeddings",
            model_type=EmbeddingModelType.SENTENCE_TRANSFORMERS,
            dimension=384,
            model_path="BAAI/bge-small-en-v1.5",
            is_available=True,
            requires_api_key=False,
            metadata={"provider": "baai", "license": "mit", "performance": "fast", "quality": "good", "multilingual": False},
        ),
        "gte-base": EmbeddingModelConfig(
            id="gte-base",
            name="GTE Base",
            description="General Text Embeddings base model with 768 dimensions",
            model_type=EmbeddingModelType.SENTENCE_TRANSFORMERS,
            dimension=768,
            model_path="thenlper/gte-base",
            is_available=True,
            requires_api_key=False,
            metadata={
                "provider": "thenlper",
                "license": "apache-2.0",
                "performance": "medium",
                "quality": "excellent",
                "multilingual": False,
            },
        ),
        # Multilingual models
        "multilingual-e5-base": EmbeddingModelConfig(
            id="multilingual-e5-base",
            name="Multilingual E5 Base",
            description="Microsoft E5 base model supporting 100+ languages",
            model_type=EmbeddingModelType.SENTENCE_TRANSFORMERS,
            dimension=768,
            model_path="intfloat/multilingual-e5-base",
            is_available=True,
            requires_api_key=False,
            metadata={
                "provider": "microsoft",
                "license": "mit",
                "performance": "medium",
                "quality": "excellent",
                "multilingual": True,
                "languages": "100+",
            },
        ),
        "multilingual-e5-large": EmbeddingModelConfig(
            id="multilingual-e5-large",
            name="Multilingual E5 Large",
            description="Microsoft E5 large model with 1024 dimensions supporting 100+ languages",
            model_type=EmbeddingModelType.SENTENCE_TRANSFORMERS,
            dimension=1024,
            model_path="intfloat/multilingual-e5-large",
            is_available=True,
            requires_api_key=False,
            metadata={
                "provider": "microsoft",
                "license": "mit",
                "performance": "slower",
                "quality": "excellent",
                "multilingual": True,
                "languages": "100+",
            },
        ),
        "bge-m3": EmbeddingModelConfig(
            id="bge-m3",
            name="BGE M3",
            description="BAAI Multilingual Embedding model supporting 100+ languages with 1024 dimensions",
            model_type=EmbeddingModelType.SENTENCE_TRANSFORMERS,
            dimension=1024,
            model_path="BAAI/bge-m3",
            is_available=True,
            requires_api_key=False,
            metadata={
                "provider": "baai",
                "license": "mit",
                "performance": "slower",
                "quality": "excellent",
                "multilingual": True,
                "languages": "100+",
            },
        ),
        "paraphrase-multilingual": EmbeddingModelConfig(
            id="paraphrase-multilingual",
            name="Paraphrase Multilingual",
            description="Multilingual paraphrase model with 768 dimensions supporting 50+ languages",
            model_type=EmbeddingModelType.SENTENCE_TRANSFORMERS,
            dimension=768,
            model_path="paraphrase-multilingual-mpnet-base-v2",
            is_available=True,
            requires_api_key=False,
            metadata={
                "provider": "sentence-transformers",
                "license": "apache-2.0",
                "performance": "medium",
                "quality": "good",
                "multilingual": True,
                "languages": "50+",
            },
        ),
    }

    @classmethod
    def get_model(cls, model_id: str) -> Optional[EmbeddingModelConfig]:
        """Get a specific model configuration by ID."""
        logger.debug(f"🧠 EmbeddingModelRegistry.get_model(model_id={model_id})")
        model = cls.MODELS.get(model_id)
        if model:
            logger.info(f"🧠 ✅ Model found: {model_id} - {model.name} (dim={model.dimension})")
        else:
            logger.warning(f"🧠 ⚠️ Model not found: {model_id}")
        return model

    @classmethod
    def get_available_models(cls) -> List[EmbeddingModelConfig]:
        """Get all available models."""
        logger.debug(f"🧠 EmbeddingModelRegistry.get_available_models()")
        available = [model for model in cls.MODELS.values() if model.is_available]
        logger.info(f"🧠 ✅ Available models: {len(available)} models")
        logger.debug(f"📋 Available model IDs: {[m.id for m in available]}")
        return available

    @classmethod
    def get_models_by_type(cls, model_type: EmbeddingModelType) -> List[EmbeddingModelConfig]:
        """Get models filtered by type."""
        logger.debug(f"🧠 EmbeddingModelRegistry.get_models_by_type(type={model_type})")
        models = [model for model in cls.MODELS.values() if model.model_type == model_type and model.is_available]
        logger.info(f"🧠 ✅ Found {len(models)} models of type {model_type}")
        return models

    @classmethod
    def get_free_models(cls) -> List[EmbeddingModelConfig]:
        """Get models that don't require API keys."""
        logger.debug(f"🧠 EmbeddingModelRegistry.get_free_models()")
        free_models = [model for model in cls.MODELS.values() if model.is_available and not model.requires_api_key]
        logger.info(f"🧠 ✅ Free models: {len(free_models)} models")
        logger.debug(f"📋 Free model IDs: {[m.id for m in free_models]}")
        return free_models

    @classmethod
    def get_paid_models(cls) -> List[EmbeddingModelConfig]:
        """Get models that require API keys."""
        logger.debug(f"🧠 EmbeddingModelRegistry.get_paid_models()")
        paid_models = [model for model in cls.MODELS.values() if model.is_available and model.requires_api_key]
        logger.info(f"🧠 ✅ Paid models: {len(paid_models)} models")
        logger.debug(f"📋 Paid model IDs: {[m.id for m in paid_models]}")
        return paid_models

    @classmethod
    def validate_model_id(cls, model_id: str) -> bool:
        """Validate if a model ID exists and is available."""
        logger.debug(f"🧠 EmbeddingModelRegistry.validate_model_id(model_id={model_id})")
        model = cls.get_model(model_id)
        is_valid = model is not None and model.is_available
        if is_valid:
            logger.info(f"🧠 ✅ Model ID validated: {model_id}")
        else:
            logger.warning(f"🧠 ❌ Invalid model ID: {model_id}")
        return is_valid

    @classmethod
    def get_model_dimension(cls, model_id: str) -> Optional[int]:
        """Get the dimension for a specific model."""
        logger.debug(f"🧠 EmbeddingModelRegistry.get_model_dimension(model_id={model_id})")
        model = cls.get_model(model_id)
        if model:
            logger.info(f"🧠 ✅ Model dimension: {model_id} -> {model.dimension}d")
            return model.dimension
        logger.warning(f"🧠 ⚠️ Could not get dimension for unknown model: {model_id}")
        return None

    @classmethod
    def get_model_display_name(cls, model_id: str) -> str:
        """Get the display name for a model."""
        logger.debug(f"🧠 EmbeddingModelRegistry.get_model_display_name(model_id={model_id})")
        model = cls.get_model(model_id)
        name = model.name if model else model_id
        logger.info(f"🧠 ✅ Model display name: {model_id} -> {name}")
        return name

    @classmethod
    def get_models_for_ui(cls) -> List[Dict]:
        """Get models formatted for UI consumption."""
        logger.debug(f"🧠 EmbeddingModelRegistry.get_models_for_ui()")
        available_models = cls.get_available_models()
        models_list = [
            {
                "id": model.id,
                "name": model.name,
                "description": model.description,
                "dimension": model.dimension,
                "requires_api_key": model.requires_api_key,
                "cost_per_token": model.cost_per_token,
                "metadata": model.metadata,
            }
            for model in available_models
        ]
        logger.info(f"🧠 ✅ Generated UI model list: {len(models_list)} models")
        logger.debug(f"📋 Model IDs in UI list: {[m['id'] for m in models_list]}")
        return models_list


# Convenience functions for backward compatibility
def get_azure_openai_model_config() -> Optional[EmbeddingModelConfig]:
    """
    Get Azure OpenAI model configuration from environment variables.

    Returns None if not configured. The returned config uses environment
    variables for endpoint, deployment name, API version, and dimensions.

    Returns:
        EmbeddingModelConfig for Azure OpenAI, or None if not configured
    """
    try:
        from primedata.core.settings import get_settings

        s = get_settings()

        # Check if Azure OpenAI is configured
        if not s.AZURE_OPENAI_ENDPOINT or not s.AZURE_OPENAI_DEPLOYMENT_NAME:
            return None

        model_name = s.AZURE_OPENAI_MODEL_NAME or s.AZURE_OPENAI_DEPLOYMENT_NAME

        config = EmbeddingModelConfig(
            id="azure-openai",
            name=f"Azure OpenAI ({model_name})",
            description="Azure OpenAI embedding model via Service Principal authentication",
            model_type=EmbeddingModelType.AZURE_OPENAI,
            dimension=s.AZURE_OPENAI_DIMENSIONS,
            model_path=s.AZURE_OPENAI_DEPLOYMENT_NAME,
            is_available=True,
            requires_api_key=False,  # Uses token-based auth instead
            metadata={
                "provider": "azure-openai",
                "api_version": s.AZURE_OPENAI_API_VERSION,
                "endpoint": s.AZURE_OPENAI_ENDPOINT,
            },
        )

        logger.info(f"🧠 ✅ Azure OpenAI model configured: {model_name}")
        return config

    except Exception as e:
        logger.debug(f"🧠 Azure OpenAI not available: {e}")
        return None


def get_embedding_model_config(model_id: str) -> Optional[EmbeddingModelConfig]:
    """Get embedding model configuration."""
    logger.debug(f"🧠 get_embedding_model_config(model_id={model_id})")

    # Check for Azure OpenAI first (dynamic, from env vars)
    if model_id == "azure-openai":
        config = get_azure_openai_model_config()
        if config:
            return config

    # Check for Azure deployment names (recognized directly in EmbeddingGenerator._load_model)
    if model_id in AZURE_OPENAI_DEPLOYMENT_NAMES:
        logger.debug(f"🧠 ⏭️  Azure deployment name recognized: {model_id} (will be handled by EmbeddingGenerator)")
        return None  # Will be handled specially in _load_model()

    # Check if model_id matches Azure model name env var
    from primedata.core.settings import get_settings
    s = get_settings()
    if s.AZURE_OPENAI_MODEL_NAME and model_id == s.AZURE_OPENAI_MODEL_NAME:
        logger.debug(f"🧠 ⏭️  Azure model name recognized: {model_id} (will be handled by EmbeddingGenerator)")
        return None  # Will be handled specially in _load_model()

    # Check registry for static models
    config = EmbeddingModelRegistry.get_model(model_id)
    if config:
        logger.info(f"🧠 ✅ Got model config: {model_id}")
    else:
        logger.warning(f"🧠 ⚠️ Model config not found: {model_id}")
    return config


def get_available_embedding_models() -> List[EmbeddingModelConfig]:
    """Get all available embedding models."""
    logger.debug(f"🧠 get_available_embedding_models()")
    models = EmbeddingModelRegistry.get_available_models()
    logger.info(f"🧠 ✅ Retrieved {len(models)} available embedding models")
    return models


def validate_embedding_model(model_id: str) -> bool:
    """Validate embedding model ID."""
    logger.debug(f"🧠 validate_embedding_model(model_id={model_id})")
    is_valid = EmbeddingModelRegistry.validate_model_id(model_id)
    if is_valid:
        logger.info(f"🧠 ✅ Model validation passed: {model_id}")
    else:
        logger.error(f"❌ Model validation failed: {model_id}")
    return is_valid


def get_embedding_dimension(model_id: str) -> Optional[int]:
    """Get embedding dimension for model."""
    logger.debug(f"🧠 get_embedding_dimension(model_id={model_id})")
    dimension = EmbeddingModelRegistry.get_model_dimension(model_id)
    if dimension:
        logger.info(f"🧠 ✅ Got embedding dimension: {model_id} -> {dimension}d")
    else:
        logger.warning(f"🧠 ⚠️ Could not get dimension for: {model_id}")
    return dimension


def format_embedding_model_name(model_id: str) -> str:
    """Format embedding model name for display."""
    logger.debug(f"🧠 format_embedding_model_name(model_id={model_id})")
    name = EmbeddingModelRegistry.get_model_display_name(model_id)
    logger.info(f"🧠 ✅ Formatted model name: {model_id} -> {name}")
    return name
