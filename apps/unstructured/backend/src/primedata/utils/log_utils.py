"""Logging utility for consistent logger configuration."""

import logging
import os


def get_logger(name: str = None) -> logging.Logger:
    """
    Get a configured logger instance.

    Args:
        name: Logger name (typically __name__). If None, uses root logger.

    Returns:
        Configured logger instance.
    """
    if name is None:
        logger = logging.getLogger()
        logger.debug(f"📋 get_logger() - returning root logger")
    else:
        logger = logging.getLogger(name)
        logger.debug(f"📋 get_logger(name={name}) - logger instance created")
    return logger


def configure_logging(level: int = None) -> None:
    """
    Configure root logger with standard format.

    Args:
        level: Logging level (default: DEBUG from LOG_LEVEL env var, or INFO if not set).
               Can be overridden by LOG_LEVEL environment variable.
    """
    if level is None:
        # Check LOG_LEVEL environment variable, default to DEBUG for pod logs
        log_level_str = os.getenv("LOG_LEVEL", "DEBUG").upper()
        level = getattr(logging, log_level_str, logging.DEBUG)
    else:
        log_level_str = logging.getLevelName(level)

    # Try basicConfig first (works if no handlers are configured)
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Force set level on root logger and all existing handlers (needed for Airflow which pre-configures handlers)
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    for handler in root_logger.handlers:
        handler.setLevel(level)

    root_logger.info(f"📋 configure_logging() - logging configured: level={logging.getLevelName(level)} (LOG_LEVEL={log_level_str})")

