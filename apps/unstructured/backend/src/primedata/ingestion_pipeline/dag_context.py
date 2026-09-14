"""
DAG Context Helpers - Parameter extraction and context building for Airflow DAG tasks.

This module provides utility functions for extracting parameters from Airflow
task context, building AIRD execution contexts, and validating stage results.
"""

from typing import Any, Dict
from uuid import UUID

from primedata.db.database import get_db
from primedata.db.models import PipelineRun
from primedata.ingestion_pipeline.aird_stages.base import StageStatus
from primedata.utils.logger import get_logger

logger = get_logger(__name__)


def get_dag_params(**context) -> Dict[str, Any]:
    """Extract and validate DAG parameters from Airflow context.

    Args:
        context: Airflow task context

    Returns:
        Dictionary with validated parameters (workspace_id, product_id, version, etc.)
    """
    logger.info(f"Context keys: {list(context.keys())}")

    # Try to get parameters from DAG run conf first, then fall back to params
    dag_run = context.get("dag_run")
    if dag_run:
        logger.info(f"DAG run found: {dag_run.run_id}")
        if dag_run.conf:
            params = dag_run.conf
            logger.info(f"Using DAG run conf parameters: {params}")
        else:
            logger.warning("DAG run conf is empty")
            params = context.get("params", {})
            logger.info(f"Using default params: {params}")
    else:
        logger.warning("No DAG run found in context")
        params = context.get("params", {})
        logger.info(f"Using default params: {params}")

    # Get required parameters
    workspace_id = params.get("workspace_id")
    product_id = params.get("product_id")
    version = params.get("version")  # PipelineRun / artifact / Qdrant version
    raw_file_version = params.get("raw_file_version")  # Input RawFile.version
    if raw_file_version is None:
        # Backward compatibility: older triggers used "version" as raw file version
        raw_file_version = version
    playbook_id = params.get("playbook_id")

    # Get embedding configuration
    embedding_config = params.get("embedding_config", {})
    embedder_name = embedding_config.get("embedder_name", "minilm")
    dim = int(embedding_config.get("embedding_dimension", 384))

    # Get chunking configuration
    chunking_config = params.get("chunking_config", {})

    logger.info(
        f"Extracted parameters: workspace_id={workspace_id}, product_id={product_id}, version={version}, playbook_id={playbook_id}, embedder={embedder_name}, dim={dim}"
    )
    logger.info(f"Chunking config: {chunking_config}")

    if not product_id:
        error_msg = f"product_id parameter is required but was None. Available params: {params}. DAG run: {dag_run.run_id if dag_run else 'None'}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    logger.info(
        f"Pipeline parameters validated: workspace_id={workspace_id}, product_id={product_id}, version={version}, embedder={embedder_name}, dim={dim}"
    )

    return {
        "workspace_id": UUID(workspace_id) if isinstance(workspace_id, str) else workspace_id,
        "product_id": UUID(product_id) if isinstance(product_id, str) else product_id,
        "version": version,
        "raw_file_version": raw_file_version,
        "playbook_id": playbook_id,
        "embedder_name": embedder_name,
        "dim": dim,
        "chunking_config": chunking_config,
    }


def get_aird_context(**context) -> Dict[str, Any]:
    """Get AIRD stage execution context.

    This helper function provides context for AIRD stages including:
    - Pipeline parameters
    - Storage adapter
    - Database session
    - Pipeline run tracking

    Args:
        context: Airflow task context

    Returns:
        Dictionary with AIRD context (storage, tracker, config, etc.)
    """
    # Lazy imports to avoid DAG import timeouts (Airflow has 30s limit)
    from primedata.ingestion_pipeline.aird_stages.config import get_aird_config
    from primedata.ingestion_pipeline.aird_stages.storage import AirdStorageAdapter
    from primedata.ingestion_pipeline.aird_stages.tracking import StageTracker

    params = get_dag_params(**context)
    workspace_id = params["workspace_id"]
    product_id = params["product_id"]
    version = params["version"]
    raw_file_version = params.get("raw_file_version", version)

    # Get database session
    db = next(get_db())

    # Get pipeline run
    pipeline_run = db.query(PipelineRun).filter(PipelineRun.product_id == product_id, PipelineRun.version == version).first()

    if not pipeline_run:
        logger.warning(f"Pipeline run not found for product {product_id}, version {version}")
        pipeline_run = None

    # Create storage adapter
    storage = AirdStorageAdapter(
        workspace_id=workspace_id,
        product_id=product_id,
        version=version,
    )

    # Create stage tracker (if pipeline run exists)
    tracker = None
    if pipeline_run:
        tracker = StageTracker(db, pipeline_run)

    # Get AIRD config
    aird_config = get_aird_config()

    return {
        "workspace_id": workspace_id,
        "product_id": product_id,
        "version": version,
        "raw_file_version": raw_file_version,
        "storage": storage,
        "tracker": tracker,
        "db": db,
        "pipeline_run": pipeline_run,
        "config": aird_config,
        "playbook_id": params.get("playbook_id"),
    }


def _get_versions_from_context(**context) -> Dict[str, int]:
    """
    Helper: return (pipeline_run_version, raw_file_version) from DAG params.
    Backward compatible: if raw_file_version is missing, it defaults to version.
    """
    logger.debug(f"🔄 ENTRY: _get_versions_from_context()")
    params = get_dag_params(**context)
    v = int(params.get("version") or 0)
    rv = int(params.get("raw_file_version") or v)
    logger.debug(f"✅ EXIT: _get_versions_from_context() -> version={v}, raw_file_version={rv}")
    return {"version": v, "raw_file_version": rv}


def get_pipeline_run_id_from_context(**context) -> str:
    """Extract pipeline run ID from DAG run parameters."""
    logger.debug(f"🔄 ENTRY: get_pipeline_run_id_from_context()")
    try:
        # Try to get from DAG run conf
        dag_run = context.get("dag_run")
        if dag_run and dag_run.conf:
            pipeline_run_id = dag_run.conf.get("pipeline_run_id")
            if pipeline_run_id:
                logger.debug(f"✅ Got pipeline_run_id from DAG run conf: {pipeline_run_id}")
                return pipeline_run_id

        # Try to get from task instance
        task_instance = context.get("task_instance")
        if task_instance and task_instance.dag_run:
            pipeline_run_id = task_instance.dag_run.conf.get("pipeline_run_id")
            if pipeline_run_id:
                logger.debug(f"✅ Got pipeline_run_id from task instance: {pipeline_run_id}")
                return pipeline_run_id

        # Try to get from params
        params = context.get("params", {})
        pipeline_run_id = params.get("pipeline_run_id")
        if pipeline_run_id:
            logger.debug(f"✅ Got pipeline_run_id from params: {pipeline_run_id}")
            return pipeline_run_id

        logger.warning(f"⚠️  Could not extract pipeline_run_id from context")
        return None

    except Exception as e:
        logger.error(f"❌ Error extracting pipeline run ID: {e}", exc_info=True)
        return None


def raise_if_stage_failed(result, stage_name: str, context_msg: str = ""):
    """
    Raise RuntimeError if stage result indicates failure.

    Airflow PythonOperator tasks only fail when exceptions are raised.
    This helper ensures that failed stage results cause task failures.

    Args:
        result: StageResult object from stage execution
        stage_name: Name of the stage (for error messages)
        context_msg: Additional context message to include in error
    """
    logger.debug(f"📋 Checking stage result: stage={stage_name}, status={result.status}")
    if result.status == StageStatus.FAILED:
        error_msg = result.error or "Unknown error"
        full_msg = f"{stage_name} stage failed: {error_msg}"
        if context_msg:
            full_msg += f" ({context_msg})"

        logger.error(f"❌ {full_msg}")
        logger.error(f"   Stage metrics: {result.metrics}")
        logger.error(f"   Stage started_at: {result.started_at}, finished_at: {result.finished_at}")

        raise RuntimeError(full_msg)
    logger.debug(f"   ✅ Stage {stage_name} succeeded")
