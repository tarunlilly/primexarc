"""
Logging configuration for PrimeData using Python's built-in logging module.
"""

import sys
import logging
import os
from logging.handlers import RotatingFileHandler


def setup_logging() -> None:
    """Setup structured logging with Python's built-in logging module.

    Configures root logger with console output (DEBUG), rotating file handler
    for all logs (logs/app.log), and a separate rotating file handler for errors
    only (logs/error.log). Suppresses verbose third-party library loggers.
    """
    print("📋 setup_logging | initializing logging configuration")

    try:
        # Create logs directory if it doesn't exist
        print("📋 setup_logging checkpoint: creating logs directory")
        os.makedirs("logs", exist_ok=True)

        # Get root logger
        print("📋 setup_logging checkpoint: configuring root logger")
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)

        # Define log format with more detailed information
        log_format = "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s"
        date_format = "%Y-%m-%d %H:%M:%S.%f"[:-3]  # Include milliseconds

        # Console handler (DEBUG level - show all logs including debug)
        print("📋 setup_logging checkpoint: configuring console handler")
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)
        console_formatter = logging.Formatter(log_format, datefmt=date_format)
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)

        # File handler for all logs (DEBUG level)
        print("📋 setup_logging checkpoint: configuring app.log file handler")
        try:
            app_log_handler = RotatingFileHandler(
                "logs/app.log",
                maxBytes=10 * 1024 * 1024,  # 10MB
                backupCount=7  # Keep 7 backup files
            )
            app_log_handler.setLevel(logging.DEBUG)
            app_log_formatter = logging.Formatter(log_format, datefmt=date_format)
            app_log_handler.setFormatter(app_log_formatter)
            root_logger.addHandler(app_log_handler)
            print("✅ setup_logging | app.log handler configured")
        except Exception as e:
            print(f"❌ setup_logging warning: could not setup app.log handler: {e}")

        # File handler for errors only (ERROR level)
        print("📋 setup_logging checkpoint: configuring error.log file handler")
        try:
            error_log_handler = RotatingFileHandler(
                "logs/error.log",
                maxBytes=10 * 1024 * 1024,  # 10MB
                backupCount=30  # Keep 30 backup files
            )
            error_log_handler.setLevel(logging.ERROR)
            error_log_formatter = logging.Formatter(log_format, datefmt=date_format)
            error_log_handler.setFormatter(error_log_formatter)
            root_logger.addHandler(error_log_handler)
            print("✅ setup_logging | error.log handler configured")
        except Exception as e:
            print(f"❌ setup_logging warning: could not setup error.log handler: {e}")

        # Suppress verbose libraries
        print("📋 setup_logging checkpoint: suppressing verbose library logs")
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("botocore").setLevel(logging.WARNING)
        logging.getLogger("googleapiclient").setLevel(logging.WARNING)
        logging.getLogger("sqlalchemy").setLevel(logging.WARNING)

        print("✅ setup_logging complete | logging system initialized")
    except Exception as e:
        print(f"❌ setup_logging error: {type(e).__name__}: {e}")
        raise


# Setup logging when module is imported
setup_logging()
