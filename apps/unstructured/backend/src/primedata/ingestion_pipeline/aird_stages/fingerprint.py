"""
AIRD fingerprint generation stage for PrimeData.

Generates readiness fingerprints by aggregating chunk-level metrics.
"""

import json
from datetime import datetime
from typing import Any, Dict
from uuid import UUID

from primedata.utils.log_utils import get_logger
from primedata.ingestion_pipeline.aird_stages.base import AirdStage, StageResult, StageStatus
from primedata.services.fingerprint import generate_fingerprint

logger = get_logger(__name__)


class FingerprintStage(AirdStage):
    """Fingerprint stage that aggregates metrics into readiness fingerprints."""

    @property
    def stage_name(self) -> str:
        return "fingerprint"

    def get_required_artifacts(self) -> list[str]:
        """Fingerprint requires metrics from scoring stage."""
        return ["metrics_json"]

    def execute(self, context: Dict[str, Any]) -> StageResult:
        """Execute fingerprint generation stage.

        Args:
            context: Stage execution context with:
                - storage: AirdStorageAdapter
                - scoring_result: Optional result from scoring stage

        Returns:
            StageResult with fingerprint metrics
        """
        logger.info(f"🎯 FingerprintStage.execute() entry | product_id={self.product_id}, version={self.version}, context_keys={list(context.keys())}")
        started_at = datetime.utcnow()
        storage = context.get("storage")

        if not storage:
            logger.error(f"❌ Storage adapter not found in context")
            return self._create_result(
                status=StageStatus.FAILED,
                metrics={},
                error="Storage adapter not found in context",
                started_at=started_at,
            )

        try:
            # Load metrics from storage
            logger.info(f"📋 Loading metrics from storage...")
            metrics = storage.get_metrics_json()
            if not metrics:
                logger.warning(f"⚠️ No metrics found for fingerprint generation")
                return self._create_result(
                    status=StageStatus.SKIPPED,
                    metrics={"reason": "no_metrics"},
                    started_at=started_at,
                )

            logger.info(f"📊 Generating fingerprint from {len(metrics)} metric entries")

            # Get preprocessing stats from scoring result for Chunk Boundary Quality
            scoring_result = context.get("scoring_result", {})
            preprocessing_stats = None
            if scoring_result and scoring_result.get("metrics"):
                # Try to get preprocessing stats from scoring result
                ai_ready_metrics = scoring_result.get("metrics", {}).get("ai_ready_metrics", {})
                # Or get from preprocess result if available
                preprocess_result = context.get("preprocess_result")
                if preprocess_result and preprocess_result.get("metrics"):
                    preprocessing_stats = preprocess_result["metrics"]
                    logger.debug(f"📋 Using preprocessing stats from preprocess_result")
                elif hasattr(storage, 'get_preprocessing_stats'):
                    preprocessing_stats = storage.get_preprocessing_stats()
                    logger.debug(f"📋 Using preprocessing stats from storage")

            # Generate fingerprint with AI-Ready metrics
            logger.info(f"🔍 Generating fingerprint...")
            fingerprint = generate_fingerprint(metrics, preprocessing_stats)

            if not fingerprint:
                logger.error(f"❌ Failed to generate fingerprint")
                return self._create_result(
                    status=StageStatus.FAILED,
                    metrics={},
                    error="Failed to generate fingerprint",
                    started_at=started_at,
                )

            # Store fingerprint
            logger.info(f"📤 Storing fingerprint artifact...")
            fingerprint_path = storage.put_artifact(
                f"fingerprint.json",
                json.dumps({"fingerprint": fingerprint}, indent=2),
                content_type="application/json",
            )
            logger.info(f"✅ Fingerprint stored at {fingerprint_path}")

            finished_at = datetime.utcnow()

            # Extract key metrics
            trust_score = fingerprint.get("AI_Trust_Score", 0.0)
            logger.info(f"📊 AI Trust Score: {trust_score}")

            artifacts = {
                "fingerprint_json": fingerprint_path,
            }

            metrics_result = {
                "trust_score": trust_score,
                "metrics_count": len(fingerprint),
                "fingerprint": fingerprint,  # Include full fingerprint in metrics
            }

            logger.info(f"✅ Fingerprint stage succeeded | trust_score={trust_score}, fingerprint_entries={len(fingerprint)}")
            return self._create_result(
                status=StageStatus.SUCCEEDED,
                metrics=metrics_result,
                artifacts=artifacts,
                started_at=started_at,
                finished_at=finished_at,
            )

        except Exception as e:
            logger.error(f"❌ Fingerprint generation failed: {e}", exc_info=True)
            return self._create_result(
                status=StageStatus.FAILED,
                metrics={},
                error=str(e),
                started_at=started_at,
            )
