"""
Fingerprint service for PrimeData.

Generates readiness fingerprints by aggregating chunk-level metrics.
"""

from typing import Any, Dict, List, Optional

from primedata.utils.log_utils import get_logger

logger = get_logger(__name__)
from primedata.services.trust_scoring import aggregate_metrics, aggregate_metrics_with_ai_ready


def generate_fingerprint(
    metrics: List[Dict[str, Any]],
    preprocessing_stats: Optional[Dict[str, Any]] = None
) -> Dict[str, float]:
    """
    Generate a readiness fingerprint from chunk-level metrics.

    Args:
        metrics: List of metric dictionaries (one per chunk)
        preprocessing_stats: Optional preprocessing statistics for Chunk Boundary Quality

    Returns:
        Readiness fingerprint dictionary with aggregated metrics
    """
    logger.info(f"🔍 generate_fingerprint ENTRY | metrics_count={len(metrics) if metrics else 0} | has_preprocessing_stats={preprocessing_stats is not None}")

    if not metrics:
        logger.warning("🔍 generate_fingerprint | No metrics provided for fingerprint generation")
        return {}

    try:
        # Use AI-Ready aggregation if preprocessing stats are available
        logger.debug(f"📋 Determining aggregation strategy | use_ai_ready={preprocessing_stats is not None}")

        if preprocessing_stats:
            logger.debug(f"📋 Using AI-Ready aggregation with preprocessing stats")
            fingerprint = aggregate_metrics_with_ai_ready(metrics, preprocessing_stats)
        else:
            logger.debug(f"📋 Using standard metrics aggregation")
            fingerprint = aggregate_metrics(metrics)

        trust_score = fingerprint.get('AI_Trust_Score', 'N/A')
        trust_score_str = f"{trust_score:.2f}" if isinstance(trust_score, (int, float)) else 'N/A'
        logger.info(f"✅ generate_fingerprint | Generated fingerprint with {len(fingerprint)} metrics | trust_score={trust_score_str}")
        return fingerprint
    except Exception as e:
        logger.error(f"❌ generate_fingerprint | Exception during fingerprint generation | error={str(e)}", exc_info=True)
        return {}


def aggregate_metrics_by_file(
    metrics: List[Dict[str, Any]],
    file_tag: str,
) -> Optional[Dict[str, float]]:
    """
    Aggregate metrics for a specific file tag.

    Args:
        metrics: List of all metrics
        file_tag: File identifier (e.g., "MyDoc.jsonl")

    Returns:
        Aggregated metrics for the file, or None if no metrics found
    """
    logger.info(f"🔍 aggregate_metrics_by_file ENTRY | file_tag={file_tag} | total_metrics={len(metrics)}")

    try:
        from primedata.services.trust_scoring import aggregate_metrics

        logger.debug(f"📋 Filtering metrics for file_tag={file_tag}")
        file_metrics = [m for m in metrics if m.get("file") == file_tag]

        logger.debug(f"📋 Filtered metrics count: {len(file_metrics)}")
        if not file_metrics:
            logger.warning(f"🔍 aggregate_metrics_by_file | No metrics found for file_tag={file_tag}")
            return None

        logger.debug(f"📋 Aggregating {len(file_metrics)} metrics for file")
        result = aggregate_metrics(file_metrics)

        trust_score = result.get('AI_Trust_Score', 'N/A')
        trust_score_str = f"{trust_score:.2f}" if isinstance(trust_score, (int, float)) else 'N/A'
        logger.info(f"✅ aggregate_metrics_by_file | file_tag={file_tag} | aggregated_metrics={len(result)} | trust_score={trust_score_str}")
        return result
    except Exception as e:
        logger.error(f"❌ aggregate_metrics_by_file | file_tag={file_tag} | Exception: {str(e)}", exc_info=True)
        return None
