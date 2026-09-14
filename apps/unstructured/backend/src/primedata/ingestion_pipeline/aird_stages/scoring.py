"""
AIRD scoring stage for PrimeData.

Scores processed chunks and generates per-chunk metrics.
"""

import json
from datetime import datetime
from typing import Any, Dict, List
from uuid import UUID

import logging
logger = logging.getLogger(__name__)
from primedata.ingestion_pipeline.aird_stages.base import AirdStage, StageResult, StageStatus
from primedata.services.trust_scoring import (
    get_scoring_weights,
    score_record,
    score_record_with_ai_ready_metrics,
    aggregate_metrics_with_ai_ready,
)


class ScoringStage(AirdStage):
    """Scoring stage that calculates trust metrics for processed chunks."""

    @property
    def stage_name(self) -> str:
        """Return the unique name of this stage.

        :return: The string 'scoring'.
        """
        return "scoring"

    def get_required_artifacts(self) -> list[str]:
        """Return artifacts required by the scoring stage.

        :return: List containing 'processed_jsonl' as the required input artifact.
        """
        return ["processed_jsonl"]

    def execute(self, context: Dict[str, Any]) -> StageResult:
        """Execute the scoring stage to calculate trust metrics for processed chunks.

        :param context: Stage execution context containing 'storage' (AirdStorageAdapter)
            and optionally 'processed_files' (list of processed file stems), 'playbook',
            and 'playbook_id'.
        :return: StageResult with scoring metrics including per-file and aggregate trust scores.
        """
        logger.info(f"🎯 ScoringStage.execute() entry | product_id={self.product_id}, version={self.version}, context_keys={list(context.keys())}")
        started_at = datetime.utcnow()
        storage = context.get("storage")
        processed_files = context.get("processed_files", [])
        chunking_config = context.get("chunking_config")
        if chunking_config:
            logger.info(f"📋 Effective chunking config (scoring stage): {chunking_config}")

        if not storage:
            logger.error(f"❌ Storage adapter not found in context")
            return self._create_result(
                status=StageStatus.FAILED,
                metrics={},
                error="Storage adapter not found in context",
                started_at=started_at,
            )

        if not processed_files:
            # Try to get from previous stage
            logger.info(f"📋 Retrieving processed files from preprocess_result...")
            preprocess_result = context.get("preprocess_result")
            if preprocess_result and preprocess_result.get("processed_file_list"):
                processed_files = preprocess_result["processed_file_list"]
                logger.info(f"✅ Loaded {len(processed_files)} processed files from preprocess_result")
            else:
                logger.warning(f"⚠️ No processed files to score")
                return self._create_result(
                    status=StageStatus.SKIPPED,
                    metrics={"reason": "no_processed_files"},
                    started_at=started_at,
                )

        logger.info(f"📊 Starting scoring for {len(processed_files)} files")

        all_metrics: List[Dict[str, Any]] = []
        scored_files = []
        failed_files = []
        total_chunks = 0

        # Get scoring weights
        logger.debug(f"📋 Loading scoring weights...")
        weights = get_scoring_weights()
        logger.info(f"✅ Scoring weights loaded")

        # Get playbook for AI-Ready metrics (noise patterns, coherence settings)
        playbook = context.get("playbook") or {}
        playbook_id = context.get("playbook_id", "TECH")

        # Check if playbook is actually loaded (not just an empty dict)
        has_playbook = playbook and isinstance(playbook, dict) and len(playbook) > 0

        if has_playbook:
            logger.info(f"📋 Using playbook {playbook_id} for AI-Ready metrics (loaded successfully, keys: {list(playbook.keys())[:5]})")
            # Log if AI-Ready sections are present
            if "noise_patterns" in playbook:
                logger.info(f"✅ Playbook {playbook_id} has noise_patterns section")
            if "coherence" in playbook:
                logger.info(f"✅ Playbook {playbook_id} has coherence section")
        else:
            logger.warning(f"⚠️ Playbook {playbook_id} not available or empty, skipping AI-Ready metrics")

        for file_stem in processed_files:
            try:
                logger.debug(f"📋 Processing file: {file_stem}")
                # Load processed JSONL
                records = storage.get_processed_jsonl(file_stem)
                if not records:
                    logger.warning(f"⚠️ Processed JSONL not found for {file_stem}, skipping")
                    failed_files.append(file_stem)
                    continue

                # Score each record
                file_metrics = []
                file_tag = f"{file_stem}.jsonl"
                logger.debug(f"📋 Scoring {len(records)} records in {file_stem}...")

                for record in records:
                    try:
                        # Use AI-Ready metrics scorer if playbook is available
                        if has_playbook:
                            scored = score_record_with_ai_ready_metrics(record, weights, playbook)
                        else:
                            scored = score_record(record, weights)

                        # Add file tag and metadata
                        scored["file"] = file_tag
                        scored["section"] = record.get("section", "unknown")
                        if record.get("chunk_id"):
                            scored["chunk_id"] = record["chunk_id"]
                        if record.get("document_id"):
                            scored["document_id"] = record["document_id"]
                        if record.get("page") is not None:
                            scored["page"] = record["page"]

                        file_metrics.append(scored)
                        total_chunks += 1
                    except Exception as e:
                        logger.error(f"❌ Failed to score chunk in {file_stem}: {e}")
                        continue

                if file_metrics:
                    logger.info(f"✅ Scored {len(file_metrics)} records in {file_stem}")
                    all_metrics.extend(file_metrics)
                    scored_files.append(file_stem)

                    # Store per-file metrics
                    logger.debug(f"📦 Storing per-file metrics for {file_stem}...")
                    storage.put_artifact(
                        f"{file_stem}.score.metrics.json",
                        json.dumps(file_metrics, indent=2),
                        content_type="application/json",
                    )
                    logger.info(f"✅ Stored metrics for {file_stem}")
                else:
                    failed_files.append(file_stem)

            except Exception as e:
                logger.error(f"❌ Failed to score {file_stem}: {e}", exc_info=True)
                failed_files.append(file_stem)

        if not all_metrics:
            logger.error(f"❌ No metrics produced from scoring | scored_files={len(scored_files)}, failed_files={len(failed_files)}")
            return self._create_result(
                status=StageStatus.FAILED,
                metrics={
                    "scored_files": len(scored_files),
                    "failed_files": len(failed_files),
                    "failed_file_list": failed_files,
                },
                error="No metrics produced from scoring",
                started_at=started_at,
            )

        # Store aggregate metrics
        logger.info(f"💾 Storing aggregate metrics ({len(all_metrics)} entries)...")
        storage.put_metrics_json(all_metrics)
        logger.info(f"✅ Aggregate metrics stored")

        # Get preprocessing stats for Chunk Boundary Quality
        logger.debug(f"📋 Retrieving preprocessing stats...")
        preprocessing_stats = context.get("preprocessing_stats", {})
        preprocess_result = context.get("preprocess_result")
        if preprocess_result and preprocess_result.get("metrics"):
            preprocessing_stats = preprocess_result["metrics"]
            logger.debug(f"📋 Using preprocessing stats from preprocess_result")

        finished_at = datetime.utcnow()

        # Calculate aggregate trust score
        trust_scores = [m.get("AI_Trust_Score", 0.0) for m in all_metrics]
        avg_trust_score = round(sum(trust_scores) / len(trust_scores), 4) if trust_scores else 0.0
        logger.info(f"📊 Average trust score: {avg_trust_score}")

        # Calculate aggregate metrics with AI-Ready metrics
        logger.debug(f"📋 Aggregating metrics with AI-Ready metrics...")
        aggregated_metrics = aggregate_metrics_with_ai_ready(all_metrics, preprocessing_stats)
        logger.info(f"✅ Aggregated metrics calculated")

        artifacts = {
            "metrics_json": f"processed/{self.product_id}/v{self.version}/metrics.json",
        }

        metrics = {
            "scored_files": len(scored_files),
            "failed_files": len(failed_files),
            "total_chunks": total_chunks,
            "avg_trust_score": avg_trust_score,
            "scored_file_list": scored_files,
            # Include AI-Ready aggregate metrics
            "ai_ready_metrics": aggregated_metrics,
            "chunking_config_used": chunking_config,
        }

        logger.info(f"✅ Scoring stage succeeded | total_chunks={total_chunks}, avg_trust_score={avg_trust_score}, scored_files={len(scored_files)}, failed_files={len(failed_files)}")
        return self._create_result(
            status=StageStatus.SUCCEEDED,
            metrics=metrics,
            artifacts=artifacts,
            started_at=started_at,
            finished_at=finished_at,
        )
