"""
Structured logging for AIRD pipeline stages.

Provides logging utilities that integrate with PrimeData's loguru-based logging.
"""

from typing import Any, Dict, Optional
from uuid import UUID

import logging
logger = logging.getLogger(__name__)


def get_aird_logger(
    stage_name: str,
    product_id: UUID,
    version: int,
    workspace_id: Optional[UUID] = None,
) -> Any:
    """Get a logger instance with AIRD stage context.

    Args:
        stage_name: Name of the pipeline stage
        product_id: Product UUID
        version: Product version number
        workspace_id: Optional workspace UUID

    Returns:
        Logger instance (standard Python logger - context info should be logged explicitly)
    """
    logger.info(f"🎯 get_aird_logger() entry | stage_name={stage_name}, product_id={product_id}, version={version}, workspace_id={workspace_id}")

    # Return the standard logger - context can be included in log messages
    return logger


def setup_aird_logging():
    """Setup AIRD-specific logging configuration.

    This is called automatically when the module is imported.
    Additional AIRD-specific log handlers can be added here if needed.
    """
    logger.info("🎯 setup_aird_logging() entry")
    # Loguru is already configured in primedata.logging_conf
    # This function can be extended if AIRD stages need special logging
    logger.info("✅ AIRD logging setup complete")
    pass


# Setup logging when module is imported
setup_aird_logging()
