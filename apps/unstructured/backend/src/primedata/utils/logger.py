"""
Logger module - alias for log_utils for backwards compatibility.
This allows imports from primedata.utils.logger instead of primedata.utils.log_utils.
"""

from primedata.utils.log_utils import get_logger, configure_logging

# Log module initialization
logger = get_logger(__name__)
logger.debug(f"📋 Logger module initialized - alias imports ready (get_logger, configure_logging)")

__all__ = ['get_logger', 'configure_logging']
