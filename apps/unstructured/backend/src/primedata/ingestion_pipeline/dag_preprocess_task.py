"""
Airflow DAG Preprocess Task Function

Extracted from dag_stage_tasks.py for maintainability.
Contains the task_preprocess function which is the largest single task.
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
    Product,
    RawFile,
    RawFileStatus,
    RetentionPolicy,
)
from primedata.ingestion_pipeline.aird_stages.base import StageStatus
from primedata.config import resolve_effective_config
from primedata.ingestion_pipeline.artifact_registry import (
    calculate_checksum,
)
from primedata.storage.storage_client import storage_client

from primedata.ingestion_pipeline.dag_context import (
    get_dag_params,
    get_aird_context,
    raise_if_stage_failed,
)
from primedata.ingestion_pipeline.stage_artifact_registry import (
    register_stage_artifacts,
)
from primedata.ingestion_pipeline.auto_detection import (
    auto_detect_playbook_and_chunking,
)

logger = get_logger(__name__)


def task_preprocess(**context) -> Dict[str, Any]:
    """Preprocess raw data using AIRD PreprocessStage."""
    params = get_dag_params(**context)
    workspace_id = params["workspace_id"]
    product_id = params["product_id"]
    version = params["version"]  # pipeline run version
    raw_file_version = params.get("raw_file_version", version)  # input raw file version
    playbook_id = params.get("playbook_id")

    logger.info(f"Starting AIRD preprocessing for product {product_id}, version {version}, playbook={playbook_id}")

    # Get AIRD context
    aird_context = get_aird_context(**context)
    storage = aird_context["storage"]
    tracker = aird_context.get("tracker")
    db = aird_context["db"]

    try:
        # Verify product exists first (enterprise best practice: validate before query)
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            logger.error(f"Product {product_id} not found in database")
            raise ValueError(f"Product {product_id} not found. Cannot process raw files for non-existent product.")

        logger.info(f"Found product: {product.name} (id: {product_id}, current_version: {product.current_version})")

        # Verify version matches (safety check)
        if version and product.current_version and version > product.current_version:
            logger.warning(f"Pipeline version {version} is greater than product current_version {product.current_version}")
            logger.info("This is normal for new ingestions - raw files may exist for this version")

        # Get playbook_id from product if not provided
        if product.playbook_id and not playbook_id:
            playbook_id = product.playbook_id
            logger.info(f"Using playbook from product: {playbook_id}")

        # Enterprise best practice: Query raw files with explicit type conversion and logging
        logger.info(
            f"Querying raw files for product_id={product_id} (type: {type(product_id).__name__}), "
            f"raw_file_version={raw_file_version} (type: {type(raw_file_version).__name__}), pipeline_run_version={version}"
        )

        # Ensure product_id is UUID type for query
        query_product_id = UUID(str(product_id)) if not isinstance(product_id, UUID) else product_id
        query_version = int(raw_file_version) if raw_file_version is not None else None

        if query_version is None:
            logger.error("Version is None - cannot query raw files without version")
            raise ValueError("Version parameter is required to query raw files")

        # Query raw files from database (stored during initial ingest)
        # Filter by exact product_id and version match (enterprise best practice: strict filtering)
        raw_file_records = (
            db.query(RawFile)
            .filter(
                RawFile.product_id == query_product_id,
                RawFile.version == query_version,
                RawFile.status != RawFileStatus.DELETED,  # Exclude deleted files
            )
            .all()
        )

        logger.info(f"Found {len(raw_file_records)} raw file records in database for product {product_id}, version {version}")

        # Additional verification: Check if any raw files exist for this product at all (helpful for debugging)
        all_product_files = db.query(RawFile).filter(RawFile.product_id == query_product_id).all()
        if all_product_files and not raw_file_records:
            # Files exist for product but not for this version
            versions_available = set(f.version for f in all_product_files)
            logger.warning(f"Raw files exist for product {product_id} but not for version {version}")
            logger.info(f"Available versions for this product: {sorted(versions_available)}")
            logger.info("Hint: Make sure initial ingest was run for the correct version")
            logger.info(
                f"Pipeline is looking for version {version}, but files exist for versions: {sorted(versions_available)}"
            )
        elif raw_file_records:
            # Log the actual files found for verification
            file_info = [
                f"{rf.filename} (stem: {rf.file_stem}, status: {rf.status.value}, storage_key: {rf.storage_key})"
                for rf in raw_file_records[:10]
            ]  # Log first 10 files
            logger.info(f"Raw files found for product {product_id}, version {version}:")
            for info in file_info:
                logger.info(f"  - {info}")
            if len(raw_file_records) > 10:
                logger.info(f"  ... and {len(raw_file_records) - 10} more files")

            # Verify all files belong to the correct product and version
            mismatched = [rf for rf in raw_file_records if rf.product_id != query_product_id or rf.version != query_version]
            if mismatched:
                logger.error(f"CRITICAL: Found {len(mismatched)} raw files with mismatched product_id or version!")
                for rf in mismatched:
                    logger.error(
                        f"  Mismatch: file_id={rf.id}, expected_product={query_product_id}, got_product={rf.product_id}, "
                        f"expected_version={query_version}, got_version={rf.version}"
                    )
                raise ValueError(
                    f"Database integrity error: {len(mismatched)} raw files have mismatched product_id or version"
                )
            else:
                logger.info(f"✓ All {len(raw_file_records)} raw files verified: correct product_id and version")

        if not raw_file_records:
            error_msg = (
                f"No raw files found in database for product {product_id}, version {version}. Please run initial ingest first."
            )
            logger.error(f"❌ PREPROCESSING FAILED: {error_msg}")
            logger.info("Raw files should be ingested first using 'Run initial ingest' button")

            # Raise exception to mark Airflow task as FAILED (this is a failure condition, not a skip)
            raise RuntimeError(error_msg)

        # Enterprise best practice: Validate files exist in storage before processing
        validated_files = []
        files_missing = []

        logger.info(f"🔍 Validating {len(raw_file_records)} raw files in storage...")
        for record in raw_file_records:
            # Check if file exists in storage
            try:
                full_path = f"s3://{record.storage_bucket}/{record.storage_key}"
                logger.debug(f"  Checking file: {full_path}")
                exists = storage_client.object_exists(record.storage_bucket, record.storage_key)
                if exists:
                    validated_files.append(record.file_stem)
                    logger.info(f"  ✅ File found: {full_path}")
                    # Update status to processing
                    if record.status == RawFileStatus.INGESTED:
                        record.status = RawFileStatus.PROCESSING
                else:
                    files_missing.append(record.file_stem)
                    logger.warning(f"  ❌ File missing in storage: {full_path}")
                    logger.warning(f"     Database reference: file_stem={record.file_stem}, storage_key={record.storage_key}, bucket={record.storage_bucket}")
                    record.status = RawFileStatus.FAILED
                    record.error_message = f"File not found in storage: {record.storage_key}"
            except Exception as e:
                full_path = f"s3://{record.storage_bucket}/{record.storage_key}"
                logger.error(f"  ❌ Error checking file existence for {full_path}: {e}")
                logger.error(f"     Details: storage_key={record.storage_key}, bucket={record.storage_bucket}, error_type={type(e).__name__}")
                files_missing.append(record.file_stem)
                record.status = RawFileStatus.FAILED
                record.error_message = f"Error validating file: {str(e)}"

        # Commit status updates
        if files_missing:
            db.commit()
            logger.warning(f"{len(files_missing)} files missing in storage: {files_missing}")
            # Log detailed info about each missing file
            for record in raw_file_records:
                if record.file_stem in files_missing:
                    logger.warning(f"  Missing file details:")
                    logger.warning(f"    - File stem: {record.file_stem}")
                    logger.warning(f"    - S3 Path: s3://{record.storage_bucket}/{record.storage_key}")
                    logger.warning(f"    - Filename: {record.filename}")
                    logger.warning(f"    - Status: {record.status}")

        if not validated_files:
            error_msg = f"No valid files found. {len(files_missing)} files missing in storage."
            logger.error(f"❌ PREPROCESSING FAILED: {error_msg}")
            logger.error(f"Missing files ({len(files_missing)}):")
            for record in raw_file_records:
                if record.file_stem in files_missing:
                    logger.error(f"  - {record.filename} (stem={record.file_stem}, s3://{record.storage_bucket}/{record.storage_key})")

            # Mark all raw files as failed
            for record in raw_file_records:
                if record.status != RawFileStatus.FAILED:
                    record.status = RawFileStatus.FAILED
                    record.error_message = error_msg
            db.commit()

            # Raise exception to mark Airflow task as FAILED
            raise RuntimeError(error_msg)

        # Extract file stems and create mapping to storage_keys for accurate file retrieval
        raw_files = validated_files

        # Create mapping: file_stem -> storage_key for accurate file retrieval
        # This ensures we use the exact storage_key from database, not construct a path with .txt extension
        file_stem_to_storage_key = {}
        for record in raw_file_records:
            if record.file_stem in raw_files:
                file_stem_to_storage_key[record.file_stem] = {
                    "storage_key": record.storage_key,
                    "storage_bucket": record.storage_bucket,
                    "filename": record.filename,
                }

        logger.info(
            f"Found {len(raw_files)} validated raw files in database to process (out of {len(raw_file_records)} total)"
        )
        logger.info(f"Raw files will be read from storage using stored keys")
        logger.info(f"File stems to process: {raw_files}")
        logger.info(f"file_stem_to_storage_key mapping: {file_stem_to_storage_key}")

        # Auto-detect playbook and chunking configuration if needed
        # This runs BEFORE preprocessing stage to set up configuration
        # Refresh product to get latest state
        db.refresh(product)
        needs_auto_detection = (
            (product.playbook_id is None)  # Auto-detect playbook
            or (
                product.chunking_config
                and isinstance(product.chunking_config, dict)
                and product.chunking_config.get("mode") == "auto"  # Auto-detect chunking
            )
        )

        if needs_auto_detection:
            # Get validated raw file records (only files that exist in storage)
            validated_raw_file_records = [rf for rf in raw_file_records if rf.file_stem in validated_files]

            if validated_raw_file_records:
                logger.info(f"🔍 Starting auto-detection for playbook and/or chunking configuration...")
                logger.info(f"  - Playbook auto-detect: {product.playbook_id is None}")
                logger.info(f"  - Chunking auto-detect: {product.chunking_config and isinstance(product.chunking_config, dict) and product.chunking_config.get('mode') == 'auto'}")
                logger.info(f"  - Sampling from {len(validated_raw_file_records)} validated files")

                try:
                    auto_detection_updates = auto_detect_playbook_and_chunking(
                        product=product,
                        raw_file_records=validated_raw_file_records,
                        storage=storage,
                        db=db,
                    )

                    if auto_detection_updates:
                        logger.info(f"✅ Auto-detection completed: {list(auto_detection_updates.keys())}")

                        # Update product with detected values
                        if "playbook_id" in auto_detection_updates:
                            product.playbook_id = auto_detection_updates["playbook_id"]
                            playbook_id = auto_detection_updates["playbook_id"]  # Update local variable
                            logger.info(f"  → Updated playbook_id: {product.playbook_id}")

                        if "playbook_selection" in auto_detection_updates:
                            product.playbook_selection = auto_detection_updates["playbook_selection"]
                            logger.info(f"  → Updated playbook_selection: {auto_detection_updates['playbook_selection']}")

                        if "chunking_config" in auto_detection_updates:
                            from sqlalchemy.orm.attributes import flag_modified
                            product.chunking_config = auto_detection_updates["chunking_config"]
                            flag_modified(product, "chunking_config")
                            chunking_config = auto_detection_updates["chunking_config"]  # Update local variable
                            logger.info(f"  → Updated chunking_config with resolved_settings")

                        # Commit updates to database
                        db.commit()
                        db.expire_all()
                        db.refresh(product)
                        logger.info("✅ Auto-detection updates committed to database")
                        refreshed_product = db.get(Product, product_id)
                        if refreshed_product:
                            product = refreshed_product
                            refreshed_chunking_config = product.chunking_config or {}
                            if isinstance(refreshed_chunking_config, dict) and refreshed_chunking_config.get("mode") == "auto":
                                refreshed_chunking_config["manual_settings"] = {}
                            chunking_config = refreshed_chunking_config
                            chunking_config = product.chunking_config
                            if product.playbook_id and not playbook_id:
                                playbook_id = product.playbook_id
                            if isinstance(chunking_config, dict):
                                logger.info(
                                    "🔄 Refreshed chunking_config after auto-detection: "
                                    f"last_analyzed={chunking_config.get('last_analyzed')}, "
                                    f"sample_files_analyzed={chunking_config.get('sample_files_analyzed')}"
                                )
                            params["chunking_config"] = refreshed_chunking_config
                            params["force_product_chunking_config"] = True
                            dag_run = context.get("dag_run")
                            if dag_run and isinstance(getattr(dag_run, "conf", None), dict):
                                dag_run.conf["chunking_config"] = refreshed_chunking_config
                                dag_run.conf["force_product_chunking_config"] = True
                    else:
                        logger.info("ℹ️ No auto-detection updates needed or available")
                except Exception as e:
                    logger.error(f"❌ Auto-detection failed: {e}", exc_info=True)
                    logger.error(f"Auto-detection failed: {e}", exc_info=True)
                    # Continue with preprocessing even if auto-detection fails
                    # The existing playbook/chunking config will be used
                    logger.warning("Continuing with preprocessing using existing/default configuration")
            else:
                logger.warning("⚠️ Auto-detection skipped: no validated raw files available")
        else:
            logger.info("ℹ️ Auto-detection not needed: playbook_id is set and chunking mode is not auto")

        # Get playbook_id from product if updated (or from params)
        if product.playbook_id and not playbook_id:
            playbook_id = product.playbook_id
            logger.info(f"Using playbook from product (after auto-detection): {playbook_id}")

        # Create and execute preprocessing stage
        # Lazy import to avoid DAG import timeouts
        from primedata.ingestion_pipeline.aird_stages.preprocess import PreprocessStage

        logger.info(
            f"Creating PreprocessStage instance: product_id={product_id}, version={version}, workspace_id={workspace_id}, playbook_id={playbook_id}"
        )
        try:
            preprocess_stage = PreprocessStage(
                product_id=product_id,
                version=version,
                workspace_id=workspace_id,
                config={"playbook_id": playbook_id} if playbook_id else {},
            )
            logger.info(f"PreprocessStage instance created successfully")
        except Exception as e:
            logger.error(f"Failed to create PreprocessStage instance: {type(e).__name__}: {str(e)}", exc_info=True)
            import traceback

            logger.error(f"PreprocessStage creation traceback:\n{traceback.format_exc()}")
            raise

        # Refresh product to get latest chunking_config (including resolved_settings from auto-detection)
        if product:
            db.refresh(product)

        # Use new resolver with precedence-based resolution
        run_conf = params or {}
        detected_playbook = None  # Could extract from auto-detection if available

        effective = resolve_effective_config(
            run_conf=run_conf,
            product_row=product,
            detected_playbook=detected_playbook,
        )

        # Convert to legacy format for backward compatibility
        effective_config = effective.to_legacy_dict(product_row=product)
        chunking_config = effective_config.get("chunking_config")
        playbook_id = effective_config.get("playbook_id") or playbook_id
        playbook_selection = effective_config.get("playbook_selection")

        # Log new resolver usage and resolution trace
        logger.info("✅ Using NEW resolver: resolve_effective_config()")
        logger.info("Resolution trace: %s", effective.resolution_trace.dict() if effective.resolution_trace else None)
        logger.info("Effective chunking: chunk_size=%s, chunk_overlap=%s, strategy=%s",
                    effective.chunking_config.chunk_size,
                    effective.chunking_config.chunk_overlap,
                    effective.chunking_config.chunking_strategy)
        logger.info("Effective playbook: %s", effective.playbook_id)
        logger.info(f"Effective chunking config (preprocess): {chunking_config}")
        logger.info(f"Effective playbook (preprocess): {playbook_selection or {'playbook_id': playbook_id}}")

        # Log preprocessing flags if present (from recommendations)
        if chunking_config and isinstance(chunking_config, dict):
            preprocessing_flags = chunking_config.get("preprocessing_flags", {})
            if preprocessing_flags:
                logger.info(f"✅ Preprocessing flags detected (from recommendations): {preprocessing_flags}")
                if preprocessing_flags.get("enhanced_normalization"):
                    logger.info("  → Enhanced normalization will be applied")
                if preprocessing_flags.get("error_correction"):
                    logger.info("  → Error correction will be applied")
                if preprocessing_flags.get("force_metadata_extraction") or preprocessing_flags.get(
                    "additional_metadata_fields"
                ):
                    logger.info("  → Enhanced metadata extraction will be applied")

        stage_context = {
            "storage": storage,
            "raw_files": raw_files,
            "playbook_id": playbook_id,
            "playbook_selection": playbook_selection,
            "file_stem_to_storage_key": file_stem_to_storage_key,  # Pass mapping for accurate file retrieval
            "chunking_config": chunking_config,  # Pass product chunking config (including preprocessing_flags)
            "workspace_id": workspace_id,  # For loading custom playbooks
            "db": db,  # For loading custom playbooks
            "use_case_description": product.use_case_description if product else None,
        }
        logger.info(f"Executing PreprocessStage with context keys: {list(stage_context.keys())}")
        logger.info(f"Context storage type: {type(stage_context['storage']).__name__}")
        logger.info(f"Context raw_files: {stage_context['raw_files']}")
        logger.info(f"Context file_stem_to_storage_key keys: {list(stage_context['file_stem_to_storage_key'].keys())}")

        try:
            result = preprocess_stage.execute(stage_context)
            logger.info(f"PreprocessStage.execute() completed: status={result.status.value}")
        except Exception as e:
            logger.error(f"EXCEPTION during PreprocessStage.execute(): {type(e).__name__}: {str(e)}", exc_info=True)
            import traceback

            logger.error(f"PreprocessStage.execute() traceback:\n{traceback.format_exc()}")
            raise

        # Track stage result
        if tracker:
            tracker.record_stage_result(result)

            # Update product preprocessing stats (save to S3 if large)
            if product and result.status == StageStatus.SUCCEEDED:
                from primedata.services.s3_json_storage import save_product_json_field

                s3_path, should_save_to_s3 = save_product_json_field(
                    product.workspace_id, product.id, "preprocessing_stats", result.metrics
                )
                if should_save_to_s3 and s3_path:
                    product.preprocessing_stats_path = s3_path
                    product.preprocessing_stats = None  # Clear DB field
                else:
                    product.preprocessing_stats = result.metrics
                    product.preprocessing_stats_path = None  # Clear S3 path if exists
                # Get playbook_id from result metrics (if auto-routed) or use the one from params
                final_playbook_id = result.metrics.get("playbook_id") or playbook_id
                if final_playbook_id:
                    product.playbook_id = final_playbook_id
                    logger.info(f"Updated product {product_id} with playbook_id: {final_playbook_id}")

                # Persist resolved chunking configuration if available (so UI can display actual used config)
                # Preserve original auto_settings and manual_settings while adding resolved_settings
                resolved_chunking = result.metrics.get("chunking_config_used")
                if resolved_chunking:
                    # Preserve existing config structure
                    current_config = product.chunking_config or {}
                    current_config.update(
                        {
                            "mode": resolved_chunking.get("mode", current_config.get("mode", "auto")),
                            "resolved_settings": resolved_chunking,
                            # Preserve auto_settings and manual_settings if they exist
                            "auto_settings": current_config.get("auto_settings", {}),
                            "manual_settings": current_config.get("manual_settings", {}),
                        }
                    )
                    product.chunking_config = current_config
                    logger.info(f"Updated product {product_id} with chunking_config: {product.chunking_config}")

                    # Store chunking config resolved_settings in pipeline_run metrics for UI display
                    if aird_context.get("pipeline_run") and resolved_chunking:
                        pipeline_run = aird_context["pipeline_run"]
                        if pipeline_run.metrics is None:
                            pipeline_run.metrics = {}

                        # Store resolved_settings for this pipeline run
                        pipeline_run.metrics["chunking_config"] = {
                            "resolved_settings": resolved_chunking,
                            "timestamp": datetime.utcnow().isoformat(),
                            "version": version
                        }
                        # Use flag_modified to ensure SQLAlchemy detects the change
                        from sqlalchemy.orm.attributes import flag_modified
                        flag_modified(pipeline_run, "metrics")
                        db.commit()
                        logger.info(f"Stored chunking_config resolved_settings in pipeline_run {pipeline_run.id} metrics")

                # Store playbook selection metadata for verification
                playbook_selection = result.metrics.get("playbook_selection")
                if playbook_selection:
                    # Ensure playbook_id is included in metadata
                    playbook_selection["playbook_id"] = final_playbook_id
                    product.playbook_selection = playbook_selection
                    logger.info(f"Updated product {product_id} with playbook_selection: {playbook_selection}")
                elif final_playbook_id and not product.playbook_selection:
                    # If playbook was provided but no metadata exists, mark as manual
                    product.playbook_selection = {
                        "playbook_id": final_playbook_id,
                        "method": "manual",
                        "reason": None,
                        "detected_at": None,
                    }

            # IMPORTANT: Do NOT mark raw files as PROCESSED here - only mark them in finalize task
            # when entire pipeline completes successfully. Files remain PROCESSING during pipeline run.
            # This allows pipeline to be retried if later stages fail.
            db.commit()

        logger.info(f"Preprocessing completed: {result.status.value}, chunks={result.metrics.get('total_chunks', 0)}")

        # Phase 1 & 2: Register artifacts for traceability
        preprocess_artifact_ids = []
        if result.status == StageStatus.SUCCEEDED and aird_context.get("pipeline_run"):
            try:
                preprocess_artifact_ids = register_stage_artifacts(
                    db=db,
                    pipeline_run_id=aird_context["pipeline_run"].id,
                    workspace_id=workspace_id,
                    product_id=product_id,
                    version=version,
                    stage_name="preprocess",
                    result=result,
                    storage=storage,
                    input_artifact_ids=None,  # Preprocess doesn't have input artifacts (raw files are tracked separately)
                )
                logger.info(f"Registered {len(preprocess_artifact_ids)} preprocessing artifacts")
                logger.info(f"Registered {len(preprocess_artifact_ids)} preprocessing artifacts")
            except Exception as e:
                logger.error(f"Failed to register preprocessing artifacts: {e}", exc_info=True)
                logger.error(f"Failed to register preprocessing artifacts: {e}", exc_info=True)
                # Don't fail the task if artifact registration fails

        # Store result in XCom for next stages (store before raising exception)
        context["task_instance"].xcom_push(
            key="preprocess_result",
            value={
                "status": result.status.value,
                "metrics": result.metrics,
                "processed_file_list": result.metrics.get("processed_file_list", []),
                "artifact_ids": [str(aid) for aid in preprocess_artifact_ids],  # Phase 2: Pass artifact IDs for lineage
            },
        )

        # Mark raw files as failed if preprocessing failed (before raising exception)
        if result.status == StageStatus.FAILED:
            error_msg = result.error or "Unknown error"
            failed_files = result.metrics.get("failed_file_list", [])

            # Mark raw files as failed
            for record in raw_file_records:
                if record.status == RawFileStatus.PROCESSING:
                    record.status = RawFileStatus.FAILED
                    record.error_message = error_msg
            db.commit()

            # Include failed files in error context
            context_msg = f"Failed files: {failed_files}" if failed_files else ""
        else:
            context_msg = ""

        # Raise exception if stage failed (Airflow only fails tasks on exceptions)
        # This will mark the Airflow task as FAILED and stop downstream tasks
        raise_if_stage_failed(result, "Preprocessing", context_msg)

        # Return success metrics only if preprocessing succeeded
        return {
            "status": result.status.value,
            "files_count": result.metrics.get("processed_files", 0),
            "total_chunks": result.metrics.get("total_chunks", 0),
            "playbook_id": result.metrics.get("playbook_id"),
            "processed_file_list": result.metrics.get("processed_file_list", []),
        }

    except Exception as e:
        logger.error(f"Preprocessing failed: {e}", exc_info=True)
        logger.error(f"Preprocessing failed: {e}", exc_info=True)
        # Mark all currently PROCESSING raw files as FAILED
        if "raw_file_records" in locals() and "db" in locals():
            try:
                for record in raw_file_records:
                    if record.status == RawFileStatus.PROCESSING:
                        record.status = RawFileStatus.FAILED
                        record.error_message = record.error_message or f"Preprocessing failed: {str(e)}"
                db.commit()
            except Exception as db_error:
                logger.error(f"Failed to update raw file status during preprocessing error: {db_error}")
                logger.error(f"Failed to update raw file status during preprocessing error: {db_error}")
                db.rollback()
        raise
    finally:
        if "db" in locals():
            db.close()
