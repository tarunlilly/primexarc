"""
Chunk coherence calculation for AI-Ready metrics.

Measures semantic cohesion within chunks to ensure they stay on one topic.
"""
from typing import Dict, List, Any, Optional
import numpy as np
import regex as re

from primedata.utils.log_utils import get_logger

logger = get_logger(__name__)

# Global model instance (lazy-loaded)
_coherence_model: Optional[Any] = None


def get_coherence_model() -> Optional[Any]:
    """Lazy-load and return the sentence-transformers coherence model.

    :return: A SentenceTransformer model instance, or None if the library is unavailable.
    """
    global _coherence_model
    if _coherence_model is None:
        try:
            from sentence_transformers import SentenceTransformer
            # Use a lightweight model for coherence checking
            _coherence_model = SentenceTransformer('all-MiniLM-L6-v2')
            logger.info("Initialized coherence model: all-MiniLM-L6-v2")
        except ImportError:
            logger.warning("sentence-transformers not available, coherence will use simple method")
            _coherence_model = None
    return _coherence_model


def calculate_chunk_coherence(
    chunk_text: str,
    method: str = "embedding_similarity",
    sentence_window: int = 3,
    min_coherence_threshold: float = 0.6
) -> Dict[str, Any]:
    """Calculate a coherence score indicating how semantically unified a chunk is.

    :param chunk_text: The chunk text to analyze for internal coherence.
    :param method: Scoring method: 'embedding_similarity', 'topic_clustering', or 'sentence_connectivity'.
    :param sentence_window: Number of preceding sentences to compare against (for embedding_similarity).
    :param min_coherence_threshold: Minimum similarity value to classify the chunk as coherent.
    :return: Dict with 'coherence_score' (0-100), 'method', 'sentence_count', 'avg_similarity', and 'is_coherent'.
    """
    logger.info(f"🔍 calculate_chunk_coherence() ENTRY: chunk_len={len(chunk_text)}, method={method}")

    if not chunk_text or len(chunk_text.strip()) < 50:
        logger.debug("📋 Text too short, returning zero coherence")
        return {
            "coherence_score": 0.0,
            "method": method,
            "sentence_count": 0,
            "avg_similarity": 0.0,
            "is_coherent": False
        }

    # Split into sentences using improved approach
    # First try: split on sentence-ending punctuation followed by space and capital letter
    # This handles most cases while avoiding abbreviations
    logger.debug("📋 Splitting text into sentences")
    sent_pattern = re.compile(r'[.!?]+(?=\s+[A-Z0-9"\'\(\[\{]|$)')
    sentences = [s.strip() for s in sent_pattern.split(chunk_text) if s.strip()]

    # Fallback: if regex didn't work well, use simple split but filter out very short segments
    # and common abbreviation patterns
    if len(sentences) < 2:
        logger.debug("📋 Regex split produced <2 sentences, using fallback")
        # Split on periods but be smarter about it
        parts = chunk_text.split('.')
        sentences = []
        for part in parts:
            part = part.strip()
            # Skip very short parts (likely abbreviations) unless it's the last one
            if part and (len(part) > 3 or part == parts[-1]):
                sentences.append(part)

    logger.debug(f"✓ Split into {len(sentences)} sentences")

    if len(sentences) < 2:
        # Single sentence chunks are considered coherent
        logger.debug("📋 Single sentence, marking as coherent")
        return {
            "coherence_score": 1.0,
            "method": method,
            "sentence_count": len(sentences),
            "avg_similarity": 1.0,
            "is_coherent": True
        }

    if method == "embedding_similarity":
        logger.debug("📋 Using embedding similarity method")
        result = _coherence_embedding_similarity(sentences, sentence_window, min_coherence_threshold)
    elif method == "sentence_connectivity":
        logger.debug("📋 Using sentence connectivity method")
        result = _coherence_sentence_connectivity(sentences, min_coherence_threshold)
    else:
        logger.warning(f"❌ Unknown coherence method: {method}, using sentence_connectivity")
        result = _coherence_sentence_connectivity(sentences, min_coherence_threshold)

    logger.info(f"✅ calculate_chunk_coherence() EXIT: score={result.get('coherence_score', 0):.2f}%")
    return result


def _coherence_embedding_similarity(
    sentences: List[str],
    window: int,
    threshold: float
) -> Dict[str, Any]:
    """Calculate coherence via cosine similarity of sentence embeddings with adaptive windowing.

    For large chunks, reduces the comparison window to focus on local coherence
    rather than penalizing naturally multi-topic documents.

    :param sentences: List of sentence strings extracted from the chunk.
    :param window: Maximum number of preceding sentences to compare against.
    :param threshold: Minimum average similarity to classify the chunk as coherent.
    :return: Dict with 'coherence_score' (0-100), 'method', 'sentence_count',
        'avg_similarity', 'is_coherent', and 'similarities' (first 10 values).
    """
    model = get_coherence_model()
    if model is None:
        # Fallback to sentence connectivity if model not available
        return _coherence_sentence_connectivity(sentences, threshold)
    
    try:
        embeddings = model.encode(sentences, convert_to_numpy=True)
        
        # Normalize embeddings for cosine similarity
        def normalize_embeddings(emb):
            norms = np.linalg.norm(emb, axis=1, keepdims=True)
            norms = np.where(norms == 0, 1, norms)  # Avoid division by zero
            return emb / norms
        
        embeddings_normalized = normalize_embeddings(embeddings)
        
        # Adaptive windowing: for large chunks, use smaller windows to focus on local coherence
        # This prevents distant sentences (which may be on different topics) from lowering coherence
        num_sentences = len(sentences)
        if num_sentences > 20:
            # Large chunk: use smaller window to focus on local coherence
            adaptive_window = min(window, 3)
            logger.debug(f"Large chunk ({num_sentences} sentences), using adaptive window {adaptive_window}")
        elif num_sentences > 10:
            # Medium chunk: use medium window
            adaptive_window = min(window, 5)
        else:
            # Small chunk: use full window
            adaptive_window = window
        
        similarities = []
        for i in range(1, len(sentences)):
            # Compare current sentence with previous N sentences (adaptive window)
            start_idx = max(0, i - adaptive_window)
            prev_embeddings = embeddings_normalized[start_idx:i]
            current_embedding = embeddings_normalized[i]
            
            # Calculate cosine similarity (dot product of normalized vectors)
            if len(prev_embeddings) > 0:
                # Cosine similarity = dot product of normalized vectors
                similarities_matrix = np.dot(prev_embeddings, current_embedding)
                avg_similarity = float(np.mean(similarities_matrix))
                similarities.append(avg_similarity)
        
        if not similarities:
            coherence_score = 1.0
            avg_similarity = 1.0
        else:
            avg_similarity = float(np.mean(similarities))
            # For regulatory/formal content, similarity scores tend to be lower
            # Apply a scaling factor to normalize better
            # If threshold is low (0.5), content is expected to have lower coherence
            if threshold < 0.6:
                # Regulatory content: scale more leniently
                # Map 0.3-0.6 similarity range to 50-100 score range
                if avg_similarity < 0.3:
                    coherence_score = (avg_similarity / 0.3) * 50.0
                elif avg_similarity <= 0.6:
                    coherence_score = 50.0 + ((avg_similarity - 0.3) / 0.3) * 50.0
                else:
                    coherence_score = min(100.0, avg_similarity * 100)
            else:
                # Standard content: use direct scaling
                coherence_score = min(100.0, max(0.0, avg_similarity * 100))
        
        return {
            "coherence_score": round(coherence_score, 2),
            "method": "embedding_similarity",
            "sentence_count": len(sentences),
            "avg_similarity": round(avg_similarity, 4),
            "is_coherent": avg_similarity >= threshold,
            "similarities": [round(s, 4) for s in similarities[:10]]  # First 10 for debugging
        }
    except Exception as e:
        logger.error(f"Error calculating embedding similarity coherence: {e}")
        # Fallback to sentence connectivity
        return _coherence_sentence_connectivity(sentences, threshold)


def _coherence_sentence_connectivity(
    sentences: List[str],
    threshold: float
) -> Dict[str, Any]:
    """Calculate coherence using Jaccard keyword overlap between consecutive sentences.

    :param sentences: List of sentence strings extracted from the chunk.
    :param threshold: Minimum average overlap to classify the chunk as coherent.
    :return: Dict with 'coherence_score' (0-100), 'method', 'sentence_count',
        'avg_similarity', 'is_coherent', and 'overlaps' (first 10 values).
    """
    # Simple approach: check for common keywords/entities between sentences
    sentence_words = [set(s.lower().split()) for s in sentences]
    
    overlaps = []
    for i in range(1, len(sentence_words)):
        prev_words = sentence_words[i-1]
        curr_words = sentence_words[i]
        
        if len(prev_words) == 0 or len(curr_words) == 0:
            overlap = 0.0
        else:
            # Jaccard similarity
            intersection = len(prev_words & curr_words)
            union = len(prev_words | curr_words)
            overlap = intersection / union if union > 0 else 0.0
        
        overlaps.append(overlap)
    
    if not overlaps:
        avg_overlap = 1.0
    else:
        avg_overlap = float(np.mean(overlaps))
    
    coherence_score = min(100.0, max(0.0, avg_overlap * 100))
    
    return {
        "coherence_score": round(coherence_score, 2),
        "method": "sentence_connectivity",
        "sentence_count": len(sentences),
        "avg_similarity": round(avg_overlap, 4),
        "is_coherent": avg_overlap >= threshold,
        "overlaps": [round(o, 4) for o in overlaps[:10]]
    }

