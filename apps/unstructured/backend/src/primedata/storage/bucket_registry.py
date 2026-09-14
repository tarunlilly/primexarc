"""Centralized bucket configuration registry for storage operations.

This module addresses the pain point of 15+ hardcoded bucket names scattered
throughout the codebase by providing a single source of truth for bucket configuration.

Benefits:
- Eliminates hardcoded bucket names (pain point #2)
- Enables bucket-per-workspace patterns
- Configuration validation on startup
- Consistent environment variable naming
"""

import os
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List

from primedata.utils.logger import get_logger

logger = get_logger(__name__)


class BucketType(Enum):
    """Enumeration of all bucket types used in PrimeData."""
    RAW = "raw"
    CLEAN = "clean"
    CHUNK = "chunk"
    EMBED = "embed"
    EXPORTS = "exports"
    CONFIG = "config"


@dataclass
class BucketConfig:
    """Configuration for a single bucket type."""
    type: BucketType
    env_var_name: str
    default_bucket: str
    description: str
    versioned: bool = True  # Whether bucket contains versioned data


class BucketRegistry:
    """
    Centralized registry for bucket configuration.

    Replaces 15+ hardcoded bucket names scattered across:
    - datasources.py (lines 863-875)
    - storage.py (lines 81, 104, 130, 151, 178)
    - dag_tasks.py (lines 172, 200, 226, 272, 319, 369)
    - retention_job.py (line 124)
    - s3_json_storage.py (line 21)
    - ... and more

    Usage:
        bucket = BucketRegistry.get_bucket(BucketType.RAW)
        storage_client.put_bytes(bucket, key, data)
    """

    BUCKETS: Dict[BucketType, BucketConfig] = {
        BucketType.RAW: BucketConfig(
            type=BucketType.RAW,
            env_var_name="S3_METADATA_BUCKET",
            default_bucket="primedata-raw",
            description="Raw uploaded data (ingestion input)",
            versioned=True
        ),
        BucketType.CLEAN: BucketConfig(
            type=BucketType.CLEAN,
            env_var_name="STORAGE_CLEAN_BUCKET",
            default_bucket="primedata-clean",
            description="Cleaned/preprocessed data",
            versioned=True
        ),
        BucketType.CHUNK: BucketConfig(
            type=BucketType.CHUNK,
            env_var_name="STORAGE_CHUNK_BUCKET",
            default_bucket="primedata-chunk",
            description="Chunked text for embedding",
            versioned=True
        ),
        BucketType.EMBED: BucketConfig(
            type=BucketType.EMBED,
            env_var_name="STORAGE_EMBED_BUCKET",
            default_bucket="primedata-embed",
            description="Vector embeddings",
            versioned=True
        ),
        BucketType.EXPORTS: BucketConfig(
            type=BucketType.EXPORTS,
            env_var_name="STORAGE_EXPORTS_BUCKET",
            default_bucket="primedata-exports",
            description="Exported artifacts (reports, PDFs, fingerprints)",
            versioned=False
        ),
        BucketType.CONFIG: BucketConfig(
            type=BucketType.CONFIG,
            env_var_name="STORAGE_CONFIG_BUCKET",
            default_bucket="primedata-config",
            description="Configuration files",
            versioned=False
        ),
    }

    @classmethod
    def get_bucket(cls, bucket_type: BucketType) -> str:
        """
        Get bucket name from registry, respecting environment variable overrides.

        Resolution order:
        1. Environment variable (if set)
        2. Default bucket name

        Args:
            bucket_type: Type of bucket to retrieve

        Returns:
            Bucket name from env var or default

        Raises:
            ValueError: If bucket_type is unknown

        Example:
            >>> bucket = BucketRegistry.get_bucket(BucketType.RAW)
            >>> # Returns env var or default "primedata-raw"
        """
        logger.debug(f"🔍 Entry get_bucket | type={bucket_type.value}")

        config = cls.BUCKETS.get(bucket_type)
        if not config:
            error_msg = f"Unknown bucket type: {bucket_type}"
            logger.error(f"❌ {error_msg}")
            raise ValueError(error_msg)

        logger.debug(f"  📋 Resolving bucket configuration | env_var={config.env_var_name}")
        env_value = os.getenv(config.env_var_name)
        if env_value:
            logger.debug(f"  ✓ Found environment override | var={config.env_var_name}, value={env_value}")
            logger.debug(f"  ✅ Exit get_bucket | resolved from env")
            return env_value

        logger.debug(f"  ✓ Using default bucket | value={config.default_bucket}")
        logger.debug(f"  ✅ Exit get_bucket | resolved from default")
        return config.default_bucket

    @classmethod
    def get_all_buckets(cls) -> Dict[BucketType, str]:
        """
        Get all configured bucket names.

        Returns:
            Dictionary mapping BucketType to resolved bucket name

        Example:
            >>> all_buckets = BucketRegistry.get_all_buckets()
            >>> print(all_buckets[BucketType.RAW])  # 'primedata-raw' or custom value
        """
        logger.info("📋 Entry get_all_buckets")
        result = {}
        logger.debug(f"  📋 Step 1: Resolving {len(BucketType)} bucket types")
        for bucket_type in BucketType:
            logger.debug(f"    Resolving: {bucket_type.value}")
            result[bucket_type] = cls.get_bucket(bucket_type)

        logger.info(f"✅ Exit get_all_buckets | Resolved {len(result)} bucket configurations")
        return result

    @classmethod
    def validate_env_vars(cls) -> List[str]:
        """
        Validate that bucket configurations are properly set.

        Checks:
        - Environment variables are not empty
        - All required buckets are accessible (checked at startup)

        Returns:
            List of error messages (empty if all valid)

        Example:
            >>> errors = BucketRegistry.validate_env_vars()
            >>> if errors:
            ...     for error in errors:
            ...         logger.error(f"Configuration error: {error}")
        """
        logger.info("🔍 Entry validate_env_vars | Validating bucket configuration")
        errors = []

        logger.debug(f"  📋 Step 1: Checking {len(cls.BUCKETS)} bucket configurations")
        for bucket_type, config in cls.BUCKETS.items():
            try:
                logger.debug(f"    🔍 Validating {bucket_type.value} (env: {config.env_var_name})")

                bucket = cls.get_bucket(bucket_type)
                if not bucket or not bucket.strip():
                    error = f"{config.env_var_name} is empty or not set"
                    logger.error(f"    ❌ {error}")
                    errors.append(error)
                else:
                    logger.debug(f"    ✅ {bucket_type.value}: {bucket}")
            except Exception as e:
                error = f"Error validating {config.env_var_name}: {e}"
                logger.error(f"    ❌ {error}")
                errors.append(error)

        if errors:
            logger.error(f"❌ Exit validate_env_vars | {len(errors)} validation errors found")
        else:
            logger.info(f"✅ Exit validate_env_vars | All {len(cls.BUCKETS)} bucket configurations validated successfully")

        return errors

    @classmethod
    def get_bucket_info(cls, bucket_type: BucketType) -> BucketConfig:
        """
        Get detailed configuration for a bucket type.

        Args:
            bucket_type: Type of bucket

        Returns:
            BucketConfig dataclass with full details

        Example:
            >>> config = BucketRegistry.get_bucket_info(BucketType.RAW)
            >>> print(config.description)  # 'Raw uploaded data (ingestion input)'
        """
        logger.debug(f"📋 Entry get_bucket_info | type={bucket_type.value}")
        config = cls.BUCKETS[bucket_type]
        logger.debug(f"  ✓ Retrieved config | description='{config.description}', versioned={config.versioned}")
        return config
