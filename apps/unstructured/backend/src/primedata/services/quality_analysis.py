"""
Quality Analysis Utilities

Pure utility functions for chunk quality analysis including boundary detection,
quality issue identification, text/vector similarity calculations, and filter matching.

Extracted from primedata.api.chunk_quality for reuse across services.
"""

import math
from typing import List


def detect_mid_sentence_boundaries(text: str) -> tuple:
    """
    Detect if chunk starts or ends mid-sentence.

    KISS: Simple heuristic - check for sentence-ending punctuation at edges.

    Args:
        text: The chunk text to analyze.

    Returns:
        Tuple of (starts_mid_sentence, ends_mid_sentence)
    """
    if not text or len(text.strip()) == 0:
        return False, False

    text = text.strip()

    # Check start - should begin with capital letter or quote
    starts_mid = text[0].islower() and text[0] not in ('"', "'", "(")

    # Check end - should end with sentence-ending punctuation
    sentence_endings = (".", "!", "?")
    ends_mid = not text[-1] in sentence_endings

    return starts_mid, ends_mid


def identify_quality_issues(
    metadata, mid_start: bool, mid_end: bool
) -> List[str]:
    """
    Identify quality issues for a chunk.

    Args:
        metadata: An object with confidence_score, noise_score, and coherence_score attributes.
        mid_start: Whether the chunk starts mid-sentence.
        mid_end: Whether the chunk ends mid-sentence.

    Returns:
        List of issue identifier strings.
    """
    issues = []

    if mid_start:
        issues.append("starts_mid_sentence")
    if mid_end:
        issues.append("ends_mid_sentence")

    # Scores are 0-100, so threshold at 50%
    if metadata.confidence_score < 50:
        issues.append("low_confidence")
    if metadata.noise_score > 50:
        issues.append("high_noise")
    if metadata.coherence_score < 50:
        issues.append("low_coherence")

    return issues


def calculate_text_similarity(text1: str, text2: str) -> float:
    """
    Calculate simple text similarity using Jaccard index.

    Args:
        text1: First text string.
        text2: Second text string.

    Returns:
        Similarity score between 0.0 and 1.0.
    """
    if not text1 or not text2:
        return 0.0

    set1 = set(text1.split())
    set2 = set(text2.split())

    if not set1 and not set2:
        return 1.0

    intersection = len(set1 & set2)
    union = len(set1 | set2)

    return intersection / union if union > 0 else 0.0


def calculate_cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """
    Calculate cosine similarity between two vectors.

    Args:
        vec1: First vector.
        vec2: Second vector (must be same length as vec1).

    Returns:
        Cosine similarity between -1.0 and 1.0, or 0.0 if inputs are invalid.
    """
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0

    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    mag1 = math.sqrt(sum(a ** 2 for a in vec1))
    mag2 = math.sqrt(sum(b ** 2 for b in vec2))

    if mag1 == 0 or mag2 == 0:
        return 0.0

    return dot_product / (mag1 * mag2)


def calculate_euclidean_distance(vec1: List[float], vec2: List[float]) -> float:
    """
    Calculate euclidean distance between two vectors.

    Args:
        vec1: First vector.
        vec2: Second vector (must be same length as vec1).

    Returns:
        Euclidean distance, or 0.0 if inputs are invalid.
    """
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0

    return math.sqrt(sum((a - b) ** 2 for a, b in zip(vec1, vec2)))


def matches_filters(metadata, filters) -> bool:
    """
    Check if chunk metadata matches all quality filters.

    Args:
        metadata: An object with confidence_score, coherence_score, noise_score,
                  source_file, section, and page_number attributes.
        filters: An object with confidence, coherence, noise, source_file, section,
                 and page_number attributes. Score filters should have min_score
                 and max_score attributes.

    Returns:
        True if metadata passes all filters, False otherwise.
    """
    # Confidence filter
    if filters.confidence:
        if filters.confidence.min_score is not None:
            if metadata.confidence_score < filters.confidence.min_score:
                return False
        if filters.confidence.max_score is not None:
            if metadata.confidence_score > filters.confidence.max_score:
                return False

    # Coherence filter
    if filters.coherence and filters.coherence.min_score is not None:
        if metadata.coherence_score < filters.coherence.min_score:
            return False

    # Noise filter (inverted - lower is better)
    if filters.noise and filters.noise.max_score is not None:
        if metadata.noise_score > filters.noise.max_score:
            return False

    # Metadata filters
    if filters.source_file and metadata.source_file != filters.source_file:
        return False
    if filters.section and metadata.section != filters.section:
        return False
    if filters.page_number and metadata.page_number != filters.page_number:
        return False

    return True
