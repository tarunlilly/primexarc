"""
AIRD configuration management for PrimeData.

Handles AIRD-specific configuration settings and playbook management.
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from primedata.core.settings import get_settings
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class AirdConfig(BaseModel):
    """AIRD pipeline configuration."""

    # Playbook settings
    default_playbook: str = Field(default="TECH", description="Default playbook ID")
    playbook_dir: Optional[str] = Field(default=None, description="Playbook directory path")

    # Storage settings
    raw_bucket: str = Field(default="primedata-raw", description="S3/GCS bucket for raw data")
    processed_bucket: str = Field(default="primedata-clean", description="S3/GCS bucket for processed data")
    artifacts_bucket: str = Field(default="primedata-exports", description="S3/GCS bucket for artifacts")

    # Scoring settings
    scoring_weights_path: Optional[str] = Field(default=None, description="Path to scoring weights JSON")
    default_scoring_threshold: float = Field(default=70.0, description="Default AI Trust Score threshold")

    # Policy settings
    policy_min_trust_score: float = Field(default=50.0, description="Minimum trust score for policy")
    policy_min_secure: float = Field(default=90.0, description="Minimum secure score for policy")
    policy_min_metadata_presence: float = Field(default=80.0, description="Minimum metadata presence for policy")
    policy_min_kb_ready: float = Field(default=50.0, description="Minimum KB readiness for policy")

    # Processing settings
    enable_deduplication: bool = Field(default=False, description="Enable MinHash deduplication")
    enable_validation: bool = Field(default=True, description="Enable validation summary generation")
    enable_pdf_reports: bool = Field(default=True, description="Enable PDF report generation")

    class Config:
        env_prefix = "AIRD_"
        case_sensitive = False


_aird_config: Optional[AirdConfig] = None


def get_aird_config() -> AirdConfig:
    """Get AIRD configuration (singleton pattern).

    Returns:
        AirdConfig instance with settings from environment and defaults
    """
    logger.info("🎯 get_aird_config() entry")
    global _aird_config
    if _aird_config is None:
        logger.info("📋 Initializing AIRD configuration (first call)")
        settings = get_settings()

        # Determine playbook directory
        playbook_dir = os.getenv("AIRD_PLAYBOOK_DIR")
        if not playbook_dir:
            # Default to the playbooks directory in the same package
            # __file__ is at: backend/src/primedata/ingestion_pipeline/aird_stages/config.py
            # playbooks are at: backend/src/primedata/ingestion_pipeline/aird_stages/playbooks/
            default_path = Path(__file__).parent / "playbooks"
            logger.debug(f"📋 Checking default playbook path: {default_path}")
            if default_path.exists():
                playbook_dir = str(default_path)
                logger.info(f"✅ Using default playbook directory: {playbook_dir}")
            else:
                # Fallback to backend/config/playbooks if it exists
                fallback_path = Path(__file__).parent.parent.parent.parent / "config" / "playbooks"
                logger.debug(f"📋 Checking fallback playbook path: {fallback_path}")
                if fallback_path.exists():
                    playbook_dir = str(fallback_path)
                    logger.info(f"✅ Using fallback playbook directory: {playbook_dir}")
                else:
                    logger.warning(f"⚠️ No playbook directory found at {default_path} or {fallback_path}")
                    playbook_dir = None

        # Determine scoring weights path
        scoring_weights_path = os.getenv("AIRD_SCORING_WEIGHTS_PATH")
        if not scoring_weights_path:
            # Try multiple possible locations for the config file
            possible_paths = [
                Path(__file__).parent.parent.parent.parent.parent / "config" / "scoring_weights.json",  # /app/config/ (Docker)
                Path(__file__).parent.parent.parent.parent / "config" / "scoring_weights.json",        # /app/src/config/ (alternate)
            ]

            for default_path in possible_paths:
                logger.debug(f"📋 Checking scoring weights path: {default_path}")
                if default_path.exists():
                    scoring_weights_path = str(default_path)
                    logger.info(f"✅ Using scoring weights file: {scoring_weights_path}")
                    break

            if not scoring_weights_path:
                logger.warning(f"⚠️ Scoring weights file not found at any of: {[str(p) for p in possible_paths]}")
                scoring_weights_path = None

        _aird_config = AirdConfig(
            playbook_dir=playbook_dir,
            scoring_weights_path=scoring_weights_path,
        )
        logger.info(f"✅ AIRD configuration initialized | playbook_dir={playbook_dir}, scoring_weights_path={scoring_weights_path}")

    return _aird_config


def get_playbook_path(playbook_id: str) -> Optional[Path]:
    """Get path to playbook YAML file.

    Args:
        playbook_id: Playbook identifier (e.g., "TECH", "SCANNED", "REGULATORY")

    Returns:
        Path to playbook YAML file, or None if not found
    """
    logger.info(f"🎯 get_playbook_path() entry | playbook_id={playbook_id}")
    config = get_aird_config()
    if not config.playbook_dir:
        logger.warning(f"⚠️ No playbook directory configured")
        return None

    playbook_dir = Path(config.playbook_dir)
    playbook_file = playbook_dir / f"{playbook_id}.yaml"
    logger.debug(f"📋 Checking playbook file: {playbook_file}")

    if playbook_file.exists():
        logger.info(f"✅ Found playbook: {playbook_file}")
        return playbook_file

    # Try case-insensitive search
    logger.debug(f"📋 Attempting case-insensitive search in {playbook_dir}")
    for yaml_file in playbook_dir.glob("*.yaml"):
        if yaml_file.stem.upper() == playbook_id.upper():
            logger.info(f"✅ Found playbook (case-insensitive): {yaml_file}")
            return yaml_file

    logger.warning(f"❌ Playbook not found: {playbook_id}")
    return None
