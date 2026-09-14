"""
Baseline Quality Assessment Stage

Assesses raw data quality BEFORE any transformations to enable before/after value demonstration.
This stage runs immediately after ingestion and calculates baseline quality metrics.
"""

import logging
import re
from typing import Dict, Any, Optional
from collections import Counter

logger = logging.getLogger(__name__)


class BaselineQualityAssessor:
    """Assess raw data quality before any transformations."""

    def __init__(self):
        """Initialize baseline quality assessor."""
        self.special_char_pattern = re.compile(r'[^\w\s\-.,!?;:()\[\]{}\'\"@#$%&+=/<>]')
        self.whitespace_pattern = re.compile(r'\s{2,}')

    def assess_raw_file(self, file_content: str, file_metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Calculate baseline quality metrics for raw file content.

        Args:
            file_content: Raw text content of the file
            file_metadata: Optional metadata dict with filename, content_type, etc.

        Returns:
            Dict with baseline metrics: {
                "completeness": 0-100 score,
                "noise_level": 0-100 score (higher = more noise),
                "structure_score": 0-100 score,
                "duplication": 0-100 rate,
                "overall_score": 0-100 aggregated score
            }
        """
        if not file_content or len(file_content.strip()) == 0:
            return {
                "completeness": 0.0,
                "noise_level": 100.0,
                "structure_score": 0.0,
                "duplication": 0.0,
                "overall_score": 0.0,
                "error": "Empty content"
            }

        try:
            completeness = self._check_completeness(file_content, file_metadata or {})
            noise_level = self._check_noise(file_content)
            structure_score = self._check_structure(file_content)
            duplication = self._check_duplicates(file_content)

            # Calculate overall score (weighted average)
            # Lower noise is better, so invert it: (100 - noise_level)
            overall_score = (
                completeness * 0.25 +
                (100 - noise_level) * 0.35 +  # Inverted - cleaner is better
                structure_score * 0.30 +
                (100 - duplication) * 0.10  # Inverted - less duplication is better
            )

            return {
                "completeness": round(completeness, 2),
                "noise_level": round(noise_level, 2),
                "structure_score": round(structure_score, 2),
                "duplication": round(duplication, 2),
                "overall_score": round(overall_score, 2)
            }

        except Exception as e:
            logger.error(f"Error calculating baseline metrics: {e}")
            return {
                "completeness": 0.0,
                "noise_level": 100.0,
                "structure_score": 0.0,
                "duplication": 0.0,
                "overall_score": 0.0,
                "error": str(e)
            }

    def _check_completeness(self, content: str, metadata: Dict[str, Any]) -> float:
        """
        Check metadata presence and content completeness.

        Completeness score based on:
        - Metadata fields populated (filename, content_type, etc.)
        - Content length (longer = more complete)
        - Presence of structural elements (sections, paragraphs)

        Returns:
            Score 0-100 (higher is better)
        """
        score = 0.0

        # Check metadata completeness (30 points)
        metadata_fields = ['filename', 'content_type', 'file_size']
        populated_fields = sum(1 for field in metadata_fields if metadata.get(field))
        score += (populated_fields / len(metadata_fields)) * 30

        # Check content length (30 points)
        content_length = len(content)
        if content_length < 100:
            score += 10  # Very short
        elif content_length < 1000:
            score += 20  # Short
        elif content_length < 10000:
            score += 30  # Good length
        else:
            score += 30  # Long content

        # Check for structural elements (40 points)
        # Paragraphs (double newlines)
        paragraphs = len(content.split('\n\n'))
        if paragraphs > 1:
            score += 15

        # Sentences (basic punctuation)
        sentences = len(re.findall(r'[.!?]+', content))
        if sentences > 5:
            score += 15

        # Words
        words = len(content.split())
        if words > 50:
            score += 10

        return min(score, 100)

    def _check_noise(self, content: str) -> float:
        """
        Detect special chars, garbled text, formatting issues.

        Noise indicators:
        - Excessive special characters
        - Repeated whitespace
        - Non-ASCII characters (except common punctuation)
        - Garbled text patterns

        Returns:
            Score 0-100 (higher = more noise, lower is better)
        """
        noise_score = 0.0

        # Check special character ratio (40 points max)
        special_chars = self.special_char_pattern.findall(content)
        special_char_ratio = len(special_chars) / len(content) if len(content) > 0 else 0
        noise_score += min(special_char_ratio * 400, 40)  # Cap at 40

        # Check excessive whitespace (20 points max)
        whitespace_matches = self.whitespace_pattern.findall(content)
        whitespace_ratio = sum(len(match) for match in whitespace_matches) / len(content) if len(content) > 0 else 0
        noise_score += min(whitespace_ratio * 200, 20)  # Cap at 20

        # Check non-ASCII ratio (30 points max)
        non_ascii_count = sum(1 for char in content if ord(char) > 127)
        non_ascii_ratio = non_ascii_count / len(content) if len(content) > 0 else 0
        noise_score += min(non_ascii_ratio * 100, 30)  # Cap at 30

        # Check for garbled text patterns (10 points max)
        # Long strings without spaces indicate garbled text
        words = content.split()
        long_words = [word for word in words if len(word) > 30]
        if long_words:
            noise_score += min(len(long_words) / len(words) * 100, 10)

        return min(noise_score, 100)

    def _check_structure(self, content: str) -> float:
        """
        Assess formatting, sections, readability.

        Structure indicators:
        - Consistent line lengths
        - Proper capitalization
        - Section markers (headings, lists)
        - Logical organization

        Returns:
            Score 0-100 (higher is better)
        """
        score = 0.0

        # Check for section headers (25 points)
        heading_patterns = [
            r'(?:^|\n)\s*(?:Chapter|Section|Part|Article)\s+[\dIVX]+',
            r'(?:^|\n)\s*[A-Z][A-Za-z\s]{2,50}:\s*$',
            r'(?:^|\n)\s*#{1,6}\s+.+$',  # Markdown headers
        ]
        has_headings = any(re.search(pattern, content, re.MULTILINE) for pattern in heading_patterns)
        if has_headings:
            score += 25

        # Check for lists (15 points)
        list_patterns = [
            r'(?:^|\n)\s*[\*\-\+\u2022]\s+',  # Bullet lists
            r'(?:^|\n)\s*\d+\.\s+',  # Numbered lists
        ]
        has_lists = any(re.search(pattern, content, re.MULTILINE) for pattern in list_patterns)
        if has_lists:
            score += 15

        # Check capitalization consistency (20 points)
        sentences = re.split(r'[.!?]+\s+', content)
        if sentences:
            capitalized = sum(1 for s in sentences if s and s[0].isupper())
            cap_ratio = capitalized / len(sentences)
            score += cap_ratio * 20

        # Check line length consistency (20 points)
        lines = content.split('\n')
        if len(lines) > 1:
            line_lengths = [len(line) for line in lines if line.strip()]
            if line_lengths:
                avg_length = sum(line_lengths) / len(line_lengths)
                # Ideal range: 60-100 chars per line
                if 60 <= avg_length <= 100:
                    score += 20
                elif 40 <= avg_length < 60 or 100 < avg_length <= 120:
                    score += 10

        # Check paragraph structure (20 points)
        paragraphs = content.split('\n\n')
        if len(paragraphs) > 2:
            score += 20

        return min(score, 100)

    def _check_duplicates(self, content: str) -> float:
        """
        Check for duplicate content.

        Duplication indicators:
        - Repeated lines
        - Repeated paragraphs
        - Repeated sentence patterns

        Returns:
            Score 0-100 (higher = more duplication, lower is better)
        """
        duplication_score = 0.0

        # Check for repeated lines (50 points max)
        lines = [line.strip() for line in content.split('\n') if line.strip()]
        if lines:
            line_counts = Counter(lines)
            duplicated_lines = sum(count - 1 for count in line_counts.values() if count > 1)
            line_dup_ratio = duplicated_lines / len(lines)
            duplication_score += min(line_dup_ratio * 100, 50)

        # Check for repeated sentences (50 points max)
        sentences = [s.strip() for s in re.split(r'[.!?]+', content) if s.strip() and len(s.strip()) > 10]
        if sentences:
            sentence_counts = Counter(sentences)
            duplicated_sentences = sum(count - 1 for count in sentence_counts.values() if count > 1)
            sentence_dup_ratio = duplicated_sentences / len(sentences) if len(sentences) > 0 else 0
            duplication_score += min(sentence_dup_ratio * 100, 50)

        return min(duplication_score, 100)


def assess_raw_file_quality(file_content: str, file_metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Convenience function to assess raw file quality.

    Args:
        file_content: Raw text content of the file
        file_metadata: Optional metadata dict

    Returns:
        Dict with baseline quality metrics
    """
    assessor = BaselineQualityAssessor()
    return assessor.assess_raw_file(file_content, file_metadata)
