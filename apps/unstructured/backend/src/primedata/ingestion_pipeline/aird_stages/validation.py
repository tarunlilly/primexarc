"""
AIRD validation summary generation stage for PrimeData.

Generates CSV validation summaries from chunk-level metrics.
"""

from datetime import datetime
from typing import Any, Dict
from uuid import UUID

import logging
logger = logging.getLogger(__name__)
from primedata.ingestion_pipeline.aird_stages.base import AirdStage, StageResult, StageStatus
from primedata.ingestion_pipeline.aird_stages.config import get_aird_config
from primedata.services.reporting import generate_validation_summary


class ValidationStage(AirdStage):
    """Validation stage that generates CSV validation summaries."""

    @property
    def stage_name(self) -> str:
        return "validation"

    def get_required_artifacts(self) -> list[str]:
        """Validation requires metrics from scoring stage."""
        return ["metrics_json"]

    def execute(self, context: Dict[str, Any]) -> StageResult:
        """Execute validation summary generation stage.

        Args:
            context: Stage execution context with:
                - storage: AirdStorageAdapter
                - scoring_result: Optional result from scoring stage

        Returns:
            StageResult with validation metrics
        """
        logger.info(f"🎯 ValidationStage.execute() entry | product_id={self.product_id}, version={self.version}, context_keys={list(context.keys())}")
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
                logger.warning(f"⚠️ No metrics found for validation summary generation")
                return self._create_result(
                    status=StageStatus.SKIPPED,
                    metrics={"reason": "no_metrics"},
                    started_at=started_at,
                )

            logger.info(f"✔️ Generating validation summary from {len(metrics)} metric entries")

            # Get threshold from config
            logger.debug(f"📋 Loading validation configuration...")
            config = get_aird_config()
            threshold = config.default_scoring_threshold
            logger.info(f"✅ Threshold loaded: {threshold}")

            # Generate validation summary
            logger.info(f"🔍 Generating validation summary CSV...")
            csv_content = generate_validation_summary(metrics, threshold)

            if not csv_content:
                logger.error(f"❌ Failed to generate validation summary")
                return self._create_result(
                    status=StageStatus.FAILED,
                    metrics={},
                    error="Failed to generate validation summary",
                    started_at=started_at,
                )

            # Store validation summary
            logger.info(f"📦 Storing validation summary artifact ({len(csv_content)} bytes)...")
            summary_path = storage.put_artifact(
                "ai_validation_summary.csv",
                csv_content,
                content_type="text/csv",
            )
            logger.info(f"✅ Validation summary stored at {summary_path}")

            finished_at = datetime.utcnow()

            artifacts = {
                "validation_summary_csv": summary_path,
            }

            metrics_result = {
                "entries_processed": len(metrics),
                "threshold": threshold,
            }

            logger.info(f"✅ Validation stage succeeded | entries={len(metrics)}, csv_size={len(csv_content)} bytes")
            return self._create_result(
                status=StageStatus.SUCCEEDED,
                metrics=metrics_result,
                artifacts=artifacts,
                started_at=started_at,
                finished_at=finished_at,
            )

        except Exception as e:
            logger.error(f"❌ Validation summary generation failed: {e}", exc_info=True)
            return self._create_result(
                status=StageStatus.FAILED,
                metrics={},
                error=str(e),
                started_at=started_at,
            )
