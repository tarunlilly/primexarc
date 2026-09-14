"""
Smart version management for pipeline runs.

This module provides utilities to determine whether a new version should be created
or if the current version should be reused based on changes to raw files and configuration.
"""

from typing import Dict, Any, Optional, Tuple
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import func

from primedata.db.models import RawFile, RawFileStatus, Product, PipelineRun
from primedata.utils.log_utils import get_logger

logger = get_logger(__name__)


class VersionChangeDetector:
    """Detects changes that warrant creating a new version."""

    def __init__(self, db: Session, product_id: UUID):
        self.db = db
        self.product_id = product_id
        self.product = self._load_product()

    def _load_product(self) -> Optional[Product]:
        """Load product from database."""
        return self.db.query(Product).filter(Product.id == self.product_id).first()

    def get_raw_file_fingerprint(self, version: int) -> Dict[str, Any]:
        """
        Get fingerprint of raw files at a specific version.

        Returns a dict with:
        - file_checksums: Set of checksums
        - file_count: Number of files
        - total_size: Total file size
        """
        raw_files = (
            self.db.query(RawFile)
            .filter(
                RawFile.product_id == self.product_id,
                RawFile.version == version,
                RawFile.status != RawFileStatus.DELETED
            )
            .all()
        )

        if not raw_files:
            return {
                "file_checksums": set(),
                "file_count": 0,
                "total_size": 0,
                "filenames": set()
            }

        return {
            "file_checksums": {rf.file_checksum for rf in raw_files if rf.file_checksum},
            "file_count": len(raw_files),
            "total_size": sum(rf.file_size for rf in raw_files if rf.file_size),
            "filenames": {rf.filename for rf in raw_files}
        }

    def get_config_fingerprint(self, product: Optional[Product] = None) -> Dict[str, Any]:
        """
        Get fingerprint of configuration settings.

        Returns a dict with key config parameters that affect output.
        """
        if product is None:
            product = self.product

        if not product:
            return {}

        chunking_config = product.chunking_config or {}
        resolved_settings = chunking_config.get("resolved_settings", {})

        return {
            "playbook_id": product.playbook_id,
            "chunk_size": resolved_settings.get("chunk_size"),
            "chunk_overlap": resolved_settings.get("chunk_overlap"),
            "chunking_strategy": resolved_settings.get("chunking_strategy"),
            "content_type": resolved_settings.get("content_type"),
            "embedding_model": (product.embedding_config or {}).get("embedder_name"),
            "embedding_dimension": (product.embedding_config or {}).get("embedding_dimension"),
        }

    def did_raw_files_change(self, old_version: int, new_raw_file_version: int) -> Tuple[bool, str]:
        """
        Check if raw files changed between versions.

        Returns:
            (changed: bool, reason: str)
        """
        old_fingerprint = self.get_raw_file_fingerprint(old_version)
        new_fingerprint = self.get_raw_file_fingerprint(new_raw_file_version)

        # If no raw files at old version, consider it changed
        if old_fingerprint["file_count"] == 0:
            return True, f"No raw files at version {old_version}"

        # If no raw files at new version, not changed (will use old version)
        if new_fingerprint["file_count"] == 0:
            return False, f"No new raw files at version {new_raw_file_version}"

        # Check file count
        if old_fingerprint["file_count"] != new_fingerprint["file_count"]:
            return True, f"File count changed: {old_fingerprint['file_count']} → {new_fingerprint['file_count']}"

        # Check filenames
        if old_fingerprint["filenames"] != new_fingerprint["filenames"]:
            added = new_fingerprint["filenames"] - old_fingerprint["filenames"]
            removed = old_fingerprint["filenames"] - new_fingerprint["filenames"]
            return True, f"Files changed (added: {added}, removed: {removed})"

        # Check checksums (file content)
        if old_fingerprint["file_checksums"] != new_fingerprint["file_checksums"]:
            return True, "File content changed (different checksums)"

        # No changes detected
        return False, "Raw files unchanged"

    def did_config_change(self, old_version: int) -> Tuple[bool, str]:
        """
        Check if configuration changed since last successful run.

        Returns:
            (changed: bool, reason: str)
        """
        # Get last successful pipeline run at old version
        last_run = (
            self.db.query(PipelineRun)
            .filter(
                PipelineRun.product_id == self.product_id,
                PipelineRun.version == old_version
            )
            .order_by(PipelineRun.created_at.desc())
            .first()
        )

        if not last_run:
            return True, f"No previous pipeline run found at version {old_version}"

        # Get config from last run's metrics
        last_run_metrics = last_run.metrics or {}

        # Compare playbook_id
        current_playbook = self.product.playbook_id if self.product else None
        last_playbook = last_run_metrics.get("playbook_id")

        if current_playbook != last_playbook:
            return True, f"Playbook changed: {last_playbook} → {current_playbook}"

        # Compare chunking config (compare resolved_settings if available)
        current_chunking = (self.product.chunking_config or {}).get("resolved_settings", {})

        # Try to get chunking_config from last run metrics (might be nested)
        last_chunking_full = last_run_metrics.get("chunking_config", {})
        last_chunking = last_chunking_full.get("resolved_settings", {}) if isinstance(last_chunking_full, dict) else {}

        # Compare key chunking parameters
        chunking_keys = ["chunk_size", "chunk_overlap", "chunking_strategy", "content_type"]
        for key in chunking_keys:
            current_val = current_chunking.get(key)
            last_val = last_chunking.get(key)
            if current_val != last_val:
                return True, f"Chunking config changed: {key} = {last_val} → {current_val}"

        # Compare embedding config
        current_embedding = self.product.embedding_config or {}
        last_embedding = last_run_metrics.get("embedding_config", {})

        embedding_keys = ["embedder_name", "embedding_dimension"]
        for key in embedding_keys:
            current_val = current_embedding.get(key)
            last_val = last_embedding.get(key)
            if current_val != last_val:
                return True, f"Embedding config changed: {key} = {last_val} → {current_val}"

        # No significant config changes
        return False, "Configuration unchanged"

    def should_create_new_version(
        self,
        raw_file_version: int,
        force_new_version: bool = False
    ) -> Tuple[bool, str, Optional[int]]:
        """
        Determine if a new version should be created or if current version should be reused.

        Args:
            raw_file_version: The raw file version that will be processed
            force_new_version: If True, always create a new version

        Returns:
            (create_new: bool, reason: str, reuse_version: Optional[int])
            - If create_new is True, reuse_version is None
            - If create_new is False, reuse_version is the version to reuse
        """
        if force_new_version:
            return True, "Force new version requested", None

        # Get current product version
        current_version = self.product.current_version if self.product else 0

        if current_version == 0:
            return True, "First version for this product", None

        # Check if raw files changed
        raw_changed, raw_reason = self.did_raw_files_change(current_version, raw_file_version)

        # Check if config changed
        config_changed, config_reason = self.did_config_change(current_version)

        # Decision logic
        if raw_changed:
            logger.info(f"Raw files changed: {raw_reason}")
            return True, f"Raw files changed: {raw_reason}", None

        if config_changed:
            logger.info(f"Configuration changed: {config_reason}")
            return True, f"Configuration changed: {config_reason}", None

        # Nothing changed - reuse current version
        reason = f"No changes detected. Raw files: {raw_reason}. Config: {config_reason}"
        logger.info(f"Reusing version {current_version}: {reason}")
        return False, reason, current_version


def determine_pipeline_version(
    db: Session,
    product_id: UUID,
    raw_file_version: int,
    force_new_version: bool = False
) -> Tuple[int, bool, str]:
    """
    Determine what version to use for a pipeline run.

    Args:
        db: Database session
        product_id: Product ID
        raw_file_version: Raw file version to process
        force_new_version: Force creation of new version

    Returns:
        (version: int, is_new: bool, reason: str)
    """
    detector = VersionChangeDetector(db, product_id)
    create_new, reason, reuse_version = detector.should_create_new_version(
        raw_file_version,
        force_new_version
    )

    if create_new:
        # Get the maximum existing pipeline run version
        max_version = (
            db.query(func.max(PipelineRun.version))
            .filter(PipelineRun.product_id == product_id)
            .scalar()
        ) or 0
        new_version = max_version + 1
        logger.info(f"Creating new pipeline version {new_version}: {reason}")
        return new_version, True, reason
    else:
        # Reuse existing version
        logger.info(f"Reusing pipeline version {reuse_version}: {reason}")
        return reuse_version, False, reason
