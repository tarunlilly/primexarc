"""
AWS S3 connector for reading files from S3 buckets.
"""

import time
from typing import Any, Dict, List, Tuple

import boto3
from botocore.exceptions import ClientError

from primedata.utils.log_utils import get_logger
from ..storage.storage_client import storage_client
from ..storage.paths import safe_filename
from .base import BaseConnector

logger = get_logger(__name__)


class S3Connector(BaseConnector):
    """Connector for reading files from AWS S3 buckets."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize S3 connector.

        Expected config:
        {
            'bucket_name': str,        # S3 bucket name (required)
            'region': str,             # AWS region (optional, default: us-east-1)
            'prefix': str,             # Prefix/path within bucket (optional)
            'include': List[str],      # Include patterns (optional)
            'exclude': List[str],      # Exclude patterns (optional)
            'max_file_size': int       # Maximum file size in bytes (default: 100MB)
        }

        Credentials: Uses AWS default credential chain
        - Environment variables: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
        - IAM role (if running on EC2)
        - AWS config files (~/.aws/credentials)
        - No explicit credentials needed in config
        """
        logger.info(f"☁️ Entry __init__ | S3Connector with bucket={config.get('bucket_name', 'unknown')}")
        super().__init__(config)
        self.bucket_name = config.get("bucket_name", "")
        self.region = config.get("region", "us-east-1")
        self.prefix = config.get("prefix", "")
        self.include_patterns = config.get("include", ["*"])
        self.exclude_patterns = config.get("exclude", [])
        self.max_file_size = config.get("max_file_size", 100 * 1024 * 1024)  # 100MB

        logger.debug(f"  📋 Step 1: Initializing S3 client using default credential chain")
        # Initialize S3 client using default credential chain (no explicit credentials needed)
        # boto3 will automatically use:
        # 1. Environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
        # 2. IAM role (if running on EC2)
        # 3. AWS config files (~/.aws/credentials)
        self.s3_client = boto3.client(
            "s3",
            region_name=self.region
        )
        logger.debug(f"  ✓ S3 client initialized with default credentials | region={self.region}, prefix={self.prefix}")
        logger.info(f"✅ Exit __init__ | S3Connector ready")

    def validate_config(self) -> Tuple[bool, str]:
        """Validate S3 connector configuration."""
        logger.debug(f"✓ Entry validate_config | S3Connector")
        if not self.bucket_name:
            logger.error(f"  ❌ Bucket name is required")
            return False, "Bucket name is required"

        logger.debug(f"  ✅ Bucket name present")
        logger.debug(f"  📋 AWS credentials will be obtained from default credential chain")
        logger.debug(f"  ✓ Checking environment: AWS_ACCESS_KEY_ID, IAM role, or ~/.aws/credentials")
        return True, "Configuration is valid (credentials from default chain)"

    def test_connection(self) -> Tuple[bool, str]:
        """Test connection to S3 bucket."""
        logger.info(f"🔗 Entry test_connection | S3 bucket={self.bucket_name}")
        try:
            logger.debug(f"  📋 Step 1: Calling head_bucket")
            # Try to list bucket or head bucket
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            msg = f"Successfully connected to S3 bucket: {self.bucket_name}"
            logger.info(f"✅ Exit test_connection | {msg}")
            return True, msg
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            if error_code == "404":
                msg = f"S3 bucket not found: {self.bucket_name}"
                logger.error(f"❌ test_connection | {msg}")
                return False, msg
            elif error_code == "403":
                msg = f"Access denied to S3 bucket: {self.bucket_name}"
                logger.error(f"❌ test_connection | {msg}")
                return False, msg
            else:
                msg = f"Error connecting to S3: {str(e)}"
                logger.error(f"❌ test_connection ClientError | {msg}")
                return False, msg
        except Exception as e:
            msg = f"Error connecting to S3: {str(e)}"
            logger.error(f"❌ test_connection exception | {msg}", exc_info=True)
            return False, msg

    def sync_full(self, output_bucket: str, output_prefix: str) -> Dict[str, Any]:
        """Sync files from S3 to S3/GCS."""
        logger.info(f"☁️ Entry sync_full | src_bucket={self.bucket_name}, dest_bucket={output_bucket}, prefix={output_prefix}")
        start_time = time.time()
        files_processed = 0
        bytes_transferred = 0
        errors = 0
        details = {"files_processed": [], "files_failed": [], "files_skipped": []}

        try:
            logger.debug(f"  📋 Step 1: Listing objects from S3 source bucket")
            logger.debug(f"    🔍 Source bucket: {self.bucket_name}")
            logger.debug(f"    🔍 Prefix filter: {self.prefix}")
            logger.debug(f"    🔍 Include patterns: {self.include_patterns}")
            logger.debug(f"    🔍 Exclude patterns: {self.exclude_patterns}")

            # List objects in S3 bucket
            paginator = self.s3_client.get_paginator("list_objects_v2")
            logger.debug(f"    📋 Creating paginator for listing...")
            pages = paginator.paginate(Bucket=self.bucket_name, Prefix=self.prefix)
            logger.debug(f"    ✓ Paginator created successfully")

            logger.debug(f"  📋 Step 2: Processing pages")
            page_count = 0
            total_objects_found = 0

            for page in pages:
                if "Contents" not in page:
                    logger.debug(f"    ℹ️ Page {page_count} has no Contents, skipping")
                    continue

                page_count += 1
                objects_in_page = len(page['Contents'])
                total_objects_found += objects_in_page
                logger.debug(f"    ✓ Processing page {page_count} | {objects_in_page} objects found (total so far: {total_objects_found})")

                for idx, obj in enumerate(page["Contents"], 1):
                    try:
                        key = obj["Key"]
                        file_size = obj["Size"]
                        logger.debug(f"      📥 [{page_count}.{idx}] Processing object: {key}")
                        logger.debug(f"          📊 File size: {file_size} bytes")

                        # Skip if too large
                        if file_size > self.max_file_size:
                            logger.debug(f"          ⏭️ Skipping: File too large ({file_size} bytes > {self.max_file_size})")
                            details["files_skipped"].append({"key": key, "reason": f"File too large: {file_size} bytes"})
                            continue

                        # Download from S3
                        logger.debug(f"          📥 Step 2.1: Downloading from source S3 bucket={self.bucket_name}, key={key}")
                        response = self.s3_client.get_object(Bucket=self.bucket_name, Key=key)
                        content = response["Body"].read()
                        logger.debug(f"          ✓ Step 2.1 complete: Downloaded {len(content)} bytes")
                        logger.debug(f"          📊 Content-Type: {response.get('ContentType', 'application/octet-stream')}")

                        # Upload to S3/GCS
                        logger.debug(f"          📤 Step 2.2: Uploading to destination storage")
                        logger.debug(f"              🎯 Destination bucket: {output_bucket}")
                        safe_key = safe_filename(key)
                        storage_key = f"{output_prefix}{safe_key}"
                        logger.debug(f"              🎯 Storage key (destination path): {storage_key}")
                        logger.debug(f"              📊 Data size: {len(content)} bytes")

                        success = storage_client.put_bytes(
                            output_bucket, storage_key, content, response.get("ContentType", "application/octet-stream")
                        )

                        if success:
                            files_processed += 1
                            bytes_transferred += len(content)
                            details["files_processed"].append({"key": key, "storage_key": storage_key, "size": len(content)})
                            logger.debug(f"          ✅ Step 2.2 complete: Successfully uploaded to {output_bucket}/{storage_key}")
                            logger.info(f"          ✅ File processed successfully: {key} → {storage_key} ({len(content)} bytes)")
                        else:
                            errors += 1
                            details["files_failed"].append({"key": key, "error": "Failed to upload to storage"})
                            logger.error(f"          ❌ Step 2.2 failed: Upload returned False for {storage_key}")
                    except Exception as e:
                        errors += 1
                        details["files_failed"].append({"key": obj.get("Key", "unknown"), "error": str(e)})
                        logger.error(f"      ❌ Error processing S3 object: {e}", exc_info=True)
                        logger.error(f"          Object details: {obj}")

            logger.debug(f"  📋 Step 3: Processing complete")
            logger.info(f"  📊 Pagination complete | Total pages: {page_count}, Total objects: {total_objects_found}")
            logger.info(f"  📊 Results: Processed={files_processed}, Skipped={len(details['files_skipped'])}, Failed={errors}")

        except Exception as e:
            logger.error(f"❌ Error during S3 sync: {e}", exc_info=True)
            logger.error(f"  📊 Partial results before error: files_processed={files_processed}, bytes={bytes_transferred}, errors={errors}")
            return {"files": 0, "bytes": 0, "errors": 1, "duration": time.time() - start_time, "details": {"error": str(e)}}

        duration = time.time() - start_time
        logger.info(f"✅ Exit sync_full | {files_processed} files, {bytes_transferred} bytes, {errors} errors in {duration:.2f}s")
        logger.info(f"  📊 Summary:")
        logger.info(f"      ✓ Files successfully synced: {files_processed}")
        logger.info(f"      ⏭️ Files skipped: {len(details['files_skipped'])}")
        logger.info(f"      ❌ Files failed: {errors}")
        logger.info(f"      📦 Total bytes transferred: {bytes_transferred}")
        logger.info(f"      ⏱️ Duration: {duration:.2f}s")
        logger.info(f"      📍 Source: s3://{self.bucket_name}/{self.prefix}")
        logger.info(f"      📍 Destination: s3://{output_bucket}/{output_prefix}")

        return {
            "files": files_processed,
            "bytes": bytes_transferred,
            "errors": errors,
            "duration": duration,
            "details": details,
        }

    def _get_config_schema(self) -> Dict[str, Any]:
        """Get JSON schema for S3 connector configuration."""
        return {
            "type": "object",
            "properties": {
                "bucket_name": {"type": "string", "description": "S3 bucket name"},
                "region": {"type": "string", "default": "us-east-1", "description": "AWS region"},
                "prefix": {"type": "string", "default": "", "description": "Prefix/path within bucket"},
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
            "required": ["bucket_name"],
        }
