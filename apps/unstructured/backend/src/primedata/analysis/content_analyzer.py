"""
Content analysis module for intelligent chunking configuration.

This module analyzes content to automatically determine optimal chunking strategies
based on content type, structure, and complexity.
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..utils.logger import get_logger
logger = get_logger(__name__)


def build_representative_sample(text: str, chunk: int = 5000, max_total: int = 20000) -> str:
    """Build a representative text sample using head, middle, and tail segments.

    Extracts three equally-sized segments (head, middle, tail) from the input text
    to create a sample that represents the overall content without reading everything.

    :param text: The full source text to sample from.
    :param chunk: Size in characters of each segment (head, middle, tail).
    :param max_total: Maximum total characters in the returned sample.
    :return: A concatenated sample string, or empty string if input is empty.
    """
    if not text:
        return ""

    normalized = " ".join(text.split())
    if not normalized:
        return ""

    if len(normalized) <= max_total:
        return normalized[:max_total]

    segment_size = min(chunk, max_total // 3)
    midpoint = len(normalized) // 2
    half_segment = segment_size // 2
    middle_start = max(0, midpoint - half_segment)
    middle_end = middle_start + segment_size
    if middle_end > len(normalized):
        middle_end = len(normalized)
        middle_start = max(0, middle_end - segment_size)

    head = normalized[:segment_size]
    middle = normalized[middle_start:middle_end]
    tail = normalized[-segment_size:]

    sample = f"{head} === MIDDLE SAMPLE === {middle} === END SAMPLE === {tail}"
    return sample[:max_total]


class ContentType(str, Enum):
    """Content type enumeration."""

    LEGAL = "legal"
    REGULATORY = "regulatory"  # For regulatory documents (EBA, ECB, Basel, etc.)
    FINANCE_BANKING = "finance_banking"  # For banking/financial documents
    CODE = "code"
    DOCUMENTATION = "documentation"
    CONVERSATION = "conversation"
    ACADEMIC = "academic"
    TECHNICAL = "technical"
    GENERAL = "general"


class ChunkingStrategy(str, Enum):
    """Chunking strategy enumeration."""

    FIXED_SIZE = "fixed_size"
    SEMANTIC = "semantic"
    RECURSIVE = "recursive"
    SENTENCE_BOUNDARY = "sentence_boundary"
    PARAGRAPH_BOUNDARY = "paragraph_boundary"


@dataclass
class ChunkingConfig:
    """Chunking configuration data class."""

    chunk_size: int
    chunk_overlap: int
    min_chunk_size: int
    max_chunk_size: int
    strategy: ChunkingStrategy
    content_type: ContentType
    confidence: float  # 0.0 to 1.0, how confident we are in this configuration
    reasoning: str  # Human-readable explanation of why these settings were chosen
    evidence: Optional[Dict[str, Any]] = None  # Detection evidence for UI display


class ContentAnalyzer:
    """Analyzes content to determine optimal chunking configuration."""

    def __init__(self) -> None:
        """Initialize the ContentAnalyzer with detection patterns and optimal configs.

        Sets up regex patterns for each ContentType and maps each type to
        a recommended ChunkingConfig (sizes expressed in tokens).
        """
        self.content_patterns = {
            ContentType.LEGAL: [
                r"\b(whereas|hereby|herein|hereinafter|pursuant to|in accordance with)\b",
                r"\b(agreement|contract|terms|conditions|clause|section)\b",
                r"\b(party|parties|plaintiff|defendant|court|legal)\b",
            ],
            ContentType.REGULATORY: [
                r"\b(supervisor|auditor|regulator|supervision|regulatory)\b",
                r"\b(eba|ecb|basel|crr|crd|ssm|pru|fca|sec)\b",  # Regulatory bodies
                r"\b(guidelines|framework|directive|regulation|compliance)\b",
                r"\b(capital|risk|governance|oversight|monitoring)\b",
                r"\b(principle|requirement|standard|provision)\b",
                r"\b(whereas|pursuant to|in accordance with|hereinafter)\b",  # Legal language in regulatory docs
            ],
            ContentType.FINANCE_BANKING: [
                r"\b(banking|financial|finance|bank|institution)\b",
                r"\b(capital|liquidity|solvency|credit|market\s+risk)\b",  # Fixed: "market risk" as two words
                r"\b(asset|liability|balance\s+sheet|income\s+statement)\b",  # Fixed: multi-word terms
                r"\b(regulation|compliance|audit|supervision)\b",
                r"\b(interest\s+rate|yield|portfolio|investment)\b",  # Fixed: "interest rate" as two words
            ],
            ContentType.CODE: [
                r"^\s*(def|class|function|import|from|if|for|while|try|except)\s+",
                r"^\s*[a-zA-Z_][a-zA-Z0-9_]*\s*[=\(]",  # Variable assignments
                r"^\s*#.*$",  # Comments
                r"^\s*//.*$",  # Comments
                r"^\s*/\*.*\*/$",  # Block comments
            ],
            ContentType.DOCUMENTATION: [
                r"^#{1,6}\s+",  # Markdown headers
                r"^\s*\*\s+",  # Bullet points
                r"^\s*\d+\.\s+",  # Numbered lists
                r"```",  # Code blocks
                r"\[.*\]\(.*\)",  # Links
            ],
            ContentType.CONVERSATION: [
                r"^\s*\d{1,2}:\d{2}\s+[AP]M\s+",  # Timestamps
                r"^\s*\[.*\]\s+",  # Speaker names
                r"^\s*<.*>\s+",  # Chat format
                r"^\s*\w+:\s+",  # Simple speaker format
            ],
            ContentType.ACADEMIC: [
                r"\b(abstract|introduction|methodology|results|conclusion|references)\b",
                r"\b(study|research|analysis|hypothesis|findings|implications)\b",
                r"^\s*\d+\.\d+\s+",  # Section numbers
                r"\[.*\]\s*\(.*\)",  # Citations
            ],
            ContentType.TECHNICAL: [
                r"\b(API|endpoint|request|response|authentication|authorization)\b",
                r"\b(database|query|table|index|schema|migration)\b",
                r"\b(algorithm|optimization|performance|scalability|architecture)\b",
                r"^\s*```\w*$",  # Code blocks
            ],
        }

        # Optimal configurations for each content type
        # All sizes are in TOKENS (not characters)
        self.optimal_configs = {
            ContentType.LEGAL: {
                "chunk_size": 1200,
                "chunk_overlap": 240,  # ~20% overlap
                "min_chunk_size": 200,
                "max_chunk_size": 2000,
                "strategy": ChunkingStrategy.SEMANTIC,
                "reasoning": "Legal documents require larger chunks to preserve context and legal meaning",
            },
            ContentType.REGULATORY: {
                "chunk_size": 1400,
                "chunk_overlap": 280,  # ~20% overlap
                "min_chunk_size": 200,
                "max_chunk_size": 2200,
                "strategy": ChunkingStrategy.SEMANTIC,
                "reasoning": "Regulatory documents require larger chunks to preserve compliance context and cross-references",
            },
            ContentType.FINANCE_BANKING: {
                "chunk_size": 1300,
                "chunk_overlap": 260,  # ~20% overlap
                "min_chunk_size": 200,
                "max_chunk_size": 2000,
                "strategy": ChunkingStrategy.SEMANTIC,
                "reasoning": "Banking documents need larger chunks to preserve financial context and relationships",
            },
            ContentType.CODE: {
                "chunk_size": 900,
                "chunk_overlap": 180,  # ~20% overlap
                "min_chunk_size": 100,
                "max_chunk_size": 1500,
                "strategy": ChunkingStrategy.RECURSIVE,
                "reasoning": "Code benefits from recursive chunking to preserve function/class boundaries",
            },
            ContentType.DOCUMENTATION: {
                "chunk_size": 800,
                "chunk_overlap": 160,  # ~20% overlap
                "min_chunk_size": 100,
                "max_chunk_size": 1500,
                "strategy": ChunkingStrategy.PARAGRAPH_BOUNDARY,
                "reasoning": "Documentation works well with paragraph-based chunking for better readability",
            },
            ContentType.CONVERSATION: {
                "chunk_size": 700,
                "chunk_overlap": 140,  # ~20% overlap
                "min_chunk_size": 50,
                "max_chunk_size": 1200,
                "strategy": ChunkingStrategy.SENTENCE_BOUNDARY,
                "reasoning": "Conversations benefit from smaller chunks at sentence boundaries",
            },
            ContentType.ACADEMIC: {
                "chunk_size": 1200,
                "chunk_overlap": 240,  # ~20% overlap
                "min_chunk_size": 150,
                "max_chunk_size": 2000,
                "strategy": ChunkingStrategy.SEMANTIC,
                "reasoning": "Academic papers need larger chunks to preserve argument structure",
            },
            ContentType.TECHNICAL: {
                "chunk_size": 800,
                "chunk_overlap": 160,  # ~20% overlap
                "min_chunk_size": 100,
                "max_chunk_size": 1500,
                "strategy": ChunkingStrategy.SEMANTIC,
                "reasoning": "Technical content benefits from semantic chunking to preserve concept boundaries",
            },
            ContentType.GENERAL: {
                "chunk_size": 1000,
                "chunk_overlap": 200,
                "min_chunk_size": 100,
                "max_chunk_size": 2000,
                "strategy": ChunkingStrategy.FIXED_SIZE,
                "reasoning": "General content uses balanced fixed-size chunking for optimal retrieval",
            },
        }

    def analyze_content(
        self,
        content: str,
        filename: Optional[str] = None,
        hint: Optional[str] = None,
        full_text_length: Optional[int] = None,
    ) -> ChunkingConfig:
        """
        Analyze content and return optimal chunking configuration.

        Args:
            content: The text content to analyze
            filename: Optional filename for additional context
            hint: Optional domain hint from playbook (e.g., "regulatory", "legal", "finance_banking")
            full_text_length: Optional length of the full text when analyzing a sample

        Returns:
            ChunkingConfig with optimal settings and detection evidence
        """
        if full_text_length is not None and full_text_length != len(content):
            logger.info(
                f"🔍 analyze_content() ENTRY: sample_len={len(content)}, full_len={full_text_length}, filename={filename}, hint={hint}"
            )
        else:
            logger.info(f"🔍 analyze_content() ENTRY: content_len={len(content)}, filename={filename}, hint={hint}")

        # Detect content type with hint and evidence
        logger.debug(f"📋 Detecting content type")
        content_type, confidence, evidence = self._detect_content_type(content, filename, hint)
        logger.debug(f"✓ Detected: {content_type.value} (confidence={confidence:.2f})")

        # Get base configuration for detected type
        logger.debug(f"📋 Loading base configuration for {content_type.value}")
        base_config = self.optimal_configs[content_type]

        # Adjust configuration based on content characteristics
        logger.debug(f"📋 Adjusting configuration based on content characteristics")
        adjusted_config = self._adjust_for_content_characteristics(content, base_config, content_type)

        # Create final configuration with evidence
        config = ChunkingConfig(
            chunk_size=adjusted_config["chunk_size"],
            chunk_overlap=adjusted_config["chunk_overlap"],
            min_chunk_size=adjusted_config["min_chunk_size"],
            max_chunk_size=adjusted_config["max_chunk_size"],
            strategy=adjusted_config["strategy"],
            content_type=content_type,
            confidence=confidence,
            reasoning=adjusted_config["reasoning"],
            evidence=evidence,
        )

        logger.info(f"✅ analyze_content() EXIT: config={content_type.value}, strategy={config.strategy.value}, chunk_size={config.chunk_size}")
        return config

    def _detect_content_type(
        self,
        content: str,
        filename: Optional[str] = None,
        hint: Optional[str] = None
    ) -> Tuple[ContentType, float, Dict[str, Any]]:
        """Detect the content type by scoring regex pattern matches and applying optional hints.

        Scores each ContentType based on how many of its patterns match the content,
        optionally boosted by a playbook hint when detection confidence is low.

        :param content: Text content to analyze.
        :param filename: Optional filename whose extension may influence scoring.
        :param hint: Optional domain hint from the playbook (e.g., "regulatory", "legal").
        :return: Tuple of (detected ContentType, confidence score 0.0-1.0, evidence dict).
        """
        scores = {}
        evidence = {
            "matched_patterns": [],  # Top matched terms for UI display (FINAL type only)
            "pattern_details": {},  # Per-type pattern match details
            "hint_applied": False,
            "hint_type": None,
            "hint_boost": 0.0,
            "filename_extension": None,
            "all_scores": {},  # All type scores for comparison
        }

        # Map hint to ContentType
        hint_to_type = {
            "regulatory": ContentType.REGULATORY,
            "finance_banking": ContentType.FINANCE_BANKING,
            "legal": ContentType.LEGAL,
            "academic": ContentType.ACADEMIC,
            "technical": ContentType.TECHNICAL,
        }

        # Check filename extension if available
        if filename:
            ext = Path(filename).suffix.lower()
            evidence["filename_extension"] = ext
            if ext in [".py", ".js", ".java", ".cpp", ".c", ".go", ".rs"]:
                scores[ContentType.CODE] = 0.8
            elif ext in [".md", ".rst", ".txt"]:
                scores[ContentType.DOCUMENTATION] = 0.6
            elif ext in [".pdf", ".doc", ".docx"]:
                scores[ContentType.GENERAL] = 0.5

        # Analyze content patterns
        for content_type, patterns in self.content_patterns.items():
            score = 0.0
            matches = 0
            pattern_details = []

            for pattern in patterns:
                # Find all matches (not just count)
                pattern_matches = re.findall(pattern, content, re.IGNORECASE | re.MULTILINE)
                match_count = len(pattern_matches)
                
                if match_count > 0:
                    matches += 1
                    # Extract actual matched terms (flatten if tuples, take unique, limit for display)
                    matched_terms = []
                    for match in pattern_matches:
                        if isinstance(match, tuple):
                            # Regex groups - take first non-empty group
                            matched_terms.extend([m for m in match if m])
                        else:
                            matched_terms.append(match)
                    
                    # Get unique terms, limit to 10 per pattern
                    unique_terms = list(set([t.strip() for t in matched_terms if t.strip()]))[:10]
                    
                    pattern_details.append({
                        "pattern": pattern,
                        "match_count": match_count,
                        "matched_terms": unique_terms,  # For UI display
                    })
                    
                    # Normalize score based on content length
                    normalized_score = min(match_count / (len(content) / 1000), 1.0)
                    score += normalized_score

            if matches > 0:
                scores[content_type] = score / len(patterns)
                evidence["pattern_details"][content_type.value] = pattern_details

        # Store all scores for UI comparison
        evidence["all_scores"] = {k.value: round(v, 3) for k, v in scores.items()}

        # FIX #1: Apply hint when detection is weak (confidence < 0.5)
        if hint:
            hinted_type = hint_to_type.get(hint.lower())
            if hinted_type:
                evidence["hint_type"] = hint
                
                # Find current best score
                current_best_type = None
                current_best_score = 0.0
                if scores:
                    current_best_type, current_best_score = max(scores.items(), key=lambda x: x[1])
                
                # If best score is weak, prefer hint
                if not scores or current_best_score < 0.5:
                    scores[hinted_type] = max(scores.get(hinted_type, 0.0), 0.6)
                    evidence["hint_applied"] = True
                    evidence["hint_boost"] = 0.0  # No boost, just using hint
                    logger.info(
                        f"Hint '{hint}' applied because detection was weak "
                        f"(best={current_best_score:.2f}). Using {hinted_type.value} at 0.60"
                    )
                elif hinted_type in scores and scores[hinted_type] > 0:
                    # Boost confidence when hint agrees with detection
                    original_score = scores[hinted_type]
                    scores[hinted_type] = min(1.0, scores[hinted_type] + 0.2)
                    evidence["hint_applied"] = True
                    evidence["hint_boost"] = 0.2
                    logger.info(
                        f"Playbook hint '{hint}' matches detected type {hinted_type.value}, "
                        f"boosting confidence from {original_score:.2f} to {scores[hinted_type]:.2f}"
                    )

        # If no specific type detected, use general
        if not scores:
            evidence["final_type"] = ContentType.GENERAL.value
            evidence["final_confidence"] = 0.3
            return ContentType.GENERAL, 0.3, evidence

        # Return the type with highest score
        best_type = max(scores.items(), key=lambda x: x[1])
        final_confidence = min(best_type[1], 1.0)
        final_type_value = best_type[0].value
        
        evidence["final_type"] = final_type_value
        evidence["final_confidence"] = final_confidence

        # FIX #2: Keep UI terms focused - only show matched terms for FINAL type
        final_details = evidence["pattern_details"].get(final_type_value, [])
        final_terms = []
        for detail in final_details:
            final_terms.extend(detail.get("matched_terms", []))
        
        # Use dict.fromkeys to preserve order while deduplicating, then limit to 30
        evidence["matched_patterns"] = list(dict.fromkeys(final_terms))[:30]

        return best_type[0], final_confidence, evidence

    def _adjust_for_content_characteristics(self, content: str, base_config: Dict[str, Any], content_type: ContentType) -> Dict[str, Any]:
        """Adjust the base chunking configuration based on measured content characteristics.

        Scales chunk_size and chunk_overlap up or down depending on average sentence
        length, total word count, and paragraph density.

        :param content: The text content to measure.
        :param base_config: Base configuration dict for the detected ContentType.
        :param content_type: The detected ContentType (for potential type-specific tweaks).
        :return: A new configuration dict with adjusted values.
        """
        config = base_config.copy()

        # Analyze content complexity
        avg_sentence_length = self._calculate_avg_sentence_length(content)
        paragraph_count = len([p for p in content.split("\n\n") if p.strip()])
        word_count = len(content.split())

        # Adjust chunk size based on sentence length
        if avg_sentence_length > 30:  # Long sentences
            config["chunk_size"] = int(config["chunk_size"] * 1.2)
            config["chunk_overlap"] = int(config["chunk_overlap"] * 1.2)
            config["reasoning"] += " (adjusted for long sentences)"
        elif avg_sentence_length < 15:  # Short sentences
            config["chunk_size"] = int(config["chunk_size"] * 0.8)
            config["chunk_overlap"] = int(config["chunk_overlap"] * 0.8)
            config["reasoning"] += " (adjusted for short sentences)"

        # Adjust for very short content
        if word_count < 100:
            config["chunk_size"] = min(config["chunk_size"], word_count * 4)
            config["chunk_overlap"] = min(config["chunk_overlap"], config["chunk_size"] // 4)
            config["reasoning"] += " (adjusted for short content)"

        # Adjust for very long content
        elif word_count > 10000:
            config["chunk_size"] = int(config["chunk_size"] * 1.1)
            config["chunk_overlap"] = int(config["chunk_overlap"] * 1.1)
            config["reasoning"] += " (adjusted for long content)"

        # Ensure min/max constraints
        config["chunk_size"] = max(config["min_chunk_size"], min(config["chunk_size"], config["max_chunk_size"]))
        config["chunk_overlap"] = min(config["chunk_overlap"], config["chunk_size"] - 1)

        return config

    def _calculate_avg_sentence_length(self, content: str) -> float:
        """Calculate the average sentence length in words.

        Splits content on sentence-ending punctuation and computes the mean
        word count across all non-empty sentences.

        :param content: The text content to measure.
        :return: Average number of words per sentence, or 0.0 if no sentences found.
        """
        sentences = re.split(r"[.!?]+", content)
        if not sentences:
            return 0.0

        total_words = sum(len(sentence.split()) for sentence in sentences if sentence.strip())
        return total_words / len([s for s in sentences if s.strip()])

    def preview_chunking(self, content: str, config: ChunkingConfig) -> Dict[str, Any]:
        """
        Preview how content would be chunked with given configuration.

        Args:
            content: Content to preview
            config: Chunking configuration to use

        Returns:
            Dictionary with preview information
        """
        logger.info(f"🔍 preview_chunking() ENTRY: content_len={len(content)}, strategy={config.strategy.value}")
        logger.debug(f"📋 Simulating chunking with chunk_size={config.chunk_size}, overlap={config.chunk_overlap}")

        chunks = self._simulate_chunking(content, config)
        logger.debug(f"✓ Simulation created {len(chunks)} chunks")

        result = {
            "total_chunks": len(chunks),
            "avg_chunk_size": sum(len(chunk["text"]) for chunk in chunks) / len(chunks) if chunks else 0,
            "min_chunk_size": min(len(chunk["text"]) for chunk in chunks) if chunks else 0,
            "max_chunk_size": max(len(chunk["text"]) for chunk in chunks) if chunks else 0,
            "chunks": chunks[:5],  # First 5 chunks as preview
            "estimated_retrieval_quality": self._estimate_retrieval_quality(chunks, config),
        }

        logger.info(f"✅ preview_chunking() EXIT: {len(chunks)} chunks, avg_size={result['avg_chunk_size']:.0f}, quality={result['estimated_retrieval_quality']}")
        return result

    def _simulate_chunking(self, content: str, config: ChunkingConfig) -> List[Dict[str, Any]]:
        """Simulate the chunking process to produce a preview of chunk boundaries.

        Converts token-based sizes to approximate character counts (1 token ~ 4 chars)
        and walks through the content producing chunk metadata dicts.

        :param content: The full text to chunk.
        :param config: The ChunkingConfig specifying sizes and overlap.
        :return: List of chunk dicts with keys: chunk_index, text, start_char, end_char, size.
        """
        chunks = []
        start = 0
        chunk_index = 0

        # Convert tokens to approximate characters (1 token ≈ 4 chars)
        approx_chars = int(config.chunk_size * 4)
        approx_overlap_chars = int(config.chunk_overlap * 4)

        while start < len(content):
            end = min(start + approx_chars, len(content))
            chunk_text = content[start:end]

            if not chunk_text.strip():
                break

            chunks.append(
                {
                    "chunk_index": chunk_index,
                    "text": chunk_text.strip(),
                    "start_char": start,
                    "end_char": end,
                    "size": len(chunk_text.strip()),
                }
            )

            chunk_index += 1
            step_size = max(1, approx_chars - approx_overlap_chars)
            start += step_size

            if start >= len(content):
                break

        return chunks

    def _estimate_retrieval_quality(self, chunks: List[Dict[str, Any]], config: ChunkingConfig) -> str:
        """Estimate retrieval quality based on chunk size distribution.

        Classifies quality as 'high', 'medium', or 'low' by comparing average chunk
        size and size variance against the configured min/max boundaries.

        :param chunks: List of chunk dicts each containing a 'size' key.
        :param config: The ChunkingConfig used to produce the chunks.
        :return: Quality rating string: 'high', 'medium', 'low', or 'unknown'.
        """
        if not chunks:
            return "unknown"

        avg_size = sum(chunk["size"] for chunk in chunks) / len(chunks)
        size_variance = sum((chunk["size"] - avg_size) ** 2 for chunk in chunks) / len(chunks)

        # Convert config sizes from tokens to chars for comparison (1 token ≈ 4 chars)
        min_chars = config.min_chunk_size * 4
        max_chars = config.max_chunk_size * 4

        # Good quality indicators
        if min_chars <= avg_size <= max_chars and size_variance < (avg_size * 0.3) ** 2:
            return "high"
        elif min_chars * 0.8 <= avg_size <= max_chars * 1.2:
            return "medium"
        else:
            return "low"


# Global instance
content_analyzer = ContentAnalyzer()
