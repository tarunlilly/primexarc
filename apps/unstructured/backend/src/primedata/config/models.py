"""
Pydantic models for PrimeData configuration.

Defines structured configuration models for playbooks, chunking, optimization,
scoring weights, and policy gates.
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from primedata.utils.log_utils import get_logger

logger = get_logger(__name__)


class ChunkingStrategy(str, Enum):
    """Chunking strategy enumeration."""

    FIXED_SIZE = "fixed_size"
    SEMANTIC = "semantic"
    RECURSIVE = "recursive"
    SENTENCE = "sentence"


class ChunkingConfig(BaseModel):
    """Chunking configuration model."""

    mode: str = Field(default="auto", description="Chunking mode: 'auto' or 'manual'")
    chunk_size: Optional[int] = Field(default=None, description="Target chunk size in tokens")
    chunk_overlap: Optional[int] = Field(default=None, description="Overlap size in tokens")
    min_chunk_size: Optional[int] = Field(default=None, description="Minimum chunk size")
    max_chunk_size: Optional[int] = Field(default=None, description="Maximum chunk size")
    chunking_strategy: Optional[ChunkingStrategy] = Field(
        default=None, description="Chunking strategy"
    )
    content_type: Optional[str] = Field(default=None, description="Detected content type")
    confidence: Optional[float] = Field(default=None, description="Confidence score (0.0-1.0)")

    class Config:
        use_enum_values = True


class PlaybookConfig(BaseModel):
    """Playbook configuration model."""

    id: str = Field(..., description="Playbook identifier (e.g., 'TECH', 'HEALTHCARE')")
    description: Optional[str] = Field(default=None, description="Playbook description")
    chunking: Optional[Dict[str, Any]] = Field(
        default=None, description="Default chunking settings from playbook"
    )
    pre_normalizers: Optional[List[Dict[str, Any]]] = Field(
        default=None, description="Text normalization rules"
    )
    quality_gates: Optional[Dict[str, Any]] = Field(
        default=None, description="Quality gate thresholds"
    )


class OptimizationConfig(BaseModel):
    """Optimization configuration model."""

    enhance_normalization: bool = Field(
        default=False, description="Enable enhanced text normalization"
    )
    error_correction: bool = Field(default=False, description="Enable OCR error correction")
    extract_metadata: bool = Field(default=False, description="Enable metadata extraction")
    increase_overlap: bool = Field(
        default=False, description="Increase chunk overlap for better context"
    )


class ScoringWeights(BaseModel):
    """Scoring weights for AI readiness metrics."""

    completeness: float = Field(default=10.0, description="Weight for Completeness metric")
    accuracy: float = Field(default=10.0, description="Weight for Accuracy metric")
    secure: float = Field(default=5.0, description="Weight for Secure metric")
    quality: float = Field(default=10.0, description="Weight for Quality metric")
    timeliness: float = Field(default=5.0, description="Weight for Timeliness metric")
    token_count: float = Field(default=5.0, description="Weight for Token_Count metric")
    gpt_confidence: float = Field(
        default=10.0, description="Weight for GPT_Confidence metric"
    )
    context_quality: float = Field(
        default=10.0, description="Weight for Context_Quality metric"
    )
    metadata_presence: float = Field(
        default=10.0, description="Weight for Metadata_Presence metric"
    )
    audience_intentionality: float = Field(
        default=10.0, description="Weight for Audience_Intentionality metric"
    )
    diversity: float = Field(default=5.0, description="Weight for Diversity metric")
    audience_accessibility: float = Field(
        default=5.0, description="Weight for Audience_Accessibility metric"
    )
    knowledgebase_ready: float = Field(
        default=5.0, description="Weight for KnowledgeBase_Ready metric"
    )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScoringWeights":
        """Create ScoringWeights from dictionary (handles key name variations)."""
        logger.debug("🔧 Parsing ScoringWeights from dict")
        # Map common variations
        key_mapping = {
            "Completeness": "completeness",
            "Accuracy": "accuracy",
            "Secure": "secure",
            "Quality": "quality",
            "Timeliness": "timeliness",
            "Token_Count": "token_count",
            "GPT_Confidence": "gpt_confidence",
            "Context_Quality": "context_quality",
            "Metadata_Presence": "metadata_presence",
            "Audience_Intentionality": "audience_intentionality",
            "Diversity": "diversity",
            "Audience_Accessibility": "audience_accessibility",
            "KnowledgeBase_Ready": "knowledgebase_ready",
        }

        normalized_data = {}
        for key, value in data.items():
            normalized_key = key_mapping.get(key, key.lower())
            normalized_data[normalized_key] = value

        logger.debug(f"📋 Normalized {len(normalized_data)} scoring weight keys")
        result = cls(**normalized_data)
        logger.debug("✅ ScoringWeights created successfully")
        return result


class PolicyGates(BaseModel):
    """Policy gate thresholds for quality evaluation."""

    min_trust_score: float = Field(default=50.0, description="Minimum AI Trust Score")
    min_secure: float = Field(default=90.0, description="Minimum Secure score")
    min_metadata_presence: float = Field(
        default=80.0, description="Minimum Metadata Presence"
    )
    min_kb_ready: float = Field(
        default=50.0, description="Minimum KnowledgeBase Ready score"
    )


class ResolutionTrace(BaseModel):
    """Tracks the source of each resolved configuration field."""

    chunk_size: str = Field(..., description="Source of chunk_size resolution")
    chunk_overlap: str = Field(..., description="Source of chunk_overlap resolution")
    min_chunk_size: str = Field(..., description="Source of min_chunk_size resolution")
    max_chunk_size: str = Field(..., description="Source of max_chunk_size resolution")
    chunking_strategy: str = Field(..., description="Source of chunking_strategy resolution")
    content_type: str = Field(..., description="Source of content_type resolution")
    playbook_id: str = Field(..., description="Source of playbook_id resolution")

    def to_dict(self) -> Dict[str, str]:
        """Convert to dictionary for logging/debugging."""
        logger.debug("📋 Converting ResolutionTrace to dict")
        result = {
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
            "min_chunk_size": self.min_chunk_size,
            "max_chunk_size": self.max_chunk_size,
            "chunking_strategy": self.chunking_strategy,
            "content_type": self.content_type,
            "playbook_id": self.playbook_id,
        }
        logger.debug("✅ ResolutionTrace converted to dict")
        return result


class EffectiveConfig(BaseModel):
    """Effective configuration after resolution with precedence."""

    chunking_config: ChunkingConfig = Field(..., description="Resolved chunking configuration")
    playbook_id: Optional[str] = Field(default=None, description="Resolved playbook ID")
    playbook_config: Optional[PlaybookConfig] = Field(
        default=None, description="Loaded playbook configuration"
    )
    optimization_config: Optional[OptimizationConfig] = Field(
        default=None, description="Optimization settings"
    )
    scoring_weights: Optional[ScoringWeights] = Field(
        default=None, description="Scoring weights"
    )
    policy_gates: Optional[PolicyGates] = Field(default=None, description="Policy gate thresholds")
    resolution_trace: ResolutionTrace = Field(..., description="Resolution trace")

    def to_legacy_dict(self, product_row: Optional[Any] = None) -> Dict[str, Any]:
        """
        Convert EffectiveConfig to legacy dict format for backward compatibility.

        Args:
            product_row: Optional product row to extract manual/auto settings from

        Returns:
            Dictionary in the format expected by existing pipeline code
        """
        logger.debug("🔧 Converting EffectiveConfig to legacy dict format")
        # Extract manual/auto settings from product if available
        manual_settings = {}
        auto_settings = {}
        if product_row:
            logger.debug("📋 Extracting manual/auto settings from product_row")
            product_chunking = getattr(product_row, "chunking_config", None) or {}
            if isinstance(product_chunking, dict):
                manual_settings = product_chunking.get("manual_settings", {})
                auto_settings = product_chunking.get("auto_settings", {})
                logger.debug(f"✓ Extracted manual_settings keys: {list(manual_settings.keys())}")
                logger.debug(f"✓ Extracted auto_settings keys: {list(auto_settings.keys())}")

        legacy_dict = {
            "chunking_config": {
                "mode": self.chunking_config.mode,
                "resolved_settings": {
                    "chunk_size": self.chunking_config.chunk_size,
                    "chunk_overlap": self.chunking_config.chunk_overlap,
                    "min_chunk_size": self.chunking_config.min_chunk_size,
                    "max_chunk_size": self.chunking_config.max_chunk_size,
                    "chunking_strategy": self.chunking_config.chunking_strategy,
                    "content_type": self.chunking_config.content_type,
                    "confidence": self.chunking_config.confidence,
                },
                "manual_settings": manual_settings,
                "auto_settings": auto_settings,
            },
            "playbook_id": self.playbook_id,
            "playbook_selection": {
                "playbook_id": self.playbook_id,
                "method": "manual" if self.playbook_id else "auto",
                "reason": None,
                "detected_at": None,
            },
            "resolution_trace": self.resolution_trace.dict() if self.resolution_trace else None,
        }
        logger.debug("✅ Legacy dict conversion complete")
        return legacy_dict

    class Config:
        use_enum_values = True
