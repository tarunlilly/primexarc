"""
Playbook YAML loader for AIRD preprocessing.

Loads and parses playbook YAML files from configured directory.
"""

from pathlib import Path
from typing import Dict, Optional

import yaml
import logging
logger = logging.getLogger(__name__)
from primedata.ingestion_pipeline.aird_stages.config import get_aird_config, get_playbook_path


def get_playbook_dir() -> Optional[Path]:
    """Get the playbook directory path.

    Returns:
        Path to playbook directory, or None if not configured
    """
    logger.debug("📚 get_playbook_dir() ENTRY")
    config = get_aird_config()
    if not config.playbook_dir:
        logger.warning("⚠️ playbook_dir not configured")
        return None
    logger.debug(f"✓ playbook_dir={config.playbook_dir}")
    return Path(config.playbook_dir)


def load_playbook_yaml(playbook_id: Optional[str], workspace_id: Optional[str] = None, db_session=None) -> Dict:
    """
    Load and parse a playbook YAML by ID (case-insensitive).
    Supports both built-in playbooks (from files) and custom playbooks (from database).

    Args:
        playbook_id: e.g., 'TECH', 'tech', 'ScAnNeD'; None allowed (uses default)
        workspace_id: Optional workspace ID for loading custom playbooks
        db_session: Optional database session for loading custom playbooks

    Returns:
        dict from YAML content

    Raises:
        FileNotFoundError: if playbook cannot be found
    """
    logger.info(f"📚 load_playbook_yaml() ENTRY: playbook_id={playbook_id}, workspace_id={workspace_id}")

    # Try to load custom playbook from database if workspace_id and db_session provided
    if workspace_id and db_session and playbook_id:
        logger.debug(f"📋 Attempting to load custom playbook: {playbook_id}")
        try:
            from uuid import UUID

            from primedata.db.models import CustomPlaybook

            custom_playbook = (
                db_session.query(CustomPlaybook)
                .filter(
                    CustomPlaybook.playbook_id == playbook_id.upper(),
                    CustomPlaybook.workspace_id == UUID(workspace_id),
                    CustomPlaybook.is_active == True,
                )
                .first()
            )

            if custom_playbook:
                try:
                    logger.debug(f"✓ Found custom playbook in database")
                    result = yaml.safe_load(custom_playbook.yaml_content)
                    logger.info(f"✅ Loaded custom playbook: {playbook_id}")
                    return result
                except yaml.YAMLError as e:
                    logger.error(f"❌ Failed to parse custom playbook YAML for {playbook_id}: {e}", exc_info=True)
                    # Fall through to try built-in playbook
        except Exception as e:
            logger.warning(f"⚠️ Failed to load custom playbook {playbook_id}: {e}")
            # Fall through to try built-in playbook

    # Try built-in playbooks (from files)
    logger.debug(f"📋 Looking for built-in playbook file")
    playbook_file = get_playbook_path(playbook_id)
    if not playbook_file:
        # Fallback: try to use default from config
        logger.debug(f"📋 Playbook file not found, trying default from config")
        config = get_aird_config()
        if config.default_playbook:
            playbook_file = get_playbook_path(config.default_playbook)

        if not playbook_file:
            error_msg = f"Playbook '{playbook_id}' not found and no default available"
            logger.error(f"❌ {error_msg}")
            raise FileNotFoundError(error_msg)

    try:
        logger.debug(f"📋 Loading playbook from file: {playbook_file}")
        with open(playbook_file, "r", encoding="utf-8") as f:
            result = yaml.safe_load(f)
        logger.info(f"✅ Loaded built-in playbook: {playbook_id}")
        return result
    except Exception as e:
        logger.error(f"❌ Failed to load playbook from {playbook_file}: {e}", exc_info=True)
        raise
