"""
Storage client for PrimeData with AWS S3 support.
"""

import json
import os
from typing import Any, Dict, List, Optional

from primedata.utils.logger import get_logger
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

logger = get_logger(__name__)


class StorageClient:
    """S3-only storage client for AWS S3 operations."""

    def __init__(self) -> None:
        """Initialize S3 storage client from environment variables."""
        self.logger = logger
        logger.info("🔧 Initializing S3 storage client")
        self._buckets_ensured = False
        self._init_s3()

    def _init_s3(self) -> None:
        """Initialize AWS S3 client with connection pooling and retry logic."""
        logger.info("📦 Initializing S3 client...")

        # Configuration from environment
        endpoint_url = os.getenv("S3_ENDPOINT_URL")  # For LocalStack (development only)
        region = os.getenv("AWS_REGION", "us-east-2")

        # Connection pooling and retry configuration
        connect_timeout = int(os.getenv("S3_CONNECT_TIMEOUT", "10"))
        read_timeout = int(os.getenv("S3_READ_TIMEOUT", "120"))
        max_retries = int(os.getenv("S3_MAX_RETRIES", "5"))
        max_pool_connections = int(os.getenv("S3_MAX_POOL_CONNECTIONS", "10"))

        logger.debug(f"S3 Config: region={region}, timeout={connect_timeout}s, retries={max_retries}, pool_size={max_pool_connections}")

        if endpoint_url:
            logger.debug(f"S3 LocalStack endpoint: {endpoint_url}")

        config = Config(
            region_name=region,
            retries={'max_attempts': max_retries, 'mode': 'adaptive'},
            connect_timeout=connect_timeout,
            read_timeout=read_timeout,
            max_pool_connections=max_pool_connections
        )

        # Initialize S3 client
        try:
            # Build client kwargs - only include credentials if explicitly set
            # This allows boto3 to use IAM roles when credentials aren't provided
            client_kwargs = {
                'region_name': region,
                'config': config
            }

            if endpoint_url:
                client_kwargs['endpoint_url'] = endpoint_url

            self.s3_client = boto3.client('s3', **client_kwargs)

            if endpoint_url:
                logger.info(f"✅ Initialized S3 client for S3-compatible service at {endpoint_url} (LocalStack)")
            else:
                logger.info(f"✅ Initialized S3 client for AWS S3 in region {region}")
            logger.info("✅ Storage client initialized successfully")
        except Exception as e:
            logger.error(f"❌ Failed to initialize S3 client: {e}", exc_info=True)
            raise ValueError(f"Failed to initialize S3 client: {e}")

    def _ensure_buckets(self) -> None:
        """Ensure storage is accessible.

        Note: Bucket names and paths are configured via environment variables:
        - S3_METADATA_BUCKET: The actual S3 bucket name (e.g., "primedata-dev")
        - S3_METADATA_PATH: The parent folder path in the bucket (e.g., "lly-light-dev/primedata-dev/")

        Subfolders (raw, clean, chunk, embed, exports, config) are created under S3_METADATA_PATH.
        """
        if self._buckets_ensured:
            return

        # Get the configured bucket and path from environment
        storage_bucket = os.getenv("S3_METADATA_BUCKET", "primedata-raw")
        storage_path = os.getenv("S3_METADATA_PATH")

        self.logger.info(f"🔍 Ensuring storage access | bucket={storage_bucket}, path={storage_path}")

        self._buckets_ensured = True

    def ensure_metadata_path_exists(self) -> bool:
        """
        Ensure the S3_METADATA_PATH parent folder exists in the bucket.
        Creates it if it doesn't exist.

        Returns:
            True if folder exists or was created successfully, False otherwise

        S3 "folders" are represented by keys ending with "/" - this creates an empty object
        at that path to represent the folder structure.
        """
        storage_bucket = os.getenv("S3_METADATA_BUCKET", "primedata-raw")
        storage_path = os.getenv("S3_METADATA_PATH")

        logger.info(f"🔍 Checking S3 metadata path | bucket={storage_bucket}, path={storage_path}")

        if not storage_bucket or not storage_path:
            logger.info("⏭️ No S3_METADATA_BUCKET or S3_METADATA_PATH configured, skipping")
            return True

        # S3 folder is represented by a key ending with "/"
        folder_key = storage_path.rstrip("/") + "/"

        try:
            # Check if folder exists by trying to head the folder object
            self.s3_client.head_object(Bucket=storage_bucket, Key=folder_key)
            logger.info(f"✅ S3 metadata path exists | s3://{storage_bucket}/{folder_key}")
            return True
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code == "404":
                # Folder doesn't exist, create it
                try:
                    self.s3_client.put_object(Bucket=storage_bucket, Key=folder_key, Body=b"")
                    logger.info(f"📁 Created S3 metadata path | s3://{storage_bucket}/{folder_key}")
                    return True
                except ClientError as create_error:
                    logger.error(
                        f"❌ Failed to create S3 metadata path | bucket={storage_bucket}, key={folder_key}, error={create_error}",
                        exc_info=True
                    )
                    return False
            else:
                logger.warning(f"⚠️ Could not check S3 metadata path | bucket={storage_bucket}, key={folder_key}, error={error_code}")
                return False
        except Exception as e:
            logger.warning(f"⚠️ Unexpected error checking S3 metadata path | bucket={storage_bucket}, key={folder_key}, error={e}", exc_info=True)
            return False


        """
        Check if a path has the given prefix (directory-aware).
        Avoids false positives like /home/user2 matching /home/user
        """
        try:
            Path(path).relative_to(os.getenv("S3_METADATA_PATH"))
            return True
        except ValueError:
            return False

    def put_bytes(self, bucket: str, key: str, data: bytes, content_type: Optional[str] = None) -> bool:
        """Upload bytes data to S3.

        Args:
            bucket: Bucket name
            key: Object key
            data: Bytes data to upload
            content_type: MIME type (optional)

        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"📤 Entry put_bytes | bucket={bucket}, key={key}, size={len(data)} bytes, content_type={content_type or 'application/octet-stream'}")
            self._ensure_buckets()

            logger.debug(f"  📋 Step 1: Preparing upload parameters")
            final_bucket = os.getenv("S3_METADATA_BUCKET", bucket)
            final_type = content_type or "application/octet-stream"
            logger.debug(f"  ✓ Parameters ready | bucket={final_bucket}, type={final_type}")

            logger.debug(f"  📋 Step 2: Uploading to S3")
            self.s3_client.put_object(
                Bucket=final_bucket,
                Key=key,
                Body=data,
                ContentType=final_type
            )
            logger.info(f"✅ Exit put_bytes | {len(data)} bytes uploaded to {final_bucket}/{key}")
            return True
        except ClientError as e:
            logger.error(f"❌ put_bytes ClientError | bucket={bucket}, key={key}: {e}", exc_info=True)
            return False
        except Exception as e:
            logger.error(f"❌ put_bytes exception | bucket={bucket}, key={key}: {e}", exc_info=True)
            return False

    def put_json(self, bucket: str, key: str, obj: Any) -> bool:
        """Upload JSON object to storage.

        Args:
            bucket: Bucket name
            key: Object key
            obj: Python object to serialize as JSON

        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"📤 Entry put_json | bucket={bucket}, key={key}, object_type={type(obj).__name__}")
            self._ensure_buckets()

            logger.debug(f"  📋 Step 1: Serializing JSON object")
            json_data = json.dumps(obj, indent=2, default=str)
            logger.debug(f"  ✓ Serialized | {len(json_data)} chars, {len(json_data.encode('utf-8'))} bytes")

            logger.debug(f"  📋 Step 2: Uploading JSON to storage")
            result = self.put_bytes(bucket, key, json_data.encode("utf-8"), "application/json")

            if result:
                logger.info(f"✅ Exit put_json | JSON uploaded to {bucket}/{key}")
            else:
                logger.error(f"❌ put_json upload failed | bucket={bucket}, key={key}")
            return result
        except Exception as e:
            logger.error(f"❌ put_json exception | bucket={bucket}, key={key}: {e}", exc_info=True)
            return False

    def list_objects(self, bucket: str, prefix: str = "") -> List[Dict[str, Any]]:
        """List objects in S3 bucket with optional prefix.

        Args:
            bucket: Bucket name
            prefix: Key prefix to filter by

        Returns:
            List of object metadata dictionaries
        """
        try:
            logger.info(f"📋 Entry list_objects | bucket={bucket}, prefix={prefix}")
            self._ensure_buckets()
            objects = []

            logger.debug(f"  📋 Step 1: Listing S3 objects with paginator")
            paginator = self.s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=bucket, Prefix=prefix)

            logger.debug(f"  📋 Step 2: Processing paginated results")
            page_count = 0
            for page in pages:
                if 'Contents' not in page:
                    continue

                page_count += 1
                logger.debug(f"  ✓ Processing page {page_count} | {len(page['Contents'])} objects")

                for obj in page['Contents']:
                    # Get full object metadata including content type
                    try:
                        logger.debug(f"    📥 Retrieving metadata for {obj['Key']}")
                        head_response = self.s3_client.head_object(Bucket=bucket, Key=obj['Key'])
                        content_type = head_response.get('ContentType')
                    except ClientError:
                        content_type = None

                    objects.append(
                        {
                            "name": obj['Key'],
                            "size": obj['Size'],
                            "last_modified": obj['LastModified'].isoformat() if 'LastModified' in obj else None,
                            "etag": obj.get('ETag', '').strip('"'),
                            "content_type": content_type,
                        }
                    )

            logger.info(f"✅ Exit list_objects | Listed {len(objects)} objects from {bucket} in {page_count} pages")
            return objects
        except ClientError as e:
            logger.error(f"❌ list_objects ClientError | bucket={bucket}, prefix={prefix}: {e}", exc_info=True)
            return []
        except Exception as e:
            logger.error(f"❌ list_objects exception | bucket={bucket}, prefix={prefix}: {e}", exc_info=True)
            return []

    def presign(self, bucket: str, key: str, expiry: int = 3600, inline: bool = False) -> Optional[str]:
        """Generate presigned URL for S3 object access.

        Args:
            bucket: Bucket name
            key: Object key
            expiry: URL expiry time in seconds (default: 1 hour)
            inline: If True, add response-content-disposition=inline to make content display in browser instead of downloading (default: False)

        Returns:
            Presigned URL or None if failed
        """
        # Validate inputs - skip special bucket names that don't have files
        if not bucket or bucket.strip() == "" or bucket.lower() in ("none",):
            logger.debug(f"🔗 Entry presign | Skipping special bucket: '{bucket}' (no file)")
            return None

        if not key or key.strip() == "":
            logger.error(f"❌ presign invalid key: '{key}' | Cannot generate presigned URL")
            return None

        try:
            logger.info(f"🔗 Entry presign | bucket={bucket}, key={key}, expiry={expiry}s, inline={inline}")
            self._ensure_buckets()

            logger.debug(f"  📋 Step 1: Preparing presigned URL parameters")
            client_method = 'get_object'
            params = {
                'Bucket': bucket,
                'Key': key
            }

            if inline:
                params['ResponseContentDisposition'] = 'inline'
                logger.debug(f"  ✓ Added inline disposition")

            logger.debug(f"  📋 Step 2: Generating presigned URL from S3")
            url = self.s3_client.generate_presigned_url(
                client_method,
                Params=params,
                ExpiresIn=expiry
            )
            logger.info(f"✅ Exit presign | URL generated for {bucket}/{key} (expires in {expiry}s)")
            return url
        except ClientError as e:
            logger.error(f"❌ presign ClientError | bucket={bucket}, key={key}: {e}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"❌ presign exception | bucket={bucket}, key={key}: {e}", exc_info=True)
            return None

    def get_object(self, bucket: str, key: str) -> Optional[bytes]:
        """Download object as bytes from S3.

        Args:
            bucket: Bucket name
            key: Object key

        Returns:
            Object data as bytes or None if failed
        """
        try:
            logger.info(f"📥 Entry get_object | bucket={bucket}, key={key}")
            self._ensure_buckets()

            logger.debug(f"  📋 Step 1: Retrieving object from S3")
            response = self.s3_client.get_object(Bucket=bucket, Key=key)
            logger.debug(f"  ✓ S3 response received")

            logger.debug(f"  📋 Step 2: Reading object data")
            data = response['Body'].read()
            logger.info(f"✅ Exit get_object | {len(data)} bytes read from {bucket}/{key}")
            return data
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'unknown')
            error_msg = e.response.get('Error', {}).get('Message', 'unknown')
            logger.error(f"❌ get_object ClientError | bucket={bucket}, key={key}, code={error_code}, msg={error_msg}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"❌ get_object exception | bucket={bucket}, key={key}: {type(e).__name__}: {e}", exc_info=True)
            return None

    def put_object(self, bucket: str, key: str, data: bytes, content_type: str = "application/octet-stream") -> bool:
        """Upload object data to S3.

        Args:
            bucket: Bucket name
            key: Object key
            data: Object data as bytes
            content_type: Content type of the object

        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"📤 Entry put_object | bucket={bucket}, key={key}, size={len(data)} bytes, type={content_type}")
            self._ensure_buckets()

            logger.debug(f"  📋 Step 1: Uploading to S3")
            self.s3_client.put_object(
                Bucket=bucket,
                Key=key,
                Body=data,
                ContentType=content_type
            )
            logger.info(f"✅ Exit put_object | {len(data)} bytes uploaded to {bucket}/{key}")
            return True
        except ClientError as e:
            logger.error(f"❌ put_object ClientError | bucket={bucket}, key={key}: {e}", exc_info=True)
            return False
        except Exception as e:
            logger.error(f"❌ put_object exception | bucket={bucket}, key={key}: {e}", exc_info=True)
            return False

    def object_exists(self, bucket: str, key: str) -> bool:
        """Check if object exists in S3.

        Args:
            bucket: Bucket name
            key: Object key

        Returns:
            True if object exists, False otherwise
        """
        try:
            logger.debug(f"🔍 Entry object_exists | bucket={bucket}, key={key}")
            self._ensure_buckets()

            logger.debug(f"  📋 Step 1: Checking S3 object existence")
            try:
                self.s3_client.head_object(Bucket=bucket, Key=key)
                logger.debug(f"  ✅ Object exists in S3: {bucket}/{key}")
                return True
            except ClientError as e:
                if e.response['Error']['Code'] == '404':
                    logger.debug(f"  ❌ Object not found in S3: {bucket}/{key}")
                    return False
                raise
        except ClientError as e:
            logger.warning(f"⚠️ object_exists ClientError | bucket={bucket}, key={key}: {e}")
            return False
        except Exception as e:
            logger.warning(f"⚠️ object_exists exception | bucket={bucket}, key={key}: {e}")
            return False

    def stat_object(self, bucket: str, key: str) -> Optional[Dict[str, Any]]:
        """Get S3 object metadata (size, ETag, etc.) using fallback chain.

        Tries multiple strategies to get file metadata:
        1. HeadObject (fastest, most efficient)
        2. ListObjectsV2 (if s3:ListBucket allowed but HeadObject denied)
        3. GetObject with Range header (if s3:GetObject allowed)
        4. Minimal metadata (graceful degradation)

        Args:
            bucket: Bucket name
            key: Object key

        Returns:
            Dictionary with 'size', 'etag', 'content_type', 'last_modified', or minimal dict if denied
        """
        try:
            logger.debug(f"📋 Entry stat_object | bucket={bucket}, key={key}")
            self._ensure_buckets()

            # Strategy 1: Try HeadObject first (most efficient)
            logger.debug(f"  📋 Strategy 1: Attempting HeadObject")
            try:
                response = self.s3_client.head_object(Bucket=bucket, Key=key)
                stat_info = {
                    "size": response.get('ContentLength', 0),
                    "etag": response.get('ETag', '').strip('"'),
                    "content_type": response.get('ContentType'),
                    "last_modified": response.get('LastModified'),
                }
                logger.debug(f"  ✓ HeadObject succeeded | size={stat_info['size']} bytes")
                return stat_info
            except ClientError as e:
                error_code = e.response.get('Error', {}).get('Code', '')
                if error_code == '404':
                    logger.debug(f"  📋 Object not found (404)")
                    return None
                elif error_code == '403':
                    logger.debug(f"  ⚠️  HeadObject denied (403), trying ListObjectsV2...")
                else:
                    logger.debug(f"  ⚠️  HeadObject failed ({error_code}), trying ListObjectsV2...")

            # Strategy 2: Try ListObjectsV2 (if s3:ListBucket allowed)
            logger.debug(f"  📋 Strategy 2: Attempting ListObjectsV2")
            try:
                # Extract prefix and filename
                parts = key.rsplit('/', 1)
                prefix = parts[0] + '/' if len(parts) > 1 else ''
                filename = parts[-1] if len(parts) > 1 else key

                response = self.s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=100)

                for obj in response.get('Contents', []):
                    if obj['Key'] == key:
                        stat_info = {
                            "size": obj['Size'],
                            "etag": obj['ETag'].strip('"'),
                            "last_modified": obj['LastModified'],
                            "content_type": obj.get('StorageClass', 'application/octet-stream'),
                        }
                        logger.debug(f"  ✓ ListObjectsV2 succeeded | size={stat_info['size']} bytes")
                        return stat_info

                logger.debug(f"  ⚠️  File not found in ListObjectsV2 results, trying GetObject Range...")
            except ClientError as e:
                error_code = e.response.get('Error', {}).get('Code', '')
                logger.debug(f"  ⚠️  ListObjectsV2 failed ({error_code}), trying GetObject Range...")

            # Strategy 3: Try GetObject with Range header (only first byte)
            logger.debug(f"  📋 Strategy 3: Attempting GetObject with Range")
            try:
                response = self.s3_client.get_object(
                    Bucket=bucket,
                    Key=key,
                    Range='bytes=0-0'  # Only first byte
                )
                stat_info = {
                    "size": response['ContentLength'],
                    "etag": response['ETag'].strip('"'),
                    "content_type": response.get('ContentType', 'application/octet-stream'),
                    "last_modified": response.get('LastModified'),
                }
                logger.debug(f"  ✓ GetObject Range succeeded | size={stat_info['size']} bytes")
                return stat_info
            except ClientError as e:
                error_code = e.response.get('Error', {}).get('Code', '')
                if error_code == '404':
                    logger.debug(f"  📋 Object not found (404)")
                    return None
                logger.debug(f"  ⚠️  GetObject Range failed ({error_code}), using minimal metadata...")

            # Strategy 4: Return minimal metadata (graceful degradation)
            logger.warning(
                f"⚠️ Could not retrieve full metadata for {key}. "
                f"Using minimal metadata to allow registration to proceed. "
                f"This is expected if IAM policy denies HeadObject and ListBucket operations."
            )
            return {
                "size": 0,
                "etag": "unknown",
                "content_type": "application/octet-stream",
                "last_modified": None,
            }

        except Exception as e:
            logger.warning(f"⚠️ stat_object exception | bucket={bucket}, key={key}: {e}")
            # Return minimal metadata as final fallback
            return {
                "size": 0,
                "etag": "unknown",
                "content_type": "application/octet-stream",
                "last_modified": None,
            }

    def get_bytes(self, bucket: str, key: str) -> Optional[bytes]:
        """Download object as bytes (alias for get_object for consistency).

        Args:
            bucket: Bucket name
            key: Object key

        Returns:
            Object data as bytes or None if failed
        """
        return self.get_object(bucket, key)

    def get_json(self, bucket: str, key: str) -> Optional[Any]:
        """Download and parse JSON object.

        Args:
            bucket: Bucket name
            key: Object key

        Returns:
            Parsed JSON object (dict/list) or None if failed
        """
        logger.debug(f"📥 Entry get_json | bucket={bucket}, key={key}")
        data = self.get_object(bucket, key)
        if data is None:
            logger.debug(f"  ❌ get_object returned no data")
            return None
        try:
            logger.debug(f"  📋 Step 1: Parsing JSON from {len(data)} bytes")
            result = json.loads(data.decode("utf-8"))
            logger.info(f"✅ Exit get_json | Parsed JSON from {bucket}/{key}")
            return result
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.error(f"❌ get_json parse error | bucket={bucket}, key={key}: {e}", exc_info=True)
            return None

    def copy_object(self, source_bucket: str, source_key: str, dest_bucket: str, dest_key: str) -> bool:
        """Copy an object from source to destination in S3.

        Args:
            source_bucket: Source bucket name
            source_key: Source object key
            dest_bucket: Destination bucket name
            dest_key: Destination object key

        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"📋 Entry copy_object | src={source_bucket}/{source_key}, dest={dest_bucket}/{dest_key}")
            self._ensure_buckets()

            try:
                logger.debug(f"  📋 Step 1: Attempting S3 server-side copy")
                # Get content type from source object
                logger.debug(f"    🔍 Retrieving source metadata")
                stat = self.stat_object(source_bucket, source_key)
                content_type = stat.get('content_type', 'application/octet-stream') if stat else 'application/octet-stream'
                logger.debug(f"    ✓ Content type: {content_type}")

                logger.debug(f"  📋 Step 2: Executing S3 server-side copy")
                # Use S3 copy_object for server-side copy (more efficient)
                self.s3_client.copy_object(
                    Bucket=dest_bucket,
                    Key=dest_key,
                    CopySource={'Bucket': source_bucket, 'Key': source_key},
                    ContentType=content_type
                )
                logger.info(f"✅ Exit copy_object | Server-side copy successful")
                return True
            except ClientError as e:
                logger.warning(f"⚠️ S3 server-side copy failed, attempting read-write fallback: {e}")

                logger.debug(f"  📋 Fallback Step 1: Reading source object")
                # Fallback to read and write
                source_data = self.get_object(source_bucket, source_key)
                if source_data is None:
                    logger.error(f"  ❌ Failed to read source object")
                    return False

                logger.debug(f"  ✓ Read {len(source_data)} bytes from source")
                logger.debug(f"  📋 Fallback Step 2: Writing to destination")
                success = self.put_object(dest_bucket, dest_key, source_data, content_type)
                if success:
                    logger.info(f"✅ Exit copy_object | Read-write fallback successful")
                return success
        except ClientError as e:
            logger.error(f"❌ copy_object ClientError | src={source_bucket}/{source_key}, dest={dest_bucket}/{dest_key}: {e}", exc_info=True)
            return False
        except Exception as e:
            logger.error(f"❌ copy_object exception | src={source_bucket}/{source_key}, dest={dest_bucket}/{dest_key}: {e}", exc_info=True)
            return False


# Global instance
storage_client = StorageClient()
