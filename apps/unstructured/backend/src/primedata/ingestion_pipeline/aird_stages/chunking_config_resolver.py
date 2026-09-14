"""
Chunking configuration resolution logic.

Resolves the effective chunking parameters (chunk_size, strategy, overlap, etc.)
from the product-level chunking_config, playbook settings, and content analysis.
"""

import logging
from typing import Any, Dict, Optional, Tuple

from primedata.analysis.content_analyzer import content_analyzer
from primedata.ingestion_pipeline.pipeline_config import resolve_content_hint

logger = logging.getLogger(__name__)


class ResolvedChunkingParams:
    """Container for resolved chunking parameters."""

    def __init__(
        self,
        strategy: str,
        max_tokens: int,
        overlap_sents: int,
        hard_overlap: int,
        chunk_size: int,
        chunk_overlap: int,
        resolved_chunking_config: Dict[str, Any],
        detected_domain_type: Optional[str],
        confidence: Optional[float],
        confidence_threshold: Optional[float],
        confidence_met: Optional[bool],
    ):
        self.strategy = strategy
        self.max_tokens = max_tokens
        self.overlap_sents = overlap_sents
        self.hard_overlap = hard_overlap
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.resolved_chunking_config = resolved_chunking_config
        self.detected_domain_type = detected_domain_type
        self.confidence = confidence
        self.confidence_threshold = confidence_threshold
        self.confidence_met = confidence_met


def _map_strategy_to_playbook(strategy: str, playbook_chunking: Dict[str, Any]) -> str:
    """Map a user-facing strategy name to the internal playbook strategy.

    :param strategy: User-facing strategy name (e.g., 'fixed_size', 'semantic').
    :param playbook_chunking: Playbook chunking config for fallback.
    :return: Internal strategy name ('char', 'paragraph', or 'sentence').
    """
    strategy_lower = strategy.lower()
    if strategy_lower == "fixed_size":
        return "char"
    elif strategy_lower == "semantic":
        return "paragraph"
    elif strategy_lower == "paragraph_boundary":
        return "paragraph"
    elif strategy_lower in ["sentence", "sentence_boundary"]:
        return "sentence"
    elif strategy_lower == "recursive":
        return "sentence"
    else:
        return playbook_chunking.get("strategy", "sentence")


def resolve_chunking_config(
    chunking_config: Optional[Dict[str, Any]],
    playbook: Dict[str, Any],
    playbook_id: str,
    cleaned_text: str,
    filename: str,
    context_cache: Optional[Dict[str, Any]],
    log: Optional[logging.Logger] = None,
) -> ResolvedChunkingParams:
    """Resolve the effective chunking configuration from multiple sources.

    Priority: Product manual settings > Product auto settings > Playbook defaults.

    :param chunking_config: Product-level chunking configuration dict (may be None).
    :param playbook: Loaded playbook configuration dictionary.
    :param playbook_id: Identifier of the playbook being used.
    :param cleaned_text: Cleaned document text for content analysis (if needed).
    :param filename: Original filename of the document.
    :param context_cache: Optional context cache with workspace_id, db, use_case_description.
    :param log: Optional logger instance.
    :return: ResolvedChunkingParams with all resolved parameters.
    """
    _log = log or logger

    playbook_chunking = playbook.get("chunking", {})

    # Ensure chunking_config is a valid dict
    if not chunking_config or not isinstance(chunking_config, dict):
        _log.warning(
            f"chunking_config is {type(chunking_config).__name__}, initializing with defaults"
        )
        chunking_config = {
            "mode": "auto",
            "auto_settings": {"content_type": "general", "model_optimized": True, "confidence_threshold": 0.7},
            "manual_settings": {
                "chunk_size": 1000,
                "chunk_overlap": 200,
                "min_chunk_size": 100,
                "max_chunk_size": 2000,
                "chunking_strategy": "fixed_size",
            },
        }

    # Track the resolved chunking configuration actually used
    resolved_chunking_config: Dict[str, Any] = {
        "mode": chunking_config.get("mode", "auto"),
        "source": None,  # manual | product_auto | playbook_default
    }
    hint_reason = None
    confidence_threshold = None
    confidence: Optional[float] = None
    confidence_met: Optional[bool] = None
    detected_domain_type: Optional[str] = None

    if chunking_config.get("mode") == "manual":
        params = _resolve_manual_mode(
            chunking_config, playbook_chunking, resolved_chunking_config, _log
        )
        return params

    elif chunking_config.get("mode") == "auto":
        params = _resolve_auto_mode(
            chunking_config, playbook, playbook_id, playbook_chunking,
            cleaned_text, filename, context_cache, resolved_chunking_config, _log
        )
        return params

    else:
        # Fallback to playbook defaults
        return _resolve_playbook_defaults(chunking_config, playbook_chunking, resolved_chunking_config, _log)


def _resolve_manual_mode(
    chunking_config: Dict[str, Any],
    playbook_chunking: Dict[str, Any],
    resolved_chunking_config: Dict[str, Any],
    _log: logging.Logger,
) -> ResolvedChunkingParams:
    """Resolve chunking config for manual mode.

    :param chunking_config: Product-level chunking configuration.
    :param playbook_chunking: Playbook chunking settings.
    :param resolved_chunking_config: Dict to populate with resolved config metadata.
    :param _log: Logger instance.
    :return: ResolvedChunkingParams for manual mode.
    """
    manual_settings = chunking_config.get("manual_settings", {})
    original_strategy = manual_settings.get("chunking_strategy", playbook_chunking.get("strategy", "sentence"))

    # chunk_size is already in tokens, use it directly as max_tokens
    max_tokens = int(manual_settings.get("chunk_size", playbook_chunking.get("max_tokens", 900)))
    chunk_size = max_tokens
    # chunk_overlap is already in tokens
    chunk_overlap = int(manual_settings.get("chunk_overlap", 200))
    # Estimate: 1 sentence ~ 20 tokens, so overlap_sentences = chunk_overlap / 20
    overlap_sents = max(1, int(chunk_overlap / 20))
    # Convert tokens to chars for hard_overlap: 1 token ~ 4 chars
    hard_overlap = chunk_overlap * 4

    # Convert strategy for playbook processing
    playbook_strategy = _map_strategy_to_playbook(original_strategy, playbook_chunking)

    # Store resolved config with ORIGINAL strategy from UI
    resolved_chunking_config.update(
        {
            "source": "manual",
            "chunk_size": max_tokens,
            "chunk_overlap": chunk_overlap,
            "min_chunk_size": int(manual_settings.get("min_chunk_size", playbook_chunking.get("min_chunk_size", 100))),
            "max_chunk_size": int(
                manual_settings.get("max_chunk_size", playbook_chunking.get("max_chunk_size", 2000))
            ),
            "chunking_strategy": original_strategy,
        }
    )

    # For manual mode, try to infer domain_type from resolved config if available
    detected_domain_type = None
    resolved = chunking_config.get("resolved_settings", {})
    if resolved:
        detected_domain_type = resolved.get("content_type")

    return ResolvedChunkingParams(
        strategy=playbook_strategy,
        max_tokens=max_tokens,
        overlap_sents=overlap_sents,
        hard_overlap=hard_overlap,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        resolved_chunking_config=resolved_chunking_config,
        detected_domain_type=detected_domain_type,
        confidence=None,
        confidence_threshold=None,
        confidence_met=None,
    )


def _resolve_auto_mode(
    chunking_config: Dict[str, Any],
    playbook: Dict[str, Any],
    playbook_id: str,
    playbook_chunking: Dict[str, Any],
    cleaned_text: str,
    filename: str,
    context_cache: Optional[Dict[str, Any]],
    resolved_chunking_config: Dict[str, Any],
    _log: logging.Logger,
) -> ResolvedChunkingParams:
    """Resolve chunking config for auto mode.

    :param chunking_config: Product-level chunking configuration.
    :param playbook: Loaded playbook configuration dictionary.
    :param playbook_id: Identifier of the playbook.
    :param playbook_chunking: Playbook chunking settings.
    :param cleaned_text: Cleaned document text for content analysis.
    :param filename: Original filename.
    :param context_cache: Optional context cache.
    :param resolved_chunking_config: Dict to populate with resolved config metadata.
    :param _log: Logger instance.
    :return: ResolvedChunkingParams for auto mode.
    """
    # Check if resolved_settings already exist from auto-detection in task_preprocess
    resolved_settings = chunking_config.get("resolved_settings", {})

    # Ensure manual_settings exists with defaults
    default_manual_settings = {
        "chunk_size": 1000,
        "chunk_overlap": 200,
        "min_chunk_size": 100,
        "max_chunk_size": 2000,
        "chunking_strategy": "fixed_size",
    }
    manual_settings = chunking_config.get("manual_settings", {})
    manual_settings_provided = (
        isinstance(manual_settings, dict)
        and bool(manual_settings)
        and manual_settings != default_manual_settings
    )
    if not manual_settings or not isinstance(manual_settings, dict):
        manual_settings = default_manual_settings.copy()
        chunking_config["manual_settings"] = manual_settings
        _log.info(f"Initialized missing manual_settings with defaults: {manual_settings}")
        manual_settings_provided = False

    confidence_threshold: Optional[float] = None
    confidence: Optional[float] = None
    confidence_met: Optional[bool] = None
    hint_reason: Optional[str] = None

    if resolved_settings and isinstance(resolved_settings, dict):
        confidence_threshold = 0.7
        auto_settings = chunking_config.get("auto_settings", {})
        if isinstance(auto_settings, dict):
            confidence_threshold = auto_settings.get("confidence_threshold", confidence_threshold)
        resolved_confidence = resolved_settings.get("confidence")
        analysis_confidence = chunking_config.get("analysis_confidence")
        confidence_met = resolved_settings.get("confidence_met")
        low_confidence = (
            confidence_met is False
            or (resolved_confidence is not None and resolved_confidence < confidence_threshold)
            or (analysis_confidence is not None and analysis_confidence < confidence_threshold)
        )
        if low_confidence:
            _log.warning(
                "Low confidence chunking detection; falling back to default/general chunking settings "
                "(confidence=%.2f, analysis_confidence=%s, threshold=%.2f).",
                resolved_confidence if resolved_confidence is not None else -1.0,
                analysis_confidence,
                confidence_threshold,
            )
            resolved_settings = {
                "chunk_size": resolved_settings.get("chunk_size", 1000),
                "chunk_overlap": resolved_settings.get("chunk_overlap", 200),
                "min_chunk_size": resolved_settings.get("min_chunk_size", 100),
                "max_chunk_size": resolved_settings.get("max_chunk_size", 2000),
                "chunking_strategy": "fixed_size",
                "content_type": "general",
                "confidence": resolved_confidence if resolved_confidence is not None else 0.0,
                "reasoning": "Low confidence fallback to default chunking",
                "evidence": resolved_settings.get("evidence"),
            }

    if resolved_settings and isinstance(resolved_settings, dict):
        # Use existing resolved_settings from task_preprocess auto-detection
        _log.info(
            f"Using existing resolved_settings from auto-detection: "
            f"content_type={resolved_settings.get('content_type')}, "
            f"chunk_size={resolved_settings.get('chunk_size')}, "
            f"chunking_strategy={resolved_settings.get('chunking_strategy')}"
        )

        # Extract values from resolved_settings with validation
        chunk_size = resolved_settings.get("chunk_size", 1000)
        chunk_overlap = resolved_settings.get("chunk_overlap", 200)
        min_chunk_size = resolved_settings.get("min_chunk_size", 100)
        max_chunk_size = resolved_settings.get("max_chunk_size", 2000)
        strategy = resolved_settings.get("chunking_strategy", "fixed_size")
        content_type = resolved_settings.get("content_type", "general")
        confidence = resolved_settings.get("confidence", 0.5)
        reasoning = resolved_settings.get("reasoning", "Auto-detected from sample files")
        evidence = resolved_settings.get("evidence")

        # Validate extracted values
        if not chunk_size or chunk_size <= 0:
            _log.error(f"Invalid chunk_size from resolved_settings: {chunk_size}. Using default 1000.")
            chunk_size = 1000
        if chunk_overlap is None or chunk_overlap < 0:
            _log.error(f"Invalid chunk_overlap from resolved_settings: {chunk_overlap}. Using default 200.")
            chunk_overlap = 200
        if not strategy:
            _log.error(f"Invalid strategy from resolved_settings: {strategy}. Using default 'fixed_size'.")
            strategy = "fixed_size"

        # Allow manual_settings to override only if explicitly provided (not defaults)
        if manual_settings_provided:
            if "chunk_size" in manual_settings and manual_settings.get("chunk_size"):
                chunk_size = manual_settings["chunk_size"]
                _log.info(f"Overriding chunk_size with manual_settings: {chunk_size}")
            if "chunk_overlap" in manual_settings and manual_settings.get("chunk_overlap") is not None:
                chunk_overlap = manual_settings["chunk_overlap"]
                _log.info(f"Overriding chunk_overlap with manual_settings: {chunk_overlap}")
            if "min_chunk_size" in manual_settings and manual_settings.get("min_chunk_size"):
                min_chunk_size = manual_settings["min_chunk_size"]
            if "max_chunk_size" in manual_settings and manual_settings.get("max_chunk_size"):
                max_chunk_size = manual_settings["max_chunk_size"]
            if "chunking_strategy" in manual_settings and manual_settings.get("chunking_strategy"):
                strategy = manual_settings["chunking_strategy"]
                _log.info(f"Overriding chunking_strategy with manual_settings: {strategy}")

        if chunk_size <= 0:
            _log.warning(f"chunk_size {chunk_size} is invalid; using default 1000.")
            chunk_size = 1000
        if chunk_overlap is None or chunk_overlap < 0:
            _log.warning(f"chunk_overlap {chunk_overlap} is invalid; using default 200.")
            chunk_overlap = 200
        if chunk_overlap >= chunk_size:
            adjusted_overlap = max(chunk_size - 1, 0)
            _log.warning(
                f"chunk_overlap {chunk_overlap} must be less than chunk_size {chunk_size}; "
                f"using {adjusted_overlap}."
            )
            chunk_overlap = adjusted_overlap
    else:
        # No resolved_settings, analyze content now
        _log.info("No resolved_settings found, running content analysis in preprocessing stage")

        # Sample cleaned text for analysis (use up to 20k chars for good detection)
        sample_text = cleaned_text[:20000] if len(cleaned_text) > 20000 else cleaned_text

        use_case_description = None
        if isinstance(context_cache, dict):
            use_case_description = context_cache.get("use_case_description")
        playbook_hint = resolve_content_hint(playbook_id, use_case_description)
        hint_reason = None
        if playbook_hint and use_case_description:
            hint_reason = "use_case_description"
        elif playbook_hint:
            hint_reason = "playbook_id"

        # Analyze content using ContentAnalyzer
        try:
            detected_config = content_analyzer.analyze_content(
                content=sample_text,
                filename=filename,
                hint=playbook_hint
            )

            # Use detected configuration
            chunk_size = detected_config.chunk_size
            chunk_overlap = detected_config.chunk_overlap
            min_chunk_size = detected_config.min_chunk_size
            max_chunk_size = detected_config.max_chunk_size
            strategy = detected_config.strategy.value  # Convert enum to string
            content_type = detected_config.content_type.value  # Convert enum to string
            confidence = detected_config.confidence
            reasoning = detected_config.reasoning
            evidence = detected_config.evidence

            _log.info(
                f"Content analysis detected: {content_type} (confidence: {confidence:.2f}, strategy: {strategy}, "
                f"chunk_size: {chunk_size}, overlap: {chunk_overlap})"
            )

            # Allow manual_settings to override only if explicitly provided
            if manual_settings_provided:
                if manual_settings.get("chunk_size"):
                    chunk_size = manual_settings["chunk_size"]
                if manual_settings.get("chunk_overlap"):
                    chunk_overlap = manual_settings["chunk_overlap"]
                if manual_settings.get("min_chunk_size"):
                    min_chunk_size = manual_settings["min_chunk_size"]
                if manual_settings.get("max_chunk_size"):
                    max_chunk_size = manual_settings["max_chunk_size"]
                if manual_settings.get("chunking_strategy"):
                    strategy = manual_settings["chunking_strategy"]

        except Exception as e:
            # Fallback to default if analysis fails
            _log.warning(f"Content analysis failed: {e}. Falling back to default configuration.", exc_info=True)

            # Fallback to general config
            chunk_size = 1000
            chunk_overlap = 200
            min_chunk_size = 100
            max_chunk_size = 2000
            strategy = "fixed_size"
            content_type = "general"
            confidence = 0.3
            reasoning = "Fallback to default due to analysis error"
            evidence = None

    # Store domain_type for use when building records
    detected_domain_type = content_type
    playbook_strategy = _map_strategy_to_playbook(strategy, playbook_chunking)

    # chunk_size is already in tokens, use it directly as max_tokens
    max_tokens = int(chunk_size) if chunk_size else int(playbook_chunking.get("max_tokens", 900))

    # Validate max_tokens is reasonable (must be > 0 and < 10000)
    if max_tokens <= 0:
        _log.error(f"Invalid max_tokens: {max_tokens} (chunk_size: {chunk_size}). Using default 900.")
        max_tokens = 900
    elif max_tokens > 10000:
        _log.warning(f"max_tokens {max_tokens} is very large. Capping at 4000.")
        max_tokens = 4000

    # Estimate: 1 sentence ~ 20 tokens, so overlap_sentences = chunk_overlap / 20
    overlap_sents = max(1, int(chunk_overlap / 20))
    # Convert tokens to chars for hard_overlap: 1 token ~ 4 chars
    hard_overlap = chunk_overlap * 4

    # Validate hard_overlap is reasonable
    if hard_overlap <= 0:
        hard_overlap = 300
        _log.warning(f"Invalid hard_overlap calculated: {hard_overlap}. Using default 300.")

    # Store resolved config with detection evidence
    resolved_chunking_config.update(
        {
            "source": "product_auto",
            "chunk_size": chunk_size,
            "chunk_overlap": chunk_overlap,
            "min_chunk_size": min_chunk_size,
            "max_chunk_size": max_chunk_size,
            "chunking_strategy": strategy,
            "content_type": content_type,
            "detection_confidence": confidence,
            "detection_reasoning": reasoning,
            "detection_evidence": evidence,
            "hint_applied": bool(evidence and evidence.get("hint_applied")),
            "hint_reason": hint_reason,
        }
    )

    return ResolvedChunkingParams(
        strategy=playbook_strategy,
        max_tokens=max_tokens,
        overlap_sents=overlap_sents,
        hard_overlap=hard_overlap,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        resolved_chunking_config=resolved_chunking_config,
        detected_domain_type=detected_domain_type,
        confidence=confidence,
        confidence_threshold=confidence_threshold,
        confidence_met=confidence_met,
    )


def _resolve_playbook_defaults(
    chunking_config: Optional[Dict[str, Any]],
    playbook_chunking: Dict[str, Any],
    resolved_chunking_config: Dict[str, Any],
    _log: logging.Logger,
) -> ResolvedChunkingParams:
    """Resolve chunking config using playbook defaults.

    :param chunking_config: Product-level chunking configuration (for domain_type inference).
    :param playbook_chunking: Playbook chunking settings.
    :param resolved_chunking_config: Dict to populate with resolved config metadata.
    :param _log: Logger instance.
    :return: ResolvedChunkingParams using playbook defaults.
    """
    max_tokens = int(playbook_chunking.get("max_tokens", 900))
    overlap_sents = int(playbook_chunking.get("overlap_sentences", 2))
    hard_overlap = int(playbook_chunking.get("hard_overlap_chars", 300))
    strategy = (playbook_chunking.get("strategy", "sentence") or "sentence").lower()
    chunk_size = max_tokens
    chunk_overlap = overlap_sents * 20  # approximate tokens

    resolved_chunking_config.update(
        {
            "source": "playbook_default",
            "chunk_size": max_tokens,
            "chunk_overlap": overlap_sents * 20,
            "min_chunk_size": int(playbook_chunking.get("min_chunk_size", 100)),
            "max_chunk_size": int(playbook_chunking.get("max_chunk_size", 2000)),
            "chunking_strategy": "fixed_size" if strategy == "char" else "semantic",
        }
    )

    # For playbook_default mode, try to infer domain_type from resolved config if available
    detected_domain_type = None
    if chunking_config:
        resolved = chunking_config.get("resolved_settings", {})
        if resolved:
            detected_domain_type = resolved.get("content_type")

    return ResolvedChunkingParams(
        strategy=strategy,
        max_tokens=max_tokens,
        overlap_sents=overlap_sents,
        hard_overlap=hard_overlap,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        resolved_chunking_config=resolved_chunking_config,
        detected_domain_type=detected_domain_type,
        confidence=None,
        confidence_threshold=None,
        confidence_met=None,
    )
