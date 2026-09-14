"""
Trust scoring service for PrimeData.

Ports AIRD scoring logic with support for primary scorer (scoring_utils) and fallback scorer.
"""

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import regex as re
from primedata.utils.log_utils import get_logger

logger = get_logger(__name__)

# Import AI-Ready metric services
from primedata.services.chunk_coherence import calculate_chunk_coherence
from primedata.services.noise_detection import calculate_noise_ratio
from primedata.core.constants import PII_EMAIL_PATTERN, PII_PHONE_PATTERN

# Try to import primary scorer
try:
    from primedata.services.scoring_utils import load_weights, score_file_data

    _PRIMARY_SCORER = True
    logger.info("Primary scorer (scoring_utils) available")
except ImportError:
    _PRIMARY_SCORER = False
    logger.warning("Primary scorer not available, using fallback scorer")
    score_file_data = None
    load_weights = None

# Regex patterns for fallback scorer
ASCII_RE = re.compile(r"^[\x00-\x7F]+$")
EMAIL_RE = re.compile(PII_EMAIL_PATTERN, re.I)
PHONE_RE = re.compile(PII_PHONE_PATTERN)
SENT_SPLIT_RE = re.compile(r"(?<!\b[A-Z])[.!?。۔؟]+(?=\s+[A-Z0-9\"'])")


def _ttr(tokens: List[str]) -> float:
    """Type-token ratio."""
    if not tokens:
        return 0.0
    return len(set(tokens)) / max(1, len(tokens))


def _ascii_ratio(s: str, probe: int = 1000) -> float:
    """Calculate ASCII character ratio."""
    ss = s[:probe]
    if not ss:
        return 1.0
    ascii_count = sum(1 for c in ss if ord(c) < 128)
    return ascii_count / len(ss)


def _avg_sentence_len(s: str) -> float:
    """
    Calculate average sentence length (words per sentence).
    Returns fallback word count if no sentences detected.

    Strips page markers before sentence detection to prevent them from
    breaking sentence boundary detection in PDF-extracted content.
    """
    if not s or not s.strip():
        return 0.0

    # Strip page markers (=== PAGE N ===) that break sentence boundary detection
    # These are added during PDF extraction and prevent proper sentence splitting
    s = re.sub(r'===\s*PAGE\s+\d+\s*===', ' ', s)

    # Collapse excessive newlines that may remain after page marker removal
    s = re.sub(r'\n{3,}', '\n\n', s)

    # Split on sentence boundaries using the configured regex
    sents = [x.strip() for x in re.split(SENT_SPLIT_RE, s) if x and x.strip()]

    if not sents:
        # Fallback: if no sentences detected, return total word count
        return float(len(s.split()))

    return sum(len(x.split()) for x in sents) / max(1, len(sents))


def _clip01(x: float) -> float:
    """Clip value to [0, 1] range."""
    return max(0.0, min(1.0, x))


# Domain-specific freshness decay half-lives in days.
# Shorter half-life = faster staleness for AI consumption.
_FRESHNESS_HALF_LIFE_DAYS: Dict[str, float] = {
    "regulatory": 60.0,       # Regulations change frequently
    "finance_banking": 90.0,  # Financial data decays quickly
    "legal": 180.0,           # Legal docs change moderately
    "technical": 365.0,       # Technical docs are relatively stable
    "documentation": 365.0,
    "code": 180.0,
    "academic": 730.0,        # Academic content is stable
    "general": 365.0,         # Default half-life
    "conversation": 90.0,
}
_DEFAULT_HALF_LIFE_DAYS = 365.0


def calculate_context_freshness_score(
    ingested_at: Optional[str],
    domain_type: Optional[str] = None,
    reference_date: Optional[datetime] = None,
) -> float:
    """Calculate a freshness score (0-100) using exponential decay based on content age.

    Uses the formula score = 100 * 0.5^(age_days / half_life), where half_life
    is determined by the content domain.

    :param ingested_at: ISO-8601 timestamp string when the chunk was ingested.
    :param domain_type: Content domain (e.g. 'regulatory', 'legal', 'technical').
    :param reference_date: Date to calculate age against; defaults to now (UTC).
    :return: Freshness score in the range [0, 100].
    """
    if not ingested_at:
        return 50.0  # Neutral when timestamp is unknown

    try:
        if isinstance(ingested_at, str):
            # Handle both 'Z' suffix and '+00:00' offset
            ts = ingested_at.replace("Z", "+00:00")
            dt = datetime.fromisoformat(ts)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        elif isinstance(ingested_at, datetime):
            dt = ingested_at if ingested_at.tzinfo else ingested_at.replace(tzinfo=timezone.utc)
        else:
            return 50.0

        now = reference_date or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        age_days = max(0.0, (now - dt).total_seconds() / 86400.0)

        half_life = _FRESHNESS_HALF_LIFE_DAYS.get(
            (domain_type or "general").lower(), _DEFAULT_HALF_LIFE_DAYS
        )

        score = 100.0 * (0.5 ** (age_days / half_life))
        return round(_clip01(score / 100.0) * 100.0, 2)

    except Exception as e:
        logger.warning(f"context_freshness_score calculation failed: {e}")
        return 50.0


def _normalize_token_count(n_tokens: float, target: float = 900.0) -> float:
    """Normalize a token count to a 0-1 score using a Gaussian curve centered on the target.

    :param n_tokens: Number of tokens in the chunk.
    :param target: Ideal token count that yields a score of 1.0.
    :return: Normalized score in [0, 1].
    """
    if n_tokens <= 0:
        return 0.0
    ratio = n_tokens / target
    return _clip01(math.exp(-((ratio - 1.0) ** 2) / 0.5))


def _fallback_weights() -> Dict[str, float]:
    """Return default metric weights used when the primary scorer config is unavailable.

    Weights are grouped as: Core Trust (55%), Technical Quality (30%),
    Context Engineering (5%), and Governance (10%).

    :return: Dict mapping metric names to their weight (values sum to ~1.0).
    """
    return {
        # Core Trust Metrics (55%)
        "Accuracy": 0.15,                # Increased from 0.08
        "Secure": 0.15,                  # Increased from 0.10
        "Quality": 0.12,                 # Slightly reduced to make room for freshness
        "Completeness": 0.08,            # Slightly reduced
        "Context_Quality": 0.05,         # Reduced from 0.10 (overlaps with Quality)

        # Technical Quality (30%) - AI-Ready Metrics
        "Avg_Chunk_Coherence": 0.15,    # Critical for RAG performance
        "Avg_Noise_Free_Score": 0.10,   # Data quality indicator
        "Chunk_Boundary_Quality": 0.05,  # Chunking effectiveness

        # Context Engineering (5%) - 14th dimension
        "Context_Freshness_Score": 0.05,  # Freshness signal for AI consumption

        # Governance (10%)
        "Metadata_Presence": 0.05,       # Reduced from 0.10
        "KnowledgeBase_Ready": 0.05,     # Reduced from 0.08

        # REMOVED (set to 0.0 for backward compatibility):
        "Timeliness": 0.0,               # Replaced by Context_Freshness_Score
        "Token_Count": 0.0,              # Technical metric, not trust
        "GPT_Confidence": 0.0,           # Placeholder metric
        "Audience_Intentionality": 0.0,  # Marketing metric
        "Diversity": 0.0,                # Variety, not trust
        "Audience_Accessibility": 0.0,   # UX metric, not trust
    }


def _fallback_score_record(entry: Dict[str, Any], weights: Dict[str, float]) -> Dict[str, Any]:
    """Score a record using heuristic rules when the primary ML scorer is unavailable.

    Produces the same metric keys as the primary scorer with values on a 0-100 scale.
    AI_Trust_Score is computed as a weighted sum of all individual metrics.

    :param entry: Chunk record containing 'text' and optional metadata fields.
    :param weights: Dict mapping metric names to their weight for trust calculation.
    :return: Dict with all 13 metric scores (0-100) plus 'AI_Trust_Score'.
    """
    text = (entry.get("text") or "").strip()
    section = (entry.get("section") or "").strip().lower()
    field_name = (entry.get("field_name") or "").strip().lower()
    document_id = (entry.get("document_id") or "").strip()
    audience = (entry.get("audience") or "unknown").strip().lower()
    token_est = float(entry.get("token_est") or len(text) / 4.0)

    # 1) Basic signals
    completeness = 1.0 if text else 0.0
    accuracy = _ascii_ratio(text)
    pii_hits = bool(EMAIL_RE.search(text) or PHONE_RE.search(text))
    secure = 1.0 if not pii_hits else 0.75

    # 2) Quality/readability proxies
    avg_sl = _avg_sentence_len(text) if text else 0.0
    if avg_sl <= 0:
        quality = 0.0
    elif avg_sl < 10:
        quality = avg_sl / 10.0
    elif avg_sl > 30:
        quality = max(0.0, 1.0 - (avg_sl - 30) / 30.0)
    else:
        quality = 1.0

    # 3) Timeliness (no date here) -> neutral 0.5
    timeliness = 0.5

    # 4) Token count shape
    token_count = _normalize_token_count(token_est)

    # 5) Placeholder confidence
    gpt_conf = 0.85

    # 6) Context quality
    ctx_hit = 1.0 if (section and section in text.lower()) else 0.5
    context_quality = ctx_hit

    # 7) Metadata presence
    meta_presence = 1.0 if (section and field_name and document_id) else 0.5

    # 8) Audience intentionality
    aud_intent = 1.0 if audience not in ("", "unknown") else 0.25

    # 9) Diversity
    toks = re.findall(r"\w+", text.lower())
    diversity = _ttr(toks)

    # 10) Audience accessibility
    if 10 <= avg_sl <= 25:
        aud_access = 1.0
    else:
        d = min(abs(avg_sl - 17.5) / 25.0, 1.0) if avg_sl > 0 else 1.0
        aud_access = max(0.0, 1.0 - d)

    # 11) KnowledgeBase_Ready
    kbr = _clip01(0.4 * meta_presence + 0.4 * quality + 0.2 * context_quality)

    # Convert to 0–100
    metrics_01 = {
        "Completeness": completeness,
        "Accuracy": accuracy,
        "Secure": secure,
        "Quality": quality,
        "Timeliness": timeliness,
        "Token_Count": token_count,
        "GPT_Confidence": gpt_conf,
        "Context_Quality": context_quality,
        "Metadata_Presence": meta_presence,
        "Audience_Intentionality": aud_intent,
        "Diversity": diversity,
        "Audience_Accessibility": aud_access,
        "KnowledgeBase_Ready": kbr,
    }
    metrics_100 = {k: round(v * 100.0, 2) for k, v in metrics_01.items()}

    # Weighted trust
    trust = 0.0
    for k, w in weights.items():
        trust += float(metrics_01.get(k, 0.0)) * float(w)
    trust_100 = round(_clip01(trust) * 100.0, 4)

    out = dict(metrics_100)
    out["AI_Trust_Score"] = trust_100
    return out


def get_scoring_weights(config_path: Optional[str] = None) -> Dict[str, float]:
    """Load scoring weights from a config file or fall back to built-in defaults.

    :param config_path: Optional filesystem path to a JSON weights configuration file.
    :return: Dict mapping metric names to their weight values.
    """
    logger.info(f"📊 get_scoring_weights ENTRY | config_path={config_path} | primary_scorer_available={_PRIMARY_SCORER}")

    try:
        if _PRIMARY_SCORER and load_weights:
            try:
                logger.debug(f"📋 Attempting to load weights from primary scorer")
                if config_path:
                    logger.debug(f"📋 Loading weights from config_path={config_path}")
                    return load_weights(config_path)
                # Try default path
                from primedata.ingestion_pipeline.aird_stages.config import get_aird_config

                config = get_aird_config()
                if config.scoring_weights_path:
                    logger.debug(f"📋 Loading weights from default config path: {config.scoring_weights_path}")
                    return load_weights(config.scoring_weights_path)
            except Exception as e:
                logger.warning(f"📋 Failed to load weights from config: {e}, using fallback", exc_info=True)

        logger.debug(f"📋 Using fallback weights")
        return _fallback_weights()
    except Exception as e:
        logger.error(f"❌ get_scoring_weights | Exception: {str(e)}", exc_info=True)
        return _fallback_weights()


def score_record(record: Dict[str, Any], weights: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    """Score a single chunk record using the primary scorer or heuristic fallback.

    :param record: Chunk record dict with 'text', 'document_id', and optional metadata.
    :param weights: Optional scoring weights; loads defaults when not provided.
    :return: Dict with all 13 metrics plus 'AI_Trust_Score' on a 0-100 scale.
    """
    logger.info(f"📊 score_record ENTRY | record_id={record.get('document_id', 'unknown')} | text_len={len((record.get('text') or '').strip())} | has_weights={weights is not None}")

    try:
        if weights is None:
            logger.debug(f"📋 Loading default weights")
            weights = get_scoring_weights()

        if _PRIMARY_SCORER and score_file_data:
            try:
                logger.debug(f"📋 Using primary scorer for record")
                result = score_file_data(record, weights)
                trust_score = result.get('AI_Trust_Score', 'N/A')
                trust_score_str = f"{trust_score:.2f}" if isinstance(trust_score, (int, float)) else 'N/A'
                logger.info(f"✅ score_record | record_id={record.get('document_id', 'unknown')} | trust_score={trust_score_str} | metrics_count={len(result)}")
                return result
            except Exception as e:
                logger.warning(f"📋 Primary scorer failed: {e}, falling back to heuristic scorer", exc_info=True)

        logger.debug(f"📋 Using fallback heuristic scorer for record")
        result = _fallback_score_record(record, weights)
        trust_score = result.get('AI_Trust_Score', 'N/A')
        trust_score_str = f"{trust_score:.2f}" if isinstance(trust_score, (int, float)) else 'N/A'
        logger.info(f"✅ score_record | record_id={record.get('document_id', 'unknown')} | trust_score={trust_score_str} | metrics_count={len(result)}")
        return result
    except Exception as e:
        logger.error(f"❌ score_record | record_id={record.get('document_id', 'unknown')} | Exception: {str(e)}", exc_info=True)
        return {}


def aggregate_metrics(metrics: List[Dict[str, Any]]) -> Dict[str, float]:
    """Aggregate per-chunk metrics into a single Readiness Fingerprint by averaging.

    :param metrics: List of metric dicts (one per chunk), each containing numeric scores.
    :return: Dict of averaged metric values across all chunks.
    """
    logger.info(f"📊 aggregate_metrics ENTRY | chunk_count={len(metrics) if metrics else 0}")

    try:
        if not metrics:
            logger.warning(f"📊 aggregate_metrics | Empty metrics list")
            return {}

        sums: Dict[str, float] = {}
        counts: Dict[str, int] = {}

        logger.debug(f"📋 Processing {len(metrics)} chunks for aggregation")

        for m in metrics:
            for k, v in m.items():
                if isinstance(v, (int, float)) and k != "file":
                    sums[k] = sums.get(k, 0.0) + float(v)
                    counts[k] = counts.get(k, 0) + 1

        agg: Dict[str, float] = {}
        for k, total in sums.items():
            c = counts.get(k, 0)
            if c > 0:
                agg[k] = round(total / c, 4)

        trust_score = agg.get('AI_Trust_Score', 'N/A')
        trust_score_str = f"{trust_score:.2f}" if isinstance(trust_score, (int, float)) else 'N/A'
        logger.info(f"✅ aggregate_metrics | aggregated_metrics={len(agg)} | trust_score={trust_score_str}")
        return agg
    except Exception as e:
        logger.error(f"❌ aggregate_metrics | Exception during aggregation: {str(e)}", exc_info=True)
        return {}


def score_record_with_ai_ready_metrics(
    record: Dict[str, Any],
    weights: Optional[Dict[str, float]] = None,
    playbook: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Score a record including AI-Ready metrics (coherence, noise, freshness).

    Extends score_record by appending Chunk_Coherence, Noise_Free_Score, and
    Context_Freshness_Score to the base metric set.

    :param record: Chunk record dict with 'text', 'document_id', and optional metadata.
    :param weights: Optional scoring weights; loads defaults when not provided.
    :param playbook: Optional playbook config supplying noise patterns and coherence settings.
    :return: Dict with all base metrics plus AI-Ready metrics on a 0-100 scale.
    """
    logger.info(f"📊 score_record_with_ai_ready_metrics ENTRY | record_id={record.get('document_id', 'unknown')} | text_len={len((record.get('text') or '').strip())} | domain_type={record.get('domain_type', 'unknown')}")

    try:
        # Get base metrics from existing scorer
        logger.debug(f"📋 Scoring record with base scorer")
        base_metrics = score_record(record, weights)

        # Extract chunk text and domain_type
        chunk_text = (record.get("text") or "").strip()
        domain_type = record.get("domain_type") or record.get("metadata", {}).get("domain_type")

        logger.debug(f"📋 Calculating AI-Ready metrics | domain_type={domain_type}")

        # 1. Calculate Chunk Coherence with domain-adaptive thresholds
        coherence_config = playbook.get("coherence", {}) if playbook else {}

        # Get domain-specific threshold if available, otherwise use default
        domain_thresholds = coherence_config.get("domain_min_thresholds", {})
        default_threshold = coherence_config.get("min_coherence_threshold", 0.6)

        if domain_type and domain_type.lower() in domain_thresholds:
            min_coherence_threshold = domain_thresholds[domain_type.lower()]
        elif domain_type and domain_type.lower() in ["regulatory", "finance_banking"]:
            min_coherence_threshold = coherence_config.get("regulatory_min_threshold", 0.5)
        else:
            min_coherence_threshold = default_threshold

        logger.debug(f"📋 Calculating chunk coherence | threshold={min_coherence_threshold}")
        coherence_result = calculate_chunk_coherence(
            chunk_text=chunk_text,
            method=coherence_config.get("method", "embedding_similarity"),
            sentence_window=coherence_config.get("sentence_window", 3),
            min_coherence_threshold=min_coherence_threshold
        )
        base_metrics["Chunk_Coherence"] = coherence_result["coherence_score"]
        logger.debug(f"📋 Chunk coherence calculated: {coherence_result['coherence_score']:.2f}")

        # 2. Calculate Noise Ratio (inverted to score: lower noise = higher score)
        noise_patterns = playbook.get("noise_patterns") if playbook else None
        logger.debug(f"📋 Calculating noise ratio")
        noise_result = calculate_noise_ratio(chunk_text, noise_patterns)
        noise_score = max(0.0, 100.0 - noise_result["noise_ratio"])
        base_metrics["Noise_Free_Score"] = round(noise_score, 2)
        logger.debug(f"📋 Noise score calculated: {noise_score:.2f}")

        # 3. Context Freshness Score — 14th quality dimension
        ingested_at = (
            record.get("ingested_at")
            or record.get("timestamp")
            or record.get("metadata", {}).get("ingested_at")
        )
        freshness_score = calculate_context_freshness_score(
            ingested_at=ingested_at,
            domain_type=domain_type,
        )
        base_metrics["Context_Freshness_Score"] = freshness_score
        logger.debug(f"📋 Context freshness score calculated: {freshness_score:.2f}")

        logger.info(f"✅ score_record_with_ai_ready_metrics | record_id={record.get('document_id', 'unknown')} | coherence={base_metrics.get('Chunk_Coherence', 'N/A')} | noise_free={base_metrics.get('Noise_Free_Score', 'N/A')} | freshness={freshness_score:.2f}")
        return base_metrics
    except Exception as e:
        logger.error(f"❌ score_record_with_ai_ready_metrics | record_id={record.get('document_id', 'unknown')} | Exception: {str(e)}", exc_info=True)
        return {}


def aggregate_metrics_with_ai_ready(
    metrics: List[Dict[str, Any]],
    preprocessing_stats: Optional[Dict[str, Any]] = None
) -> Dict[str, float]:
    """Aggregate per-chunk metrics including AI-Ready dimensions and recalculate AI_Trust_Score.

    Computes averages for Chunk_Coherence, Noise_Free_Score, Context_Freshness_Score,
    and derives Chunk_Boundary_Quality from preprocessing statistics.

    :param metrics: List of per-chunk metric dicts containing AI-Ready scores.
    :param preprocessing_stats: Optional dict with 'mid_sentence_boundary_rate' for boundary quality.
    :return: Aggregated metrics dict with AI-Ready metrics and recalculated AI_Trust_Score.
    """
    logger.info(f"📊 aggregate_metrics_with_ai_ready ENTRY | chunk_count={len(metrics) if metrics else 0} | has_preprocessing_stats={preprocessing_stats is not None}")

    try:
        # Get base aggregated metrics
        logger.debug(f"📋 Computing base aggregated metrics")
        agg = aggregate_metrics(metrics)

        # Add AI-Ready aggregate metrics

        # 1. Average Chunk Coherence
        logger.debug(f"📋 Computing average chunk coherence")
        coherence_scores = [m.get("Chunk_Coherence", 0) for m in metrics if "Chunk_Coherence" in m]
        if coherence_scores:
            agg["Avg_Chunk_Coherence"] = round(sum(coherence_scores) / len(coherence_scores), 2)
            logger.debug(f"📋 Avg chunk coherence: {agg['Avg_Chunk_Coherence']:.2f} (from {len(coherence_scores)} chunks)")
        else:
            agg["Avg_Chunk_Coherence"] = 0.0

        # 2. Average Noise-Free Score
        logger.debug(f"📋 Computing average noise-free score")
        noise_scores = [m.get("Noise_Free_Score", 100) for m in metrics if "Noise_Free_Score" in m]
        if noise_scores:
            agg["Avg_Noise_Free_Score"] = round(sum(noise_scores) / len(noise_scores), 2)
            logger.debug(f"📋 Avg noise-free score: {agg['Avg_Noise_Free_Score']:.2f} (from {len(noise_scores)} chunks)")
        else:
            agg["Avg_Noise_Free_Score"] = 100.0

        # 3. Chunk Boundary Quality (from preprocessing stats)
        if preprocessing_stats:
            mid_sentence_rate = preprocessing_stats.get("mid_sentence_boundary_rate", 0.0)
            boundary_quality = max(0.0, 100.0 - (mid_sentence_rate * 100))
            agg["Chunk_Boundary_Quality"] = round(boundary_quality, 2)
            logger.debug(f"📋 Chunk boundary quality: {agg['Chunk_Boundary_Quality']:.2f} (mid_sentence_rate={mid_sentence_rate:.4f})")
        else:
            agg["Chunk_Boundary_Quality"] = 0.0

        # 4. Average Context Freshness Score (14th dimension)
        freshness_scores = [
            m.get("Context_Freshness_Score")
            for m in metrics
            if m.get("Context_Freshness_Score") is not None
        ]
        if freshness_scores:
            agg["Context_Freshness_Score"] = round(
                sum(freshness_scores) / len(freshness_scores), 2
            )
            logger.debug(f"📋 Avg context freshness score: {agg['Context_Freshness_Score']:.2f} (from {len(freshness_scores)} chunks)")
        else:
            agg["Context_Freshness_Score"] = 50.0  # Neutral default when unknown

        # 5. Recalculate AI_Trust_Score with updated weights including AI-Ready metrics
        logger.debug(f"📋 Recalculating AI_Trust_Score with AI-Ready weights")
        weights = _fallback_weights()

        # Convert 0-100 metrics to 0-1 for weighted calculation
        trust = 0.0
        for metric_name, weight in weights.items():
            if weight > 0.0:
                metric_value = agg.get(metric_name, 0.0) / 100.0
                trust += metric_value * weight
                logger.debug(f"💾 Metric: {metric_name}={agg.get(metric_name, 0.0):.2f} | weight={weight:.2f} | contribution={metric_value * weight:.4f}")

        # Clip to [0, 1] and convert to 0-100 scale
        trust_100 = round(_clip01(trust) * 100.0, 4)
        agg["AI_Trust_Score"] = trust_100
        logger.debug(f"📋 Final AI_Trust_Score: {trust_100:.2f}")

        logger.info(f"✅ aggregate_metrics_with_ai_ready | aggregated_metrics={len(agg)} | trust_score={trust_100:.2f} | avg_coherence={agg.get('Avg_Chunk_Coherence', 'N/A')} | avg_noise_free={agg.get('Avg_Noise_Free_Score', 'N/A')} | boundary_quality={agg.get('Chunk_Boundary_Quality', 'N/A')}")
        return agg
    except Exception as e:
        logger.error(f"❌ aggregate_metrics_with_ai_ready | Exception during aggregation: {str(e)}", exc_info=True)
        return {}
