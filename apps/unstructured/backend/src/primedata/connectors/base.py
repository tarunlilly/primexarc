"""
Base connector class for data source integrations.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Tuple

from primedata.utils.log_utils import get_logger

logger = get_logger(__name__)


class BaseConnector(ABC):
    """Abstract base class for all data source connectors."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize connector with configuration.

        Args:
            config: Connector-specific configuration dictionary
        """
        logger.info(f"🔗 Entry __init__ | connector={self.__class__.__name__}, config_keys={list(config.keys())}")
        self.config = config
        logger.debug(f"  ✓ Configuration stored | keys={list(config.keys())}")
        logger.info(f"✅ Exit __init__ | {self.__class__.__name__} initialized")

    @abstractmethod
    def test_connection(self) -> Tuple[bool, str]:
        """Test connection to the data source.

        Returns:
            Tuple of (success: bool, message: str)
        """
        pass

    @abstractmethod
    def sync_full(self, output_bucket: str, output_prefix: str) -> Dict[str, Any]:
        """Perform full synchronization of data source.

        Args:
            output_bucket: S3/GCS bucket to store data
            output_prefix: Prefix path within bucket

        Returns:
            Dictionary with sync results:
            {
                'files': int,      # Number of files processed
                'bytes': int,      # Total bytes transferred
                'errors': int,     # Number of errors encountered
                'duration': float, # Sync duration in seconds
                'details': dict    # Connector-specific details
            }
        """
        pass

    def sync_incremental(self, cursor: Optional[str], output_bucket: str, output_prefix: str) -> Dict[str, Any]:
        """Perform incremental synchronization of data source.

        Args:
            cursor: Cursor from previous sync (optional)
            output_bucket: S3/GCS bucket to store data
            output_prefix: Prefix path within bucket

        Returns:
            Dictionary with sync results (same format as sync_full)
        """
        logger.info(f"🔄 Entry sync_incremental | cursor={cursor}, output_bucket={output_bucket}, output_prefix={output_prefix}")
        logger.debug(f"  📋 Incremental sync not implemented, falling back to full sync")
        # Default implementation falls back to full sync
        # Subclasses can override for true incremental behavior
        result = self.sync_full(output_bucket, output_prefix)
        logger.info(f"✅ Exit sync_incremental | Fell back to full sync")
        return result

    def validate_config(self) -> Tuple[bool, str]:
        """Validate connector configuration.

        Returns:
            Tuple of (valid: bool, error_message: str)
        """
        logger.debug(f"✓ Entry validate_config | Using default implementation")
        return True, "Configuration is valid"

    def get_connector_info(self) -> Dict[str, Any]:
        """Get connector metadata and capabilities.

        Returns:
            Dictionary with connector information
        """
        logger.debug(f"📊 Entry get_connector_info | connector={self.__class__.__name__}")
        info = {
            "name": self.__class__.__name__,
            "supports_incremental": hasattr(self, "sync_incremental")
            and self.sync_incremental != BaseConnector.sync_incremental,
            "config_schema": self._get_config_schema(),
        }
        logger.debug(f"  ✓ Connector info | incremental={info['supports_incremental']}")
        logger.debug(f"✅ Exit get_connector_info")
        return info

    def _get_config_schema(self) -> Dict[str, Any]:
        """Get JSON schema for connector configuration.

        Returns:
            JSON schema dictionary
        """
        logger.debug(f"📋 Entry _get_config_schema | Using default schema")
        schema = {"type": "object", "properties": {}, "required": []}
        logger.debug(f"  ✓ Default schema: {schema}")
        return schema
