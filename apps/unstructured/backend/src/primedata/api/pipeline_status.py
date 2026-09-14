"""
Pipeline status, sync, logs, and chunking-config endpoints.

These route handlers are registered on the shared router from pipeline.py.
"""

import os
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from primedata.api.airflow_client import (
    _sync_pipeline_runs_with_airflow,
)
from primedata.api.pipeline import router, AIRFLOW_DAG_ID
from primedata.core.scope import ensure_product_access
from primedata.db.database import get_db
from primedata.db.models import PipelineRun, PipelineRunStatus
from primedata.utils.logger import get_logger

logger = get_logger(__name__)


@router.post("/sync")
async def sync_pipeline_runs_with_airflow(
    request_obj: Request, db: Session = Depends(get_db)
):
    """
    Manually sync all running pipeline runs with Airflow status.
    """
    logger.info(f"🔄 ENTER sync_pipeline_runs_with_airflow")
    try:
        logger.debug(f"🔄 📋 Starting manual sync with Airflow for all running pipelines")
        updated_count = _sync_pipeline_runs_with_airflow(db)
        logger.debug(f"💾 Updated {updated_count} pipeline runs from Airflow status")
        result = {"message": f"Successfully synced {updated_count} pipeline runs with Airflow", "updated_count": updated_count}
        logger.info(f"✅ EXIT sync_pipeline_runs_with_airflow - synced {updated_count} runs")
        return result
    except Exception as e:
        logger.error(f"❌ EXIT sync_pipeline_runs_with_airflow FAILED: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to sync with Airflow: {str(e)}")


@router.get("/status/{run_id}")
async def get_pipeline_status(
    run_id: UUID, request_obj: Request, db: Session = Depends(get_db)
):
    """
    Get the current status of a pipeline run.
    """
    logger.info(f"🔄 ENTER get_pipeline_status - run_id={run_id}")
    try:
        # Get pipeline run
        logger.debug(f"🔄 💾 Querying database for pipeline run_id={run_id}")
        run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
        if not run:
            logger.warning(f"⚠️ Pipeline run not found: run_id={run_id}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline run not found")

        logger.debug(f"🔄 ✓ Found pipeline run with current_status={run.status.value}")

        # Ensure user has access to the product
        logger.debug(f"🔄 🔐 Verifying access to product_id={run.product_id}")
        ensure_product_access(db, request_obj, run.product_id)
        logger.debug(f"🔄 ✓ Access verified")

        result = {
            "run_id": str(run.id),
            "status": run.status.value,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "dag_run_id": run.dag_run_id,
            "metrics": run.metrics,
        }
        logger.info(f"✅ EXIT get_pipeline_status - run_id={run_id}, status={run.status.value}")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ EXIT get_pipeline_status FAILED - run_id={run_id}: {e}", exc_info=True)
        raise


@router.get("/runs/{run_id}/logs")
async def get_pipeline_run_logs(
    run_id: UUID,
    request_obj: Request,
    db: Session = Depends(get_db)
):
    """
    Get logs for a specific pipeline run.
    Fetches logs from Airflow in a secure, workspace-scoped manner.
    """
    logger.info(f"🔄 ENTER get_pipeline_run_logs - run_id={run_id}")
    try:
        # Get pipeline run
        logger.debug(f"🔄 💾 Querying database for pipeline run_id={run_id}")
        run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
        if not run:
            logger.warning(f"⚠️ Pipeline run not found: run_id={run_id}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline run not found")

        logger.debug(f"🔄 ✓ Found pipeline run")

        # Ensure user has access to the product (security check)
        logger.debug(f"🔄 🔐 Verifying access to product_id={run.product_id}")
        ensure_product_access(db, request_obj, run.product_id)
        logger.debug(f"🔄 ✓ Access verified")

        # Lazy-load metrics from S3 if archived (do this early so we always have stage metrics)
        logger.debug(f"🔄 Loading metrics from S3 storage")
        from primedata.services.lazy_json_loader import load_pipeline_run_metrics

        metrics = load_pipeline_run_metrics(run)
        stage_metrics = metrics.get("aird_stages", {}) if metrics else {}
        logger.debug(f"📊 Loaded metrics with {len(stage_metrics)} stage metrics")

        if not run.dag_run_id:
            logger.warning(f"⚠️ No DAG run ID available for pipeline run_id={run_id}")
            return {
                "run_id": str(run.id),
                "dag_run_id": None,
                "logs": {},
                "stage_metrics": stage_metrics,
                "metrics": metrics,  # Include full metrics object
                "message": "No DAG run ID available for this pipeline run",
            }

        logger.debug(f"🔄 dag_run_id={run.dag_run_id}, fetching logs from Airflow")

        # Fetch logs from Airflow
        # ⚠️ WARNING: Replace with your actual Airflow URL and credentials in production!
        logger.debug(f"🔄 Loading Airflow credentials from environment")
        airflow_url = os.getenv("AIRFLOW_URL", "http://localhost:8080")
        # ⚠️ WARNING: Set AIRFLOW_USERNAME environment variable!
        airflow_username = os.getenv("AIRFLOW_USERNAME")
        if not airflow_username:
            logger.error(f"❌ AIRFLOW_USERNAME environment variable must be set")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="AIRFLOW_USERNAME environment variable must be set",
            )
        airflow_password = os.getenv("AIRFLOW_PASSWORD")  # Must be set via environment variable
        if not airflow_password:
            logger.error(f"❌ AIRFLOW_PASSWORD environment variable must be set")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="AIRFLOW_PASSWORD environment variable must be set",
            )

        logger.debug(f"🔄 ✓ Airflow credentials loaded - url={airflow_url}")

        try:
            import requests
            from requests.auth import HTTPBasicAuth

            # Get DAG run details
            logger.debug(f"🔄 📋 Fetching DAG run details from Airflow")
            dag_run_url = f"{airflow_url}/api/v1/dags/{AIRFLOW_DAG_ID}/dagRuns/{run.dag_run_id}"
            dag_run_response = requests.get(
                dag_run_url,
                auth=HTTPBasicAuth(airflow_username, airflow_password),
                timeout=10,
            )

            if dag_run_response.status_code != 200:
                logger.warning(f"⚠️ Failed to get DAG run details: {dag_run_response.status_code}")
                # Return stage metrics even if Airflow is unavailable
                return {
                    "run_id": str(run.id),
                    "dag_run_id": run.dag_run_id,
                    "logs": {},
                    "stage_metrics": stage_metrics,
                    "metrics": metrics,  # Include full metrics object
                    "error": "Failed to fetch logs from Airflow",
                }

            logger.debug(f"🔄 ✓ DAG run details retrieved")
            dag_run_data = dag_run_response.json()

            # Get task instances for this DAG run
            logger.debug(f"🔄 📋 Fetching task instances from Airflow")
            task_instances_url = f"{airflow_url}/api/v1/dags/{AIRFLOW_DAG_ID}/dagRuns/{run.dag_run_id}/taskInstances"
            task_instances_response = requests.get(
                task_instances_url,
                auth=HTTPBasicAuth(airflow_username, airflow_password),
                timeout=10,
            )

            logs = {}
            if task_instances_response.status_code == 200:
                task_instances = task_instances_response.json().get("task_instances", [])
                logger.debug(f"🔄 ✓ Retrieved {len(task_instances)} task instances")

                for task_instance in task_instances:
                    task_id = task_instance.get("task_id")
                    if not task_id:
                        continue

                    logger.debug(f"🔄 📋 Fetching logs for task_id={task_id}")
                    # Get logs for this task
                    # Airflow logs API returns plain text, not JSON
                    log_url = f"{airflow_url}/api/v1/dags/{AIRFLOW_DAG_ID}/dagRuns/{run.dag_run_id}/taskInstances/{task_id}/logs/1"
                    log_response = requests.get(
                        log_url,
                        auth=HTTPBasicAuth(airflow_username, airflow_password),
                        timeout=10,
                    )

                    if log_response.status_code == 200:
                        # Airflow returns logs as plain text, not JSON
                        log_content = log_response.text
                        logs[task_id] = {
                            "content": log_content,
                            "status": task_instance.get("state", "unknown"),
                            "start_date": task_instance.get("start_date"),
                            "end_date": task_instance.get("end_date"),
                        }
                        logger.debug(f"✓ Logs retrieved for task_id={task_id}, size={len(log_content)} bytes")
                    else:
                        logs[task_id] = {
                            "content": "",
                            "status": task_instance.get("state", "unknown"),
                            "error": f"Failed to fetch logs: {log_response.status_code}",
                        }
                        logger.warning(f"⚠️ Failed to fetch logs for task_id={task_id}: {log_response.status_code}")

            logger.info(f"✅ EXIT get_pipeline_run_logs - run_id={run_id}, tasks_logged={len(logs)}")
            return {
                "run_id": str(run.id),
                "dag_run_id": run.dag_run_id,
                "dag_run_state": dag_run_data.get("state", "unknown"),
                "logs": logs,
                "stage_metrics": stage_metrics,
                "metrics": metrics,  # Include full metrics object for cancelled_reason and other metadata
            }

        except Exception as e:
            logger.error(f"❌ Error fetching logs from Airflow: {e}", exc_info=True)
            # Return stage metrics even if Airflow fetch fails
            return {
                "run_id": str(run.id),
                "dag_run_id": run.dag_run_id,
                "logs": {},
                "stage_metrics": stage_metrics,
                "metrics": metrics,  # Include full metrics object
                "error": f"Failed to fetch logs: {str(e)}",
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ EXIT get_pipeline_run_logs FAILED - run_id={run_id}: {e}", exc_info=True)
        raise


@router.get("/runs/{run_id}/chunking-config")
async def get_pipeline_chunking_config(
    run_id: UUID,
    request_obj: Request,
    db: Session = Depends(get_db)
):
    """
    Get chunking configuration for a pipeline run from stored metrics.
    Returns resolved_settings that were used during preprocessing.
    """
    logger.info(f"🔄 ENTER get_pipeline_chunking_config - run_id={run_id}")
    try:
        logger.debug(f"🔄 💾 Querying database for pipeline run_id={run_id}")
        run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
        if not run:
            logger.warning(f"⚠️ Pipeline run not found: run_id={run_id}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline run not found")

        logger.debug(f"🔄 ✓ Found pipeline run")

        logger.debug(f"🔄 🔐 Verifying access to product_id={run.product_id}")
        ensure_product_access(db, request_obj, run.product_id)
        logger.debug(f"🔄 ✓ Access verified")

        # Load metrics (handles S3 archival)
        logger.debug(f"🔄 Loading metrics from S3 storage")
        from primedata.services.lazy_json_loader import load_pipeline_run_metrics
        metrics = load_pipeline_run_metrics(run)

        logger.debug(f"📊 Extracting chunking_config from metrics")
        chunking_config = metrics.get("chunking_config", {})
        resolved_settings = chunking_config.get("resolved_settings")

        result = {
            "resolved_settings": resolved_settings,
            "timestamp": chunking_config.get("timestamp"),
            "version": chunking_config.get("version")
        }
        logger.info(f"✅ EXIT get_pipeline_chunking_config - run_id={run_id}, has_resolved_settings={resolved_settings is not None}")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ EXIT get_pipeline_chunking_config FAILED - run_id={run_id}: {e}", exc_info=True)
        raise


def update_pipeline_run_status(
    db: Session, dag_run_id: str, status: PipelineRunStatus, metrics: Optional[Dict[str, Any]] = None
):
    """
    Update pipeline run status from Airflow.

    This function is called by the Airflow DAG to update the pipeline run status.

    Args:
        db: Database session
        dag_run_id: DAG run ID
        status: New status
        metrics: Optional metrics to update
    """
    try:
        # Find pipeline run by DAG run ID
        pipeline_run = db.query(PipelineRun).filter(PipelineRun.dag_run_id == dag_run_id).first()

        if not pipeline_run:
            logger.warning(f"Pipeline run not found for DAG run ID: {dag_run_id}")
            return

        # Update status
        pipeline_run.status = status

        if status == PipelineRunStatus.RUNNING and not pipeline_run.started_at:
            pipeline_run.started_at = datetime.utcnow()
        elif status in [PipelineRunStatus.SUCCEEDED, PipelineRunStatus.FAILED]:
            pipeline_run.finished_at = datetime.utcnow()

        # Update metrics if provided (save to S3 if large)
        if metrics:
            from primedata.services.s3_json_storage import save_json_to_s3, should_save_to_s3

            # Merge with existing metrics
            if pipeline_run.metrics is None:
                pipeline_run.metrics = {}
            pipeline_run.metrics.update(metrics)

            # Check if metrics should be saved to S3 (if >1MB)
            if should_save_to_s3(pipeline_run.metrics):
                s3_path = save_json_to_s3(
                    pipeline_run.workspace_id,
                    pipeline_run.product_id,
                    "metrics",
                    pipeline_run.metrics,
                    version=pipeline_run.version,
                    subfolder="pipeline_runs",
                )
                if s3_path:
                    pipeline_run.metrics_path = s3_path
                    pipeline_run.archived_at = datetime.utcnow()
                    pipeline_run.metrics = {}  # Clear DB field after archiving
                    logger.info(f"Archived metrics to S3 for pipeline run {pipeline_run.id}")

        db.commit()

        logger.info(f"Updated pipeline run {pipeline_run.id} status to {status.value}")

    except Exception as e:
        logger.error(f"Failed to update pipeline run status: {e}")
        db.rollback()
        raise
