"""
Artifact Retention Job - Phase 3

Background worker to enforce retention policies on pipeline artifacts.
Archives or deletes artifacts based on their retention policy and age.

Enterprise best practices:
- Soft delete first (mark as DELETED)
- Hard delete after grace period (mark as PURGED)
- Archive to cold storage (optional)
- Cost optimization
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict

logger = logging.getLogger(__name__)
from primedata.db.database import get_db
from primedata.db.models import (
    ArtifactStatus,
    ArtifactType,
    PipelineArtifact,
    PipelineRun,
    PipelineRunStatus,
    Product,
    RetentionPolicy,
)
from primedata.indexing.vector_search_client import get_vector_search_client
from primedata.storage.storage_client import storage_client
from sqlalchemy.orm import Session


def apply_retention_policies(
    db: Session,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Apply retention policies to artifacts.

    Phase 3: Retention policy enforcement

    Args:
        db: Database session
        dry_run: If True, only report what would be done without making changes

    Returns:
        Dictionary with statistics on what was processed
    """
    logger.info(f"🗑️  ENTRY: apply_retention_policies(dry_run={dry_run})")
    stats = {
        "archived": 0,
        "deleted": 0,
        "purged": 0,
        "errors": 0,
        "total_processed": 0,
        "total_size_freed_bytes": 0,
    }

    try:
        cutoff_dates = {
            RetentionPolicy.DAYS_30: datetime.utcnow() - timedelta(days=30),
            RetentionPolicy.DAYS_90: datetime.utcnow() - timedelta(days=90),
            RetentionPolicy.DAYS_365: datetime.utcnow() - timedelta(days=365),
            RetentionPolicy.ON_FAILURE_KEEP_90: datetime.utcnow() - timedelta(days=90),
        }

        logger.debug(f"   📋 Processing {len(cutoff_dates)} retention policies")

        # Process each retention policy
        for policy, cutoff_date in cutoff_dates.items():
            logger.debug(f"   🗑️  Policy {policy.value}, cutoff_date={cutoff_date}")
            artifacts = (
                db.query(PipelineArtifact)
                .filter(
                    PipelineArtifact.retention_policy == policy,
                    PipelineArtifact.status == ArtifactStatus.ACTIVE,
                    PipelineArtifact.created_at < cutoff_date,
                )
                .all()
            )
            logger.debug(f"   📋 Found {len(artifacts)} artifacts for policy {policy.value}")

            for artifact in artifacts:
                try:
                    stats["total_processed"] += 1

                    if policy == RetentionPolicy.DELETE_ON_PROMOTE:
                        logger.debug(f"   📋 Skipping DELETE_ON_PROMOTE policy (requires product context)")
                        continue

                    if dry_run:
                        logger.info(f"   [DRY RUN] 🗑️  Would archive artifact {artifact.id} ({artifact.artifact_name})")
                        stats["archived"] += 1
                        stats["total_size_freed_bytes"] += artifact.file_size
                        continue

                    # Archive artifact (soft delete)
                    logger.debug(f"   🗑️  Archiving artifact {artifact.id}")
                    artifact.status = ArtifactStatus.DELETED
                    artifact.deleted_at = datetime.utcnow()
                    db.commit()

                    stats["archived"] += 1
                    stats["total_size_freed_bytes"] += artifact.file_size
                    logger.info(f"   ✅ Archived artifact {artifact.id} ({artifact.artifact_name}) from {artifact.stage_name}")

                except Exception as e:
                    logger.error(f"   ❌ Error processing artifact {artifact.id}: {e}", exc_info=True)
                    stats["errors"] += 1

        # Hard delete artifacts marked as DELETED for more than 7 days
        logger.debug(f"   📋 Processing hard deletions (purge)")
        purge_cutoff = datetime.utcnow() - timedelta(days=7)
        logger.debug(f"   🗑️  Hard delete cutoff: {purge_cutoff}")
        deleted_artifacts = (
            db.query(PipelineArtifact)
            .filter(
                PipelineArtifact.status == ArtifactStatus.DELETED,
                PipelineArtifact.deleted_at < purge_cutoff,
            )
            .all()
        )
        logger.debug(f"   📋 Found {len(deleted_artifacts)} artifacts eligible for hard delete")

        for artifact in deleted_artifacts:
            try:
                # Optionally delete from storage (if not already deleted)
                if artifact.storage_bucket != "none" and artifact.storage_bucket != "elasticsearch":
                    try:
                        logger.debug(f"   📁 Deleting from storage: {artifact.storage_bucket}/{artifact.storage_key}")
                        storage_client.s3_client.delete_object(Bucket=artifact.storage_bucket, Key=artifact.storage_key)
                        logger.info(f"   ✅ Deleted artifact from storage: {artifact.storage_bucket}/{artifact.storage_key}")
                    except Exception as e:
                        logger.warning(
                            f"   ⚠️  Failed to delete artifact from storage {artifact.storage_bucket}/{artifact.storage_key}: {e}"
                        )

                # Mark as purged (hard delete from DB)
                logger.debug(f"   🗑️  Marking artifact {artifact.id} as PURGED")
                artifact.status = ArtifactStatus.PURGED
                db.commit()

                stats["purged"] += 1
                logger.info(f"   ✅ Purged artifact {artifact.id} ({artifact.artifact_name})")

            except Exception as e:
                logger.error(f"   ❌ Error purging artifact {artifact.id}: {e}", exc_info=True)
                stats["errors"] += 1

        logger.info(
            f"✅ EXIT: apply_retention_policies() -> archived={stats['archived']}, "
            f"purged={stats['purged']}, errors={stats['errors']}, size_freed={stats['total_size_freed_bytes']} bytes"
        )

        return stats
    except Exception as e:
        logger.error(f"   ❌ Critical error in retention job: {e}", exc_info=True)
        stats["errors"] += 1
        raise


def enforce_keep_last_n_runs_per_product(
    db: Session,
    keep_last_n: int = 5,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Keep full artifact/vector details for only the last N pipeline runs per product.

    - Preserves promoted_version (if any), regardless of age.
    - Preserves current_version (if any), regardless of age.
    - Marks older artifacts as DELETED and attempts to remove their objects from S3/GCS.
    - Deletes old Qdrant collections when we can identify the collection name from artifacts.

    This reduces storage and keeps UI responsive while retaining recent operational history.
    """
    logger.info(f"🗑️  ENTRY: enforce_keep_last_n_runs_per_product(keep_last_n={keep_last_n}, dry_run={dry_run})")
    stats: Dict[str, Any] = {
        "products_processed": 0,
        "artifacts_marked_deleted": 0,
        "storage_objects_removed": 0,
        "elasticsearch_indices_deleted": 0,
        "errors": 0,
    }

    try:
        keep_last_n = max(1, int(keep_last_n))
        logger.debug(f"   📋 Keeping last {keep_last_n} runs per product")

        # Use factory pattern to get OpenSearch client
        vector_search_client = get_vector_search_client()

        logger.debug(f"   💾 Querying all products")
        products = db.query(Product).all()
        logger.debug(f"   📋 Processing {len(products)} products")

        for product in products:
            try:
                stats["products_processed"] += 1
                logger.debug(f"   📦 Processing product {product.id}")

                # Determine versions to keep: last N runs + promoted + current
                logger.debug(f"   📋 Retrieving last {keep_last_n} pipeline runs")
                runs = (
                    db.query(PipelineRun)
                    .filter(PipelineRun.product_id == product.id)
                    .order_by(PipelineRun.created_at.desc())
                    .limit(keep_last_n)
                    .all()
                )
                keep_versions = {int(r.version) for r in runs if r and r.version is not None}
                logger.debug(f"   ✅ Versions from last {keep_last_n} runs: {keep_versions}")

                if product.promoted_version:
                    keep_versions.add(int(product.promoted_version))
                    logger.debug(f"   📋 Added promoted_version: {product.promoted_version}")
                if product.current_version:
                    keep_versions.add(int(product.current_version))
                    logger.debug(f"   📋 Added current_version: {product.current_version}")

                logger.debug(f"   ✅ Final versions to keep: {keep_versions}")

                # Mark older artifacts as deleted (but do not hard-delete DB rows)
                logger.debug(f"   📁 Querying old artifacts")
                old_artifacts = (
                    db.query(PipelineArtifact)
                    .filter(
                        PipelineArtifact.product_id == product.id,
                        PipelineArtifact.status == ArtifactStatus.ACTIVE,
                        ~PipelineArtifact.version.in_(list(keep_versions)),
                    )
                    .all()
                )
                logger.debug(f"   📋 Found {len(old_artifacts)} artifacts to mark deleted")

                for artifact in old_artifacts:
                    try:
                        if dry_run:
                            logger.debug(f"   [DRY RUN] 🗑️  Would delete artifact {artifact.id}")
                            stats["artifacts_marked_deleted"] += 1
                            continue

                        # Attempt to delete underlying object for non-elasticsearch buckets
                        if artifact.storage_bucket not in ("none", "elasticsearch"):
                            try:
                                # Use S3 client for storage. Best-effort.
                                logger.debug(f"   📁 Removing from storage: {artifact.storage_bucket}/{artifact.storage_key}")
                                storage_client.s3_client.delete_object(Bucket=artifact.storage_bucket, Key=artifact.storage_key)
                                stats["storage_objects_removed"] += 1
                                logger.debug(f"   ✅ Removed from storage")
                            except Exception as e:
                                logger.warning(f"   ⚠️  Failed to delete from storage: {e}")

                        artifact.status = ArtifactStatus.DELETED
                        artifact.deleted_at = datetime.utcnow()
                        stats["artifacts_marked_deleted"] += 1
                        logger.debug(f"   ✅ Marked artifact {artifact.id} as DELETED")
                    except Exception as e:
                        logger.error(f"   ❌ Error handling artifact {artifact.id}: {e}", exc_info=True)
                        stats["errors"] += 1

                # Delete old OpenSearch indices for versions not kept (best-effort)
                # We only delete when we can confidently identify the index name.
                if vector_search_client.is_connected():
                    logger.debug(f"   🔍 Querying old vector artifacts for OpenSearch cleanup")
                    vector_artifacts = (
                        db.query(PipelineArtifact)
                        .filter(
                            PipelineArtifact.product_id == product.id,
                            PipelineArtifact.artifact_type == ArtifactType.VECTOR,
                            PipelineArtifact.status.in_([ArtifactStatus.ACTIVE, ArtifactStatus.DELETED]),
                            ~PipelineArtifact.version.in_(list(keep_versions)),
                        )
                        .order_by(PipelineArtifact.created_at.desc())
                        .all()
                    )
                    logger.debug(f"   📋 Found {len(vector_artifacts)} old vector artifacts")

                    seen = set()
                    for va in vector_artifacts:
                        meta = va.artifact_metadata or {}
                        collection_name = meta.get("collection_name") if isinstance(meta, dict) else None
                        if not collection_name or collection_name in seen:
                            continue
                        seen.add(collection_name)
                        logger.debug(f"   🗑️  Deleting OpenSearch collection: {collection_name}")
                        if dry_run:
                            logger.debug(f"   [DRY RUN] Would delete collection {collection_name}")
                            stats["elasticsearch_indices_deleted"] += 1
                            continue
                        try:
                            if vector_search_client.delete_collection(collection_name):
                                stats["elasticsearch_indices_deleted"] += 1
                                logger.info(f"   ✅ Deleted OpenSearch collection {collection_name}")
                        except Exception as e:
                            logger.error(f"   ❌ Failed to delete OpenSearch collection {collection_name}: {e}", exc_info=True)
                            stats["errors"] += 1

                # Prune DB-heavy pipeline run metrics for older runs (keep row, keep minimal dict)
                logger.debug(f"   📊 Pruning pipeline run metrics")
                old_runs = (
                    db.query(PipelineRun)
                    .filter(
                        PipelineRun.product_id == product.id,
                        ~PipelineRun.version.in_(list(keep_versions)),
                    )
                    .all()
                )
                logger.debug(f"   📋 Found {len(old_runs)} old pipeline runs")

                for r in old_runs:
                    try:
                        if dry_run:
                            continue
                        if r.metrics is None:
                            r.metrics = {}
                        r.metrics = {"archived": True, "archived_at": datetime.utcnow().isoformat()}
                        r.stage_metrics = None
                        logger.debug(f"   ✅ Archived metrics for run {r.id}")
                    except Exception as e:
                        logger.error(f"   ❌ Error pruning metrics for run {r.id}: {e}", exc_info=True)
                        stats["errors"] += 1

                if not dry_run:
                    logger.debug(f"   💾 Committing product changes")
                    db.commit()
                    logger.debug(f"   ✅ Committed")

            except Exception as e:
                logger.error(f"   ❌ Error processing product {product.id}: {e}", exc_info=True)
                stats["errors"] += 1
                try:
                    db.rollback()
                except Exception as rb_err:
                    logger.error(f"   ❌ Error rolling back: {rb_err}")

        logger.info(
            f"✅ EXIT: enforce_keep_last_n_runs_per_product() -> "
            f"products={stats['products_processed']}, artifacts_deleted={stats['artifacts_marked_deleted']}, "
            f"storage_removed={stats['storage_objects_removed']}, es_deleted={stats['elasticsearch_indices_deleted']}, "
            f"errors={stats['errors']}"
        )

        return stats
    except Exception as e:
        logger.error(f"   ❌ Critical error in keep_last_n: {e}", exc_info=True)
        stats["errors"] += 1
        raise


def run_retention_job(dry_run: bool = False) -> Dict[str, Any]:
    """
    Main entry point for retention job.

    Can be called as:
    - Standalone script
    - Cron job
    - Airflow DAG
    - Scheduled task

    Args:
        dry_run: If True, only report without making changes

    Returns:
        Statistics dictionary
    """
    logger.info(f"🗑️  ENTRY: run_retention_job(dry_run={dry_run})")

    db = next(get_db())
    try:
        logger.debug(f"   📋 Starting retention job phases")

        # Optional: storage optimization by keeping only last N runs per product (default 5)
        keep_last_n = int(os.getenv("RETAIN_LAST_N_PIPELINE_RUNS", "5"))
        logger.debug(f"   🗑️  Running keep-last-N (n={keep_last_n})")
        extra = enforce_keep_last_n_runs_per_product(db, keep_last_n=keep_last_n, dry_run=dry_run)
        logger.info(f"   ✅ Keep-last-N phase: {extra}")

        logger.debug(f"   🗑️  Running retention policy enforcement")
        stats = apply_retention_policies(db, dry_run=dry_run)

        logger.info(
            f"✅ EXIT: run_retention_job() -> "
            f"processed={stats['total_processed']}, "
            f"archived={stats['archived']}, "
            f"purged={stats['purged']}, "
            f"errors={stats['errors']}, "
            f"size_freed={stats['total_size_freed_bytes']} bytes"
        )

        return stats

    except Exception as e:
        logger.error(f"   ❌ Critical error in retention job: {e}", exc_info=True)
        raise
    finally:
        logger.debug(f"   📋 Closing database connection")
        db.close()


if __name__ == "__main__":
    # Allow running as standalone script
    import sys

    dry_run = "--dry-run" in sys.argv
    stats = run_retention_job(dry_run=dry_run)
    print(f"Retention job stats: {stats}")
