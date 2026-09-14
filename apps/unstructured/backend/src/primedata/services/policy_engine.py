"""
Policy engine service for PrimeData.

Evaluates readiness fingerprints against policy thresholds.
"""

from typing import Any, Dict, List, Optional

from primedata.utils.log_utils import get_logger

logger = get_logger(__name__)

# Default thresholds
DEFAULT_THRESHOLDS: Dict[str, float] = {
    "min_trust_score": 50.0,
    "min_secure": 90.0,
    "min_metadata_presence": 80.0,
    "min_kb_ready": 50.0,
}


def evaluate_policy(
    fingerprint: Dict[str, float],
    thresholds: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """
    Evaluate whether a readiness fingerprint satisfies policy constraints.

    Args:
        fingerprint: Readiness fingerprint dictionary with metrics
        thresholds: Optional threshold overrides

    Returns:
        Dict with:
            - policy_passed: bool
            - violations: List[str]
            - thresholds: Dict[str, float]
    """
    logger.info(f"📋 evaluate_policy ENTRY | fingerprint_metrics={len(fingerprint) if fingerprint else 0} | has_threshold_overrides={thresholds is not None}")

    try:
        # Merge defaults + overrides
        th = dict(DEFAULT_THRESHOLDS)
        if thresholds:
            logger.debug(f"📋 Applying threshold overrides: {list(thresholds.keys())}")
            th.update(thresholds)

        # No fingerprint at all → automatic fail
        if not fingerprint:
            logger.warning("📋 evaluate_policy | Empty fingerprint provided, policy automatically fails")
            return {
                "status": "failed",
                "policy_passed": False,
                "violations": ["no_fingerprint"],
                "warnings": [],
                "thresholds": th,
            }

        violations: List[str] = []

        trust = float(fingerprint.get("AI_Trust_Score", 0.0))
        secure = float(fingerprint.get("Secure", 0.0))
        metadata = float(fingerprint.get("Metadata_Presence", 0.0))
        kb_ready = float(fingerprint.get("KnowledgeBase_Ready", 0.0))

        logger.debug(f"📋 Extracted metrics | trust={trust:.2f} | secure={secure:.2f} | metadata={metadata:.2f} | kb_ready={kb_ready:.2f}")

        # Overall trust
        if trust < th["min_trust_score"]:
            violation = f"low_trust(<{th['min_trust_score']})"
            violations.append(violation)
            logger.debug(f"📋 Policy violation detected: {violation}")

        # Security
        if secure < th["min_secure"]:
            violation = f"security_not_full(<{th['min_secure']})"
            violations.append(violation)
            logger.debug(f"📋 Policy violation detected: {violation}")

        # Metadata completeness
        if metadata < th["min_metadata_presence"]:
            violation = f"weak_metadata(<{th['min_metadata_presence']})"
            violations.append(violation)
            logger.debug(f"📋 Policy violation detected: {violation}")

        # KB / RAG readiness
        if kb_ready < th["min_kb_ready"]:
            violation = f"kb_not_ready(<{th['min_kb_ready']})"
            violations.append(violation)
            logger.debug(f"📋 Policy violation detected: {violation}")

        policy_passed = len(violations) == 0

        # Determine status: "passed", "failed", or "warnings" (if passed but has minor issues)
        if policy_passed:
            status = "passed"
        else:
            # Check if violations are critical (trust score or security) vs warnings
            critical_violations = [v for v in violations if "low_trust" in v or "security_not_full" in v]
            status = "failed" if critical_violations else "warnings"

        logger.info(
            f"✅ evaluate_policy | policy_passed={policy_passed} | status={status} | violations={len(violations)} | trust={trust:.2f} | secure={secure:.2f}"
        )

        return {
            "status": status,
            "policy_passed": policy_passed,
            "violations": violations,
            "warnings": [],
            "thresholds": th,
        }
    except Exception as e:
        logger.error(f"❌ evaluate_policy | Exception during policy evaluation: {str(e)}", exc_info=True)
        return {
            "status": "failed",
            "policy_passed": False,
            "violations": ["evaluation_error"],
            "warnings": [],
            "thresholds": DEFAULT_THRESHOLDS,
        }
