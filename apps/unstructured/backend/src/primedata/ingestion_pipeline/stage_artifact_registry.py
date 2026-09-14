"""
Stage Artifact Registry - Functions for registering pipeline stage artifacts.

This module contains all functions related to artifact registration for
pipeline stages (preprocess, scoring, fingerprint, reporting, validation, indexing).
Extracted from dag_tasks.py for better separation of concerns and testability.
"""

import os
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from primedata.db.models import ArtifactType, RetentionPolicy
from primedata.ingestion_pipeline.aird_stages.base import StageStatus
from primedata.ingestion_pipeline.artifact_registry import (
    calculate_checksum,
    register_artifact,
)
from primedata.storage.paths import clean_prefix, safe_filename
from primedata.utils.logger import get_logger

logger = get_logger(__name__)


# =============================================================================
# HELPER FUNCTIONS - Single Responsibility Principle
# =============================================================================


def _retrieve_file_stats(bucket: str, storage_key: str) -> Optional[Dict[str, Any]]:
    """Retrieve file statistics from storage.

    Responsibility: Get file metadata (size, etag) from S3.

    Note: If HeadObject permission is denied (403), returns minimal metadata.
    This is expected when IAM policy is scoped to S3_METADATA_PATH folder only.
    Falls back to downloading file to get size if stat_object fails.
    """
    from primedata.storage.storage_client import storage_client

    logger.debug(f"   📥 Retrieving file stats from S3: {storage_key}")
    try:
        stat_info = storage_client.stat_object(bucket, storage_key)
        if not stat_info:
            logger.debug(f"   ⚠️  stat_object returned None for {storage_key}, trying fallback by downloading file")
            # Fallback: Try to get file size by downloading it
            try:
                file_data = storage_client.get_bytes(bucket, storage_key)
                if file_data:
                    logger.debug(f"   ℹ️  Retrieved file via fallback download | size={len(file_data)} bytes")
                    return {
                        "size": len(file_data),
                        "etag": "unknown"  # ETag not available via fallback
                    }
            except Exception as fallback_error:
                logger.debug(f"   ℹ️  Fallback download also failed: {fallback_error}")

            logger.warning(f"   ⚠️  Could not get file info for {storage_key} (likely 404 Not Found)")
            return None

        # Check if this is minimal metadata (returned due to 403 permission error)
        if stat_info.get("etag") == "unknown":
            logger.debug(f"   ℹ️  Using minimal metadata for {storage_key} (HeadObject permission denied - expected if IAM scoped to S3_METADATA_PATH)")
        else:
            logger.debug(f"   ✓ File size: {stat_info['size']} bytes, ETag: {stat_info.get('etag', 'N/A')}")

        return stat_info
    except Exception as e:
        logger.debug(f"   ⚠️  stat_object exception for {storage_key}: {e}, trying fallback download")
        # Fallback: Try to get file size by downloading it
        try:
            from primedata.storage.storage_client import storage_client
            file_data = storage_client.get_bytes(bucket, storage_key)
            if file_data:
                logger.debug(f"   ✓ Retrieved file via fallback download | size={len(file_data)} bytes")
                return {
                    "size": len(file_data),
                    "etag": "unknown"  # ETag not available via fallback
                }
        except Exception as fallback_error:
            logger.error(f"   ❌ Fallback download also failed for {storage_key}: {fallback_error}", exc_info=True)

        return None


def _calculate_file_checksum(bucket: str, storage_key: str) -> Optional[str]:
    """Calculate SHA256 checksum of file content.

    Responsibility: Download file and compute its checksum.
    """
    from primedata.storage.storage_client import storage_client

    logger.debug(f"   📥 Downloading file for checksum calculation")
    try:
        file_data = storage_client.get_bytes(bucket, storage_key)
        if not file_data:
            logger.warning(f"   ⚠️  Could not download file: {storage_key}")
            return None

        logger.debug(f"   🔐 Calculating SHA256 checksum")
        checksum = calculate_checksum(file_data, algorithm="sha256")
        logger.debug(f"   ✓ Checksum: {checksum[:16]}...")
        return checksum
    except Exception as e:
        logger.error(f"   ❌ Error calculating checksum for {storage_key}: {e}", exc_info=True)
        return None


def _register_artifact_in_db(
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
    checksum: str,
    storage_etag: str,
    artifact_metadata: Dict[str, Any],
    input_artifact_ids: Optional[List[UUID]] = None,
) -> Optional[UUID]:
    """Register artifact in database.

    Responsibility: Save artifact metadata to database with lineage.
    """
    logger.debug(f"   📝 Registering artifact in database")
    try:
        artifact_id = register_artifact(
            db=db,
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
            input_artifact_ids=input_artifact_ids,
            artifact_metadata=artifact_metadata,
            retention_policy=RetentionPolicy.DAYS_90,
        ).id
        logger.info(f"   ✅ Artifact registered: {artifact_id}")
        return artifact_id
    except Exception as e:
        logger.error(f"   ❌ Error registering artifact: {e}", exc_info=True)
        return None


def _register_preprocess_artifacts(
    db: Session,
    pipeline_run_id: UUID,
    workspace_id: UUID,
    product_id: UUID,
    version: int,
    result: Any,
    input_artifact_ids: Optional[List[UUID]] = None,
) -> List[UUID]:
    """Register preprocessing stage artifacts.

    Responsibility: Handle preprocess-specific artifact registration logic.
    """
    registered_ids = []
    # Use bucket from environment variable (S3_METADATA_BUCKET), default to primedata-clean
    bucket = os.getenv("S3_METADATA_BUCKET", "primedata-clean")
    processed_files = result.metrics.get("processed_file_list", [])
    logger.info(f"🔄 Registering preprocess artifacts: {len(processed_files)} files")

    for idx, file_stem in enumerate(processed_files, 1):
        logger.debug(f"   [{idx}/{len(processed_files)}] Processing file: {file_stem}")
        clean_prefix_path = clean_prefix(workspace_id, product_id, version)
        safe_file_stem = safe_filename(file_stem)
        storage_key = f"{clean_prefix_path}{safe_file_stem}.jsonl"

        # Get file stats
        stat_info = _retrieve_file_stats(bucket, storage_key)
        if not stat_info:
            continue

        # Calculate checksum
        checksum = _calculate_file_checksum(bucket, storage_key)
        if not checksum:
            continue

        # Register in database
        artifact_id = _register_artifact_in_db(
            db=db,
            pipeline_run_id=pipeline_run_id,
            workspace_id=workspace_id,
            product_id=product_id,
            version=version,
            stage_name="preprocess",
            artifact_type=ArtifactType.JSONL,
            artifact_name=f"processed_chunks_{safe_file_stem}",
            storage_bucket=bucket,
            storage_key=storage_key,
            file_size=stat_info["size"],
            checksum=checksum,
            storage_etag=stat_info.get("etag", ""),
            artifact_metadata={
                "file_stem": file_stem,
                "chunks_count": result.metrics.get("file_chunk_counts", {}).get(
                    file_stem, result.metrics.get("total_chunks", 0)
                ),
                "playbook_id": result.metrics.get("playbook_id"),
            },
            input_artifact_ids=input_artifact_ids,
        )
        if artifact_id:
            registered_ids.append(artifact_id)

    return registered_ids


def _register_scoring_artifacts(
    db: Session,
    pipeline_run_id: UUID,
    workspace_id: UUID,
    product_id: UUID,
    version: int,
    result: Any,
    input_artifact_ids: Optional[List[UUID]] = None,
) -> List[UUID]:
    """Register scoring stage artifacts.

    Responsibility: Handle scoring-specific artifact registration logic.
    """
    registered_ids = []
    # Use bucket from environment variable (S3_METADATA_BUCKET), default to primedata-clean
    bucket = os.getenv("S3_METADATA_BUCKET", "primedata-clean")
    metrics_key = f"{clean_prefix(workspace_id, product_id, version)}metrics.json"
    logger.info(f"🔄 Registering scoring artifacts")
    logger.debug(f"   Bucket: {bucket}, Metrics key: {metrics_key}")

    # Get file stats
    stat_info = _retrieve_file_stats(bucket, metrics_key)
    if not stat_info:
        return registered_ids

    # Calculate checksum
    checksum = _calculate_file_checksum(bucket, metrics_key)
    if not checksum:
        return registered_ids

    # Register in database
    artifact_id = _register_artifact_in_db(
        db=db,
        pipeline_run_id=pipeline_run_id,
        workspace_id=workspace_id,
        product_id=product_id,
        version=version,
        stage_name="scoring",
        artifact_type=ArtifactType.JSON,
        artifact_name="metrics",
        storage_bucket=bucket,
        storage_key=metrics_key,
        file_size=stat_info["size"],
        checksum=checksum,
        storage_etag=stat_info.get("etag", ""),
        artifact_metadata={
            "total_chunks": result.metrics.get("total_chunks", 0),
            "avg_trust_score": result.metrics.get("avg_trust_score", 0.0),
        },
        input_artifact_ids=input_artifact_ids,
    )
    if artifact_id:
        registered_ids.append(artifact_id)

    return registered_ids


def _register_fingerprint_artifacts(
    db: Session,
    pipeline_run_id: UUID,
    workspace_id: UUID,
    product_id: UUID,
    version: int,
    result: Any,
    storage: Any,
    input_artifact_ids: Optional[List[UUID]] = None,
) -> List[UUID]:
    """Register fingerprint stage artifacts.

    Responsibility: Handle fingerprint-specific artifact registration logic.
    """
    registered_ids = []
    artifacts = result.artifacts or {}

    logger.info(f"🔄 Registering fingerprint artifacts | artifacts_count={len(artifacts)}")

    if not artifacts.get("fingerprint_json"):
        logger.warning(f"No fingerprint_json artifact found in result")
        return registered_ids

    fingerprint_path = artifacts["fingerprint_json"]
    logger.debug(f"   Fingerprint artifact path: {fingerprint_path}")

    # Determine S3 bucket and extract metadata from the path
    # fingerprint_path is already the full S3 key from storage.put_artifact()
    s3_bucket = os.getenv("S3_METADATA_BUCKET", "primedata-raw")

    # Get file stats from S3
    stat_info = _retrieve_file_stats(s3_bucket, fingerprint_path)
    file_size = stat_info["size"] if stat_info else 0
    checksum = _calculate_file_checksum(s3_bucket, fingerprint_path) or ""
    storage_etag = stat_info.get("etag", "") if stat_info else ""

    # Register in database
    artifact_id = _register_artifact_in_db(
        db=db,
        pipeline_run_id=pipeline_run_id,
        workspace_id=workspace_id,
        product_id=product_id,
        version=version,
        stage_name="fingerprint",
        artifact_type=ArtifactType.JSON,
        artifact_name="fingerprint",
        storage_bucket=s3_bucket,
        storage_key=fingerprint_path,
        file_size=file_size,
        checksum=checksum,
        storage_etag=storage_etag,
        artifact_metadata={
            "trust_score": result.metrics.get("trust_score"),
            "metrics_count": result.metrics.get("metrics_count", 0),
        },
        input_artifact_ids=input_artifact_ids,
    )
    if artifact_id:
        registered_ids.append(artifact_id)

    return registered_ids


def _register_reporting_artifacts(
    db: Session,
    pipeline_run_id: UUID,
    workspace_id: UUID,
    product_id: UUID,
    version: int,
    result: Any,
    storage: Any,
    input_artifact_ids: Optional[List[UUID]] = None,
) -> List[UUID]:
    """Register reporting stage artifacts.

    Responsibility: Handle reporting-specific artifact registration logic.
    """
    registered_ids = []
    artifacts = result.artifacts or {}

    logger.info(f"🔄 Registering reporting artifacts | artifacts_count={len(artifacts)}")

    if not artifacts.get("trust_report_pdf"):
        logger.warning(f"No trust_report_pdf artifact found in result")
        return registered_ids

    report_path = artifacts["trust_report_pdf"]
    logger.debug(f"   Report artifact path: {report_path}")

    # Determine S3 bucket
    s3_bucket = os.getenv("S3_METADATA_BUCKET", "primedata-raw")

    # Get file stats from S3
    stat_info = _retrieve_file_stats(s3_bucket, report_path)
    file_size = stat_info["size"] if stat_info else 0
    checksum = _calculate_file_checksum(s3_bucket, report_path) or ""
    storage_etag = stat_info.get("etag", "") if stat_info else ""

    # Register in database
    artifact_id = _register_artifact_in_db(
        db=db,
        pipeline_run_id=pipeline_run_id,
        workspace_id=workspace_id,
        product_id=product_id,
        version=version,
        stage_name="reporting",
        artifact_type=ArtifactType.PDF,
        artifact_name="trust_report",
        storage_bucket=s3_bucket,
        storage_key=report_path,
        file_size=file_size,
        checksum=checksum,
        storage_etag=storage_etag,
        artifact_metadata={
            "entries_processed": result.metrics.get("entries_processed", 0),
        },
        input_artifact_ids=input_artifact_ids,
    )
    if artifact_id:
        registered_ids.append(artifact_id)

    return registered_ids


def _register_validation_artifacts(
    db: Session,
    pipeline_run_id: UUID,
    workspace_id: UUID,
    product_id: UUID,
    version: int,
    result: Any,
    storage: Any,
    input_artifact_ids: Optional[List[UUID]] = None,
) -> List[UUID]:
    """Register validation stage artifacts.

    Responsibility: Handle validation-specific artifact registration logic.
    """
    registered_ids = []
    artifacts = result.artifacts or {}

    logger.info(f"🔄 Registering validation artifacts | artifacts_count={len(artifacts)}")

    if not artifacts.get("validation_summary_csv"):
        logger.warning(f"No validation_summary_csv artifact found in result")
        return registered_ids

    validation_path = artifacts["validation_summary_csv"]
    logger.debug(f"   Validation artifact path: {validation_path}")

    # Determine S3 bucket
    s3_bucket = os.getenv("S3_METADATA_BUCKET", "primedata-raw")

    # Get file stats from S3
    stat_info = _retrieve_file_stats(s3_bucket, validation_path)
    file_size = stat_info["size"] if stat_info else 0
    checksum = _calculate_file_checksum(s3_bucket, validation_path) or ""
    storage_etag = stat_info.get("etag", "") if stat_info else ""

    # Register in database
    artifact_id = _register_artifact_in_db(
        db=db,
        pipeline_run_id=pipeline_run_id,
        workspace_id=workspace_id,
        product_id=product_id,
        version=version,
        stage_name="validation",
        artifact_type=ArtifactType.CSV,
        artifact_name="validation_summary",
        storage_bucket=s3_bucket,
        storage_key=validation_path,
        file_size=file_size,
        checksum=checksum,
        storage_etag=storage_etag,
        artifact_metadata={
            "entries_processed": result.metrics.get("entries_processed", 0),
        },
        input_artifact_ids=input_artifact_ids,
    )
    if artifact_id:
        registered_ids.append(artifact_id)

    return registered_ids


def _register_indexing_artifacts(
    db: Session,
    pipeline_run_id: UUID,
    workspace_id: UUID,
    product_id: UUID,
    version: int,
    result: Any,
    input_artifact_ids: Optional[List[UUID]] = None,
) -> List[UUID]:
    """Register indexing stage artifacts (OpenSearch/vector collections).

    Responsibility: Record the vector collection name and indexing metrics in pipeline_artifacts.
    """
    registered_ids = []

    logger.info(f"🔄 Registering indexing artifacts | metrics={result.metrics}")

    # Extract collection name from metrics (set by IndexingStage)
    collection_name = result.metrics.get("collection_name")
    if not collection_name:
        logger.warning(f"No collection_name found in indexing metrics")
        return registered_ids

    # Register in database - the key thing is to preserve collection_name in artifact_metadata
    # This allows the promote endpoint to find the correct OpenSearch collection
    artifact_id = _register_artifact_in_db(
        db=db,
        pipeline_run_id=pipeline_run_id,
        workspace_id=workspace_id,
        product_id=product_id,
        version=version,
        stage_name="indexing",
        artifact_type=ArtifactType.VECTOR,
        artifact_name="vector_collection",
        storage_bucket="opensearch",  # Virtual bucket - vectors live in OpenSearch, not S3
        storage_key=collection_name,  # Collection name is the key
        file_size=result.metrics.get("points_indexed", 0),  # Number of vectors
        checksum="",
        storage_etag="",
        artifact_metadata={
            "collection_name": collection_name,  # Critical for promote endpoint!
            "points_indexed": result.metrics.get("points_indexed", 0),
            "embedding_model": result.metrics.get("embedding_model", ""),
            "embedding_dimension": result.metrics.get("embedding_dimension", 0),
            "vector_quality_score": result.metrics.get("Vector_Quality_Score"),
        },
        input_artifact_ids=input_artifact_ids,
    )
    if artifact_id:
        registered_ids.append(artifact_id)

    return registered_ids


def register_stage_artifacts(
    db: Session,
    pipeline_run_id: UUID,
    workspace_id: UUID,
    product_id: UUID,
    version: int,
    stage_name: str,
    result: Any,  # StageResult
    storage: Any,  # AirdStorageAdapter
    input_artifact_ids: Optional[List[UUID]] = None,
) -> List[UUID]:
    """Register artifacts generated by a stage - ORCHESTRATOR.

    Responsibility: Coordinate artifact registration by delegating to stage-specific handlers.
    """
    logger.info(f"📋 Starting artifact registration for stage: {stage_name}")
    logger.debug(f"   Pipeline: {pipeline_run_id}")
    logger.debug(f"   Product: {product_id}, Version: {version}")

    if result.status != StageStatus.SUCCEEDED:
        logger.warning(f"Stage {stage_name} Can  (status={result.status}), skipping artifact registration")
        return []

    # Delegate to stage-specific handler
    if stage_name == "preprocess":
        return _register_preprocess_artifacts(
            db, pipeline_run_id, workspace_id, product_id, version, result, input_artifact_ids
        )
    elif stage_name == "scoring":
        return _register_scoring_artifacts(
            db, pipeline_run_id, workspace_id, product_id, version, result, input_artifact_ids
        )
    elif stage_name == "fingerprint":
        return _register_fingerprint_artifacts(
            db, pipeline_run_id, workspace_id, product_id, version, result, storage, input_artifact_ids
        )
    elif stage_name == "reporting":
        return _register_reporting_artifacts(
            db, pipeline_run_id, workspace_id, product_id, version, result, storage, input_artifact_ids
        )
    elif stage_name == "validation":
        return _register_validation_artifacts(
            db, pipeline_run_id, workspace_id, product_id, version, result, storage, input_artifact_ids
        )
    elif stage_name == "indexing":
        return _register_indexing_artifacts(
            db, pipeline_run_id, workspace_id, product_id, version, result, input_artifact_ids
        )
    else:
        logger.debug(f"No artifact registration logic for stage: {stage_name}")
        return []
