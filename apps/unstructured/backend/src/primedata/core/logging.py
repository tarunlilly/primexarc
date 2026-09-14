"""Centralized logging configuration for PrimeData."""

import logging
from typing import Optional

# Configure logging once at module load time
_configured = False
logger = logging.getLogger(__name__)


def configure_logging(level: str = "INFO") -> None:
    """Configure logging for the entire application.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    global _configured

    if _configured:
        logger.debug("📋 Logging already configured, skipping")
        return

    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger.info(f"✅ Logging configured with level: {level}")
    _configured = True


def get_logger(name: str, level: Optional[str] = None) -> logging.Logger:
    """Get a logger instance for the given module.

    Replaces: logging.getLogger(__name__)

    Args:
        name: Logger name (typically __name__)
        level: Optional logging level override

    Returns:
        Configured logger instance

    Usage:
        from primedata.core.logging import get_logger
        logger = get_logger(__name__)

        # Instead of:
        # import logging
        # logger = logging.getLogger(__name__)
    """
    logger = logging.getLogger(name)
    logger.debug(f"📋 Getting logger for module: {name}")

    if level:
        logger.setLevel(getattr(logging, level))
        logger.debug(f"✓ Set logger level to: {level}")

    return logger
