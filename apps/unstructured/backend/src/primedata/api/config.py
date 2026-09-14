"""
Configuration Management API endpoints for discovering and validating configurations.

Endpoints:
- GET /api/v1/config/chunking-strategies - List available chunking strategies
- GET /api/v1/config/embeddings - List available embedding models
- GET /api/v1/config/playbooks - List available playbooks
- POST /api/v1/config/validate - Validate configuration before pipeline execution
"""

from typing import Any, Dict, List, Optional
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from primedata.db.database import get_db
from primedata.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/config", tags=["config"])


# ============================================================================
# ENUMS
# ============================================================================


class ChunkingStrategy(str, Enum):
    """Available chunking strategies."""

    FIXED_SIZE = "fixed_size"
    SEMANTIC = "semantic"
    SLIDING_WINDOW = "sliding_window"
    DOCUMENT_BOUNDARY = "document_boundary"
    RECURSIVE = "recursive"
    SENTENCE_BASED = "sentence_based"


class EmbeddingModelType(str, Enum):
    """Available embedding model types."""

    AZURE_OPENAI = "azure_openai"
    OPENAI = "openai"
    LOCAL_MINILM = "local_minilm"
    LOCAL_MPNET = "local_mpnet"


# ============================================================================
# PYDANTIC MODELS
# ============================================================================


class ChunkingStrategyConfig(BaseModel):
    """Configuration for a chunking strategy."""

    strategy_id: str
    name: str
    description: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    recommended_for: List[str] = Field(default_factory=list)
    performance: Dict[str, str] = Field(default_factory=dict)


class EmbeddingModelConfig(BaseModel):
    """Configuration for an embedding model."""

    model_id: str
    name: str
    provider: EmbeddingModelType
    dimensions: int
    cost_per_1k_tokens: Optional[float] = None
    max_token_length: int
    supports_batch: bool
    recommended_use_case: str
    current: bool = False


class PlaybookConfig(BaseModel):
    """Configuration for a playbook."""

    playbook_id: str
    name: str
    description: str
    category: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    min_trust_score: Optional[float] = None
    input_requirements: List[str] = Field(default_factory=list)
    is_builtin: bool
    is_custom: bool


class ConfigValidationRequest(BaseModel):
    """Request to validate configuration."""

    chunking_config: Optional[Dict[str, Any]] = None
    embedding_config: Optional[Dict[str, Any]] = None
    pipeline_config: Optional[Dict[str, Any]] = None
    playbook_config: Optional[Dict[str, Any]] = None


class ValidationError(BaseModel):
    """Validation error detail."""

    field: str
    error: str
    suggestion: Optional[str] = None


class ConfigValidationResponse(BaseModel):
    """Response from configuration validation."""

    valid: bool
    errors: List[ValidationError] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)


# ============================================================================
# ENDPOINTS
# ============================================================================


@router.get("/chunking-strategies")
async def list_chunking_strategies(
    category: Optional[str] = None,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    List all available chunking strategies with their configurations.

    Args:
        category: Optional category filter
        db: Database session

    Returns:
        List of available chunking strategies
    """
    logger.info(f"📋 GET /api/v1/config/chunking-strategies")

    try:
        strategies = [
            {
                "strategy_id": "fixed_size",
                "name": "Fixed Size Chunking",
                "description": "Splits text into fixed-size chunks with optional overlap",
                "parameters": {
                    "chunk_size": {"type": "integer", "default": 512, "min": 50, "max": 4000},
                    "overlap": {"type": "integer", "default": 100, "min": 0, "max": 500},
                    "separator": {"type": "string", "default": "\\n\\n"},
                },
                "recommended_for": ["documents", "articles", "web_content"],
                "performance": {
                    "speed": "very_fast",
                    "consistency": "high",
                    "semantic_preservation": "medium",
                },
            },
            {
                "strategy_id": "semantic",
                "name": "Semantic Chunking",
                "description": "Chunks text based on semantic boundaries using embeddings",
                "parameters": {
                    "max_chunk_size": {"type": "integer", "default": 1024, "min": 100, "max": 4000},
                    "similarity_threshold": {"type": "float", "default": 0.85, "min": 0.5, "max": 0.99},
                    "model": {"type": "string", "default": "text-embedding-3-large"},
                },
                "recommended_for": ["technical_docs", "research_papers", "books"],
                "performance": {
                    "speed": "medium",
                    "consistency": "high",
                    "semantic_preservation": "very_high",
                },
            },
            {
                "strategy_id": "sliding_window",
                "name": "Sliding Window Chunking",
                "description": "Uses sliding window with configurable stride",
                "parameters": {
                    "window_size": {"type": "integer", "default": 512, "min": 50, "max": 2000},
                    "stride": {"type": "integer", "default": 256, "min": 10, "max": 1000},
                },
                "recommended_for": ["continuous_text", "time_series"],
                "performance": {
                    "speed": "fast",
                    "consistency": "high",
                    "semantic_preservation": "medium",
                },
            },
            {
                "strategy_id": "sentence_based",
                "name": "Sentence-Based Chunking",
                "description": "Chunks at sentence boundaries",
                "parameters": {
                    "sentences_per_chunk": {"type": "integer", "default": 3, "min": 1, "max": 10},
                    "language": {"type": "string", "default": "english"},
                },
                "recommended_for": ["natural_language", "news", "transcripts"],
                "performance": {
                    "speed": "very_fast",
                    "consistency": "medium",
                    "semantic_preservation": "high",
                },
            },
            {
                "strategy_id": "document_boundary",
                "name": "Document Boundary Chunking",
                "description": "Respects document boundaries, never splits across documents",
                "parameters": {
                    "max_chunk_size": {"type": "integer", "default": 2048, "min": 500, "max": 8000},
                    "boundary_markers": {"type": "array", "default": ["---", "==="]},
                },
                "recommended_for": ["multi_document_corpus", "structured_data"],
                "performance": {
                    "speed": "fast",
                    "consistency": "very_high",
                    "semantic_preservation": "high",
                },
            },
        ]

        logger.info(f"✓ Retrieved {len(strategies)} chunking strategies")

        return {
            "strategies": strategies,
            "count": len(strategies),
        }

    except Exception as e:
        logger.error(f"❌ Error listing chunking strategies: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list chunking strategies: {str(e)}",
        )


@router.get("/embeddings")
async def list_embedding_models(
    provider: Optional[EmbeddingModelType] = None,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    List all available embedding models with their specifications.

    Args:
        provider: Optional provider filter
        db: Database session

    Returns:
        List of available embedding models
    """
    logger.info(f"📋 GET /api/v1/config/embeddings")

    try:
        models = [
            {
                "model_id": "azure-openai-text-embedding-3-large",
                "name": "Azure OpenAI - Text Embedding 3 Large",
                "provider": "azure_openai",
                "dimensions": 3072,
                "cost_per_1k_tokens": 0.13,
                "max_token_length": 8191,
                "supports_batch": True,
                "recommended_use_case": "High-quality semantic search and recommendation",
                "current": True,
                "status": "production",
                "latency_ms": 50,
            },
            {
                "model_id": "azure-openai-text-embedding-3-small",
                "name": "Azure OpenAI - Text Embedding 3 Small",
                "provider": "azure_openai",
                "dimensions": 1536,
                "cost_per_1k_tokens": 0.02,
                "max_token_length": 8191,
                "supports_batch": True,
                "recommended_use_case": "Fast embeddings with good quality",
                "current": False,
                "status": "production",
                "latency_ms": 30,
            },
            {
                "model_id": "openai-text-embedding-3-large",
                "name": "OpenAI - Text Embedding 3 Large",
                "provider": "openai",
                "dimensions": 3072,
                "cost_per_1k_tokens": 0.13,
                "max_token_length": 8191,
                "supports_batch": True,
                "recommended_use_case": "High-quality semantic search",
                "current": False,
                "status": "production",
                "latency_ms": 100,
            },
            {
                "model_id": "local-minilm-l12",
                "name": "Local - MiniLM-L12",
                "provider": "local_minilm",
                "dimensions": 384,
                "cost_per_1k_tokens": 0.0,
                "max_token_length": 512,
                "supports_batch": True,
                "recommended_use_case": "Local/offline processing",
                "current": False,
                "status": "available",
                "latency_ms": 20,
            },
            {
                "model_id": "local-mpnet",
                "name": "Local - MPNet Base v2",
                "provider": "local_mpnet",
                "dimensions": 768,
                "cost_per_1k_tokens": 0.0,
                "max_token_length": 512,
                "supports_batch": True,
                "recommended_use_case": "Local embeddings with better quality",
                "current": False,
                "status": "available",
                "latency_ms": 40,
            },
        ]

        if provider:
            models = [m for m in models if m["provider"] == provider.value]

        logger.info(f"✓ Retrieved {len(models)} embedding models")

        return {
            "models": models,
            "count": len(models),
            "current_model": next((m["model_id"] for m in models if m["current"]), None),
        }

    except Exception as e:
        logger.error(f"❌ Error listing embedding models: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list embedding models: {str(e)}",
        )


@router.get("/playbooks")
async def list_playbooks(
    include_builtin: bool = True,
    include_custom: bool = True,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    List all available playbooks (built-in and custom).

    Args:
        include_builtin: Include built-in playbooks
        include_custom: Include custom playbooks
        db: Database session

    Returns:
        List of available playbooks
    """
    logger.info(f"📋 GET /api/v1/config/playbooks")

    try:
        playbooks = [
            {
                "playbook_id": "TECH",
                "name": "Technical Documentation",
                "description": "Optimized for technical documents, code, and specifications",
                "category": "technical",
                "parameters": {
                    "focus_areas": ["accuracy", "structure", "terminology"],
                    "quality_gates": {"min_metadata": 0.9, "min_trust_score": 0.8},
                },
                "min_trust_score": 75.0,
                "input_requirements": ["structured_text", "code_blocks"],
                "is_builtin": True,
                "is_custom": False,
                "recommended_content": ["API docs", "code repos", "specifications"],
            },
            {
                "playbook_id": "SCANNED",
                "name": "Scanned Documents",
                "description": "Optimized for OCR'd documents and images",
                "category": "document",
                "parameters": {
                    "ocr_quality_threshold": 0.85,
                    "skip_confidence_checks": False,
                },
                "min_trust_score": 70.0,
                "input_requirements": ["image_content", "ocr_text"],
                "is_builtin": True,
                "is_custom": False,
                "recommended_content": ["PDFs", "scanned images", "forms"],
            },
            {
                "playbook_id": "REGULATORY",
                "name": "Regulatory & Compliance",
                "description": "Focused on compliance, regulations, and legal documents",
                "category": "compliance",
                "parameters": {
                    "enforce_accuracy": True,
                    "audit_trail": True,
                    "policy_enforcement": True,
                },
                "min_trust_score": 85.0,
                "input_requirements": ["verified_content", "audit_logs"],
                "is_builtin": True,
                "is_custom": False,
                "recommended_content": ["regulations", "policies", "legal_docs"],
            },
            {
                "playbook_id": "CONVERSATIONAL",
                "name": "Conversational Content",
                "description": "Optimized for dialogues, transcripts, and interviews",
                "category": "content",
                "parameters": {
                    "preserve_context": True,
                    "speaker_identification": True,
                },
                "min_trust_score": 65.0,
                "input_requirements": ["dialogue_format"],
                "is_builtin": True,
                "is_custom": False,
                "recommended_content": ["interviews", "transcripts", "conversations"],
            },
        ]

        # Filter by type
        if include_builtin and not include_custom:
            playbooks = [p for p in playbooks if p["is_builtin"]]
        elif include_custom and not include_builtin:
            playbooks = [p for p in playbooks if p["is_custom"]]

        logger.info(f"✓ Retrieved {len(playbooks)} playbooks")

        return {
            "playbooks": playbooks,
            "count": len(playbooks),
            "builtin_count": len([p for p in playbooks if p["is_builtin"]]),
            "custom_count": len([p for p in playbooks if p["is_custom"]]),
        }

    except Exception as e:
        logger.error(f"❌ Error listing playbooks: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list playbooks: {str(e)}",
        )


@router.post("/validate")
async def validate_configuration(
    validation_request: ConfigValidationRequest,
    db: Session = Depends(get_db),
) -> ConfigValidationResponse:
    """
    Validate configuration before pipeline execution.

    Args:
        validation_request: Configuration to validate
        db: Database session

    Returns:
        Validation results with errors and suggestions
    """
    logger.info(f"📋 POST /api/v1/config/validate")

    try:
        errors = []
        warnings = []
        suggestions = []

        # Validate chunking config
        if validation_request.chunking_config:
            chunk_config = validation_request.chunking_config
            strategy = chunk_config.get("strategy")

            if not strategy:
                errors.append(
                    ValidationError(
                        field="chunking_config.strategy",
                        error="Chunking strategy is required",
                        suggestion="Choose from: fixed_size, semantic, sliding_window, sentence_based",
                    )
                )

            if strategy == "fixed_size":
                chunk_size = chunk_config.get("chunk_size")
                if not chunk_size or chunk_size < 50 or chunk_size > 4000:
                    errors.append(
                        ValidationError(
                            field="chunking_config.chunk_size",
                            error=f"Chunk size must be between 50 and 4000 (got {chunk_size})",
                            suggestion="Recommended: 512 for general use",
                        )
                    )

        # Validate embedding config
        if validation_request.embedding_config:
            embed_config = validation_request.embedding_config
            model_name = embed_config.get("model_name")
            deployment_name = embed_config.get("deployment_name")

            if not model_name:
                errors.append(
                    ValidationError(
                        field="embedding_config.model_name",
                        error="Embedding model name is required",
                        suggestion="Use: text-embedding-3-large",
                    )
                )

            if not deployment_name:
                warnings.append("No Azure deployment name specified - using default")

            dimensions = embed_config.get("dimensions")
            if dimensions and dimensions not in [384, 768, 1536, 3072]:
                warnings.append(
                    f"Unusual embedding dimension {dimensions}. Standard values: 384, 768, 1536, 3072"
                )

        # Validate pipeline config
        if validation_request.pipeline_config:
            pipeline_config = validation_request.pipeline_config
            stages = pipeline_config.get("stages", [])

            if not stages:
                warnings.append("No pipeline stages specified - will use default stages")

            required_stages = ["ingest", "preprocess", "chunk", "embed", "index"]
            for stage in required_stages:
                if stage not in stages:
                    suggestions.append(f"Consider including '{stage}' stage in pipeline")

        # Validate playbook config
        if validation_request.playbook_config:
            playbook_config = validation_request.playbook_config
            playbook_id = playbook_config.get("playbook_id")

            if not playbook_id:
                warnings.append("No playbook specified - using default playbook")

        logger.info(
            f"✓ Validation complete: {len(errors)} errors, {len(warnings)} warnings"
        )

        return ConfigValidationResponse(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            suggestions=suggestions,
        )

    except Exception as e:
        logger.error(f"❌ Error validating configuration: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to validate configuration: {str(e)}",
        )


@router.get("/health")
async def config_health() -> Dict[str, str]:
    """Health check for configuration API."""
    return {"status": "healthy", "message": "Configuration API is operational"}
