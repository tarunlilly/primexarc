"""
Azure Blob Storage connector for reading files from Azure containers.
"""

import time
from typing import Any, Dict, List, Tuple

from azure.core.exceptions import AzureError
from azure.storage.blob import BlobServiceClient

from primedata.utils.logger import get_logger
from ..storage.storage_client import storage_client
from ..storage.paths import safe_filename
from .base import BaseConnector

logger = get_logger(__name__)


class AzureBlobConnector(BaseConnector):
    """Connector for reading files from Azure Blob Storage."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize Azure Blob connector.

        Expected config:
        {
            'storage_account_name': str,  # Azure storage account name
            'container_name': str,          # Container name
            'account_key': str,             # Storage account key (or use connection_string)
            'connection_string': str,        # Full connection string (alternative to account_key)
            'prefix': str,                  # Prefix/path within container (optional)
            'include': List[str],           # Include patterns (optional)
            'exclude': List[str],           # Exclude patterns (optional)
            'max_file_size': int            # Maximum file size in bytes (default: 100MB)
        }
        """
        logger.info(f"☁️ Entry __init__ | AzureBlobConnector with container={config.get('container_name', 'unknown')}")
        super().__init__(config)
        self.storage_account_name = config.get("storage_account_name", "")
        self.container_name = config.get("container_name", "")
        self.account_key = config.get("account_key", "")
        self.connection_string = config.get("connection_string", "")
        self.prefix = config.get("prefix", "")
        self.include_patterns = config.get("include", ["*"])
        self.exclude_patterns = config.get("exclude", [])
        self.max_file_size = config.get("max_file_size", 100 * 1024 * 1024)  # 100MB

        logger.debug(f"  📋 Step 1: Initializing Azure Blob client")
        # Initialize Azure Blob client
        if self.connection_string:
            logger.debug(f"    Using connection string")
            self.blob_service_client = BlobServiceClient.from_connection_string(self.connection_string)
        elif self.storage_account_name and self.account_key:
            logger.debug(f"    Using account name + key | account={self.storage_account_name}")
            account_url = f"https://{self.storage_account_name}.blob.core.windows.net"
            self.blob_service_client = BlobServiceClient(account_url, credential=self.account_key)
        else:
            logger.error(f"  ❌ No authentication method provided")
            raise ValueError("Either connection_string or (storage_account_name + account_key) must be provided")

        logger.debug(f"  ✓ Azure Blob client initialized | container={self.container_name}, prefix={self.prefix}")
        logger.info(f"✅ Exit __init__ | AzureBlobConnector ready")

    def validate_config(self) -> Tuple[bool, str]:
        """Validate Azure Blob connector configuration."""
        logger.debug(f"✓ Entry validate_config | AzureBlobConnector")
        if not self.container_name:
            logger.error(f"  ❌ Container name is required")
            return False, "Container name is required"
        if not self.connection_string and (not self.storage_account_name or not self.account_key):
            logger.error(f"  ❌ Authentication required")
            return False, "Either connection_string or (storage_account_name + account_key) is required"
        logger.debug(f"  ✅ Configuration valid")
        return True, "Configuration is valid"

    def test_connection(self) -> Tuple[bool, str]:
        """Test connection to Azure Blob container."""
        logger.info(f"🔗 Entry test_connection | Azure container={self.container_name}")
        try:
            logger.debug(f"  📋 Step 1: Getting container client")
            container_client = self.blob_service_client.get_container_client(self.container_name)
            logger.debug(f"  📋 Step 2: Retrieving container properties")
            container_client.get_container_properties()
            msg = f"Successfully connected to Azure container: {self.container_name}"
            logger.info(f"✅ Exit test_connection | {msg}")
            return True, msg
        except AzureError as e:
            msg = f"Error connecting to Azure Blob: {str(e)}"
            logger.error(f"❌ test_connection AzureError | {msg}")
            return False, msg
        except Exception as e:
            msg = f"Error connecting to Azure Blob: {str(e)}"
            logger.error(f"❌ test_connection exception | {msg}", exc_info=True)
            return False, msg

    def sync_full(self, output_bucket: str, output_prefix: str) -> Dict[str, Any]:
        """Sync files from Azure Blob to S3/GCS."""
        logger.info(f"☁️ Entry sync_full | src_container={self.container_name}, dest_bucket={output_bucket}, prefix={output_prefix}")
        start_time = time.time()
        files_processed = 0
        bytes_transferred = 0
        errors = 0
        details = {"files_processed": [], "files_failed": [], "files_skipped": []}

        try:
            logger.debug(f"  📋 Step 1: Getting container client")
            container_client = self.blob_service_client.get_container_client(self.container_name)

            logger.debug(f"  📋 Step 2: Listing blobs")
            # List blobs
            blobs = container_client.list_blobs(name_starts_with=self.prefix)

            logger.debug(f"  📋 Step 3: Processing blobs")
            for blob in blobs:
                try:
                    logger.debug(f"    📥 Processing blob: {blob.name} ({blob.size} bytes)")

                    if blob.size > self.max_file_size:
                        logger.debug(f"      ⏭️ Skipping: File too large ({blob.size} bytes > {self.max_file_size})")
                        details["files_skipped"].append({"name": blob.name, "reason": f"File too large: {blob.size} bytes"})
                        continue

                    logger.debug(f"      📥 Downloading blob")
                    # Download blob
                    blob_client = container_client.get_blob_client(blob.name)
                    content = blob_client.download_blob().readall()

                    logger.debug(f"      📤 Uploading to destination storage")
                    # Upload to S3/GCS
                    safe_key = safe_filename(blob.name)
                    storage_key = f"{output_prefix}{safe_key}"

                    content_type = blob.content_settings.content_type or "application/octet-stream"
                    success = storage_client.put_bytes(output_bucket, storage_key, content, content_type)

                    if success:
                        files_processed += 1
                        bytes_transferred += len(content)
                        details["files_processed"].append({"name": blob.name, "storage_key": storage_key, "size": len(content)})
                        logger.debug(f"      ✅ Successfully processed {blob.name} ({len(content)} bytes)")
                    else:
                        errors += 1
                        details["files_failed"].append({"name": blob.name, "error": "Failed to upload to storage"})
                        logger.error(f"      ❌ Failed to upload {blob.name} to storage")
                except Exception as e:
                    errors += 1
                    details["files_failed"].append({"name": blob.name, "error": str(e)})
                    logger.error(f"    ❌ Error processing Azure blob: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"❌ Error during Azure Blob sync: {e}", exc_info=True)
            return {"files": 0, "bytes": 0, "errors": 1, "duration": time.time() - start_time, "details": {"error": str(e)}}

        duration = time.time() - start_time
        logger.info(f"✅ Exit sync_full | {files_processed} files, {bytes_transferred} bytes, {errors} errors in {duration:.2f}s")
        return {
            "files": files_processed,
            "bytes": bytes_transferred,
            "errors": errors,
            "duration": duration,
            "details": details,
        }

    def _get_config_schema(self) -> Dict[str, Any]:
        """Get JSON schema for Azure Blob connector configuration."""
        return {
            "type": "object",
            "properties": {
                "storage_account_name": {"type": "string", "description": "Azure storage account name"},
                "container_name": {"type": "string", "description": "Container name"},
                "account_key": {"type": "string", "description": "Storage account key"},
                "connection_string": {"type": "string", "description": "Full connection string"},
                "prefix": {"type": "string", "default": "", "description": "Prefix/path within container"},
                "include": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": ["*"],
                    "description": "Include file patterns",
                },
                "exclude": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": [],
                    "description": "Exclude file patterns",
                },
                "max_file_size": {
                    "type": "integer",
                    "minimum": 1024,
                    "default": 104857600,
                    "description": "Maximum file size in bytes (default: 100MB)",
                },
            },
            "required": ["container_name"],
        }
