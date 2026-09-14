"""
Artifact Registry Service for Enterprise Traceability

This module provides functions for registering and managing pipeline artifacts
with full traceability, lineage, and retention policy support.

Phases:
- Phase 1: Basic artifact tracking (S3/GCS location, size, checksum)
- Phase 2: Data lineage (input artifacts dependencies)
- Phase 3: Retention policies (lifecycle management)
- Phase 4: Advanced features (comparison, diffing, analytics)
"""

import hashlib
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from primedata.utils.log_utils import get_logger

logger = get_logger(__name__)
from primedata.db.models import (
    ArtifactStatus,
    ArtifactType,
    PipelineArtifact,
    PipelineRun,
    PipelineRunStatus,
    RetentionPolicy,
)
from sqlalchemy.orm import Session


def calculate_checksum(data: bytes, algorithm: str = "sha256") -> str:
    """Calculate checksum for data integrity verification.

    Args:
        data: Data bytes to checksum
        algorithm: Hash algorithm ("md5" or "sha256")

    Returns:
        Hexadecimal checksum string
    """
    logger.info(f"🔐 ENTRY: calculate_checksum(data_size={len(data)} bytes, algorithm={algorithm})")
    try:
        logger.debug(f"   📋 Hashing {len(data)} bytes with {algorithm}")
        if algorithm == "md5":
            checksum = hashlib.md5(data).hexdigest()
        elif algorithm == "sha256":
            checksum = hashlib.sha256(data).hexdigest()
        else:
            logger.error(f"   ❌ Unsupported checksum algorithm: {algorithm}")
            raise ValueError(f"Unsupported algorithm: {algorithm}")
        logger.debug(f"   ✅ Checksum computed: {checksum[:16]}...")
        logger.info(f"✅ EXIT: calculate_checksum() -> {checksum[:16]}...")
        return checksum
    except Exception as e:
        logger.error(f"   ❌ Error in calculate_checksum: {e}", exc_info=True)
        raise


def register_artifact(
    db: Session,
    pipeline_run_id: UUID,
    workspace_id: UUID,
    product_id: UUID,
    version: int,
    stage_name: str,
    artifact_type: ArtifactType,
    artifact_name: str,
    storage_bucket: str,
    storage_key: str,
    file_size: int,
    checksum: Optional[str] = None,
    storage_etag: Optional[str] = None,
    input_artifact_ids: Optional[List[UUID]] = None,
    artifact_metadata: Optional[Dict[str, Any]] = None,
    retention_policy: RetentionPolicy = RetentionPolicy.DAYS_90,
    created_by: Optional[str] = None,
) -> PipelineArtifact:
    """
    Register a new pipeline artifact.

    Phase 1 & 2: Basic tracking + lineage

    Args:
        db: Database session
        pipeline_run_id: Pipeline run that generated this artifact
        workspace_id: Workspace ID
        product_id: Product ID
        version: Product version
        stage_name: Stage that generated artifact ("preprocess", "scoring", etc.)
        artifact_type: Type of artifact (JSONL, JSON, CSV, PDF, VECTOR)
        artifact_name: Name of artifact ("processed_chunks", "metrics", etc.)
        storage_bucket: S3/GCS bucket name
        storage_key: Full S3/GCS object key
        file_size: File size in bytes
        checksum: Optional checksum (MD5 or SHA256)
        storage_etag: Optional S3/GCS ETag
        input_artifact_ids: List of artifact IDs this depends on (Phase 2: lineage)
        metadata: Stage-specific metadata dictionary
        retention_policy: Retention policy (Phase 3)
        created_by: Optional user ID if user-triggered

    Returns:
        Created PipelineArtifact instance
    """
    logger.info(f"📦 ENTRY: register_artifact(artifact_name={artifact_name}, type={artifact_type.value}, stage={stage_name})")
    logger.debug(f"   product_id={product_id}, version={version}, workspace_id={workspace_id}")
    logger.debug(f"   storage={storage_bucket}/{storage_key}, size={file_size} bytes")

    try:
        # Build input_artifacts lineage data (Phase 2)
        input_artifacts_data = []
        if input_artifact_ids:
            logger.debug(f"   🔗 Building lineage with {len(input_artifact_ids)} input artifacts")
            # Fetch input artifacts to get their details for lineage
            input_artifacts = db.query(PipelineArtifact).filter(PipelineArtifact.id.in_(input_artifact_ids)).all()
            logger.debug(f"   💾 Retrieved {len(input_artifacts)} input artifacts from database")

            for input_artifact in input_artifacts:
                input_artifacts_data.append(
                    {
                        "artifact_id": str(input_artifact.id),
                        "stage": input_artifact.stage_name,
                        "artifact_name": input_artifact.artifact_name,
                        "storage_key": input_artifact.storage_key,
                    }
                )
            logger.debug(f"   ✅ Lineage data prepared: {len(input_artifacts_data)} artifacts")

        # Determine retention policy based on pipeline run status
        if retention_policy == RetentionPolicy.DAYS_90:
            # Check if pipeline failed - use longer retention for failures
            pipeline_run = db.query(PipelineRun).filter(PipelineRun.id == pipeline_run_id).first()
            logger.debug(f"   💾 Retrieved pipeline run {pipeline_run_id}")
            if pipeline_run and pipeline_run.status == PipelineRunStatus.FAILED:
                logger.warning(f"   ⚠️  Pipeline run {pipeline_run_id} failed, extending retention policy")
                retention_policy = RetentionPolicy.ON_FAILURE_KEEP_90

        artifact = PipelineArtifact(
            pipeline_run_id=pipeline_run_id,
            workspace_id=workspace_id,
            product_id=product_id,
            version=version,
            stage_name=stage_name,
            artifact_type=artifact_type,
            artifact_name=artifact_name,
            storage_bucket=storage_bucket,
            storage_key=storage_key,
            file_size=file_size,
            checksum=checksum,
            storage_etag=storage_etag,
            input_artifacts=input_artifacts_data,
            artifact_metadata=artifact_metadata or {},
            retention_policy=retention_policy,
            status=ArtifactStatus.ACTIVE,
            created_by=created_by,
        )

        logger.debug(f"   📝 Saving artifact to database")
        db.add(artifact)
        db.commit()
        db.refresh(artifact)
        logger.debug(f"   ✅ Artifact persisted with ID {artifact.id}")

        logger.info(
            f"✅ EXIT: register_artifact() -> ID={artifact.id}, name={artifact_name} ({artifact_type.value}) from {stage_name} "
            f"for product {product_id} v{version}, size={file_size} bytes, "
            f"lineage={len(input_artifacts_data)} inputs, retention={retention_policy.value}"
        )

        return artifact
    except Exception as e:
        logger.error(f"   ❌ Error registering artifact: {e}", exc_info=True)
        db.rollback()
        raise


def get_artifacts_by_stage(
    db: Session,
    pipeline_run_id: UUID,
    stage_name: str,
) -> List[PipelineArtifact]:
    """Get all artifacts for a specific stage in a pipeline run.

    Args:
        db: Database session
        pipeline_run_id: Pipeline run ID
        stage_name: Stage name

    Returns:
        List of PipelineArtifact instances
    """
    logger.info(f"📦 ENTRY: get_artifacts_by_stage(stage='{stage_name}', pipeline_run_id={pipeline_run_id})")
    try:
        logger.debug(f"   💾 Querying database for artifacts")
        artifacts = (
            db.query(PipelineArtifact)
            .filter(
                PipelineArtifact.pipeline_run_id == pipeline_run_id,
                PipelineArtifact.stage_name == stage_name,
                PipelineArtifact.status != ArtifactStatus.PURGED,
            )
            .all()
        )
        logger.info(f"✅ EXIT: get_artifacts_by_stage() -> Found {len(artifacts)} active artifacts for stage '{stage_name}'")
        return artifacts
    except Exception as e:
        logger.error(f"   ❌ Error fetching artifacts: {e}", exc_info=True)
        raise


def get_artifact_lineage(
    db: Session,
    artifact_id: UUID,
    direction: str = "downstream",  # "upstream" or "downstream"
) -> List[PipelineArtifact]:
    """Get artifact lineage (Phase 2).

    Args:
        db: Database session
        artifact_id: Artifact ID
        direction: "upstream" (inputs) or "downstream" (outputs using this)

    Returns:
        List of related artifacts
    """
    logger.info(f"📦 ENTRY: get_artifact_lineage(artifact_id={artifact_id}, direction={direction})")
    try:
        logger.debug(f"   💾 Retrieving artifact {artifact_id}")
        artifact = db.query(PipelineArtifact).filter(PipelineArtifact.id == artifact_id).first()
        if not artifact:
            logger.warning(f"   ⚠️  Artifact {artifact_id} not found")
            return []

        if direction == "upstream":
            logger.debug(f"   🔗 Traversing upstream dependencies")
            # Get input artifacts (artifacts this one depends on)
            input_ids = []
            for input_ref in artifact.input_artifacts or []:
                if isinstance(input_ref, dict) and "artifact_id" in input_ref:
                    try:
                        input_ids.append(UUID(input_ref["artifact_id"]))
                    except (ValueError, TypeError):
                        continue

            if not input_ids:
                logger.debug(f"   ✅ No upstream dependencies")
                return []

            logger.debug(f"   💾 Querying {len(input_ids)} upstream artifacts")
            result = (
                db.query(PipelineArtifact)
                .filter(
                    PipelineArtifact.id.in_(input_ids),
                    PipelineArtifact.status != ArtifactStatus.PURGED,
                )
                .all()
            )
            logger.info(f"✅ EXIT: get_artifact_lineage() -> Found {len(result)} upstream artifacts")
            return result

        elif direction == "downstream":
            logger.debug(f"   🔗 Traversing downstream dependents")
            # Get artifacts that depend on this one (artifacts with this in their input_artifacts)
            # This requires a JSON query - PostgreSQL supports this
            artifact_id_str = str(artifact_id)

            # Query artifacts where input_artifacts contains this artifact_id
            # PostgreSQL JSON query: WHERE input_artifacts @> '[{"artifact_id": "..."}]'::jsonb
            from sqlalchemy import text

            logger.debug(f"   💾 Querying downstream artifacts using JSON search")
            result = db.execute(
                text(
                    """
                    SELECT * FROM pipeline_artifacts
                    WHERE input_artifacts::text LIKE :pattern
                    AND status != 'purged'
                """
                ),
                {"pattern": f"%{artifact_id_str}%"},
            )

            artifacts = []
            for row in result:
                artifact_obj = db.query(PipelineArtifact).filter(PipelineArtifact.id == row.id).first()
                if artifact_obj:
                    artifacts.append(artifact_obj)

            logger.info(f"✅ EXIT: get_artifact_lineage() -> Found {len(artifacts)} downstream dependents")
            return artifacts

        else:
            error_msg = f"Invalid direction: {direction}. Use 'upstream' or 'downstream'"
            logger.error(f"   ❌ {error_msg}")
            raise ValueError(error_msg)
    except Exception as e:
        logger.error(f"   ❌ Error retrieving artifact lineage: {e}", exc_info=True)
        raise


def update_artifact_status(
    db: Session,
    artifact_id: UUID,
    status: ArtifactStatus,
    archived_at: Optional[datetime] = None,
    deleted_at: Optional[datetime] = None,
) -> PipelineArtifact:
    """Update artifact status (Phase 3: retention).

    Args:
        db: Database session
        artifact_id: Artifact ID
        status: New status
        archived_at: Timestamp if archiving
        deleted_at: Timestamp if deleting

    Returns:
        Updated PipelineArtifact instance
    """
    logger.info(f"📦 ENTRY: update_artifact_status(artifact_id={artifact_id}, status={status.value})")
    try:
        logger.debug(f"   💾 Retrieving artifact {artifact_id}")
        artifact = db.query(PipelineArtifact).filter(PipelineArtifact.id == artifact_id).first()
        if not artifact:
            error_msg = f"Artifact {artifact_id} not found"
            logger.error(f"   ❌ {error_msg}")
            raise ValueError(error_msg)

        logger.debug(f"   📝 Updating status from {artifact.status.value} to {status.value}")
        artifact.status = status
        if archived_at:
            artifact.archived_at = archived_at
            logger.debug(f"   ✅ Archived at: {archived_at}")
        if deleted_at:
            artifact.deleted_at = deleted_at
            logger.debug(f"   ✅ Deleted at: {deleted_at}")

        logger.debug(f"   💾 Persisting changes to database")
        db.commit()
        db.refresh(artifact)

        logger.info(f"✅ EXIT: update_artifact_status() -> Artifact {artifact_id} status updated to {status.value}")
        return artifact
    except Exception as e:
        logger.error(f"   ❌ Error updating artifact status: {e}", exc_info=True)
        db.rollback()
        raise


def get_artifacts_for_retention(
    db: Session,
    retention_policy: RetentionPolicy,
    older_than_days: int,
) -> List[PipelineArtifact]:
    """Get artifacts that should be archived/deleted based on retention policy (Phase 3).

    Args:
        db: Database session
        retention_policy: Retention policy to check
        older_than_days: Artifacts older than this many days

    Returns:
        List of artifacts that match criteria
    """
    logger.info(f"📦 ENTRY: get_artifacts_for_retention(policy={retention_policy.value}, older_than_days={older_than_days})")
    try:
        from datetime import timedelta

        cutoff_date = datetime.utcnow() - timedelta(days=older_than_days)
        logger.debug(f"   📋 Cutoff date: {cutoff_date}")

        logger.debug(f"   💾 Querying database for artifacts")
        artifacts = (
            db.query(PipelineArtifact)
            .filter(
                PipelineArtifact.retention_policy == retention_policy,
                PipelineArtifact.status == ArtifactStatus.ACTIVE,
                PipelineArtifact.created_at < cutoff_date,
            )
            .all()
        )
        logger.info(f"✅ EXIT: get_artifacts_for_retention() -> Found {len(artifacts)} artifacts for retention")
        return artifacts
    except Exception as e:
        logger.error(f"   ❌ Error querying retention artifacts: {e}", exc_info=True)
        raise


def get_artifact_summary_for_run(
    db: Session,
    pipeline_run_id: UUID,
) -> Dict[str, Any]:
    """Get artifact summary for a pipeline run (for lightweight metadata in pipeline_runs.metrics).

    Returns lightweight summary for pipeline_runs.metrics JSON field.

    Args:
        db: Database session
        pipeline_run_id: Pipeline run ID

    Returns:
        Dictionary with artifact summary
    """
    logger.info(f"📊 ENTRY: get_artifact_summary_for_run(pipeline_run_id={pipeline_run_id})")
    try:
        logger.debug(f"   💾 Querying artifacts for pipeline run")
        artifacts = (
            db.query(PipelineArtifact)
            .filter(
                PipelineArtifact.pipeline_run_id == pipeline_run_id,
                PipelineArtifact.status != ArtifactStatus.PURGED,
            )
            .all()
        )
        logger.debug(f"   ✅ Retrieved {len(artifacts)} artifacts")

        summary = {
            "total_artifacts": len(artifacts),
            "total_size_bytes": sum(a.file_size for a in artifacts),
            "by_stage": {},
            "by_type": {},
        }

        logger.debug(f"   📋 Total artifacts: {summary['total_artifacts']}, total size: {summary['total_size_bytes']} bytes")

        for artifact in artifacts:
            # By stage
            if artifact.stage_name not in summary["by_stage"]:
                summary["by_stage"][artifact.stage_name] = {
                    "count": 0,
                    "total_size_bytes": 0,
                    "artifacts": [],
                }

            summary["by_stage"][artifact.stage_name]["count"] += 1
            summary["by_stage"][artifact.stage_name]["total_size_bytes"] += artifact.file_size
            summary["by_stage"][artifact.stage_name]["artifacts"].append(
                {
                    "id": str(artifact.id),
                    "name": artifact.artifact_name,
                    "type": artifact.artifact_type.value,
                    "size_bytes": artifact.file_size,
                    "storage_key": artifact.storage_key,
                }
            )

            # By type
            type_key = artifact.artifact_type.value
            if type_key not in summary["by_type"]:
                summary["by_type"][type_key] = {"count": 0, "total_size_bytes": 0}
            summary["by_type"][type_key]["count"] += 1
            summary["by_type"][type_key]["total_size_bytes"] += artifact.file_size

        logger.debug(f"   ✅ Aggregated by {len(summary['by_stage'])} stages and {len(summary['by_type'])} types")
        logger.info(f"✅ EXIT: get_artifact_summary_for_run() -> {len(artifacts)} artifacts, {summary['total_size_bytes']} bytes total")

        return summary
    except Exception as e:
        logger.error(f"   ❌ Error generating artifact summary: {e}", exc_info=True)
        raise
