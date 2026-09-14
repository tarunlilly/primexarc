# Make log_utils available as logger module for backwards compatibility
import logging
from primedata.utils.log_utils import get_logger, configure_logging

logger = logging.getLogger(__name__)
logger.info("📋 utils module | initializing")
logger.debug("📋 utils.__init__ checkpoint: importing log_utils")

__all__ = ['get_logger', 'configure_logging']

logger.info("✅ utils module | initialization complete")
