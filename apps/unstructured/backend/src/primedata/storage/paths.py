"""
Path helper functions for organizing data in S3/GCS storage.
"""

import os
import uuid
from typing import Union

from primedata.utils.logger import get_logger

logger = get_logger(__name__)


def _get_base_prefix() -> str:
    """Get the base prefix from S3_METADATA_PATH environment variable.

    Returns:
        Base prefix (e.g., "lly-light-dev/primedata-dev/") or empty string
    """
    base = os.getenv("S3_METADATA_PATH", "")
    if base and not base.endswith("/"):
        base = base + "/"
    return base


def raw_prefix(workspace_id: Union[str, uuid.UUID], product_id: Union[str, uuid.UUID], version: int) -> str:
    """Generate prefix for raw data storage.

    Args:
        workspace_id: Workspace identifier
        product_id: Product identifier
        version: Version number

    Returns:
        Storage prefix string like "{S3_METADATA_PATH}/ws/{ws}/prod/{prod}/v/{version}/raw/"
    """
    logger.debug(f"📋 Entry raw_prefix | ws={workspace_id}, prod={product_id}, v={version}")
    base = _get_base_prefix()
    prefix = f"{base}ws/{workspace_id}/prod/{product_id}/v/{version}/raw/"
    logger.debug(f"  ✓ Generated prefix: {prefix}")
    return prefix


def clean_prefix(workspace_id: Union[str, uuid.UUID], product_id: Union[str, uuid.UUID], version: int) -> str:
    """Generate prefix for cleaned data storage.

    Args:
        workspace_id: Workspace identifier
        product_id: Product identifier
        version: Version number

    Returns:
        Storage prefix string like "{S3_METADATA_PATH}/ws/{ws}/prod/{prod}/v/{version}/clean/"
    """
    logger.debug(f"📋 Entry clean_prefix | ws={workspace_id}, prod={product_id}, v={version}")
    base = _get_base_prefix()
    prefix = f"{base}ws/{workspace_id}/prod/{product_id}/v/{version}/clean/"
    logger.debug(f"  ✓ Generated prefix: {prefix}")
    return prefix


def chunk_prefix(workspace_id: Union[str, uuid.UUID], product_id: Union[str, uuid.UUID], version: int) -> str:
    """Generate prefix for chunked data storage.

    Args:
        workspace_id: Workspace identifier
        product_id: Product identifier
        version: Version number

    Returns:
        Storage prefix string like "{S3_METADATA_PATH}/ws/{ws}/prod/{prod}/v/{version}/chunk/"
    """
    logger.debug(f"📋 Entry chunk_prefix | ws={workspace_id}, prod={product_id}, v={version}")
    base = _get_base_prefix()
    prefix = f"{base}ws/{workspace_id}/prod/{product_id}/v/{version}/chunk/"
    logger.debug(f"  ✓ Generated prefix: {prefix}")
    return prefix


def embed_prefix(workspace_id: Union[str, uuid.UUID], product_id: Union[str, uuid.UUID], version: int) -> str:
    """Generate prefix for embedded data storage.

    Args:
        workspace_id: Workspace identifier
        product_id: Product identifier
        version: Version number

    Returns:
        Storage prefix string like "{S3_METADATA_PATH}/ws/{ws}/prod/{prod}/v/{version}/embed/"
    """
    logger.debug(f"📋 Entry embed_prefix | ws={workspace_id}, prod={product_id}, v={version}")
    base = _get_base_prefix()
    prefix = f"{base}ws/{workspace_id}/prod/{product_id}/v/{version}/embed/"
    logger.debug(f"  ✓ Generated prefix: {prefix}")
    return prefix


def export_prefix(workspace_id: Union[str, uuid.UUID], product_id: Union[str, uuid.UUID], version: int) -> str:
    """Generate prefix for exported data storage.

    Args:
        workspace_id: Workspace identifier
        product_id: Product identifier
        version: Version number

    Returns:
        Storage prefix string like "{S3_METADATA_PATH}/ws/{ws}/prod/{prod}/v/{version}/export/"
    """
    logger.debug(f"📋 Entry export_prefix | ws={workspace_id}, prod={product_id}, v={version}")
    base = _get_base_prefix()
    prefix = f"{base}ws/{workspace_id}/prod/{product_id}/v/{version}/export/"
    logger.debug(f"  ✓ Generated prefix: {prefix}")
    return prefix


def artifacts_prefix(workspace_id: Union[str, uuid.UUID], product_id: Union[str, uuid.UUID], version: int) -> str:
    """Generate prefix for pipeline artifact files.

    Args:
        workspace_id: Workspace identifier
        product_id: Product identifier
        version: Version number

    Returns:
        Storage prefix string like "{S3_METADATA_PATH}/ws/{ws}/prod/{prod}/v/{version}/artifacts/"
    """
    logger.debug(f"📋 Entry artifacts_prefix | ws={workspace_id}, prod={product_id}, v={version}")
    base = _get_base_prefix()
    prefix = f"{base}ws/{workspace_id}/prod/{product_id}/v/{version}/artifacts/"
    logger.debug(f"  ✓ Generated prefix: {prefix}")
    return prefix


def dq_rules_key(workspace_id: Union[str, uuid.UUID], product_id: Union[str, uuid.UUID]) -> str:
    """Generate full S3 key for a product's data quality rules file.

    Args:
        workspace_id: Workspace identifier
        product_id: Product identifier

    Returns:
        Full S3 key like "{S3_METADATA_PATH}/ws/{ws}/prod/{prod}/dq/rules.yaml"
    """
    logger.debug(f"📋 Entry dq_rules_key | ws={workspace_id}, prod={product_id}")
    base = _get_base_prefix()
    key = f"{base}ws/{workspace_id}/prod/{product_id}/dq/rules.yaml"
    logger.debug(f"  ✓ Generated key: {key}")
    return key


def bundle_key(workspace_id: Union[str, uuid.UUID], product_id: Union[str, uuid.UUID], bundle_name: str) -> str:
    """Generate full S3 key for an export bundle zip file.

    Args:
        workspace_id: Workspace identifier
        product_id: Product identifier
        bundle_name: Bundle filename (e.g., "bundle-20250126.zip")

    Returns:
        Full S3 key like "{S3_METADATA_PATH}/ws/{ws}/prod/{prod}/exports/{bundle_name}"
    """
    logger.debug(f"📋 Entry bundle_key | ws={workspace_id}, prod={product_id}, bundle={bundle_name}")
    base = _get_base_prefix()
    key = f"{base}ws/{workspace_id}/prod/{product_id}/exports/{bundle_name}"
    logger.debug(f"  ✓ Generated key: {key}")
    return key


def safe_filename(filename: str) -> str:
    """Convert filename to safe storage key by removing/replacing unsafe characters.

    Args:
        filename: Original filename

    Returns:
        Safe filename for storage
    """
    import re

    logger.debug(f"📋 Entry safe_filename | original='{filename}'")

    # Replace unsafe characters with underscores
    safe = re.sub(r"[^\w\-_\.]", "_", filename)
    logger.debug(f"  ✓ Replaced unsafe chars")

    # Remove multiple consecutive underscores
    safe = re.sub(r"_+", "_", safe)
    logger.debug(f"  ✓ Collapsed underscores")

    # Remove leading/trailing underscores
    safe = safe.strip("_")
    logger.debug(f"  ✓ Trimmed underscores")

    # Remove leading/trailing underscores
    result = safe or "unnamed_file"
    logger.debug(f"  ✅ Safe filename: '{result}'")
    return result

