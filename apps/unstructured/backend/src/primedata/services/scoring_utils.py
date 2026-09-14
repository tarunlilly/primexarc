"""
Primary scoring utilities (optional).

This module provides advanced scoring using external libraries.
If these libraries are not available, the fallback scorer in trust_scoring.py will be used.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from primedata.core.constants import PII_EMAIL_PATTERN, PII_PHONE_PATTERN, PII_SSN_PATTERN, PII_CREDIT_CARD_PATTERN, SCORING_FRESHNESS_DECAY_DAYS_DEFAULT, SCORING_TOKEN_TARGET
from primedata.utils.log_utils import get_logger

logger = get_logger(__name__)

try:
    import textstat

    HAS_TEXTSTAT = True
except ImportError:
    HAS_TEXTSTAT = False

try:
    import tiktoken

    TOK = tiktoken.get_encoding("cl100k_base")
    HAS_TIKTOKEN = True
except ImportError:
    HAS_TIKTOKEN = False

try:
    from spellchecker import SpellChecker

    spell = SpellChecker()
    HAS_SPELLCHECKER = True
except ImportError:
    HAS_SPELLCHECKER = False

# PII Detection patterns
PII_PATTERNS = [
    PII_SSN_PATTERN,
    PII_PHONE_PATTERN,
    PII_EMAIL_PATTERN,
]


def detect_pii(text: str) -> bool:
    """Detect PII in text."""
    return any(re.search(p, text) for p in PII_PATTERNS)


def score_completeness(tokens) -> float:
    """Score completeness based on token count."""
    return 100.0 if len(tokens) > 1000 else 75.0


def score_accuracy(words) -> float:
    """Score accuracy using spell checker."""
    if not HAS_SPELLCHECKER:
        return 85.0  # Default if spellchecker unavailable
    errors = len(spell.unknown(words[:500]))
    ratio = 1.0 - (errors / max(len(words), 1))
    return max(0.0, min(ratio * 100, 100))


def score_secure(text: str) -> float:
    """Score security (PII detection)."""
    return 0.0 if detect_pii(text) else 100.0


def score_quality(text: str) -> float:
    """Score quality using readability metrics and heuristics."""
    if HAS_TEXTSTAT:
        # Use textstat if available
        try:
            flesch = textstat.flesch_reading_ease(text)
            # Normalize Flesch score (0-100 scale) to 0-100
            # Flesch scores: 0-30 (very difficult), 30-50 (difficult), 50-60 (fairly difficult),
            # 60-70 (standard), 70-80 (fairly easy), 80-90 (easy), 90-100 (very easy)
            # We want to reward readable text (60-100), but not penalize technical content too much
            if flesch < 0:
                return 50.0  # Even difficult text has some quality
            elif flesch < 30:
                return 55.0
            elif flesch < 50:
                return 65.0
            elif flesch < 60:
                return 75.0
            elif flesch < 70:
                return 82.0
            elif flesch < 80:
                return 88.0
            else:
                return 92.0
        except Exception:
            # If textstat fails, fall through to heuristics
            pass

    # Fallback: Use heuristics based on sentence length and vocabulary
    if not text or len(text.strip()) < 50:
        return 40.0

    words = text.split()
    if len(words) < 20:
        return 55.0  # Short text still has some quality

    # Calculate average sentence length (heuristic for readability)
    sentences = re.split(r"[.!?]+", text)
    sentences = [s.strip() for s in sentences if s.strip()]
    if not sentences:
        return 60.0  # Default for unparseable text

    avg_sentence_len = len(words) / len(sentences)

    # For regulatory/formal content, longer sentences are acceptable
    # Ideal sentence length for readability: 15-25 words
    # But regulatory content often has 25-40 word sentences which are still acceptable
    if avg_sentence_len < 5:
        return 60.0  # Very short sentences might be fragments
    elif avg_sentence_len < 10:
        return 70.0  # Short but acceptable
    elif avg_sentence_len <= 25:
        return 85.0  # Ideal range
    elif avg_sentence_len <= 35:
        return 80.0  # Still good for formal content (was 75.0)
    elif avg_sentence_len <= 45:
        return 70.0  # Acceptable for regulatory content (was 65.0)
    elif avg_sentence_len <= 60:
        return 60.0  # Long but readable for formal content (was 55.0)
    else:
        return 50.0  # Very long sentences, harder to read


def score_timeliness(timestamp: str, ref: str = "2023-01-01") -> float:
    """Score timeliness based on date."""
    try:
        t1 = datetime.strptime(timestamp, "%Y-%m-%d")
        t2 = datetime.strptime(ref, "%Y-%m-%d")
        days = (t2 - t1).days
        return max(0.0, min((1 - days / SCORING_FRESHNESS_DECAY_DAYS_DEFAULT) * 100, 100.0))
    except Exception:
        return 50.0


def score_gpt_confidence(text: str) -> float:
    """Placeholder for GPT confidence."""
    return 85.0


def score_context_quality(text: str) -> float:
    """Score context quality based on text structure and information richness."""
    if not text or len(text.strip()) < 50:
        return 30.0

    # Base score for having meaningful content
    score = 40.0  # Start with a baseline - meaningful text has context
    text_lower = text.lower()
    words = text.split()

    # 1. Structure indicators (paragraphs, headings, lists) - higher weight
    has_paragraphs = "\n\n" in text or text.count("\n") > 3
    has_lists = bool(re.search(r"(?:^|\n)[\s]*[•\-\*\+]\s", text, re.MULTILINE))
    has_numbered_lists = bool(re.search(r"(?:^|\n)[\s]*\d+[\.\)]\s", text, re.MULTILINE))
    if has_paragraphs:
        score += 20.0  # Structured text has better context
    if has_lists or has_numbered_lists:
        score += 15.0

    # 2. Information density (numbers, dates, references) - important for context
    has_numbers = bool(re.search(r"\b\d+(?:[.,]\d+)?(?:%|\$|USD|EUR|million|billion)?\b", text))
    has_dates = bool(
        re.search(
            r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}\b|\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|\b\d{4}\b",
            text_lower,
        )
    )
    has_references = bool(re.search(r"\b(?:see|refer|reference|section|chapter|page|table|figure)\s+[\d]+", text_lower))
    if has_numbers:
        score += 15.0
    if has_dates:
        score += 10.0
    if has_references:
        score += 10.0

    # 3. Contextual keywords (domain-agnostic) - shows coherent writing
    contextual_indicators = [
        "because",
        "therefore",
        "however",
        "although",
        "in addition",
        "furthermore",
        "specifically",
        "for example",
        "such as",
        "including",
        "namely",
        "in particular",
        "according to",
        "based on",
        "related to",
        "associated with",
        "compared to",
        "as a result",
        "consequently",
        "meanwhile",
        "furthermore",
        "moreover",
    ]
    context_hits = sum(1 for indicator in contextual_indicators if indicator in text_lower)
    score += min(context_hits * 2.0, 15.0)  # Max 15 points for contextual language

    # 4. Entity mentions (proper nouns, organizations, concepts) - shows real-world context
    has_proper_nouns = bool(re.search(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b", text))
    if has_proper_nouns:
        score += 10.0

    # 5. Length bonus - longer text typically has more context (up to a point)
    if len(words) > 100:
        score += min((len(words) - 100) / 20.0, 10.0)  # Up to 10 points for longer content

    return min(score, 100.0)


def score_metadata_presence(meta: Dict[str, Any]) -> float:
    """Score metadata presence and quality."""
    required = ["source", "section", "audience", "timestamp"]
    present = sum(1 for k in required if k in meta and meta[k])

    base_score = (present / len(required)) * 100

    # Bonus for quality metadata (non-empty, meaningful values)
    quality_bonus = 0.0

    # Section quality
    section = str(meta.get("section", "")).strip().lower()
    if section and section not in ("", "general", "unknown", "none"):
        quality_bonus += 10.0

    # Field name quality
    field_name = str(meta.get("field_name", "")).strip().lower()
    if field_name and field_name not in ("", "general", "unknown", "none"):
        quality_bonus += 10.0

    # Audience quality (not "unknown")
    audience = str(meta.get("audience", "")).strip().lower()
    if audience and audience not in ("", "unknown", "general"):
        quality_bonus += 10.0

    # Document ID presence
    if meta.get("document_id") or meta.get("doc_scope"):
        quality_bonus += 10.0

    return min(base_score + quality_bonus, 100.0)


def score_audience_intentionality(text: str, domain_type: Optional[str] = None) -> float:
    """Score audience intentionality based on audience signals in text.
    
    Args:
        text: Text content to analyze
        domain_type: Optional domain type (e.g., "regulatory", "finance_banking") for domain-specific scoring
        
    Returns:
        Score from 0-100 indicating how well content targets its audience
    """
    if not text or len(text.strip()) < 20:
        return 0.0

    text_lower = text.lower()
    score = 0.0
    domain_matched = False
    
    # Domain-specific lexicons (priority when domain_type matches)
    if domain_type:
        domain_type_lower = domain_type.lower()
        
        # Regulatory domain
        if domain_type_lower in ["regulatory", "reg"]:
            regulatory_terms = [
                "supervisor", "auditor", "regulator", "supervision", "regulatory",
                "compliance officer", "risk manager", "internal audit",
                "regulatory authority", "supervisory authority", "audit committee",
                "compliance framework", "regulatory requirement", "supervisory review",
                "regulatory reporting", "audit trail", "regulatory compliance",
                "compliance", "supervisory", "audit"
            ]
            regulatory_hits = sum(1 for term in regulatory_terms if re.search(r"\b" + re.escape(term) + r"\b", text_lower))
            if regulatory_hits > 0:
                score += min(regulatory_hits * 20.0, 60.0)
                domain_matched = True
        
        # Finance/Banking domain
        elif domain_type_lower in ["finance_banking", "finance", "banking"]:
            finance_terms = [
                "bank", "banking", "financial institution", "lender", "borrower",
                "credit risk", "market risk", "liquidity risk", "operational risk",
                "capital adequacy", "solvency", "balance sheet", "income statement",
                "financial statement", "audit", "auditor", "compliance officer",
                "risk manager", "treasurer", "cfo", "financial analyst", "investor",
                "shareholder", "stakeholder", "regulatory reporting", "financial"
            ]
            finance_hits = sum(1 for term in finance_terms if re.search(r"\b" + re.escape(term) + r"\b", text_lower))
            if finance_hits > 0:
                score += min(finance_hits * 18.0, 60.0)
                domain_matched = True

    # Generic lexicons (reduced weight when domain matched to prevent saturation)
    generic_multiplier = 0.5 if domain_matched else 1.0  # Reduce generic boosts when domain matched
    
    # Healthcare audience signals (REMOVED "regulatory" from this list)
    healthcare_terms = [
        "hcp",
        "physician",
        "patient",
        "doctor",
        "nurse",
        "clinician",
        "prescriber",
        "caregiver",
        "healthcare",
    ]
    healthcare_hits = sum(1 for term in healthcare_terms if re.search(r"\b" + re.escape(term) + r"\b", text_lower))
    if healthcare_hits > 0:
        score += min(healthcare_hits * 25.0 * generic_multiplier, 50.0 * generic_multiplier)

    # Business/Executive audience signals
    business_terms = [
        "executive",
        "management",
        "stakeholder",
        "board",
        "investor",
        "shareholder",
        "revenue",
        "profit",
        "quarterly",
        "annual",
    ]
    business_hits = sum(1 for term in business_terms if re.search(r"\b" + re.escape(term) + r"\b", text_lower))
    if business_hits > 0:
        score += min(business_hits * 15.0 * generic_multiplier, 50.0 * generic_multiplier)

    # Technical/Developer audience signals
    tech_terms = [
        "developer",
        "engineer",
        "api",
        "sdk",
        "cli",
        "code",
        "implementation",
        "integration",
        "deployment",
        "architecture",
        "technical",
    ]
    tech_hits = sum(1 for term in tech_terms if re.search(r"\b" + re.escape(term) + r"\b", text_lower))
    if tech_hits > 0:
        score += min(tech_hits * 15.0 * generic_multiplier, 50.0 * generic_multiplier)

    # Operations audience signals
    ops_terms = [
        "operations",
        "monitoring",
        "maintenance",
        "support",
        "service",
        "infrastructure",
        "scalability",
        "performance",
    ]
    ops_hits = sum(1 for term in ops_terms if re.search(r"\b" + re.escape(term) + r"\b", text_lower))
    if ops_hits > 0:
        score += min(ops_hits * 15.0 * generic_multiplier, 50.0 * generic_multiplier)

    # Legal domain signals
    legal_terms = [
        "attorney", "lawyer", "counsel", "legal counsel", "compliance",
        "legal requirement", "legal framework", "jurisdiction", "litigation",
        "contract", "agreement", "legal entity", "legal obligation"
    ]
    legal_hits = sum(1 for term in legal_terms if re.search(r"\b" + re.escape(term) + r"\b", text_lower))
    if legal_hits > 0:
        score += min(legal_hits * 20.0 * generic_multiplier, 50.0 * generic_multiplier)

    # General audience signals (you, your, users, customers) - always apply
    general_signals = bool(re.search(r"\b(?:you|your|users?|customers?|readers?|audience)\b", text_lower))
    if general_signals:
        score += 30.0

    # Direct audience addressing (for, intended for, designed for) - always apply
    direct_addressing = bool(re.search(r"\b(?:for|intended\s+for|designed\s+for|targeted\s+to)\s+(?:the\s+)?\w+", text_lower))
    if direct_addressing:
        score += 20.0

    return min(score, 100.0)


def score_diversity(text: str) -> float:
    """Score diversity using Type-Token Ratio (TTR).
    
    TTR measures vocabulary diversity: unique words / total words.
    Higher TTR = more diverse vocabulary = better score.
    """
    if not text or len(text.strip()) < 20:
        return 0.0
    
    # Extract words (lowercase, alphanumeric)
    words = re.findall(r'\b[a-z0-9]+\b', text.lower())
    if not words:
        return 0.0
    
    # Calculate Type-Token Ratio
    unique_words = len(set(words))
    total_words = len(words)
    ttr = unique_words / total_words if total_words > 0 else 0.0
    
    # Normalize TTR to 0-100 scale
    # TTR typically ranges from 0.3-0.7 for most text
    # We'll scale it: 0.3 TTR = 50 score, 0.7 TTR = 100 score
    if ttr < 0.3:
        score = (ttr / 0.3) * 50.0
    elif ttr <= 0.7:
        score = 50.0 + ((ttr - 0.3) / 0.4) * 50.0
    else:
        score = 100.0
    
    return min(100.0, max(0.0, score))


def score_audience_accessibility(meta: Dict[str, Any]) -> float:
    """Score audience accessibility based on detected audience and text readability."""
    audience = str(meta.get("audience", "")).strip().lower()
    text = meta.get("text", "")

    # If audience is explicitly set and not "unknown", give base score
    if audience and audience not in ("", "unknown", "general"):
        base_score = 70.0

        # Reward specific, well-defined audiences
        well_defined_audiences = ["hcp", "executive", "regulatory", "patient", "finance", "ops", "dev"]
        if audience in well_defined_audiences:
            base_score = 85.0

        # Adjust based on text readability (shorter, clearer sentences = more accessible)
        if text:
            words = text.split()
            sentences = re.split(r"[.!?]+", text)
            sentences = [s.strip() for s in sentences if s.strip()]
            if sentences:
                avg_sentence_len = len(words) / len(sentences)
                # Ideal: 10-20 words per sentence for accessibility
                if 10 <= avg_sentence_len <= 20:
                    readability_bonus = 15.0
                elif 8 <= avg_sentence_len <= 25:
                    readability_bonus = 10.0
                elif 5 <= avg_sentence_len <= 30:
                    readability_bonus = 5.0
                else:
                    readability_bonus = 0.0
                return min(base_score + readability_bonus, 100.0)

        return base_score

    # If no audience detected, check text for accessibility indicators
    if text:
        text_lower = text.lower()
        # Check for simple language indicators
        has_simple_language = bool(re.search(r"\b(simple|easy|clear|straightforward|basic)\b", text_lower))
        has_examples = bool(re.search(r"\b(?:example|for instance|such as|including)\b", text_lower))

        if has_simple_language or has_examples:
            return 50.0

    return 30.0  # Default lower score if no audience signals found


def score_kb_ready(text: str) -> float:
    """Score knowledge base readiness."""
    return 100.0 if len(text.split()) > 50 and "\n" in text else 50.0


def load_weights(path: str) -> Dict[str, float]:
    """Load scoring weights from JSON file."""
    with open(path) as f:
        return json.load(f)


def score_file_data(data: Dict[str, Any], weights: Dict[str, float]) -> Dict[str, Any]:
    """
    Score a file data record using primary scoring methods.

    Args:
        data: Record with text and metadata
        weights: Scoring weights dictionary

    Returns:
        Dictionary with all 13 metrics + AI_Trust_Score
    """
    logger.info(f"📊 score_file_data() ENTRY: data_keys={list(data.keys())}, num_weights={len(weights)}")
    text = data.get("text", "")
    meta = data.copy()

    logger.debug(f"📋 Extracting and tokenizing text ({len(text)} chars)")
    if HAS_TIKTOKEN:
        tokens = TOK.encode(text)
        logger.debug(f"✓ Encoded with tiktoken: {len(tokens)} tokens")
    else:
        tokens = text.split()  # Fallback
        logger.debug(f"⚠️ Using word-based fallback: {len(tokens)} tokens")

    words = text.split()
    token_score = min(len(tokens) / 1000.0, 1.0) * 100.0

    # Prepare meta with text for audience accessibility scoring
    meta_with_text = dict(meta)
    meta_with_text["text"] = text

    # Extract domain_type from record (check both flat and nested locations)
    domain_type = data.get("domain_type") or data.get("metadata", {}).get("domain_type")
    logger.debug(f"📋 Domain type: {domain_type}")

    logger.debug(f"📋 Computing 13 scoring metrics...")
    scores = {
        "Completeness": score_completeness(tokens),
        "Accuracy": score_accuracy(words),
        "Secure": score_secure(text),
        "Quality": score_quality(text),
        "Timeliness": score_timeliness(meta.get("timestamp", "")),
        "Token_Count": round(token_score, 2),
        "GPT_Confidence": score_gpt_confidence(text),
        "Context_Quality": score_context_quality(text),
        "Metadata_Presence": score_metadata_presence(meta),
        "Audience_Intentionality": score_audience_intentionality(text, domain_type=domain_type),
        "Diversity": score_diversity(text),
        "Audience_Accessibility": score_audience_accessibility(meta_with_text),
        "KnowledgeBase_Ready": score_kb_ready(text),
    }

    logger.debug(f"✓ Individual scores: {[(k, round(v, 1)) for k, v in scores.items()]}")

    # Penalty adjustments
    alpha = sum(c.isalpha() for c in text) / max(len(text), 1)
    if alpha < 0.5:
        logger.warning(f"⚠️ Low alpha ratio ({alpha:.2f}), applying penalty adjustments")
        scores["Quality"] *= 0.4
        scores["Accuracy"] *= 0.7

    # Weighted aggregate
    logger.debug(f"📋 Calculating weighted AI_Trust_Score")
    # Only include weights for metrics that exist in scores, skip missing metrics
    # (AI-ready metrics like Avg_Chunk_Coherence are calculated separately in aggregate_metrics_with_ai_ready())
    applicable_weights = {k: v for k, v in weights.items() if k in scores}
    missing_metrics = set(weights.keys()) - set(scores.keys())
    if missing_metrics:
        logger.debug(f"⚠️ Missing metrics (not in this record): {missing_metrics}")

    total_w = sum(applicable_weights.values())

    if total_w > 0:
        weighted = sum(min(scores[k], 100.0) * applicable_weights[k] for k in applicable_weights)
        scores["AI_Trust_Score"] = round(weighted / total_w, 2)
    else:
        logger.warning(f"⚠️ No applicable weights found, setting AI_Trust_Score to 0")
        scores["AI_Trust_Score"] = 0.0

    logger.info(f"✅ score_file_data() EXIT: AI_Trust_Score={scores['AI_Trust_Score']}")
    return scores
