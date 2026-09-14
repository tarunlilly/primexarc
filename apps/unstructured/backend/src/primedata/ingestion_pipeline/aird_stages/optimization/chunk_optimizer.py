"""
Per-chunk optimization logic for LLM/hybrid optimization modes.

Handles applying LLM-based or hybrid (pattern + LLM) optimization to individual
text chunks during the preprocessing pipeline.
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def optimize_chunk(
    chunk_text: str,
    chunk_idx: int,
    optimization_config: Dict[str, Any],
    stats: Dict[str, Any],
    log: Optional[logging.Logger] = None,
) -> str:
    """Apply per-chunk LLM/hybrid optimization if configured.

    :param chunk_text: The raw chunk text to optimize.
    :param chunk_idx: Index of the chunk (for logging).
    :param optimization_config: Dict with keys 'mode', 'llm_config', 'quality_threshold', 'preprocessing_flags'.
    :param stats: Mutable stats dict to update with optimization metrics.
    :param log: Optional logger instance.
    :return: The optimized chunk text (or original if optimization is skipped/fails).
    """
    _log = log or logger

    opt_mode = optimization_config.get("mode", "pattern")

    # Only apply if mode is llm or hybrid and we have config
    if opt_mode not in ["llm", "hybrid"] or not optimization_config.get("llm_config"):
        return chunk_text

    stats["total_chunks"] += 1

    # Quick quality check first - skip if already high quality
    quality_threshold = optimization_config.get("quality_threshold", 75)
    try:
        from primedata.ingestion_pipeline.aird_stages.optimization.pattern_based import (
            PatternBasedOptimizer,
        )

        quick_quality_check = PatternBasedOptimizer()
        current_quality = quick_quality_check.estimate_quality(chunk_text)

        if current_quality >= quality_threshold:
            stats["skipped_high_quality"] += 1
            return chunk_text
        else:
            return _run_hybrid_optimization(
                chunk_text, chunk_idx, opt_mode, optimization_config, quality_threshold, stats, _log
            )
    except Exception as e:
        _log.warning(f"Quality check failed for chunk {chunk_idx}, attempting optimization: {e}")
        return _run_hybrid_optimization(
            chunk_text, chunk_idx, opt_mode, optimization_config, quality_threshold, stats, _log
        )


def _run_hybrid_optimization(
    chunk_text: str,
    chunk_idx: int,
    opt_mode: str,
    optimization_config: Dict[str, Any],
    quality_threshold: int,
    stats: Dict[str, Any],
    _log: logging.Logger,
) -> str:
    """Run hybrid/LLM optimization on a chunk.

    :param chunk_text: The chunk text to optimize.
    :param chunk_idx: Index of the chunk (for logging).
    :param opt_mode: Optimization mode ('llm' or 'hybrid').
    :param optimization_config: Full optimization config dict.
    :param quality_threshold: Quality threshold for optimization decisions.
    :param stats: Mutable stats dict to update.
    :param _log: Logger instance.
    :return: Optimized text, or original on failure.
    """
    try:
        from primedata.ingestion_pipeline.aird_stages.optimization.hybrid import HybridOptimizer

        optimizer = HybridOptimizer()
        chunk_result = optimizer.optimize(
            text=chunk_text,
            mode=opt_mode,
            pattern_flags={},
            llm_config=optimization_config.get("llm_config"),
            quality_threshold=quality_threshold,
        )

        optimized_text = chunk_result["optimized_text"]

        if chunk_result["method_used"] in ["llm", "hybrid"]:
            stats["llm_optimized"] += 1
            stats["total_cost"] += chunk_result.get("cost", 0.0)
        else:
            stats["pattern_only"] += 1

        return optimized_text
    except Exception as e:
        stats["failed"] += 1
        _log.warning(f"Per-chunk LLM optimization failed for chunk {chunk_idx}: {e}")
        return chunk_text


def create_optimization_stats() -> Dict[str, Any]:
    """Create a fresh optimization stats dictionary.

    :return: Dict with zeroed counters for optimization tracking.
    """
    return {
        "total_chunks": 0,
        "llm_optimized": 0,
        "skipped_high_quality": 0,
        "failed": 0,
        "pattern_only": 0,
        "total_cost": 0.0,
    }
