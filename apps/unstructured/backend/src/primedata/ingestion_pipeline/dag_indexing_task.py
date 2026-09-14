"""
Airflow DAG Indexing Task Function

Extracted from dag_stage_tasks.py for maintainability.
Contains the task_indexing function.
"""

from typing import Any, Dict
from uuid import UUID

from primedata.utils.logger import get_logger
from primedata.db.models import (
    Product,
)
from primedata.ingestion_pipeline.aird_stages.base import StageStatus
from primedata.ingestion_pipeline.pipeline_config import should_skip_vectors
from primedata.config import resolve_effective_config
from primedata.ingestion_pipeline.dag_context import (
    get_dag_params,
    get_aird_context,
    raise_if_stage_failed,
)
from primedata.ingestion_pipeline.stage_artifact_registry import (
    register_stage_artifacts,
)

logger = get_logger(__name__)


def _mark_raw_files_as_failed(product_id: UUID, version: int, error_message: str, db_session=None) -> int:
    """Helper to mark raw files as failed - imports from dag_tasks."""
    from primedata.ingestion_pipeline.dag_tasks import mark_raw_files_as_failed as _mark
    return _mark(product_id, version, error_message, db_session=db_session)


def task_indexing(**context) -> Dict[str, Any]:
    """Index chunks to Qdrant using AIRD IndexingStage."""
    params = get_dag_params(**context)
    workspace_id = params["workspace_id"]
    product_id = params["product_id"]
    version = params["version"]
    raw_file_version = params.get("raw_file_version", version)

    logger.info(f"Starting AIRD indexing for product {product_id}, version {version}")

    aird_context = get_aird_context(**context)
    storage = aird_context["storage"]
    tracker = aird_context.get("tracker")
    db = aird_context["db"]
    pipeline_run = aird_context.get("pipeline_run")

    try:
        # Check if vector creation is enabled for this product
        from primedata.db.models import Product
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            raise ValueError(f"Product {product_id} not found")

        if should_skip_vectors(product):
            logger.info(f"Vector creation is disabled for product {product_id}, skipping indexing stage")
            if pipeline_run is not None:
                if pipeline_run.metrics is None:
                    pipeline_run.metrics = {}
                pipeline_run.metrics["vectors_skipped"] = True
                pipeline_run.metrics["vectors_skip_reason"] = "vector_creation_enabled is False"
                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(pipeline_run, "metrics")
                db.commit()
            if tracker:
                from primedata.ingestion_pipeline.aird_stages.base import StageResult
                skipped_result = StageResult(
                    status=StageStatus.SKIPPED,
                    stage_name="indexing",
                    product_id=product_id,
                    version=version,
                    metrics={"points_indexed": 0, "reason": "vector_creation_enabled is False"},
                    error=None,
                )
                tracker.record_stage_result(skipped_result)
            return {
                "status": "skipped",
                "vectors_indexed": 0,
                "reason": "vector_creation_enabled is False",
            }

    except Exception as e:
        logger.error(f"Failed to check vector_creation_enabled for product {product_id}: {e}", exc_info=True)
        # Continue with indexing if we can't check the flag (fallback to default behavior)

    try:
        # Use new resolver with precedence-based resolution
        run_conf = params or {}
        detected_playbook = None

        effective = resolve_effective_config(
            run_conf=run_conf,
            product_row=product,
            detected_playbook=detected_playbook,
        )

        # Convert to legacy format for backward compatibility
        effective_config = effective.to_legacy_dict(product_row=product)
        chunking_config = effective_config.get("chunking_config")
        playbook_selection = effective_config.get("playbook_selection")
        playbook_id = effective_config.get("playbook_id") or params.get("playbook_id") or getattr(product, "playbook_id", None)

        # Log new resolver usage
        logger.info("✅ Using NEW resolver: resolve_effective_config() (indexing)")
        logger.info("Resolution trace: %s", effective.resolution_trace.dict() if effective.resolution_trace else None)
        logger.info(f"Effective chunking config (indexing): {chunking_config}")
        logger.info(f"Effective playbook (indexing): {playbook_selection or {'playbook_id': playbook_id or product.playbook_id}}")

        # Get processed files from preprocessing
        preprocess_result = context["task_instance"].xcom_pull(task_ids="preprocess", key="preprocess_result")
        if not preprocess_result:
            preprocess_result = context["task_instance"].xcom_pull(task_ids="preprocess")
        processed_files = preprocess_result.get("processed_file_list", []) if preprocess_result else []

        # Get scoring result
        scoring_result = context["task_instance"].xcom_pull(task_ids="scoring", key="scoring_result")
        if not scoring_result:
            scoring_result = context["task_instance"].xcom_pull(task_ids="scoring")

        # Load playbook (used for optional RAG evaluation settings)
        playbook = {}
        if playbook_id:
            try:
                from primedata.ingestion_pipeline.aird_stages.playbooks import load_playbook_yaml

                playbook = load_playbook_yaml(playbook_id, workspace_id=str(workspace_id), db_session=db)
                logger.info(f"Loaded playbook {playbook_id} for indexing stage (keys: {list(playbook.keys())[:10]})")
            except Exception as e:
                logger.warning(f"Failed to load playbook {playbook_id} for indexing: {e}", exc_info=True)

        # Create and execute indexing stage
        # Lazy import to avoid DAG import timeouts
        from primedata.ingestion_pipeline.aird_stages.indexing import IndexingStage

        indexing_stage = IndexingStage(
            product_id=product_id,
            version=version,
            workspace_id=workspace_id,
        )

        stage_context = {
            "storage": storage,
            "processed_files": processed_files,
            "preprocess_result": preprocess_result,
            "scoring_result": scoring_result,
            "chunking_config": chunking_config,
            "playbook": playbook,
            "playbook_id": playbook_id,
        }

        result = indexing_stage.execute(stage_context)

        if tracker:
            tracker.record_stage_result(result)

        logger.info(f"Indexing completed: {result.status.value}, vectors={result.metrics.get('points_indexed', 0)}")

        # Persist vector + RAG metrics into product readiness_fingerprint (so UI reflects real computations)
        if result.status == StageStatus.SUCCEEDED:
            try:
                from primedata.services.lazy_json_loader import load_product_json_field
                from primedata.services.s3_json_storage import save_product_json_field

                product_for_update = db.query(Product).filter(Product.id == product_id).first()
                if product_for_update:
                    existing_fp = load_product_json_field(product_for_update, "readiness_fingerprint") or {}
                    if not isinstance(existing_fp, dict):
                        existing_fp = {}

                    # Only merge keys that the UI expects + keep details fields under dedicated keys
                    keys_to_merge = [
                        "Embedding_Dimension_Consistency",
                        "Embedding_Success_Rate",
                        "Vector_Quality_Score",
                        "Embedding_Model_Health",
                        "Semantic_Search_Readiness",
                        "Retrieval_Recall_At_K",
                        "Average_Precision_At_K",
                        "Query_Coverage",
                    ]
                    for k in keys_to_merge:
                        if k in result.metrics:
                            existing_fp[k] = result.metrics[k]

                    # Attach details (optional, useful for debugging)
                    if "vector_metrics_details" in result.metrics:
                        existing_fp["vector_metrics_details"] = result.metrics["vector_metrics_details"]
                    if "rag_metrics_details" in result.metrics:
                        existing_fp["rag_metrics_details"] = result.metrics["rag_metrics_details"]

                    s3_path, should_save_to_s3 = save_product_json_field(
                        product_for_update.workspace_id, product_for_update.id, "readiness_fingerprint", existing_fp
                    )
                    if should_save_to_s3 and s3_path:
                        product_for_update.readiness_fingerprint_path = s3_path
                        product_for_update.readiness_fingerprint = None
                    else:
                        # Assign a fresh dict so SQLAlchemy sees the JSON change.
                        product_for_update.readiness_fingerprint = dict(existing_fp)
                        product_for_update.readiness_fingerprint_path = None
                        from sqlalchemy.orm.attributes import flag_modified

                        flag_modified(product_for_update, "readiness_fingerprint")

                    db.commit()
                    logger.info(f"Updated product {product_id} readiness_fingerprint with vector/RAG metrics")
            except Exception as e:
                logger.warning(f"Failed to persist vector/RAG metrics into readiness_fingerprint: {e}", exc_info=True)

        # Phase 1 & 2: Register artifacts for traceability
        indexing_artifact_ids = []
        if result.status == StageStatus.SUCCEEDED and aird_context.get("pipeline_run"):
            try:
                # Get input artifact IDs from preprocess AND scoring (for lineage)
                preprocess_artifact_ids_str = preprocess_result.get("artifact_ids", []) if preprocess_result else []
                scoring_artifact_ids_str = scoring_result.get("artifact_ids", []) if scoring_result else []

                # Combine input artifacts from both stages
                input_artifact_ids = []
                if preprocess_artifact_ids_str:
                    input_artifact_ids.extend([UUID(aid) for aid in preprocess_artifact_ids_str])
                if scoring_artifact_ids_str:
                    input_artifact_ids.extend([UUID(aid) for aid in scoring_artifact_ids_str])

                indexing_artifact_ids = register_stage_artifacts(
                    db=db,
                    pipeline_run_id=aird_context["pipeline_run"].id,
                    workspace_id=workspace_id,
                    product_id=product_id,
                    version=version,
                    stage_name="indexing",
                    result=result,
                    storage=storage,
                    input_artifact_ids=input_artifact_ids if input_artifact_ids else None,
                )
                logger.info(f"Registered {len(indexing_artifact_ids)} indexing artifacts")
                logger.info(f"Registered {len(indexing_artifact_ids)} indexing artifacts")
            except Exception as e:
                logger.error(f"Failed to register indexing artifacts: {e}", exc_info=True)
                logger.error(f"Failed to register indexing artifacts: {e}", exc_info=True)

        # Mark raw files as failed if indexing failed (before raising exception)
        if result.status == StageStatus.FAILED:
            error_msg = result.error or "Unknown error"
            _mark_raw_files_as_failed(product_id, raw_file_version, f"Indexing stage failed: {error_msg}", db_session=db)

        # Raise exception if stage failed (Airflow only fails tasks on exceptions)
        raise_if_stage_failed(result, "Indexing")

        return {
            "status": result.status.value,
            "vectors_indexed": result.metrics.get("points_indexed", 0),  # Indexing stage uses 'points_indexed'
            # Expose key computed metrics in XCom/response (optional, helps UI/logs)
            "vector_metrics": {
                k: result.metrics.get(k)
                for k in [
                    "Embedding_Dimension_Consistency",
                    "Embedding_Success_Rate",
                    "Vector_Quality_Score",
                    "Embedding_Model_Health",
                    "Semantic_Search_Readiness",
                ]
                if k in result.metrics
            },
            "rag_metrics": {
                k: result.metrics.get(k)
                for k in ["Retrieval_Recall_At_K", "Average_Precision_At_K", "Query_Coverage"]
                if k in result.metrics
            },
        }
    except Exception as e:
        logger.error(f"Indexing failed: {e}", exc_info=True)
        logger.error(f"Indexing failed: {e}", exc_info=True)
        # Mark raw files as FAILED since pipeline failed at indexing stage
        _mark_raw_files_as_failed(product_id, raw_file_version, f"Indexing stage failed: {str(e)}", db_session=db)
        raise
    finally:
        db.close()
