"""
Airflow REST API client utilities for PrimeData pipeline orchestration.

This module encapsulates all direct interactions with the Apache Airflow REST API,
including triggering DAG runs, checking run status, syncing pipeline state, and
ensuring DAGs are unpaused before execution.
"""

import json
import os
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from primedata.db.models import PipelineRun, PipelineRunStatus
from primedata.utils.logger import get_logger

logger = get_logger(__name__)

# Airflow DAG Configuration
AIRFLOW_DAG_ID = os.getenv("AIRFLOW_DAG_ID", "primedata_simple")


def _check_airflow_dag_run_status(
    airflow_url: str, airflow_username: str, airflow_password: str, dag_run_id: str
) -> Dict[str, Any]:
    """
    Check the status of a specific DAG run in Airflow.
    Returns the DAG run status and details.
    """
    try:
        import requests
        from requests.auth import HTTPBasicAuth

        # Get DAG run status from Airflow REST API
        dag_run_url = f"{airflow_url}/api/v1/dags/{AIRFLOW_DAG_ID}/dagRuns/{dag_run_id}"

        response = requests.get(
            dag_run_url,
            auth=HTTPBasicAuth(airflow_username, airflow_password),
            headers={"Content-Type": "application/json"},
            timeout=30,
        )

        if response.status_code == 200:
            dag_run_data = response.json()
            return {
                "status": dag_run_data.get("state", "unknown"),
                "start_date": dag_run_data.get("start_date"),
                "end_date": dag_run_data.get("end_date"),
                "execution_date": dag_run_data.get("execution_date"),
                "dag_run_id": dag_run_data.get("dag_run_id"),
            }
        else:
            logger.error(f"Failed to get DAG run status: {response.status_code} - {response.text}")
            return {"status": "unknown", "error": f"HTTP {response.status_code}"}

    except Exception as e:
        logger.error(f"Error checking DAG run status: {e}")
        return {"status": "unknown", "error": str(e)}


def _sync_pipeline_runs_with_airflow(db: Session) -> int:
    """
    Sync running pipeline runs with Airflow status.
    Returns the number of runs updated.
    """
    try:
        # Get Airflow configuration
        # ⚠️ WARNING: Replace with your actual Airflow URL and credentials in production!
        airflow_url = os.getenv("AIRFLOW_URL", "http://localhost:8080")
        # ⚠️ WARNING: Set AIRFLOW_USERNAME environment variable!
        airflow_username = os.getenv("AIRFLOW_USERNAME")
        if not airflow_username:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="AIRFLOW_USERNAME environment variable must be set",
            )
        airflow_password = os.getenv("AIRFLOW_PASSWORD")  # Must be set via environment variable
        if not airflow_password:
            logger.error("AIRFLOW_PASSWORD environment variable must be set")
            return  # Skip sync if password not configured

        # Get all running pipeline runs
        running_runs = (
            db.query(PipelineRun).filter(PipelineRun.status.in_([PipelineRunStatus.RUNNING, PipelineRunStatus.QUEUED])).all()
        )

        updated_count = 0

        for run in running_runs:
            if not run.dag_run_id:
                continue

            # Check Airflow status
            airflow_status = _check_airflow_dag_run_status(airflow_url, airflow_username, airflow_password, run.dag_run_id)

            if airflow_status.get("status") in ["success", "failed"]:
                # Update the pipeline run status
                if airflow_status["status"] == "success":
                    run.status = PipelineRunStatus.SUCCEEDED
                else:
                    run.status = PipelineRunStatus.FAILED

                # Update finished_at if available
                if airflow_status.get("end_date"):
                    try:
                        run.finished_at = datetime.fromisoformat(airflow_status["end_date"].replace("Z", "+00:00"))
                    except ValueError:
                        run.finished_at = datetime.utcnow()
                else:
                    run.finished_at = datetime.utcnow()

                # Add some basic metrics
                if not run.metrics:
                    run.metrics = {}
                run.metrics["airflow_sync"] = True
                run.metrics["airflow_status"] = airflow_status["status"]

                updated_count += 1
                logger.info(f"Updated pipeline run {run.id} to status {run.status.value}")

        if updated_count > 0:
            db.commit()
            logger.info(f"Synced {updated_count} pipeline runs with Airflow")

        return updated_count

    except Exception as e:
        logger.error(f"Error syncing pipeline runs with Airflow: {e}")
        return 0


def _ensure_dag_unpaused(airflow_url: str, airflow_username: str, airflow_password: str, dag_id: str) -> bool:
    """
    Ensure a DAG is unpaused. Returns True if successful, False otherwise.
    """
    try:
        import requests
        from requests.auth import HTTPBasicAuth

        # Get DAG info
        dag_info_url = f"{airflow_url}/api/v1/dags/{dag_id}"
        logger.debug(f"🔍 Checking DAG status | url={dag_info_url}")
        dag_info_response = requests.get(
            dag_info_url,
            auth=HTTPBasicAuth(airflow_username, airflow_password),
            headers={"Content-Type": "application/json"},
            timeout=30,
        )

        if dag_info_response.status_code == 200:
            dag_info = dag_info_response.json()
            is_paused = dag_info.get("is_paused", True)

            if is_paused:
                logger.info(f"DAG {dag_id} is paused, attempting to unpause")
                unpause_data = {"is_paused": False}

                unpause_response = requests.patch(
                    dag_info_url,
                    json=unpause_data,
                    auth=HTTPBasicAuth(airflow_username, airflow_password),
                    headers={"Content-Type": "application/json"},
                    timeout=30,
                )

                if unpause_response.status_code == 200:
                    logger.info(f"Successfully unpaused DAG {dag_id}")
                    return True
                else:
                    logger.error(f"Failed to unpause DAG {dag_id}: {unpause_response.status_code} - {unpause_response.text}")
                    return False
            else:
                logger.info(f"DAG {dag_id} is already unpaused")
                return True
        elif dag_info_response.status_code == 404:
            logger.error(f"❌ DAG {dag_id} not found in Airflow")
            logger.error(f"   This means the DAG file is not in Airflow's DAG folder")
            logger.error(f"   Response: {dag_info_response.text}")
            return False
        else:
            logger.error(f"Failed to get DAG info for {dag_id}: {dag_info_response.status_code} - {dag_info_response.text}")
            return False

    except Exception as e:
        logger.error(f"Error checking/unpausing DAG {dag_id}: {e}")
        return False


def _trigger_airflow_dag(
    workspace_id: UUID,
    product_id: UUID,
    version: int,
    pipeline_run_id: UUID,
    raw_file_version: Optional[int] = None,
    chunking_config: Dict[str, Any] = None,
    embedding_config: Dict[str, Any] = None,
    playbook_id: str = None
) -> str:
    """
    Trigger Airflow DAG for pipeline execution.

    This function creates a trigger file that the Airflow scheduler can read
    to trigger the DAG with the appropriate parameters.

    Args:
        workspace_id: Workspace ID
        product_id: Product ID
        version: Version number
        pipeline_run_id: Pipeline run ID
        raw_file_version: Raw file version to process (defaults to version if not provided)
        chunking_config: Chunking configuration dictionary
        embedding_config: Embedding configuration dictionary
        playbook_id: Optional playbook ID

    Returns:
        DAG run ID
    """
    try:
        # Generate DAG run ID
        dag_run_id = f"{AIRFLOW_DAG_ID}_{pipeline_run_id}_{int(datetime.utcnow().timestamp())}"
        logger.info(f"✅ DAG run ID created: {dag_run_id}")

        logger.info(f"📤 Triggering DAG: {AIRFLOW_DAG_ID} | workspace_id={workspace_id}, product_id={product_id}, version={version}")

        # Trigger DAG using Airflow REST API
        # ⚠️ WARNING: Replace with your actual Airflow URL and credentials in production!
        airflow_url = os.getenv("AIRFLOW_URL", "http://localhost:8080")
        # ⚠️ WARNING: Set AIRFLOW_USERNAME environment variable!
        airflow_username = os.getenv("AIRFLOW_USERNAME")
        if not airflow_username:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="AIRFLOW_USERNAME environment variable must be set",
            )
        airflow_password = os.getenv("AIRFLOW_PASSWORD")  # Must be set via environment variable
        if not airflow_password:
            # Debug: Log available env vars that contain 'AIRFLOW'
            airflow_vars = {k: v for k, v in os.environ.items() if 'AIRFLOW' in k.upper()}
            logger.error(f"❌ AIRFLOW_PASSWORD not set. Available AIRFLOW_* env vars: {list(airflow_vars.keys())}")
            error_detail = {
                "message": "AIRFLOW_PASSWORD environment variable must be set",
                "suggestion": "Please set AIRFLOW_PASSWORD environment variable to authenticate with Airflow",
                "available_vars": list(airflow_vars.keys()),
            }
            logger.error("Pipeline trigger failed: AIRFLOW_PASSWORD not set")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=error_detail)

        trigger_url = f"{airflow_url}/api/v1/dags/{AIRFLOW_DAG_ID}/dagRuns"
        logger.info(f"Triggering Airflow DAG via REST API at {trigger_url}")
        trigger_data = {
            "dag_run_id": dag_run_id,
            "conf": {
                "workspace_id": str(workspace_id),
                "product_id": str(product_id),
                "version": version,
                "raw_file_version": raw_file_version if raw_file_version is not None else version,
                "pipeline_run_id": str(pipeline_run_id),
                "chunking_config": chunking_config or {},
                "embedding_config": embedding_config or {},
                "playbook_id": playbook_id,
            },
        }

        # Log the exact configuration being sent to Airflow
        logger.info(
            f"Sending to Airflow DAG:\n"
            f"  chunking_config: {json.dumps(chunking_config or {}, indent=2)}\n"
            f"  embedding_config: {json.dumps(embedding_config or {}, indent=2)}\n"
            f"  playbook_id: {playbook_id}"
        )
        logger.info(f"Airflow trigger data is {json.dumps(trigger_data, indent=2)}")
        try:
            logger.info(f"Airflow try")
            import requests
            from requests.auth import HTTPBasicAuth

            # Ensure DAG is unpaused before triggering
            if not _ensure_dag_unpaused(airflow_url, airflow_username, airflow_password, AIRFLOW_DAG_ID):
                raise Exception("Failed to ensure DAG is unpaused")

            # Now trigger the DAG run
            response = requests.post(
                trigger_url,
                json=trigger_data,
                auth=HTTPBasicAuth(airflow_username, airflow_password),
                headers={"Content-Type": "application/json"},
                timeout=30,
            )
            logger.info(f"response from Airflow DAG trigger: status_code={response.status_code}, "
                        f"response_body={response.text}")
            if response.status_code in [200, 201]:
                logger.info(f"Successfully triggered DAG run {dag_run_id} via REST API (status {response.status_code})")
            else:
                error_msg = f"Failed to trigger DAG run via REST API: {response.status_code} - {response.text}"
                logger.error(error_msg)
                raise Exception(error_msg)

        except Exception as e:
            logger.error(f"Error triggering DAG via REST API: {e}", exc_info=True)
            # Fallback to file-based trigger (use tmp directory that's writable)
            trigger_dir = os.getenv("AIRFLOW_TRIGGER_DIR", os.path.join(tempfile.gettempdir(), "airflow_triggers"))

            try:
                os.makedirs(trigger_dir, exist_ok=True)
            except OSError as dir_error:
                logger.error(f"Failed to create trigger directory {trigger_dir}: {dir_error}")
                # Last resort: use tempfile.gettempdir() directly
                trigger_dir = tempfile.gettempdir()
                logger.warning(f"Using temp directory as fallback: {trigger_dir}")

            trigger_file = os.path.join(trigger_dir, f"{dag_run_id}.json")

            try:
                with open(trigger_file, "w") as f:
                    json.dump(trigger_data, f, indent=2)
                logger.info(f"Created trigger file {trigger_file} for DAG run {dag_run_id}")
                logger.warning(
                    f"Using file-based Airflow trigger fallback. Ensure Airflow can read from {trigger_dir}. "
                    f"REST API error was: {e}"
                )
            except OSError as file_error:
                error_msg = (
                    f"Failed to create Airflow trigger file {trigger_file}: {file_error}. "
                    f"REST API error was: {e}. "
                    f"Please check AIRFLOW_URL, AIRFLOW_USERNAME, and AIRFLOW_PASSWORD environment variables."
                )
                logger.error(error_msg)
                raise Exception(error_msg) from e
        logger.info(f"✅ Airflow DAG triggered with run ID: {dag_run_id}")
        return dag_run_id

    except Exception as e:
        error_msg = f"Failed to trigger Airflow DAG: {e}"
        logger.error(error_msg, exc_info=True)
        raise Exception(error_msg) from e
