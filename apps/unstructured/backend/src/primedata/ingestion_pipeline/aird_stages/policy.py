"""
AIRD policy evaluation stage for PrimeData.

Evaluates readiness fingerprints against policy thresholds.
"""

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

import logging
logger = logging.getLogger(__name__)
from primedata.ingestion_pipeline.aird_stages.base import AirdStage, StageResult, StageStatus
from primedata.ingestion_pipeline.aird_stages.config import get_aird_config
from primedata.services.policy_engine import evaluate_policy


class PolicyStage(AirdStage):
    """Policy stage that evaluates fingerprints against policy thresholds."""

    @property
    def stage_name(self) -> str:
        return "policy"

    def get_required_artifacts(self) -> list[str]:
        """Policy requires fingerprint from fingerprint stage."""
        return ["fingerprint_json"]

    def execute(self, context: Dict[str, Any]) -> StageResult:
        """Execute policy evaluation stage.

        Args:
            context: Stage execution context with:
                - storage: AirdStorageAdapter
                - fingerprint_result: Optional result from fingerprint stage

        Returns:
            StageResult with policy evaluation metrics
        """
        logger.info(f"🎯 PolicyStage.execute() entry | product_id={self.product_id}, version={self.version}, context_keys={list(context.keys())}")
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
            # Get fingerprint from previous stage or load from storage
            logger.info(f"📋 Retrieving fingerprint...")
            fingerprint_result = context.get("fingerprint_result")
            if fingerprint_result and fingerprint_result.get("metrics", {}).get("fingerprint"):
                fingerprint = fingerprint_result["metrics"]["fingerprint"]
                logger.debug(f"📋 Using fingerprint from fingerprint_result | entries={len(fingerprint)}")
            else:
                # Try to load from storage
                logger.debug(f"📋 Loading fingerprint from storage...")
                fingerprint_data = storage.get_artifact("fingerprint.json")
                if fingerprint_data:
                    import json

                    fingerprint_obj = json.loads(fingerprint_data.decode("utf-8"))
                    fingerprint = fingerprint_obj.get("fingerprint", {})
                    logger.info(f"✅ Loaded fingerprint from storage | entries={len(fingerprint)}")
                else:
                    logger.warning(f"⚠️ No fingerprint found for policy evaluation")
                    return self._create_result(
                        status=StageStatus.SKIPPED,
                        metrics={"reason": "no_fingerprint"},
                        started_at=started_at,
                    )

            if not fingerprint:
                logger.error(f"❌ Empty fingerprint")
                return self._create_result(
                    status=StageStatus.FAILED,
                    metrics={},
                    error="Empty fingerprint",
                    started_at=started_at,
                )

            logger.info(f"📋 Evaluating policy against fingerprint | fingerprint_entries={len(fingerprint)}")

            # Get policy thresholds from config
            logger.debug(f"📋 Loading policy configuration...")
            config = get_aird_config()
            thresholds = {
                "min_trust_score": config.policy_min_trust_score,
                "min_secure": config.policy_min_secure,
                "min_metadata_presence": config.policy_min_metadata_presence,
                "min_kb_ready": config.policy_min_kb_ready,
            }
            logger.info(f"✅ Policy thresholds loaded | thresholds={thresholds}")

            # Evaluate policy
            logger.info(f"🔍 Running policy evaluation...")
            policy_result = evaluate_policy(fingerprint, thresholds)

            finished_at = datetime.utcnow()

            metrics = {
                "policy_passed": policy_result["policy_passed"],
                "violations": policy_result["violations"],
                "violations_count": len(policy_result["violations"]),
                "thresholds": policy_result["thresholds"],
            }

            if policy_result["policy_passed"]:
                logger.info(f"✅ Policy evaluation passed | violations_count={len(policy_result['violations'])}")
            else:
                logger.warning(f"❌ Policy evaluation failed | violations_count={len(policy_result['violations'])}, violations={policy_result['violations']}")

            # Store policy result to S3
            logger.info(f"📤 Storing policy result artifact...")
            import json
            policy_path = storage.put_artifact(
                f"policy_result.json",
                json.dumps(policy_result, indent=2),
                content_type="application/json",
            )
            logger.info(f"✅ Policy result stored at {policy_path}")

            return self._create_result(
                status=StageStatus.SUCCEEDED if policy_result["policy_passed"] else StageStatus.FAILED,
                metrics=metrics,
                started_at=started_at,
                finished_at=finished_at,
            )

        except Exception as e:
            logger.error(f"❌ Policy evaluation failed: {e}", exc_info=True)
            return self._create_result(
                status=StageStatus.FAILED,
                metrics={},
                error=str(e),
                started_at=started_at,
            )
