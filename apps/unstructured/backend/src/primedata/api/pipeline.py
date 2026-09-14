"""
Pipeline API endpoints for PrimeData.

This module provides REST API endpoints for managing data processing pipelines,
including triggering pipeline runs and monitoring their status.
"""

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from primedata.api.billing import check_billing_limits
from primedata.core.plan_limits import get_plan_limit
from primedata.core.settings import get_settings
from primedata.core.scope import allowed_workspaces, ensure_product_access
from primedata.db.database import get_db
from primedata.db.models import PipelineRun, PipelineRunStatus, Product, RawFile, RawFileStatus
from pydantic import BaseModel, ConfigDict
from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from primedata.api.airflow_client import (
    _sync_pipeline_runs_with_airflow,
    _trigger_airflow_dag,
)
from primedata.utils.logger import get_logger
logger = get_logger(__name__)

# Airflow DAG Configuration
AIRFLOW_DAG_ID = os.getenv("AIRFLOW_DAG_ID", "primedata_simple")  # Default DAG ID for pipeline orchestration
logger.debug(f"🔧 Airflow DAG ID configured: {AIRFLOW_DAG_ID}")

router = APIRouter(prefix="/api/v1/pipeline", tags=["Pipeline"])


class PipelineRunRequest(BaseModel):
    """Request model for triggering a pipeline run."""

    product_id: UUID
    version: Optional[int] = None
    force_run: Optional[bool] = False


class PipelineRunResponse(BaseModel):
    """Response model for pipeline run information."""

    model_config = ConfigDict(from_attributes=True)  # Pydantic v2 syntax

    id: UUID
    product_id: UUID
    version: int
    status: str
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    dag_run_id: Optional[str]
    metrics: Dict[str, Any]
    created_at: datetime


class TriggerPipelineResponse(BaseModel):
    """Response model for pipeline trigger."""

    product_id: UUID
    version: int
    run_id: UUID
    status: str
    message: str



def _check_pipeline_billing_limit(db: Session, product: Product, settings) -> None:
    """Check pipeline run billing limits for the current month.

    :param db: Database session.
    :param product: The product being triggered.
    :param settings: Application settings instance.
    :raises HTTPException: If the monthly pipeline run limit is exceeded.
    """
    if settings.ENV == "production":
        logger.debug(f"🔍 Checking pipeline run limits (production mode)")
        billing_profile = db.query(BillingProfile).filter(
            BillingProfile.workspace_id == product.workspace_id
        ).first()

        if billing_profile:
            plan_name = (
                billing_profile.plan.value.lower()
                if hasattr(billing_profile.plan, "value")
                else str(billing_profile.plan).lower()
            )
            max_runs = get_plan_limit(plan_name, "max_pipeline_runs_per_month")
            logger.debug(f"Plan: {plan_name}, max_runs: {max_runs}")

            if max_runs != -1:  # If not unlimited
                # Count pipeline runs in current month
                now = datetime.now(timezone.utc)
                month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
                current_month_runs = (
                    db.query(func.count(PipelineRun.id))
                    .filter(
                        and_(
                            PipelineRun.workspace_id == product.workspace_id,
                            PipelineRun.started_at >= month_start,
                        )
                    )
                    .scalar()
                    or 0
                )

                if current_month_runs >= max_runs:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=(
                            "Pipeline runs limit exceeded. You have used "
                            f"{current_month_runs} of {max_runs} runs this month. "
                            "Please upgrade your plan or wait until next month."
                        ),
                    )


def _resolve_raw_file_version(db: Session, product: Product, request_version: Optional[int]) -> int:
    """Resolve which raw file version to process.

    :param db: Database session.
    :param product: The product being triggered.
    :param request_version: Explicitly requested version, or None for auto-detection.
    :return: The resolved raw file version integer.
    :raises HTTPException: If no raw files are found for the requested or auto-detected version.
    """
    # Option C: Smart Version Resolution (Enterprise Best Practice)
    # If version is explicitly provided, validate it exists
    # If version is None, auto-detect latest ingested version
    # This determines which raw file version to process (separate from pipeline run version)
    if request_version is not None:
        # Explicit version provided - validate raw files exist
        # Include PROCESSED files to allow reprocessing with new configurations
        raw_file_version = request_version
        raw_file_count = (
            db.query(RawFile)
            .filter(
                RawFile.product_id == product.id,
                RawFile.version == raw_file_version,
                RawFile.status.in_(
                    [RawFileStatus.INGESTED, RawFileStatus.FAILED, RawFileStatus.PROCESSING, RawFileStatus.PROCESSED]
                ),
            )
            .count()
        )

        if raw_file_count == 0:
            # Provide helpful error message with available versions
            latest_version = (
                db.query(func.max(RawFile.version))
                .filter(RawFile.product_id == product.id, RawFile.status != RawFileStatus.DELETED)
                .scalar()
            )

            # Get all available versions
            available_versions = (
                db.query(RawFile.version)
                .filter(RawFile.product_id == product.id, RawFile.status != RawFileStatus.DELETED)
                .distinct()
                .order_by(RawFile.version.desc())
                .all()
            )

            available_versions_list = [v[0] for v in available_versions] if available_versions else []

            error_detail = {
                "message": f"No raw files found for version {raw_file_version}",
                "requested_version": raw_file_version,
                "latest_ingested_version": latest_version,
                "available_versions": available_versions_list,
                "suggestion": (
                    f"Please run initial ingestion for version {raw_file_version}, "
                    f"or use version={latest_version} to process latest ingested data"
                    if latest_version
                    else "Please run initial ingestion first"
                ),
            }

            logger.warning(
                f"Pipeline trigger failed: No raw files for product {product.id}, version {raw_file_version}. "
                f"Available versions: {available_versions_list}"
            )

            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error_detail)

        logger.info(f"Using explicit raw file version {raw_file_version} (validated: {raw_file_count} raw files found)")
    else:
        # Auto-detect: Pick the latest raw file version regardless of status (except DELETED)
        # This allows retrying failed pipelines easily - picks latest version with any status
        logger.debug(f"   📋 Auto-detecting latest raw file for product_id={product.id}")

        latest_raw_file = (
            db.query(RawFile)
            .filter(RawFile.product_id == product.id, RawFile.status != RawFileStatus.DELETED)
            .order_by(RawFile.version.desc())
            .first()
        )

        logger.debug(f"   💾 Raw file query executed | result={latest_raw_file is not None}")

        if not latest_raw_file:
            error_detail = {
                "message": "No raw files found for this product",
                "suggestion": "Please run initial ingestion first to upload data",
            }
            logger.warning(f"⚠️  Pipeline trigger failed: No raw files for product {product.id}")
            logger.debug(f"   ❌ Product exists but no raw files: product_id={product.id}, product_name={product.name}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_detail)

        raw_file_version = latest_raw_file.version
        logger.debug(f"   ✓ Raw file found | version={raw_file_version}, status={latest_raw_file.status.value}")
        logger.info(
            f"✅ Auto-detected latest raw file: version={raw_file_version}, "
            f"status={latest_raw_file.status.value}, filename={latest_raw_file.filename}"
        )

    return raw_file_version


def _handle_existing_running_pipeline(db: Session, product_id: UUID, force_run: bool) -> None:
    """Check for an existing running pipeline and handle conflicts.

    :param db: Database session.
    :param product_id: The product ID to check for running pipelines.
    :param force_run: If True, cancel the existing run instead of raising an error.
    :raises HTTPException: If a pipeline is already running and force_run is False.
    """
    # Check if there's already a running pipeline (regardless of version)
    # Only block if there's a QUEUED or RUNNING pipeline for this product
    existing_running_run = (
        db.query(PipelineRun)
        .filter(
            PipelineRun.product_id == product_id,
            PipelineRun.status.in_([PipelineRunStatus.QUEUED, PipelineRunStatus.RUNNING]),
        )
        .first()
    )

    if existing_running_run:
        # Check if user wants to force run (override existing)
        if not force_run:
            # Provide helpful error message with details about existing run
            status_msg = existing_running_run.status.value.lower()
            started_msg = ""
            if existing_running_run.started_at:
                now = datetime.now(timezone.utc)
                elapsed = now - existing_running_run.started_at.replace(tzinfo=timezone.utc)
                started_msg = f" (running for {int(elapsed.total_seconds() / 60)} minutes)"

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": f"A pipeline run is already {status_msg} for this product (version {existing_running_run.version}){started_msg}",
                    "existing_run_id": str(existing_running_run.id),
                    "existing_status": existing_running_run.status.value,
                    "existing_started_at": existing_running_run.started_at.isoformat() if existing_running_run.started_at else None,
                    "suggestion": "You can force run to cancel the existing run and start a new one, or wait for the current run to complete.",
                },
            )
        else:
            # Cancel existing run and start new one
            logger.info(f"Cancelling existing pipeline run {existing_running_run.id} to start new run")
            existing_running_run.status = PipelineRunStatus.FAILED
            existing_running_run.finished_at = datetime.utcnow()
            existing_running_run.metrics = existing_running_run.metrics or {}
            existing_running_run.metrics["cancelled_reason"] = "Replaced by new pipeline run"
            db.commit()


def _reprocess_if_needed(db: Session, product_id: UUID, raw_file_version: int) -> int:
    """Handle reprocessing of already-processed files by creating a new version.

    :param db: Database session.
    :param product_id: The product ID to check for reprocessing.
    :param raw_file_version: The current raw file version.
    :return: The potentially-updated raw file version integer.
    :raises HTTPException: If file copy operations fail during reprocessing.
    """
    # Check if we're reprocessing already-processed files - if so, create a new version
    # Only do this if version was auto-detected (not explicitly provided)

    # First, check if there are any existing raw files for this version that might be missing files in storage
    existing_files_for_version = (
        db.query(RawFile)
        .filter(
            RawFile.product_id == product_id,
            RawFile.version == raw_file_version,
            RawFile.status.in_([RawFileStatus.FAILED, RawFileStatus.INGESTED, RawFileStatus.PROCESSING]),
        )
        .all()
    )

    # Check if any of these files are missing in storage and need to be copied from previous version
    if existing_files_for_version:
        from primedata.storage.storage_client import storage_client as storage_client_instance

        files_need_copy = []

        for existing_file in existing_files_for_version:
            if not storage_client_instance.object_exists(existing_file.storage_bucket, existing_file.storage_key):
                # File doesn't exist, need to find the original source file from previous version
                # Find the original PROCESSED file from previous versions
                original_file = (
                    db.query(RawFile)
                    .filter(
                        RawFile.product_id == product_id,
                        RawFile.filename == existing_file.filename,
                        RawFile.status == RawFileStatus.PROCESSED,
                    )
                    .order_by(RawFile.version.desc())
                    .first()
                )

                if original_file and storage_client_instance.object_exists(
                    original_file.storage_bucket, original_file.storage_key
                ):
                    # Copy from original location
                    logger.info(
                        f"Copying missing file from original version: {original_file.storage_key} to {existing_file.storage_key}"
                    )
                    copy_success = storage_client_instance.copy_object(
                        source_bucket=original_file.storage_bucket,
                        source_key=original_file.storage_key,
                        dest_bucket=existing_file.storage_bucket,
                        dest_key=existing_file.storage_key,
                    )

                    if copy_success:
                        # Verify copy succeeded
                        if storage_client_instance.object_exists(existing_file.storage_bucket, existing_file.storage_key):
                            existing_file.status = RawFileStatus.INGESTED
                            existing_file.error_message = None
                            logger.info(f"Successfully copied file and updated status for {existing_file.filename}")
                        else:
                            logger.error(f"Copy verification failed for {existing_file.filename}")
                    else:
                        logger.error(f"Failed to copy file for {existing_file.filename}")
                else:
                    logger.warning(f"Cannot find source file to copy for {existing_file.filename}")

        if existing_files_for_version:
            db.commit()

    # Now check for PROCESSED files to create a new version from
    processed_files_to_reprocess = (
        db.query(RawFile)
        .filter(
            RawFile.product_id == product_id, RawFile.version == raw_file_version, RawFile.status == RawFileStatus.PROCESSED
        )
        .all()
    )

    if processed_files_to_reprocess:
        # We're reprocessing - create a new raw file version by incrementing
        # Get the maximum raw file version number for this product
        max_raw_file_version = db.query(func.max(RawFile.version)).filter(RawFile.product_id == product_id).scalar() or 0

        new_raw_file_version = max_raw_file_version + 1
        logger.info(
            f"Reprocessing {len(processed_files_to_reprocess)} PROCESSED files from raw file version {raw_file_version} "
            f"to new raw file version {new_raw_file_version} with new configuration"
        )

        # Create new raw file records with the new version (copy the old ones)
        import uuid as uuid_lib

        from primedata.storage.storage_client import storage_client as storage_client_instance
        from primedata.storage.paths import raw_prefix

        for old_raw_file in processed_files_to_reprocess:
            # Update storage_key to use the new version number
            # Extract just the filename from the old storage_key
            # Old format: ws/{ws}/prod/{prod}/v/{old_version}/raw/{filename}
            # New format: ws/{ws}/prod/{prod}/v/{new_raw_file_version}/raw/{filename}
            old_key_parts = old_raw_file.storage_key.split("/")
            filename = old_key_parts[-1]  # Get the filename
            new_storage_key = f"{raw_prefix(old_raw_file.workspace_id, old_raw_file.product_id, new_raw_file_version)}{filename}"

            # Verify source file exists before copying
            source_exists = storage_client_instance.object_exists(old_raw_file.storage_bucket, old_raw_file.storage_key)

            if not source_exists:
                logger.error(f"Source file does not exist in storage: {old_raw_file.storage_key}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Source file {old_raw_file.filename} not found in storage at {old_raw_file.storage_key}. Cannot reprocess.",
                )

            # Check if destination already exists (shouldn't happen, but be safe)
            dest_exists = storage_client_instance.object_exists(old_raw_file.storage_bucket, new_storage_key)
            if dest_exists:
                logger.info(f"Destination file already exists in storage: {new_storage_key}, skipping copy")
            else:
                # Copy the file in storage from old version path to new version path
                logger.info(f"Copying file from {old_raw_file.storage_key} to {new_storage_key}")
                copy_success = storage_client_instance.copy_object(
                    source_bucket=old_raw_file.storage_bucket,
                    source_key=old_raw_file.storage_key,
                    dest_bucket=old_raw_file.storage_bucket,
                    dest_key=new_storage_key,
                )

                if not copy_success:
                    logger.error(f"❌ Failed to copy file from {old_raw_file.storage_key} to {new_storage_key}")
                    logger.error(f"   Source bucket: {old_raw_file.storage_bucket}")
                    logger.error(f"   Destination bucket: {old_raw_file.storage_bucket}")
                    logger.error(f"   Filename: {old_raw_file.filename}")
                    logger.error(f"   File size: {old_raw_file.file_size}")
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"Failed to copy file {old_raw_file.filename} to new version path. "
                               f"Check storage permissions and bucket configuration.",
                    )

                # Verify the copy succeeded
                verify_exists = storage_client_instance.object_exists(old_raw_file.storage_bucket, new_storage_key)
                if not verify_exists:
                    logger.error(f"Copy verification failed: file does not exist at {new_storage_key} after copy")
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"File copy verification failed for {old_raw_file.filename}",
                    )

            new_raw_file = RawFile(
                id=uuid_lib.uuid4(),
                workspace_id=old_raw_file.workspace_id,
                product_id=old_raw_file.product_id,
                data_source_id=old_raw_file.data_source_id,
                version=new_raw_file_version,
                filename=old_raw_file.filename,
                file_stem=old_raw_file.file_stem,
                storage_key=new_storage_key,  # Use new version in the key
                storage_bucket=old_raw_file.storage_bucket,
                file_size=old_raw_file.file_size,
                content_type=old_raw_file.content_type,
                status=RawFileStatus.INGESTED,  # Start as INGESTED for reprocessing
                file_checksum=old_raw_file.file_checksum,
                storage_etag=old_raw_file.storage_etag,
                ingested_at=datetime.utcnow(),
                processed_at=None,
                error_message=None,
            )
            db.add(new_raw_file)
            logger.info(f"Copied file {old_raw_file.filename} from raw file v{raw_file_version} to raw file v{new_raw_file_version} in storage")

        raw_file_version = new_raw_file_version  # Update to use the new raw file version
        db.commit()
        logger.info(f"Created new raw file version {raw_file_version} for reprocessing")

    return raw_file_version


@router.post("/run", response_model=TriggerPipelineResponse)
def trigger_pipeline(
    request: PipelineRunRequest,
    request_obj: Request,
    db: Session = Depends(get_db)
):
    """
    Trigger a pipeline run for a product.

    **Version Management**:
    - Each pipeline run gets a unique version number, independent of raw file version
    - Pipeline run versions increment sequentially (1, 2, 3, ...) for each product
    - Raw file version is stored separately in metrics for traceability
    - Even if a previous run failed, a new run will get a new version number

    **Smart Version Resolution (Enterprise Best Practice)**:
    - If `version` is explicitly provided: Validates that raw files exist for that version
    - If `version` is `None`: Automatically uses the latest ingested version that has raw files

    This ensures seamless workflow: users can simply click "Run Pipeline" without
    manual version coordination. The system automatically processes the latest available data.

    **Examples**:
    - Auto-detect: `{"product_id": "...", "version": null}` → Uses latest ingested version
    - Explicit: `{"product_id": "...", "version": 3}` → Processes version 3 (validates files exist)
    """
    logger.info(f"🚀 Triggering pipeline for product {request.product_id}, version={request.version}")

    # Ensure user has access to the product
    ensure_product_access(db, request_obj, request.product_id)
    logger.debug(f"✓ User access verified for product {request.product_id}")

    # Get the product
    product = db.query(Product).filter(Product.id == request.product_id).first()
    if not product:
        logger.warning(f"⚠️ Product not found: {request.product_id}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    logger.info(f"📊 Pipeline trigger details - workspace: {product.workspace_id}, force_run: {request.force_run}")

    # Check pipeline runs limit for current month (production only)
    settings = get_settings()
    _check_pipeline_billing_limit(db, product, settings)

    # Resolve which raw file version to process
    raw_file_version = _resolve_raw_file_version(db, product, request.version)

    # ALWAYS create a new pipeline run version number (independent of raw file version)
    # Get the maximum existing pipeline run version for this product
    max_pipeline_run_version = (
        db.query(func.max(PipelineRun.version))
        .filter(PipelineRun.product_id == request.product_id)
        .scalar()
    ) or 0

    # Increment to get the next pipeline run version
    pipeline_run_version = max_pipeline_run_version + 1

    logger.info(
        f"Creating new pipeline run version {pipeline_run_version} "
        f"(processing raw files from version {raw_file_version})"
    )

    # Handle existing running pipeline conflicts
    _handle_existing_running_pipeline(db, request.product_id, request.force_run)

    # Check if we're reprocessing already-processed files - if so, create a new version
    # Only do this if version was auto-detected (not explicitly provided)
    if request.version is None:
        raw_file_version = _reprocess_if_needed(db, request.product_id, raw_file_version)

    try:
        # Create pipeline run record with the NEW pipeline run version
        # Store raw file version in metrics for traceability
        pipeline_run = PipelineRun(
            workspace_id=product.workspace_id,
            product_id=request.product_id,
            version=pipeline_run_version,  # Use the new unique pipeline run version
            status=PipelineRunStatus.QUEUED,
            started_at=datetime.now(timezone.utc),  # Explicitly set started_at with timezone
            metrics={
                "raw_file_version": raw_file_version,  # Store the raw file version in metrics for reference
            },
        )
        db.add(pipeline_run)
        db.commit()
        db.refresh(pipeline_run)

        # Refresh product from database to ensure we have latest configuration
        db.refresh(product)

        # Get chunking and embedding configuration from product (after refresh)
        chunking_config = product.chunking_config or {}
        embedding_config = product.embedding_config or {}

        # Log the configuration being passed to Airflow for verification
        logger.info(
            f"Triggering pipeline for product {request.product_id}:\n"
            f"  pipeline_run_version: {pipeline_run_version}\n"
            f"  raw_file_version: {raw_file_version}\n"
            f"  chunking_config: {chunking_config}\n"
            f"  embedding_config: {embedding_config}\n"
            f"  playbook_id: {product.playbook_id}"
        )

        # Trigger Airflow DAG with configuration
        # IMPORTANT:
        # - pipeline_run_version is the version for the PipelineRun record + artifact/Qdrant naming
        # - raw_file_version is only used to select input RawFile rows and stored keys
        logger.info(f"Triggering pipeline for product with airflow dag {request.product_id}:\n")
        dag_run_id = _trigger_airflow_dag(
            workspace_id=product.workspace_id,
            product_id=request.product_id,
            version=pipeline_run_version,  # Airflow uses this as PipelineRun/Artifact/Qdrant version
            pipeline_run_id=pipeline_run.id,
            raw_file_version=raw_file_version,
            chunking_config=chunking_config,
            embedding_config=embedding_config,
            playbook_id=product.playbook_id,
        )
        logger.info(f"✅ Airflow DAG triggered successfully with DAG Run ID: {dag_run_id}")
        # Update pipeline run with DAG run ID
        pipeline_run.dag_run_id = dag_run_id
        pipeline_run.status = PipelineRunStatus.RUNNING
        pipeline_run.started_at = datetime.utcnow()
        db.commit()

        # Create informative message
        version_source = "explicitly provided" if request.version is not None else "auto-detected (latest ingested)"
        message = (
            f"Pipeline run version {pipeline_run_version} triggered successfully "
            f"(processing raw files from version {raw_file_version}, {version_source}). "
            f"DAG Run ID: {dag_run_id}"
        )

        logger.info(
            f"Triggered pipeline run {pipeline_run.id} for product {request.product_id} "
            f"(pipeline_run_version: {pipeline_run_version}, raw_file_version: {raw_file_version}, {version_source})"
        )

        return TriggerPipelineResponse(
            product_id=request.product_id,
            version=pipeline_run_version,  # Return the pipeline run version
            run_id=pipeline_run.id,
            status=pipeline_run.status.value,
            message=message,
        )

    except Exception as e:
        logger.error(f"Failed to trigger pipeline for product {request.product_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to trigger pipeline: {str(e)}")


@router.get("/runs")
async def list_pipeline_runs(
    product_id: UUID,
    request_obj: Request,
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    sync: bool = Query(True, description="Sync with Airflow before returning"),
    db: Session = Depends(get_db)
):
    """
    List pipeline runs for a product with pagination support.
    """
    logger.info(f"🔄 ENTER list_pipeline_runs - product_id={product_id}, limit={limit}, offset={offset}, sync={sync}")
    try:
        # Ensure user has access to the product
        product = ensure_product_access(db, request_obj, product_id)
        logger.debug(f"🔄 ✓ Access verified for product_id={product_id}")

        # Sync with Airflow if requested
        if sync:
            logger.debug(f"🔄 📋 Syncing with Airflow...")
            _sync_pipeline_runs_with_airflow(db)
            logger.debug(f"🔄 ✓ Airflow sync complete")

        # Get pipeline runs - filter by product_id AND workspace_id for security
        # This ensures users can only see pipeline runs for products in their workspaces
        logger.debug(f"🔄 📊 Determining allowed workspaces for security")
        allowed_workspace_ids = allowed_workspaces(request_obj, db)

        # Get total count for pagination
        logger.debug(f"🔄 💾 Querying total pipeline run count")
        total_count = (
            db.query(func.count(PipelineRun.id))
            .join(Product, PipelineRun.product_id == Product.id)
            .filter(PipelineRun.product_id == product_id, Product.workspace_id.in_(allowed_workspace_ids))
            .scalar()
        )

        # Retrieve paginated runs
        logger.debug(f"🔄 💾 Querying pipeline runs with limit={limit}, offset={offset}")
        runs = (
            db.query(PipelineRun)
            .join(Product, PipelineRun.product_id == Product.id)
            .filter(PipelineRun.product_id == product_id, Product.workspace_id.in_(allowed_workspace_ids))
            .order_by(PipelineRun.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        logger.debug(f"💾 Retrieved {len(runs)} pipeline runs from database (total: {total_count})")

        # Lazy-load metrics from S3 if archived
        logger.debug(f"🔄 Loading metrics for {len(runs)} pipeline runs")
        from primedata.services.lazy_json_loader import load_pipeline_run_metrics

        result = {
            "runs": [
                PipelineRunResponse(
                    id=run.id,
                    product_id=run.product_id,
                    version=run.version,
                    status=run.status.value,
                    started_at=run.started_at,
                    finished_at=run.finished_at,
                    dag_run_id=run.dag_run_id,
                    metrics=load_pipeline_run_metrics(run),
                    created_at=run.created_at,
                )
                for run in runs
            ],
            "total": total_count,
            "limit": limit,
            "offset": offset,
        }
        logger.info(f"✅ EXIT list_pipeline_runs - returned {len(result['runs'])} runs from {total_count} total")
        return result
    except Exception as e:
        logger.error(f"❌ EXIT list_pipeline_runs FAILED - product_id={product_id}: {e}", exc_info=True)
        raise


@router.get("/runs/{run_id}", response_model=PipelineRunResponse)
async def get_pipeline_run(
    run_id: UUID, request_obj: Request, db: Session = Depends(get_db)
):
    """
    Get details of a specific pipeline run.
    """
    logger.info(f"🔄 ENTER get_pipeline_run - run_id={run_id}")
    try:
        # Get pipeline run
        logger.debug(f"🔄 💾 Querying database for pipeline run_id={run_id}")
        run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
        if not run:
            logger.warning(f"⚠️ Pipeline run not found: run_id={run_id}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline run not found")

        logger.debug(f"🔄 ✓ Found pipeline run with status={run.status.value}")

        # Ensure user has access to the product
        logger.debug(f"🔄 🔐 Verifying access to product_id={run.product_id}")
        ensure_product_access(db, request_obj, run.product_id)
        logger.debug(f"🔄 ✓ Access verified for product_id={run.product_id}")

        # Lazy-load metrics from S3 if archived
        logger.debug(f"🔄 Loading metrics from S3 storage")
        from primedata.services.lazy_json_loader import load_pipeline_run_metrics

        metrics = load_pipeline_run_metrics(run)
        logger.debug(f"📊 Metrics loaded - keys: {list(metrics.keys()) if metrics else []}")

        response = PipelineRunResponse(
            id=run.id,
            product_id=run.product_id,
            version=run.version,
            status=run.status.value,
            started_at=run.started_at,
            finished_at=run.finished_at,
            dag_run_id=run.dag_run_id,
            metrics=metrics,
            created_at=run.created_at,
        )
        logger.info(f"✅ EXIT get_pipeline_run - run_id={run_id}, status={run.status.value}")
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ EXIT get_pipeline_run FAILED - run_id={run_id}: {e}", exc_info=True)
        raise


class PipelineRunUpdateRequest(BaseModel):
    """Request model for updating a pipeline run."""

    status: Optional[str] = None
    finished_at: Optional[str] = None
    metrics: Optional[Dict[str, Any]] = None


@router.patch("/runs/{run_id}")
async def update_pipeline_run(
    run_id: UUID,
    request_body: PipelineRunUpdateRequest,
    request_obj: Request,
    db: Session = Depends(get_db)
):
    """
    Update a pipeline run status (used by Airflow DAG or for manual cancellation).
    """
    logger.info(f"🔄 ENTER update_pipeline_run - run_id={run_id}, status={request_body.status}")
    try:
        logger.debug(f"🔄 💾 Querying database for pipeline run_id={run_id}")
        run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
        if not run:
            logger.warning(f"⚠️ Pipeline run not found: run_id={run_id}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline run not found")

        # Ensure user has access to the product
        logger.debug(f"🔄 🔐 Verifying access to product_id={run.product_id}")
        ensure_product_access(db, request_obj, run.product_id)
        logger.debug(f"🔄 ✓ Access verified")

        # Update fields if provided
        if request_body.status is not None:
            logger.debug(f"🔄 📋 Updating status to {request_body.status}")
            try:
                new_status = PipelineRunStatus(request_body.status)
                # If cancelling a running/queued pipeline, mark it as failed
                if new_status == PipelineRunStatus.FAILED and run.status in [PipelineRunStatus.RUNNING, PipelineRunStatus.QUEUED]:
                    logger.info(f"🔄 Cancelling pipeline run {run_id} (was {run.status.value})")

                    # Cancel the DAG run in Airflow if dag_run_id exists
                    if run.dag_run_id:
                        try:
                            logger.debug(f"🔄 Attempting to cancel DAG run {run.dag_run_id} in Airflow")
                            import requests
                            from requests.auth import HTTPBasicAuth

                            # Use same environment variables as get_pipeline_run_logs
                            # ⚠️ WARNING: Replace with your actual Airflow URL and credentials in production!
                            airflow_url = os.getenv("AIRFLOW_URL", "http://localhost:8080")
                            # ⚠️ WARNING: Set AIRFLOW_USERNAME environment variable!
                            airflow_username = os.getenv("AIRFLOW_USERNAME")
                            if not airflow_username:
                                logger.error("❌ AIRFLOW_USERNAME environment variable must be set")
                                raise ValueError("AIRFLOW_USERNAME environment variable must be set")
                            airflow_password = os.getenv("AIRFLOW_PASSWORD")  # Must be set via environment variable
                            if not airflow_password:
                                logger.error("❌ AIRFLOW_PASSWORD environment variable must be set")
                                raise ValueError("AIRFLOW_PASSWORD environment variable must be set")

                            dag_id = AIRFLOW_DAG_ID
                            # Use PATCH to update DAG run state to failed (stops execution)
                            cancel_url = f"{airflow_url}/api/v1/dags/{dag_id}/dagRuns/{run.dag_run_id}"

                            logger.debug(f"🔄 Sending PATCH to {cancel_url}")
                            cancel_response = requests.patch(
                                cancel_url,
                                json={"state": "failed"},
                                auth=HTTPBasicAuth(airflow_username, airflow_password),
                                timeout=10,
                            )

                            if cancel_response.status_code == 200:
                                logger.info(f"✅ Successfully cancelled DAG run {run.dag_run_id} in Airflow")
                            else:
                                logger.warning(f"⚠️ Failed to cancel DAG run in Airflow: {cancel_response.status_code} - {cancel_response.text}")
                        except Exception as e:
                            logger.warning(f"⚠️ Failed to cancel DAG run in Airflow (continuing with DB update): {e}")

                    run.status = PipelineRunStatus.FAILED
                    run.finished_at = datetime.utcnow()
                    if not run.metrics:
                        run.metrics = {}
                    run.metrics["cancelled_reason"] = "Manually cancelled by user"
                    logger.debug(f"🔄 ✓ Set status to FAILED with cancelled_reason")
                else:
                    run.status = new_status
                    logger.debug(f"🔄 ✓ Set status to {new_status.value}")
            except ValueError as e:
                logger.error(f"❌ Invalid status value: {request_body.status}", exc_info=True)
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid status: {request_body.status}")

        if request_body.finished_at is not None:
            logger.debug(f"🔄 📋 Updating finished_at to {request_body.finished_at}")
            try:
                run.finished_at = datetime.fromisoformat(request_body.finished_at.replace("Z", "+00:00"))
                logger.debug(f"🔄 ✓ finished_at set")
            except ValueError as e:
                logger.error(f"❌ Invalid finished_at format: {request_body.finished_at}", exc_info=True)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid finished_at format: {request_body.finished_at}"
                )

        if request_body.metrics is not None:
            logger.debug(f"🔄 📋 Updating metrics with {len(request_body.metrics)} keys")
            if run.metrics:
                run.metrics.update(request_body.metrics)
            else:
                run.metrics = request_body.metrics
            logger.debug(f"🔄 ✓ Metrics updated")

        logger.debug(f"💾 Committing changes to database for run_id={run_id}")
        db.commit()
        db.refresh(run)
        logger.debug(f"💾 ✓ Database commit complete")

        # Lazy-load metrics from S3 if archived
        logger.debug(f"🔄 Loading metrics from S3 storage")
        from primedata.services.lazy_json_loader import load_pipeline_run_metrics

        metrics = load_pipeline_run_metrics(run)

        response = PipelineRunResponse(
            id=run.id,
            product_id=run.product_id,
            version=run.version,
            status=run.status.value,
            started_at=run.started_at,
            finished_at=run.finished_at,
            dag_run_id=run.dag_run_id,
            metrics=metrics,
            created_at=run.created_at,
        )
        logger.info(f"✅ EXIT update_pipeline_run - run_id={run_id}, new_status={run.status.value}")
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ EXIT update_pipeline_run FAILED - run_id={run_id}: {e}", exc_info=True)
        raise


# Side-effect imports: register route handlers from sub-modules
import primedata.api.pipeline_status  # noqa: F401
import primedata.api.pipeline_artifacts  # noqa: F401
