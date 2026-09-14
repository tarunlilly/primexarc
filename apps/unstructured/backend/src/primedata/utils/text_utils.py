"""
Shared text processing utilities for PrimeData.

Functions in this module are used across multiple services (trust_scoring,
chunk_coherence, noise_detection) to avoid duplicating text manipulation logic.
"""

import re
from typing import List

SENTENCE_SPLIT_RE = re.compile(r"(?<!\b[A-Z])[.!?]+(?=\s+[A-Z0-9\"'])")
PAGE_MARKER_RE = re.compile(r"===\s*PAGE\s+\d+\s*===")


def split_into_sentences(text: str) -> List[str]:
    """Split text into a list of non-empty sentences.

    Uses punctuation-based sentence boundary detection. Strips
    page markers (e.g. '=== PAGE 3 ===') that are artifacts of
    PDF extraction before splitting.

    :param text: Raw text to split into sentences.
    :return: List of stripped, non-empty sentence strings.
    """
    if not text or not text.strip():
        return []

    cleaned = PAGE_MARKER_RE.sub(" ", text)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    sentences = [s.strip() for s in re.split(SENTENCE_SPLIT_RE, cleaned) if s and s.strip()]
    return sentences
