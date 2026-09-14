"""
Airflow DAG Stage Task Functions

This module contains the individual pipeline stage task functions
(preprocess, scoring, fingerprint, validation, policy, reporting, indexing, etc.).
Extracted from dag_tasks.py for maintainability.
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from primedata.utils.logger import get_logger
from primedata.db.database import get_db
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
from primedata.ingestion_pipeline.aird_stages.base import StageStatus
from primedata.ingestion_pipeline.pipeline_config import should_skip_vectors
from primedata.config import resolve_effective_config
from primedata.ingestion_pipeline.artifact_registry import (
    calculate_checksum,
    get_artifact_summary_for_run,
)
from primedata.storage.storage_client import storage_client

from primedata.ingestion_pipeline.dag_context import (
    get_dag_params,
    get_aird_context,
    get_pipeline_run_id_from_context,
    raise_if_stage_failed,
)
from primedata.ingestion_pipeline.stage_artifact_registry import (
    _retrieve_file_stats,
    _calculate_file_checksum,
    register_stage_artifacts,
)
from primedata.ingestion_pipeline.auto_detection import (
    sample_files_for_analysis,
    auto_detect_playbook_and_chunking,
)

logger = get_logger(__name__)


def mark_raw_files_as_failed(product_id: UUID, version: int, error_message: str, db_session=None) -> int:
    """
    Mark all PROCESSING raw files for a product/version as FAILED.

    Imported from dag_tasks to avoid circular imports - this is a convenience re-import.
    """
    from primedata.ingestion_pipeline.dag_tasks import mark_raw_files_as_failed as _mark
    return _mark(product_id, version, error_message, db_session=db_session)


# Re-export task_preprocess from extracted module for backward compatibility
from primedata.ingestion_pipeline.dag_preprocess_task import task_preprocess  # noqa: F401


def task_scoring(**context) -> Dict[str, Any]:
    """Score processed chunks using AIRD ScoringStage."""
    params = get_dag_params(**context)
    workspace_id = params["workspace_id"]
    product_id = params["product_id"]
    version = params["version"]
    raw_file_version = params.get("raw_file_version", version)

    logger.info(f"Starting AIRD scoring for product {product_id}, version {version}")

    aird_context = get_aird_context(**context)
    storage = aird_context["storage"]
    tracker = aird_context.get("tracker")
    db = aird_context["db"]

    try:
        # Get processed files from preprocessing
        preprocess_result = context["task_instance"].xcom_pull(task_ids="preprocess", key="preprocess_result")
        if not preprocess_result:
            preprocess_result = context["task_instance"].xcom_pull(task_ids="preprocess")
        processed_files = preprocess_result.get("processed_file_list", []) if preprocess_result else []

        if not processed_files:
            logger.warning("No processed files found from preprocessing stage")
            return {
                "status": "skipped",
                "message": "No processed files to score",
            }

        product = db.query(Product).filter(Product.id == product_id).first()

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
        playbook_id = effective_config.get("playbook_id")

        # Log new resolver usage
        logger.info("✅ Using NEW resolver: resolve_effective_config() (scoring)")
        logger.info("Resolution trace: %s", effective.resolution_trace.dict() if effective.resolution_trace else None)
        logger.info(f"Effective chunking config (scoring): {chunking_config}")
        logger.info(f"Effective playbook (scoring): {playbook_selection or {'playbook_id': playbook_id}}")

        # Load playbook for AI-Ready metrics (noise patterns, coherence settings)
        playbook = {}
        if playbook_id:
            try:
                from primedata.ingestion_pipeline.aird_stages.playbooks import load_playbook_yaml
                playbook = load_playbook_yaml(playbook_id, workspace_id=str(workspace_id), db_session=db)
                logger.info(f"Loaded playbook {playbook_id} for scoring stage (keys: {list(playbook.keys())[:10]})")
                # Log if AI-Ready sections are present
                if "noise_patterns" in playbook:
                    logger.info(f"Playbook {playbook_id} has noise_patterns section")
                if "coherence" in playbook:
                    logger.info(f"Playbook {playbook_id} has coherence section")
            except Exception as e:
                logger.warning(f"Failed to load playbook {playbook_id}: {e}, using empty playbook", exc_info=True)

        # Create and execute scoring stage
        # Lazy import to avoid DAG import timeouts
        from primedata.ingestion_pipeline.aird_stages.scoring import ScoringStage

        scoring_stage = ScoringStage(
            product_id=product_id,
            version=version,
            workspace_id=workspace_id,
        )

        stage_context = {
            "storage": storage,
            "processed_files": processed_files,
            "preprocess_result": preprocess_result,
            "playbook": playbook,
            "playbook_id": playbook_id,
            "chunking_config": chunking_config,
        }

        result = scoring_stage.execute(stage_context)

        if tracker:
            tracker.record_stage_result(result)

        logger.info(f"Scoring completed: {result.status.value}, chunks={result.metrics.get('total_chunks', 0)}")

        # Phase 1 & 2: Register artifacts for traceability
        scoring_artifact_ids = []
        if result.status == StageStatus.SUCCEEDED and aird_context.get("pipeline_run"):
            try:
                # Get input artifact IDs from preprocess stage (for lineage)
                preprocess_artifact_ids_str = preprocess_result.get("artifact_ids", []) if preprocess_result else []
                input_artifact_ids = (
                    [UUID(aid) for aid in preprocess_artifact_ids_str] if preprocess_artifact_ids_str else None
                )

                scoring_artifact_ids = register_stage_artifacts(
                    db=db,
                    pipeline_run_id=aird_context["pipeline_run"].id,
                    workspace_id=workspace_id,
                    product_id=product_id,
                    version=version,
                    stage_name="scoring",
                    result=result,
                    storage=storage,
                    input_artifact_ids=input_artifact_ids,
                )
                logger.info(f"Registered {len(scoring_artifact_ids)} scoring artifacts")
                logger.info(f"Registered {len(scoring_artifact_ids)} scoring artifacts")
            except Exception as e:
                logger.error(f"Failed to register scoring artifacts: {e}", exc_info=True)
                logger.error(f"Failed to register scoring artifacts: {e}", exc_info=True)

        # Store result in XCom (store before raising exception if failed)
        context["task_instance"].xcom_push(
            key="scoring_result",
            value={
                "status": result.status.value,
                "metrics": result.metrics,
                "artifact_ids": [str(aid) for aid in scoring_artifact_ids],  # Phase 2: Pass artifact IDs for lineage
            },
        )

        # Mark raw files as failed if scoring failed (before raising exception)
        if result.status == StageStatus.FAILED:
            error_msg = result.error or "Unknown error"
            mark_raw_files_as_failed(product_id, raw_file_version, f"Scoring stage failed: {error_msg}", db_session=db)

        # Raise exception if stage failed (Airflow only fails tasks on exceptions)
        raise_if_stage_failed(result, "Scoring")

        return {
            "status": result.status.value,
            "total_chunks": result.metrics.get("total_chunks", 0),
            "avg_trust_score": result.metrics.get("avg_trust_score", 0.0),
        }
    except Exception as e:
        logger.error(f"Scoring failed: {e}", exc_info=True)
        logger.error(f"Scoring failed: {e}", exc_info=True)
        # Mark raw files as FAILED since pipeline failed at scoring stage
        mark_raw_files_as_failed(product_id, raw_file_version, f"Scoring stage failed: {str(e)}", db_session=db)
        raise
    finally:
        db.close()


def task_fingerprint(**context) -> Dict[str, Any]:
    """Generate readiness fingerprint using AIRD FingerprintStage."""
    params = get_dag_params(**context)
    workspace_id = params["workspace_id"]
    product_id = params["product_id"]
    version = params["version"]
    raw_file_version = params.get("raw_file_version", version)

    logger.info(f"Starting AIRD fingerprint generation for product {product_id}, version {version}")

    aird_context = get_aird_context(**context)
    storage = aird_context["storage"]
    tracker = aird_context.get("tracker")
    db = aird_context["db"]

    try:
        # Get scoring result
        scoring_result = context["task_instance"].xcom_pull(task_ids="scoring", key="scoring_result")
        if not scoring_result:
            scoring_result = context["task_instance"].xcom_pull(task_ids="scoring")

        # Get preprocess result for preprocessing stats (needed for Chunk Boundary Quality)
        preprocess_result = context["task_instance"].xcom_pull(task_ids="preprocess", key="preprocess_result")
        if not preprocess_result:
            preprocess_result = context["task_instance"].xcom_pull(task_ids="preprocess")

        # Create and execute fingerprint stage
        # Lazy import to avoid DAG import timeouts
        from primedata.ingestion_pipeline.aird_stages.fingerprint import FingerprintStage

        fingerprint_stage = FingerprintStage(
            product_id=product_id,
            version=version,
            workspace_id=workspace_id,
        )

        stage_context = {
            "storage": storage,
            "scoring_result": scoring_result,
            "preprocess_result": preprocess_result,
        }

        result = fingerprint_stage.execute(stage_context)

        if tracker:
            tracker.record_stage_result(result)

        logger.info(f"Fingerprint generation completed: {result.status.value}")

        # Phase 1 & 2: Register artifacts for traceability
        fingerprint_artifact_ids = []
        if result.status == StageStatus.SUCCEEDED and aird_context.get("pipeline_run"):
            try:
                # Get input artifact IDs from scoring stage (for lineage)
                scoring_artifact_ids_str = scoring_result.get("artifact_ids", []) if scoring_result else []
                input_artifact_ids = [UUID(aid) for aid in scoring_artifact_ids_str] if scoring_artifact_ids_str else None

                fingerprint_artifact_ids = register_stage_artifacts(
                    db=db,
                    pipeline_run_id=aird_context["pipeline_run"].id,
                    workspace_id=workspace_id,
                    product_id=product_id,
                    version=version,
                    stage_name="fingerprint",
                    result=result,
                    storage=storage,
                    input_artifact_ids=input_artifact_ids,
                )
                logger.info(f"Registered {len(fingerprint_artifact_ids)} fingerprint artifacts")
                logger.info(f"Registered {len(fingerprint_artifact_ids)} fingerprint artifacts")
            except Exception as e:
                logger.error(f"Failed to register fingerprint artifacts: {e}", exc_info=True)
                logger.error(f"Failed to register fingerprint artifacts: {e}", exc_info=True)

        # Store result in XCom (store before raising exception if failed)
        context["task_instance"].xcom_push(
            key="fingerprint_result",
            value={
                "status": result.status.value,
                "metrics": result.metrics,
                "artifact_ids": [str(aid) for aid in fingerprint_artifact_ids],  # Phase 2: Pass artifact IDs for lineage
            },
        )

        # Mark raw files as failed if fingerprint failed (before raising exception)
        if result.status == StageStatus.FAILED:
            error_msg = result.error or "Unknown error"
            mark_raw_files_as_failed(product_id, raw_file_version, f"Fingerprint stage failed: {error_msg}", db_session=db)

        # Raise exception if stage failed (Airflow only fails tasks on exceptions)
        raise_if_stage_failed(result, "Fingerprint")

        # Update product readiness fingerprint and trust score (save to S3 if large)
        product = db.query(Product).filter(Product.id == product_id).first()
        if product and result.status == StageStatus.SUCCEEDED:
            # Extract fingerprint from result.metrics (fingerprint is nested inside metrics)
            fingerprint = result.metrics.get("fingerprint", {})
            if fingerprint:
                from primedata.services.s3_json_storage import save_product_json_field

                s3_path, should_save_to_s3 = save_product_json_field(
                    product.workspace_id, product.id, "readiness_fingerprint", fingerprint
                )
                if should_save_to_s3 and s3_path:
                    product.readiness_fingerprint_path = s3_path
                    product.readiness_fingerprint = None  # Clear DB field
                else:
                    product.readiness_fingerprint = fingerprint
                    product.readiness_fingerprint_path = None  # Clear S3 path if exists
                # Extract AI_Trust_Score from fingerprint and set trust_score
                trust_score = fingerprint.get("AI_Trust_Score")
                if trust_score is not None:
                    product.trust_score = float(trust_score)  # Ensure it's a float
                else:
                    # Fallback: try to get trust_score from metrics_result directly
                    trust_score = result.metrics.get("trust_score")
                    if trust_score is not None:
                        product.trust_score = float(trust_score)
                db.commit()
                logger.info(f"Updated product {product_id} with fingerprint and trust_score={product.trust_score}")
            else:
                logger.warning(f"No fingerprint found in result.metrics for product {product_id}")

        return {
            "status": result.status.value,
            "metrics": result.metrics,
        }
    except Exception as e:
        logger.error(f"Fingerprint generation failed: {e}", exc_info=True)
        logger.error(f"Fingerprint generation failed: {e}", exc_info=True)
        # Mark raw files as FAILED since pipeline failed at fingerprint stage
        mark_raw_files_as_failed(product_id, raw_file_version, f"Fingerprint stage failed: {str(e)}", db_session=db)
        raise
    finally:
        db.close()


def task_validation(**context) -> Dict[str, Any]:
    """Generate validation summary using AIRD ValidationStage."""
    params = get_dag_params(**context)
    workspace_id = params["workspace_id"]
    product_id = params["product_id"]
    version = params["version"]
    raw_file_version = params.get("raw_file_version", version)

    logger.info(f"Starting AIRD validation summary generation for product {product_id}, version {version}")

    aird_context = get_aird_context(**context)
    storage = aird_context["storage"]
    tracker = aird_context.get("tracker")
    db = aird_context["db"]

    try:
        # Get scoring result
        scoring_result = context["task_instance"].xcom_pull(task_ids="scoring", key="scoring_result")
        if not scoring_result:
            scoring_result = context["task_instance"].xcom_pull(task_ids="scoring")

        # Create and execute validation stage
        # Lazy import to avoid DAG import timeouts
        from primedata.ingestion_pipeline.aird_stages.validation import ValidationStage

        validation_stage = ValidationStage(
            product_id=product_id,
            version=version,
            workspace_id=workspace_id,
        )

        stage_context = {
            "storage": storage,
            "scoring_result": scoring_result,
        }

        result = validation_stage.execute(stage_context)

        if tracker:
            tracker.record_stage_result(result)

        logger.info(f"Validation summary generation completed: {result.status.value}")

        # Phase 1 & 2: Register artifacts for traceability
        validation_artifact_ids = []
        if result.status == StageStatus.SUCCEEDED and aird_context.get("pipeline_run"):
            try:
                # Get input artifact IDs from scoring stage (for lineage)
                scoring_result = context["task_instance"].xcom_pull(task_ids="scoring", key="scoring_result")
                if not scoring_result:
                    scoring_result = context["task_instance"].xcom_pull(task_ids="scoring")
                scoring_artifact_ids_str = scoring_result.get("artifact_ids", []) if scoring_result else []
                input_artifact_ids = [UUID(aid) for aid in scoring_artifact_ids_str] if scoring_artifact_ids_str else None

                validation_artifact_ids = register_stage_artifacts(
                    db=db,
                    pipeline_run_id=aird_context["pipeline_run"].id,
                    workspace_id=workspace_id,
                    product_id=product_id,
                    version=version,
                    stage_name="validation",
                    result=result,
                    storage=storage,
                    input_artifact_ids=input_artifact_ids,
                )
                logger.info(f"Registered {len(validation_artifact_ids)} validation artifacts")
                logger.info(f"Registered {len(validation_artifact_ids)} validation artifacts")
            except Exception as e:
                logger.error(f"Failed to register validation artifacts: {e}", exc_info=True)
                logger.error(f"Failed to register validation artifacts: {e}", exc_info=True)

        # Raise exception if stage failed (Airflow only fails tasks on exceptions)
        raise_if_stage_failed(result, "Validation")

        # Update product validation summary path
        product = db.query(Product).filter(Product.id == product_id).first()
        if product and result.status == StageStatus.SUCCEEDED:
            if "validation_summary_path" in result.metrics:
                product.validation_summary_path = result.metrics["validation_summary_path"]
                db.commit()

        return {
            "status": result.status.value,
            "validation_summary_path": result.metrics.get("validation_summary_path"),
        }
    except Exception as e:
        logger.error(f"Validation summary generation failed: {e}", exc_info=True)
        logger.error(f"Validation summary generation failed: {e}", exc_info=True)
        # Mark raw files as FAILED since pipeline failed at validation stage
        mark_raw_files_as_failed(product_id, raw_file_version, f"Validation stage failed: {str(e)}", db_session=db)
        raise
    finally:
        db.close()


def task_policy(**context) -> Dict[str, Any]:
    """Evaluate policy using AIRD PolicyStage."""
    params = get_dag_params(**context)
    workspace_id = params["workspace_id"]
    product_id = params["product_id"]
    version = params["version"]
    raw_file_version = params.get("raw_file_version", version)

    logger.info(f"Starting AIRD policy evaluation for product {product_id}, version {version}")

    aird_context = get_aird_context(**context)
    storage = aird_context["storage"]
    tracker = aird_context.get("tracker")
    db = aird_context["db"]

    try:
        # Get fingerprint result
        fingerprint_result = context["task_instance"].xcom_pull(task_ids="fingerprint", key="fingerprint_result")
        if not fingerprint_result:
            fingerprint_result = context["task_instance"].xcom_pull(task_ids="fingerprint")

        # Create and execute policy stage
        # Lazy import to avoid DAG import timeouts
        from primedata.ingestion_pipeline.aird_stages.policy import PolicyStage

        policy_stage = PolicyStage(
            product_id=product_id,
            version=version,
            workspace_id=workspace_id,
        )

        stage_context = {
            "storage": storage,
            "fingerprint_result": fingerprint_result,
        }

        result = policy_stage.execute(stage_context)

        if tracker:
            tracker.record_stage_result(result)

        logger.info(f"Policy evaluation completed: {result.status.value}")

        # Phase 1 & 2: Register artifacts for traceability
        # Note: Policy stage doesn't generate files, but we track the evaluation result as metadata
        policy_artifact_ids = []
        if result.status == StageStatus.SUCCEEDED and aird_context.get("pipeline_run"):
            try:
                # Get input artifact IDs from fingerprint stage (for lineage)
                fingerprint_artifact_ids_str = fingerprint_result.get("artifact_ids", []) if fingerprint_result else []
                input_artifact_ids = (
                    [UUID(aid) for aid in fingerprint_artifact_ids_str] if fingerprint_artifact_ids_str else None
                )

                from primedata.db.models import PipelineArtifact as PA

                # Policy now generates a file, retrieve its stats from storage
                # Must use artifacts_prefix to match where put_artifact() saves the file
                from primedata.storage.paths import artifacts_prefix, safe_filename
                policy_storage_key = f"{artifacts_prefix(workspace_id, product_id, version)}{safe_filename('policy_result.json')}"
                s3_bucket = os.getenv("S3_METADATA_BUCKET", "primedata-raw")
                stat_info = _retrieve_file_stats(s3_bucket, policy_storage_key)

                if stat_info:
                    file_size = stat_info.get("size", 0)
                    storage_etag = stat_info.get("etag", "unknown")
                    logger.info(f"✅ Policy result file size: {file_size} bytes")
                else:
                    logger.warning(f"⚠️  Could not retrieve policy result file stats, using default file_size=0")
                    file_size = 0
                    storage_etag = "unknown"

                # Prepare artifact metadata
                artifact_metadata_dict = {
                    "policy_passed": result.metrics.get("policy_passed", False),
                    "violations": result.metrics.get("violations", []),
                    "violations_count": result.metrics.get("violations_count", 0),
                    "thresholds": result.metrics.get("thresholds", {}),
                }

                # Calculate checksum from metadata JSON
                metadata_json = json.dumps(artifact_metadata_dict, sort_keys=True)
                metadata_bytes = metadata_json.encode("utf-8")
                metadata_checksum = calculate_checksum(metadata_bytes, algorithm="sha256")

                policy_artifact = PA(
                    pipeline_run_id=aird_context["pipeline_run"].id,
                    workspace_id=workspace_id,
                    product_id=product_id,
                    version=version,
                    stage_name="policy",
                    artifact_type=ArtifactType.JSON,
                    artifact_name="policy_evaluation",
                    storage_bucket=s3_bucket,
                    storage_key=policy_storage_key,
                    file_size=file_size,  # Actual file size from S3
                    checksum=metadata_checksum,
                    storage_etag=storage_etag,
                    input_artifacts=(
                        [
                            {
                                "artifact_id": str(aid),
                                "stage": "fingerprint",
                                "artifact_name": "fingerprint",
                            }
                            for aid in input_artifact_ids
                        ]
                        if input_artifact_ids
                        else []
                    ),
                    artifact_metadata=artifact_metadata_dict,
                    retention_policy=RetentionPolicy.KEEP_FOREVER,
                    status=ArtifactStatus.ACTIVE,
                )
                db.add(policy_artifact)
                db.commit()
                db.refresh(policy_artifact)
                policy_artifact_ids.append(policy_artifact.id)
                logger.info(f"Registered policy evaluation artifact with file_size={file_size}")
            except Exception as e:
                logger.error(f"Failed to register policy artifacts: {e}", exc_info=True)

        # Mark raw files as failed if policy failed (before raising exception)
        if result.status == StageStatus.FAILED:
            error_msg = result.error or "Unknown error"
            mark_raw_files_as_failed(product_id, raw_file_version, f"Policy stage failed: {error_msg}", db_session=db)

        # Raise exception if stage failed (Airflow only fails tasks on exceptions)
        raise_if_stage_failed(result, "Policy")

        # Update product policy status
        product = db.query(Product).filter(Product.id == product_id).first()
        if product and result.status == StageStatus.SUCCEEDED:
            # Derive policy_status from policy_passed boolean (PolicyStage doesn't return policy_status directly)
            policy_passed = result.metrics.get("policy_passed", False)
            violations = result.metrics.get("violations", [])

            # Map policy_passed boolean to PolicyStatus enum
            if policy_passed:
                product.policy_status = PolicyStatus.PASSED
            else:
                product.policy_status = PolicyStatus.FAILED

            product.policy_violations = violations
            db.commit()
            logger.info(f"Updated product policy_status to {product.policy_status.value}, violations_count={len(violations)}")
            logger.info(
                f"Updated product policy_status to {product.policy_status.value}, violations_count={len(violations)}"
            )

        # Determine policy_status for return value
        policy_passed = result.metrics.get("policy_passed", False)
        policy_status_str = "passed" if policy_passed else "failed"

        return {
            "status": result.status.value,
            "policy_status": policy_status_str,
            "violations": result.metrics.get("violations", []),
        }
    except Exception as e:
        logger.error(f"Policy evaluation failed: {e}", exc_info=True)
        logger.error(f"Policy evaluation failed: {e}", exc_info=True)
        # Mark raw files as FAILED since pipeline failed at policy stage
        mark_raw_files_as_failed(product_id, raw_file_version, f"Policy stage failed: {str(e)}", db_session=db)
        raise
    finally:
        db.close()


def task_reporting(**context) -> Dict[str, Any]:
    """Generate PDF trust report using AIRD ReportingStage."""
    params = get_dag_params(**context)
    workspace_id = params["workspace_id"]
    product_id = params["product_id"]
    version = params["version"]
    raw_file_version = params.get("raw_file_version", version)

    logger.info(f"Starting AIRD PDF report generation for product {product_id}, version {version}")

    aird_context = get_aird_context(**context)
    storage = aird_context["storage"]
    tracker = aird_context.get("tracker")
    db = aird_context["db"]

    try:
        # Get scoring result
        scoring_result = context["task_instance"].xcom_pull(task_ids="scoring", key="scoring_result")
        if not scoring_result:
            scoring_result = context["task_instance"].xcom_pull(task_ids="scoring")

        # Create and execute reporting stage
        # Lazy import to avoid DAG import timeouts
        from primedata.ingestion_pipeline.aird_stages.reporting import ReportingStage

        reporting_stage = ReportingStage(
            product_id=product_id,
            version=version,
            workspace_id=workspace_id,
        )

        stage_context = {
            "storage": storage,
            "scoring_result": scoring_result,
        }

        result = reporting_stage.execute(stage_context)

        if tracker:
            tracker.record_stage_result(result)

        logger.info(f"PDF report generation completed: {result.status.value}")

        # Phase 1 & 2: Register artifacts for traceability
        reporting_artifact_ids = []
        if result.status == StageStatus.SUCCEEDED and aird_context.get("pipeline_run"):
            try:
                # Get input artifact IDs from scoring stage (for lineage)
                scoring_artifact_ids_str = scoring_result.get("artifact_ids", []) if scoring_result else []
                input_artifact_ids = [UUID(aid) for aid in scoring_artifact_ids_str] if scoring_artifact_ids_str else None

                reporting_artifact_ids = register_stage_artifacts(
                    db=db,
                    pipeline_run_id=aird_context["pipeline_run"].id,
                    workspace_id=workspace_id,
                    product_id=product_id,
                    version=version,
                    stage_name="reporting",
                    result=result,
                    storage=storage,
                    input_artifact_ids=input_artifact_ids,
                )
                logger.info(f"Registered {len(reporting_artifact_ids)} reporting artifacts")
                logger.info(f"Registered {len(reporting_artifact_ids)} reporting artifacts")
            except Exception as e:
                logger.error(f"Failed to register reporting artifacts: {e}", exc_info=True)
                logger.error(f"Failed to register reporting artifacts: {e}", exc_info=True)

        # Mark raw files as failed if reporting failed (before raising exception)
        if result.status == StageStatus.FAILED:
            error_msg = result.error or "Unknown error"
            mark_raw_files_as_failed(product_id, raw_file_version, f"Reporting stage failed: {error_msg}", db_session=db)

        # Raise exception if stage failed (Airflow only fails tasks on exceptions)
        raise_if_stage_failed(result, "Reporting")

        # Update product trust report path
        # The path is stored in result.artifacts['trust_report_pdf'], not in metrics
        trust_report_path = None
        if result.artifacts and "trust_report_pdf" in result.artifacts:
            trust_report_path = result.artifacts["trust_report_pdf"]

        product = db.query(Product).filter(Product.id == product_id).first()
        if product and result.status == StageStatus.SUCCEEDED and trust_report_path:
            product.trust_report_path = trust_report_path
            db.commit()

        return {
            "status": result.status.value,
            "trust_report_path": trust_report_path,
        }
    except Exception as e:
        logger.error(f"PDF report generation failed: {e}", exc_info=True)
        logger.error(f"PDF report generation failed: {e}", exc_info=True)
        # Mark raw files as FAILED since pipeline failed at reporting stage
        mark_raw_files_as_failed(product_id, raw_file_version, f"Reporting stage failed: {str(e)}", db_session=db)
        raise
    finally:
        db.close()


def task_decide_vector_indexing(**context) -> str:
    """Branching task: decide whether to run indexing based on vector_creation_enabled."""
    params = get_dag_params(**context)
    product_id = params["product_id"]
    db = next(get_db())

    try:
        product = db.query(Product).filter(Product.id == product_id).first()
        if product and should_skip_vectors(product):
            logger.info(f"Vector creation disabled for product {product_id}; branching to skip_indexing")
            return "skip_indexing"
        logger.info(f"Vector creation enabled for product {product_id}; branching to indexing")
        return "indexing"
    finally:
        db.close()


def task_record_vectors_skipped(**context) -> Dict[str, Any]:
    """Record vector skip in pipeline metrics when vector creation is disabled."""
    params = get_dag_params(**context)
    product_id = params["product_id"]
    version = params["version"]
    db = next(get_db())

    try:
        product = db.query(Product).filter(Product.id == product_id).first()
        if product and should_skip_vectors(product):
            pipeline_run = (
                db.query(PipelineRun)
                .filter(PipelineRun.product_id == product_id, PipelineRun.version == version)
                .first()
            )
            if pipeline_run:
                if pipeline_run.metrics is None:
                    pipeline_run.metrics = {}
                pipeline_run.metrics["vectors_skipped"] = True
                pipeline_run.metrics["vectors_skip_reason"] = "vector_creation_enabled is False"
                from sqlalchemy.orm.attributes import flag_modified

                flag_modified(pipeline_run, "metrics")
                db.commit()
                logger.info(f"Recorded vectors_skipped in pipeline_run {pipeline_run.id}")
        return {"status": "skipped", "vectors_skipped": True}
    finally:
        db.close()


# Re-export task_indexing from extracted module for backward compatibility
from primedata.ingestion_pipeline.dag_indexing_task import task_indexing  # noqa: F401


def task_validate_data_quality(**context) -> Dict[str, Any]:
    """Validate data quality rules and generate violations."""
    params = get_dag_params(**context)
    workspace_id = params["workspace_id"]
    product_id = params["product_id"]
    version = params["version"]
    raw_file_version = params.get("raw_file_version", version)
    pipeline_run_id = get_pipeline_run_id_from_context(**context)

    logger.info(f"Starting data quality validation for product {product_id}, version {version}")

    # Get database session
    db = next(get_db())

    try:
        # Import here to avoid circular imports
        from primedata.db.models import DqViolation
        from primedata.db.models_enterprise import DataQualityRule

        # Get current data quality rules for the product
        rules = (
            db.query(DataQualityRule)
            .filter(DataQualityRule.product_id == product_id, DataQualityRule.is_current == True)
            .all()
        )

        logger.info(f"Found {len(rules)} data quality rules for product {product_id}")

        if not rules:
            logger.info("No data quality rules found, skipping validation")
            return {
                "status": "skipped",
                "message": "No data quality rules configured",
            }

        violations_count = 0

        for rule in rules:
            if not rule.enabled:
                logger.info(f"Skipping disabled rule: {rule.name}")
                continue

            logger.info(f"Evaluating rule: {rule.name} ({rule.rule_type})")
            # Add rule evaluation logic here
            # For now, this is a placeholder

        logger.info(f"Data quality validation completed: {violations_count} violations found")

        return {
            "status": "completed",
            "violations_count": violations_count,
        }

    except Exception as e:
        logger.error(f"Data quality validation failed: {e}", exc_info=True)
        logger.error(f"Data quality validation failed: {e}", exc_info=True)
        # Mark raw files as FAILED since pipeline failed at data quality validation stage
        mark_raw_files_as_failed(product_id, raw_file_version, f"Data quality validation stage failed: {str(e)}", db_session=db)
        raise
    finally:
        db.close()
