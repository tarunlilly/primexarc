"""
S3 JSON storage service for PrimeData.

Handles saving and loading large JSON objects to/from S3 to reduce PostgreSQL storage costs.
Uses hybrid storage pattern: small JSON stays in DB, large JSON moves to S3.
"""

import json
import os
from typing import Any, Optional, Tuple
from uuid import UUID

from primedata.utils.log_utils import get_logger

logger = get_logger(__name__)
from primedata.storage.storage_client import storage_client

# Size threshold for moving JSON to S3 (1MB)
JSON_SIZE_THRESHOLD = 1024 * 1024  # 1MB

# S3 bucket and path for storing JSON metadata (both configurable via environment variables)
METADATA_BUCKET = os.getenv("S3_METADATA_BUCKET", "primedata-exports")
METADATA_PATH = os.getenv("S3_METADATA_PATH", "metadata")  # Parent folder/path within bucket


def _get_json_size(data: Any) -> int:
    """Calculate size of JSON data when serialized.

    Args:
        data: Python object to serialize

    Returns:
        Size in bytes
    """
    logger.debug(f"📋 Calculating JSON size for data")

    try:
        json_str = json.dumps(data, default=str)
        size = len(json_str.encode("utf-8"))
        logger.debug(f"📋 JSON size calculated: {size} bytes")
        return size
    except Exception as e:
        logger.error(f"❌ Failed to calculate JSON size: {e}", exc_info=True)
        return 0


def save_json_to_s3(
    workspace_id: UUID,
    product_id: UUID,
    field_name: str,
    data: Any,
    version: Optional[int] = None,
    subfolder: str = "metadata",
) -> Optional[str]:
    """Save JSON data to S3 and return the S3 path.

    Args:
        workspace_id: Workspace UUID
        product_id: Product UUID
        field_name: Name of the field (e.g., "chunk_metrics", "readiness_fingerprint")
        data: Python object to serialize as JSON
        version: Optional version number (for versioned storage)
        subfolder: Subfolder within the product path (default: "metadata")

    Returns:
        S3 path (key) if successful, None otherwise
    """
    logger.info(f"📦 save_json_to_s3 ENTRY | workspace_id={workspace_id} | product_id={product_id} | field_name={field_name} | version={version} | subfolder={subfolder}")

    try:
        # Build S3 path under parent METADATA_PATH
        # METADATA_PATH/{workspace_id}/prod/{product_id}/v/{version}/{subfolder}/{field_name}.json
        # Or: METADATA_PATH/{workspace_id}/prod/{product_id}/{subfolder}/{field_name}.json
        if version is not None:
            key = f"{METADATA_PATH}/{workspace_id}/prod/{product_id}/v/{version}/{subfolder}/{field_name}.json"
        else:
            key = f"{METADATA_PATH}/{workspace_id}/prod/{product_id}/{subfolder}/{field_name}.json"

        logger.debug(f"📦 Saving JSON to S3 path | bucket={METADATA_BUCKET} | key={key}")

        # Save to S3 using global storage_client
        success = storage_client.put_json(METADATA_BUCKET, key, data)
        if success:
            logger.info(f"✅ save_json_to_s3 | field_name={field_name} | bucket={METADATA_BUCKET} | key={key} | success=True")
            return key
        else:
            logger.error(f"❌ save_json_to_s3 | Failed to save {field_name} to S3 | key={key}")
            return None
    except Exception as e:
        logger.error(f"❌ save_json_to_s3 | field_name={field_name} | Exception: {str(e)}", exc_info=True)
        return None


def load_json_from_s3(s3_path: str) -> Optional[Any]:
    """Load JSON data from S3.

    Args:
        s3_path: S3 path (key) to the JSON object

    Returns:
        Parsed JSON object (dict/list) or None if failed
    """
    logger.info(f"📦 load_json_from_s3 ENTRY | path={s3_path}")

    try:
        logger.debug(f"📦 Loading JSON from S3 | bucket={METADATA_BUCKET} | path={s3_path}")
        data = storage_client.get_json(METADATA_BUCKET, s3_path)
        if data is not None:
            logger.info(f"✅ load_json_from_s3 | path={s3_path} | success=True | data_type={type(data).__name__}")
        else:
            logger.warning(f"📦 load_json_from_s3 | Failed to load JSON from S3 | path={s3_path}")
        return data
    except Exception as e:
        logger.error(f"❌ load_json_from_s3 | path={s3_path} | Exception: {str(e)}", exc_info=True)
        return None


def delete_json_from_s3(s3_path: str) -> bool:
    """Delete JSON data from S3.

    Args:
        s3_path: S3 path (key) to the JSON object

    Returns:
        True if successful, False otherwise
    """
    logger.info(f"📦 delete_json_from_s3 ENTRY | path={s3_path}")

    try:
        # Use S3 client for deletion
        logger.debug(f"📦 Deleting JSON from S3 | bucket={METADATA_BUCKET} | path={s3_path}")
        storage_client.s3_client.delete_object(Bucket=METADATA_BUCKET, Key=s3_path)
        logger.info(f"✅ delete_json_from_s3 | path={s3_path} | success=True")
        return True
    except Exception as e:
        logger.error(f"❌ delete_json_from_s3 | path={s3_path} | Exception: {str(e)}", exc_info=True)
        return False


def should_save_to_s3(data: Any, threshold: int = JSON_SIZE_THRESHOLD) -> bool:
    """Determine if JSON data should be saved to S3 based on size.

    Args:
        data: Python object to check
        threshold: Size threshold in bytes (default: 1MB)

    Returns:
        True if data should be saved to S3, False otherwise
    """
    logger.debug(f"📋 Determining storage destination | threshold={threshold} bytes")

    try:
        size = _get_json_size(data)
        should_save = size >= threshold
        logger.debug(f"📋 Data size evaluation | size={size} bytes | threshold={threshold} bytes | should_save_to_s3={should_save}")
        return should_save
    except Exception as e:
        logger.error(f"❌ should_save_to_s3 | Exception while determining storage: {str(e)}", exc_info=True)
        return False


def save_product_json_field(
    workspace_id: UUID,
    product_id: UUID,
    field_name: str,
    data: Any,
    threshold: int = JSON_SIZE_THRESHOLD,
) -> Tuple[Optional[str], bool]:
    """Save product JSON field, choosing between DB and S3 based on size.

    Args:
        workspace_id: Workspace UUID
        product_id: Product UUID
        field_name: Name of the field
        data: Python object to save
        threshold: Size threshold for S3 storage (default: 1MB)

    Returns:
        Tuple of (s3_path, should_save_to_s3)
        - s3_path: S3 path if saved to S3, None if should stay in DB
        - should_save_to_s3: Whether data should be saved to S3
    """
    logger.info(f"📦 save_product_json_field ENTRY | workspace_id={workspace_id} | product_id={product_id} | field_name={field_name} | threshold={threshold} bytes")

    try:
        logger.debug(f"📋 Evaluating storage destination")
        if should_save_to_s3(data, threshold):
            logger.debug(f"📦 Data exceeds threshold, saving to S3")
            s3_path = save_json_to_s3(workspace_id, product_id, field_name, data)
            logger.info(f"✅ save_product_json_field | field_name={field_name} | destination=S3 | path={s3_path}")
            return (s3_path, True)
        else:
            logger.debug(f"💾 Data within threshold, will save to DB")
            logger.info(f"✅ save_product_json_field | field_name={field_name} | destination=DB")
            return (None, False)
    except Exception as e:
        logger.error(f"❌ save_product_json_field | field_name={field_name} | Exception: {str(e)}", exc_info=True)
        return (None, False)

