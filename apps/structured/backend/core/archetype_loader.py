"""Load and validate archetype YAML configs at import time.

All 13 archetype configs are loaded into ARCHETYPES dict, validated against
the ArchetypeConfig model. Fails fast on startup if any YAML is malformed.
"""
from __future__ import annotations

import logging
from pathlib import Path

import yaml

from core.models import ArchetypeConfig

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path(__file__).parent / "archetypes"


def _load_archetypes() -> dict[str, ArchetypeConfig]:
    """Load all .yaml files from the archetypes directory."""
    archetypes: dict[str, ArchetypeConfig] = {}
    if not _CONFIG_DIR.exists():
        logger.warning("Archetypes directory not found: %s", _CONFIG_DIR)
        return archetypes

    for yaml_path in sorted(_CONFIG_DIR.glob("*.yaml")):
        with open(yaml_path) as f:
            raw = yaml.safe_load(f)
        if not raw:
            logger.warning("Empty archetype file: %s", yaml_path.name)
            continue
        config = ArchetypeConfig.model_validate(raw)
        archetypes[config.id] = config

    logger.info("Loaded %d archetype configs", len(archetypes))
    return archetypes


# Loaded at import time — fail fast if YAMLs are broken.
ARCHETYPES: dict[str, ArchetypeConfig] = _load_archetypes()
