"""
Airflow DAG Task Functions - Modular Task Definitions

This module contains all task functions for Airflow DAGs.
Following enterprise best practices:
- Separation of concerns: DAG orchestration vs business logic
- Modularity: Task functions are reusable and testable
- Maintainability: Business logic in one place, DAG files stay minimal
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from primedata.utils.logger import get_logger, configure_logging
from primedata.db.database import get_db

# Configure logging for Airflow tasks (DEBUG level by default, can be overridden with LOG_LEVEL env var)
configure_logging()

logger = get_logger(__name__)
from primedata.db.models import (
    ArtifactStatus,
    ArtifactType,
    PipelineRun,
    PolicyStatus,
    Product,
    RawFile,
    RawFileStatus,
    RetentionPolicy,
)

# NOTE: AIRD stage imports are done lazily inside functions to avoid DAG import timeouts
# Airflow has a 30s timeout for DAG imports, and importing all stages at module level
# causes heavy import chains (embedding_config, sentence_transformers, etc.) that exceed this limit.
# Import only lightweight enums at module level.
from primedata.ingestion_pipeline.aird_stages.base import StageStatus
from primedata.ingestion_pipeline.pipeline_config import (
    should_skip_vectors,
)
from primedata.config import resolve_effective_config
from primedata.ingestion_pipeline.artifact_registry import (
    calculate_checksum,
    get_artifact_summary_for_run,
)
from primedata.storage.storage_client import storage_client
from sqlalchemy.orm import Session

# Re-export extracted functions for backward compatibility
from primedata.ingestion_pipeline.dag_context import (
    get_dag_params,
    get_aird_context,
    _get_versions_from_context,
    get_pipeline_run_id_from_context,
    raise_if_stage_failed,
)
from primedata.ingestion_pipeline.stage_artifact_registry import (
    _retrieve_file_stats,
    _calculate_file_checksum,
    _register_preprocess_artifacts,
    _register_scoring_artifacts,
    _register_fingerprint_artifacts,
    _register_reporting_artifacts,
    _register_validation_artifacts,
    _register_indexing_artifacts,
    register_stage_artifacts,
)
from primedata.ingestion_pipeline.auto_detection import (
    sample_files_for_analysis,
    auto_detect_playbook_and_chunking,
)

# Re-export stage task functions for backward compatibility
from primedata.ingestion_pipeline.dag_stage_tasks import (
    task_preprocess,
    task_scoring,
    task_fingerprint,
    task_validation,
    task_policy,
    task_reporting,
    task_indexing,
    task_validate_data_quality,
    task_decide_vector_indexing,
    task_record_vectors_skipped,
)



def mark_raw_files_as_failed(product_id: UUID, version: int, error_message: str, db_session=None) -> int:
    """
    Mark all PROCESSING raw files for a product/version as FAILED.

    This helper can be called from any task to mark files as failed when pipeline fails.

    Args:
        product_id: Product UUID
        version: Version number
        error_message: Error message to store
        db_session: Database session (will create new one if None)

    Returns:
        Number of files marked as FAILED
    """
    logger.info(f"📁 ENTRY: mark_raw_files_as_failed(product_id={product_id}, version={version})")
    logger.debug(f"   Error message: {error_message}")

    if db_session is None:
        db = next(get_db())
        should_close = True
    else:
        db = db_session
        should_close = False

    try:
        logger.debug(f"   💾 Querying raw files with status=PROCESSING")
        raw_files_to_fail = (
            db.query(RawFile)
            .filter(RawFile.product_id == product_id, RawFile.version == version, RawFile.status == RawFileStatus.PROCESSING)
            .all()
        )
        logger.debug(f"   ✅ Found {len(raw_files_to_fail)} files to mark as failed")

        if raw_files_to_fail:
            for record in raw_files_to_fail:
                record.status = RawFileStatus.FAILED
                record.error_message = error_message
            db.commit()
            logger.info(f"✅ EXIT: mark_raw_files_as_failed() -> Marked {len(raw_files_to_fail)} raw files as FAILED")
            return len(raw_files_to_fail)
        logger.info(f"✅ EXIT: mark_raw_files_as_failed() -> No files to mark")
        return 0
    except Exception as e:
        logger.error(f"   ❌ Error marking files as failed: {e}", exc_info=True)
        db.rollback()
        return 0
    finally:
        if should_close:
            logger.debug(f"   📁 Closing database connection")
            db.close()


def update_pipeline_status(pipeline_run_id: str, status: str, metrics: Dict[str, Any] = None):
    """Update pipeline run status in the database via API."""
    logger.info(f"📊 ENTRY: update_pipeline_status(pipeline_run_id={pipeline_run_id}, status={status})")
    logger.debug(f"   Metrics keys: {list(metrics.keys()) if metrics else 'None'}")

    try:
        import requests

        # Get the backend URL from environment
        # Priority: explicit env var > docker-compose service name > localhost > host.docker.internal
        backend_url = os.getenv("PRIMEDATA_BACKEND_URL")

        logger.info(f"   ✅ Using PRIMEDATA_BACKEND_URL env var: {backend_url}")

        logger.debug(f"   Backend URL: {backend_url}")

        # Update the pipeline run status
        update_data = {
            "status": status,
            "finished_at": datetime.utcnow().isoformat() if status in ["succeeded", "failed"] else None,
            "metrics": metrics or {},
        }

        logger.debug(f"   📡 Sending PATCH request to API")
        response = requests.patch(
            f"{backend_url}/api/v1/pipeline/runs/{pipeline_run_id}",
            json=update_data,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )

        logger.debug(f"   📡 Response status code: {response.status_code}")

        if response.status_code == 200:
            logger.info(f"✅ EXIT: update_pipeline_status() -> Successfully updated to {status}")
        else:
            logger.error(f"❌ Failed to update pipeline run {pipeline_run_id}: {response.status_code} - {response.text}")

    except Exception as e:
        logger.error(f"❌ Error updating pipeline run {pipeline_run_id}: {e}", exc_info=True)
        logger.warning(f"   💡 Tip: Set PRIMEDATA_BACKEND_URL env var to specify backend URL")


def task_finalize(**context) -> Dict[str, Any]:
    """Finalize pipeline - ORCHESTRATOR. Responsibility: Coordinate finalization steps."""
    params = get_dag_params(**context)
    workspace_id = params["workspace_id"]
    product_id = params["product_id"]
    version = params["version"]
    raw_file_version = params.get("raw_file_version", version)
    pipeline_run_id = get_pipeline_run_id_from_context(**context)

    logger.info(f"🏁 =============== FINALIZING PIPELINE ===============")
    logger.info(f"   Pipeline Run ID: {pipeline_run_id}")
    logger.info(f"   Product: {product_id}, Version: {version}")

    db = next(get_db())

    try:
        # Step 1: Update pipeline status
        logger.info(f"📊 [Step 1/4] Updating pipeline run status...")
        _finalize_update_pipeline_status(pipeline_run_id, version)

        # Step 2: Update product status
        logger.info(f"📝 [Step 2/4] Updating product status...")
        _finalize_update_product_status(db, product_id, version)

        # Step 3: Mark raw files as processed
        logger.info(f"📂 [Step 3/4] Finalizing raw files...")
        _finalize_mark_raw_files_processed(db, product_id, raw_file_version)

        # Step 4: Generate artifact summary
        logger.info(f"📦 [Step 4/4] Generating artifact summary...")
        _finalize_generate_artifact_summary(db, pipeline_run_id)

        logger.info(f"🏁 =============== PIPELINE FINALIZED SUCCESSFULLY ===============")

        return {
            "status": "succeeded",
            "product_id": str(product_id),
            "version": version,
            "pipeline_run_id": str(pipeline_run_id) if pipeline_run_id else None,
        }

    except Exception as e:
        logger.error(f"❌ Error finalizing pipeline: {e}", exc_info=True)
        mark_raw_files_as_failed(product_id, raw_file_version, f"Finalization failed: {str(e)}", db_session=db)
        raise
    finally:
        db.close()


# Helper functions for task_finalize - each with single responsibility

def _finalize_update_pipeline_status(pipeline_run_id: Optional[str], version: int) -> None:
    """Update pipeline run status to succeeded. Responsibility: API call to update status."""
    if pipeline_run_id:
        update_pipeline_status(
            pipeline_run_id,
            "succeeded",
            {
                "pipeline_duration": "complete",
                "product_status": "ready",
                "version": version,
            },
        )
        logger.info(f"   ✅ Pipeline status updated to 'succeeded'")
    else:
        logger.warning(f"   ⚠️  No pipeline_run_id found, skipping status update")


def _finalize_update_product_status(db: Session, product_id: UUID, version: int) -> None:
    """Update product status to ready. Responsibility: Update product record in database."""
    product = db.query(Product).filter(Product.id == product_id).first()
    if product:
        logger.debug(f"   Product found: {product.name}")
        logger.debug(f"   Current status: {product.status}")
        logger.debug(f"   Current version: {product.current_version}")

        product.status = "ready"
        product.current_version = version
        db.commit()
        logger.info(f"   ✅ Product marked as ready with version {version}")
    else:
        logger.warning(f"   ⚠️  Product {product_id} not found in database")


def _finalize_mark_raw_files_processed(db: Session, product_id: UUID, raw_file_version: int) -> None:
    """Mark all PROCESSING raw files as PROCESSED. Responsibility: Update raw file statuses."""
    logger.debug(f"   Looking for PROCESSING files: product_id={product_id}, version={raw_file_version}")

    raw_files_to_finalize = (
        db.query(RawFile)
        .filter(
            RawFile.product_id == product_id,
            RawFile.version == raw_file_version,
            RawFile.status == RawFileStatus.PROCESSING,
        )
        .all()
    )

    if raw_files_to_finalize:
        logger.info(f"   Found {len(raw_files_to_finalize)} PROCESSING files to finalize")
        for idx, record in enumerate(raw_files_to_finalize, 1):
            record.status = RawFileStatus.PROCESSED
            record.processed_at = datetime.utcnow()
            record.error_message = None  # Clear any previous error messages
            if idx <= 3:  # Log first 3 files
                logger.debug(f"   [{idx}] {record.filename} -> PROCESSED")
            elif idx == 4:
                logger.debug(f"   ... and {len(raw_files_to_finalize) - 3} more files")

        db.commit()
        logger.info(f"   ✅ Marked {len(raw_files_to_finalize)} raw files as PROCESSED")
    else:
        logger.warning(f"   ⚠️  No PROCESSING raw files found to finalize")


def _finalize_generate_artifact_summary(db: Session, pipeline_run_id: Optional[str]) -> None:
    """Generate and log artifact summary. Responsibility: Retrieve and display artifact statistics."""
    if not pipeline_run_id:
        logger.warning(f"   ⚠️  No pipeline_run_id found, skipping artifact summary")
        return

    try:
        pipeline_run_uuid = UUID(pipeline_run_id) if isinstance(pipeline_run_id, str) else pipeline_run_id
        pipeline_run = db.query(PipelineRun).filter(PipelineRun.id == pipeline_run_uuid).first()

        if pipeline_run:
            db.expire_all()
            artifact_summary = get_artifact_summary_for_run(db, pipeline_run_uuid)

            logger.info(f"   ✅ Artifact Summary:")
            logger.info(f"      Total Artifacts: {artifact_summary['total_artifacts']}")
            logger.info(f"      By Stage:")
            for stage, count in artifact_summary.get("by_stage", {}).items():
                logger.info(f"        - {stage}: {count}")
            logger.info(f"      By Type:")
            for atype, count in artifact_summary.get("by_type", {}).items():
                logger.info(f"        - {atype}: {count}")
            logger.info(f"      Total Size: {artifact_summary['total_size_bytes']} bytes")
        else:
            logger.warning(f"   ⚠️  Pipeline run not found")
    except Exception as e:
        logger.error(f"   ❌ Error generating artifact summary: {e}", exc_info=True)
