"""
Configuration resolver with precedence-based resolution.

Implements resolve_effective_config with the following precedence order:
1. run_conf overrides (highest priority)
2. force_product_chunking_config
3. product manual settings
4. playbook defaults
5. global defaults (lowest priority)
"""

from typing import Any, Dict, Optional

from primedata.utils.log_utils import get_logger

logger = get_logger(__name__)

from primedata.analysis.content_analyzer import ContentType, content_analyzer
from primedata.config.models import (
    ChunkingConfig,
    EffectiveConfig,
    PlaybookConfig,
    ResolutionTrace,
)
from primedata.ingestion_pipeline.aird_stages.playbooks.loader import load_playbook_yaml

# Global defaults
DEFAULT_MANUAL_SETTINGS: Dict[str, Any] = {
    "chunk_size": 1000,
    "chunk_overlap": 200,
    "min_chunk_size": 100,
    "max_chunk_size": 2000,
    "chunking_strategy": "fixed_size",
}

DEFAULT_AUTO_SETTINGS: Dict[str, Any] = {
    "content_type": "general",
    "model_optimized": True,
    "confidence_threshold": 0.7,
}


def _ensure_dict(value: Any) -> Dict[str, Any]:
    """Ensure value is a dictionary.

    :param value: Any value to check.
    :return: The value if it is a dict, otherwise an empty dict.
    """
    logger.debug("🔧 Ensuring value is dict")
    result = value if isinstance(value, dict) else {}
    logger.debug(f"✓ Result is dict with {len(result)} keys")
    return result


def _get_playbook_chunking_defaults(playbook_config: Optional[PlaybookConfig]) -> Dict[str, Any]:
    """Extract chunking defaults from playbook configuration.

    :param playbook_config: Loaded playbook configuration or None.
    :return: Dictionary of chunking default values from the playbook.
    """
    logger.debug("🔧 Extracting playbook chunking defaults")
    if not playbook_config or not playbook_config.chunking:
        logger.debug("✓ No playbook config or chunking settings found")
        return {}

    chunking = playbook_config.chunking
    defaults = {}

    # Map playbook chunking config to our format
    # Convert tokens to characters: 1 token ≈ 4 characters (conservative estimate)
    if "max_tokens" in chunking:
        max_tokens = chunking["max_tokens"]
        defaults["chunk_size"] = max_tokens * 4
        logger.debug(f"📋 Set chunk_size from max_tokens: {defaults['chunk_size']}")
    elif "chunk_size" in chunking:
        defaults["chunk_size"] = chunking["chunk_size"]
        logger.debug(f"📋 Set chunk_size from playbook: {defaults['chunk_size']}")

    # Handle overlap: prefer hard_overlap_chars, fallback to overlap_sentences
    if "hard_overlap_chars" in chunking:
        defaults["chunk_overlap"] = chunking["hard_overlap_chars"]
        logger.debug(f"📋 Set chunk_overlap from hard_overlap_chars: {defaults['chunk_overlap']}")
    elif "overlap_sentences" in chunking:
        # Rough conversion: 1 sentence ≈ 50-100 chars, use 75 as average
        defaults["chunk_overlap"] = chunking["overlap_sentences"] * 75
        logger.debug(f"📋 Set chunk_overlap from overlap_sentences: {defaults['chunk_overlap']}")
    elif "chunk_overlap" in chunking:
        defaults["chunk_overlap"] = chunking["chunk_overlap"]
        logger.debug(f"📋 Set chunk_overlap from playbook: {defaults['chunk_overlap']}")

    if "strategy" in chunking:
        strategy = chunking["strategy"]
        # Map playbook strategies to our enum values
        if strategy == "sentence":
            defaults["chunking_strategy"] = "semantic"
        elif strategy == "fixed_size":
            defaults["chunking_strategy"] = "fixed_size"
        else:
            defaults["chunking_strategy"] = "fixed_size"  # Default fallback
        logger.debug(f"📋 Set chunking_strategy: {defaults['chunking_strategy']}")

    logger.debug(f"✅ Extracted {len(defaults)} playbook defaults")
    return defaults


def _get_content_type_defaults(content_type: Optional[str]) -> Dict[str, Any]:
    """Get defaults from content analyzer for a given content type.

    :param content_type: Content type string (e.g., 'legal', 'technical').
    :return: Dictionary of default chunking values for the content type.
    """
    logger.debug(f"🔧 Getting content type defaults for: {content_type}")
    if not content_type:
        logger.debug("✓ No content type specified")
        return {}

    try:
        content_type_enum = ContentType(content_type)
        default_config = content_analyzer.optimal_configs.get(content_type_enum)
        if default_config:
            logger.debug("📋 Found optimal config for content type")
            result = {
                "chunk_size": default_config["chunk_size"],
                "chunk_overlap": default_config["chunk_overlap"],
                "min_chunk_size": default_config["min_chunk_size"],
                "max_chunk_size": default_config["max_chunk_size"],
                "chunking_strategy": default_config["strategy"].value,
            }
            logger.debug(f"✅ Extracted {len(result)} content type defaults")
            return result
    except (ValueError, KeyError) as e:
        logger.debug(f"⚠️ Failed to get content type defaults: {e}")
        pass

    logger.debug("✓ Using empty defaults for content type")
    return {}


def resolve_effective_config(
    run_conf: Optional[Dict[str, Any]],
    product_row: Any,
    detected_playbook: Optional[str] = None,
) -> EffectiveConfig:
    """
    Resolve effective configuration with precedence-based resolution.

    Precedence order (highest to lowest):
    1. run_conf overrides
    2. force_product_chunking_config
    3. product manual settings
    4. playbook defaults
    5. global defaults

    Args:
        run_conf: Runtime configuration overrides (from DAG run config)
        product_row: Product database row/model instance
        detected_playbook: Detected playbook ID (optional)

    Returns:
        EffectiveConfig with resolved configuration and ResolutionTrace
    """
    logger.info(f"🔧 Resolving effective config for product {getattr(product_row, 'id', 'unknown')}")
    logger.debug(f"📋 run_conf: {bool(run_conf)}, detected_playbook: {detected_playbook}")

    run_conf = run_conf or {}
    trace = ResolutionTrace(
        chunk_size="",
        chunk_overlap="",
        min_chunk_size="",
        max_chunk_size="",
        chunking_strategy="",
        content_type="",
        playbook_id="",
    )

    # Extract product configuration
    logger.debug("📋 Extracting product configuration")
    product_chunking = _ensure_dict(getattr(product_row, "chunking_config", None))
    product_playbook_id = getattr(product_row, "playbook_id", None)
    product_manual_settings = _ensure_dict(product_chunking.get("manual_settings"))
    product_auto_settings = _ensure_dict(product_chunking.get("auto_settings"))
    logger.debug(f"✓ Product manual_settings keys: {list(product_manual_settings.keys())}")
    logger.debug(f"✓ Product auto_settings keys: {list(product_auto_settings.keys())}")

    # Determine playbook ID (precedence: run_conf > detected > product)
    logger.debug("🔎 Determining playbook ID precedence")
    playbook_id = (
        run_conf.get("playbook_id")
        or detected_playbook
        or product_playbook_id
        or "TECH"  # Global default
    )
    trace.playbook_id = (
        "run_conf"
        if run_conf.get("playbook_id")
        else ("detected_playbook" if detected_playbook else ("product" if product_playbook_id else "global_default"))
    )
    logger.debug(f"✓ Selected playbook: {playbook_id} (source: {trace.playbook_id})")

    # Load playbook configuration
    logger.debug(f"📋 Loading playbook configuration for: {playbook_id}")
    playbook_config: Optional[PlaybookConfig] = None
    try:
        workspace_id = getattr(product_row, "workspace_id", None)
        db_session = getattr(product_row, "__session__", None)  # Try to get session if available
        playbook_dict = load_playbook_yaml(playbook_id, str(workspace_id) if workspace_id else None, db_session)
        if playbook_dict:
            playbook_config = PlaybookConfig(**playbook_dict)
            logger.debug(f"✅ Loaded playbook config for {playbook_id}")
    except Exception as e:
        logger.warning(f"⚠️ Failed to load playbook {playbook_id}: {e}")

    # Get playbook chunking defaults
    logger.debug("🔧 Extracting playbook defaults")
    playbook_defaults = _get_playbook_chunking_defaults(playbook_config)
    logger.debug(f"✓ Playbook defaults: {list(playbook_defaults.keys())}")

    # Get content type defaults
    logger.debug("🔧 Determining content type")
    content_type = product_auto_settings.get("content_type") or playbook_defaults.get("content_type") or "general"
    content_type_defaults = _get_content_type_defaults(content_type)
    trace.content_type = (
        "product_auto_settings"
        if product_auto_settings.get("content_type")
        else ("playbook" if playbook_defaults.get("content_type") else "global_default")
    )
    logger.debug(f"✓ Content type: {content_type} (source: {trace.content_type})")

    # Start with global defaults
    logger.debug("📋 Applying precedence resolution (lowest to highest)")
    resolved = {
        "chunk_size": DEFAULT_MANUAL_SETTINGS["chunk_size"],
        "chunk_overlap": DEFAULT_MANUAL_SETTINGS["chunk_overlap"],
        "min_chunk_size": DEFAULT_MANUAL_SETTINGS["min_chunk_size"],
        "max_chunk_size": DEFAULT_MANUAL_SETTINGS["max_chunk_size"],
        "chunking_strategy": DEFAULT_MANUAL_SETTINGS["chunking_strategy"],
        "content_type": content_type,
    }
    logger.debug(f"✓ Step 1: Applied global defaults")

    # Apply precedence (lowest to highest, so later overrides earlier)

    # 5. Global defaults (already set above)
    trace.chunk_size = "global_default"
    trace.chunk_overlap = "global_default"
    trace.min_chunk_size = "global_default"
    trace.max_chunk_size = "global_default"
    trace.chunking_strategy = "global_default"

    # 4. Playbook defaults
    logger.debug("✓ Step 4: Applying playbook defaults")
    for key, value in playbook_defaults.items():
        if value is not None and key in resolved:
            resolved[key] = value
            if key == "chunk_size":
                trace.chunk_size = "playbook_defaults"
            elif key == "chunk_overlap":
                trace.chunk_overlap = "playbook_defaults"
            elif key == "min_chunk_size":
                trace.min_chunk_size = "playbook_defaults"
            elif key == "max_chunk_size":
                trace.max_chunk_size = "playbook_defaults"
            elif key == "chunking_strategy":
                trace.chunking_strategy = "playbook_defaults"
    logger.debug(f"✓ Updated keys from playbook: {list(playbook_defaults.keys())}")

    # 4b. Content type defaults (can override playbook if more specific)
    logger.debug("✓ Step 4b: Applying content type defaults")
    for key, value in content_type_defaults.items():
        if value is not None and key in resolved:
            resolved[key] = value
            if key == "chunk_size":
                trace.chunk_size = "content_type_defaults"
            elif key == "chunk_overlap":
                trace.chunk_overlap = "content_type_defaults"
            elif key == "min_chunk_size":
                trace.min_chunk_size = "content_type_defaults"
            elif key == "max_chunk_size":
                trace.max_chunk_size = "content_type_defaults"
            elif key == "chunking_strategy":
                trace.chunking_strategy = "content_type_defaults"
    logger.debug(f"✓ Updated keys from content type: {list(content_type_defaults.keys())}")

    # 3. Product manual settings
    logger.debug("✓ Step 3: Applying product manual settings")
    for key, value in product_manual_settings.items():
        if value is not None and key in resolved:
            resolved[key] = value
            if key == "chunk_size":
                trace.chunk_size = "product_manual_settings"
            elif key == "chunk_overlap":
                trace.chunk_overlap = "product_manual_settings"
            elif key == "min_chunk_size":
                trace.min_chunk_size = "product_manual_settings"
            elif key == "max_chunk_size":
                trace.max_chunk_size = "product_manual_settings"
            elif key == "chunking_strategy":
                trace.chunking_strategy = "product_manual_settings"
    logger.debug(f"✓ Updated keys from product manual: {list(product_manual_settings.keys())}")

    # 2. force_product_chunking_config (if set in run_conf)
    logger.debug("✓ Step 2: Checking force_product_chunking_config")
    if run_conf.get("force_product_chunking_config"):
        logger.debug("📋 force_product_chunking_config is enabled")
        for key, value in product_chunking.items():
            if value is not None and key in resolved:
                resolved[key] = value
                if key == "chunk_size":
                    trace.chunk_size = "force_product_chunking_config"
                elif key == "chunk_overlap":
                    trace.chunk_overlap = "force_product_chunking_config"
                elif key == "min_chunk_size":
                    trace.min_chunk_size = "force_product_chunking_config"
                elif key == "max_chunk_size":
                    trace.max_chunk_size = "force_product_chunking_config"
                elif key == "chunking_strategy":
                    trace.chunking_strategy = "force_product_chunking_config"
        logger.debug(f"✓ Updated keys from force config")

    # 1. run_conf overrides (highest priority)
    logger.debug("✓ Step 1: Applying run_conf overrides (highest priority)")
    run_chunking = _ensure_dict(run_conf.get("chunking_config"))
    for key, value in run_chunking.items():
        if value is not None and key in resolved:
            resolved[key] = value
            if key == "chunk_size":
                trace.chunk_size = "run_conf"
            elif key == "chunk_overlap":
                trace.chunk_overlap = "run_conf"
            elif key == "min_chunk_size":
                trace.min_chunk_size = "run_conf"
            elif key == "max_chunk_size":
                trace.max_chunk_size = "run_conf"
            elif key == "chunking_strategy":
                trace.chunking_strategy = "run_conf"
    logger.debug(f"✓ Updated keys from run_chunking: {list(run_chunking.keys())}")

    # Also check for direct overrides in run_conf
    for key in ["chunk_size", "chunk_overlap", "min_chunk_size", "max_chunk_size", "chunking_strategy"]:
        if key in run_conf and run_conf[key] is not None:
            resolved[key] = run_conf[key]
            if key == "chunk_size":
                trace.chunk_size = "run_conf"
            elif key == "chunk_overlap":
                trace.chunk_overlap = "run_conf"
            elif key == "min_chunk_size":
                trace.min_chunk_size = "run_conf"
            elif key == "max_chunk_size":
                trace.max_chunk_size = "run_conf"
            elif key == "chunking_strategy":
                trace.chunking_strategy = "run_conf"
    if any(k in run_conf for k in ["chunk_size", "chunk_overlap", "min_chunk_size", "max_chunk_size", "chunking_strategy"]):
        logger.debug("✓ Applied direct run_conf overrides")

    # Build ChunkingConfig
    logger.debug("💾 Building ChunkingConfig")
    chunking_config = ChunkingConfig(
        mode=product_chunking.get("mode", "auto"),
        chunk_size=resolved["chunk_size"],
        chunk_overlap=resolved["chunk_overlap"],
        min_chunk_size=resolved["min_chunk_size"],
        max_chunk_size=resolved["max_chunk_size"],
        chunking_strategy=resolved["chunking_strategy"],
        content_type=resolved["content_type"],
        confidence=product_auto_settings.get("confidence"),
    )
    logger.debug(f"✓ ChunkingConfig created: chunk_size={chunking_config.chunk_size}, chunk_overlap={chunking_config.chunk_overlap}")

    result = EffectiveConfig(
        chunking_config=chunking_config,
        playbook_id=playbook_id,
        playbook_config=playbook_config,
        resolution_trace=trace,
    )
    logger.info(f"✅ Configuration resolution complete for product {getattr(product_row, 'id', 'unknown')}")
    return result
