"""ydata-profiling enrichment — extracts ML-signal-quality metrics.

Runs ydata-profiling in minimal mode and extracts:
- Near-constant columns (one value dominates >threshold)
- Infinite-value columns
- Semantic type mismatches (stored dtype vs inferred type)
- Mixed-type correlation pairs (Phi_k above threshold)
- Missingness co-occurrence groups (columns that are null together)

Graceful degradation: if ydata-profiling fails for any reason, returns
empty results and logs a warning. Scoring proceeds with empty enrichment
fields — no dimension rule breaks.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from config import settings

logger = logging.getLogger(__name__)

# Mapping from ydata inferred types to our DType vocabulary
_YDATA_TYPE_MAP: dict[str, str] = {
    "Numeric": "float",
    "Categorical": "string",
    "Boolean": "bool",
    "DateTime": "datetime",
    "Text": "string",
    "Unsupported": "object",
}

# Our dtype labels that are "compatible" with ydata inferred types
_COMPATIBLE_PAIRS: set[tuple[str, str]] = {
    ("int", "Numeric"),
    ("float", "Numeric"),
    ("string", "Categorical"),
    ("string", "Text"),
    ("bool", "Boolean"),
    ("bool", "Categorical"),
    ("datetime", "DateTime"),
    ("object", "Categorical"),
    ("object", "Text"),
    ("object", "Unsupported"),
}


@dataclass
class EnrichmentResult:
    """Structured output from ydata-profiling enrichment."""
    infinite_columns: list[str] = field(default_factory=list)
    near_constant_columns: list[str] = field(default_factory=list)
    type_mismatches: list[dict] = field(default_factory=list)
    correlated_pairs_mixed: list[dict] = field(default_factory=list)
    missingness_groups: list[list[str]] = field(default_factory=list)


def enrich(df: pd.DataFrame, column_dtypes: dict[str, str] | None = None) -> EnrichmentResult:
    """Run ydata-profiling and extract actionable ML-signal metrics.

    Args:
        df: The DataFrame to profile (already row-capped by csv_parser).
        column_dtypes: Mapping of column name → our DType string, for
            type-mismatch detection. If None, type mismatch check is skipped.

    Returns:
        EnrichmentResult with populated fields. On failure, all fields are empty.
    """
    if not settings.ydata_enabled:
        return EnrichmentResult()

    try:
        return _run_enrichment(df, column_dtypes)
    except Exception:
        logger.warning("ydata-profiling enrichment failed; proceeding without it", exc_info=True)
        return EnrichmentResult()


def _run_enrichment(df: pd.DataFrame, column_dtypes: dict[str, str] | None) -> EnrichmentResult:
    """Internal: run profiling and extract metrics."""
    from ydata_profiling import ProfileReport

    report = ProfileReport(
        df,
        minimal=True,
        correlations={"phi_k": {"calculate": True}},
        missing_diagrams={"bar": False, "matrix": False, "heatmap": True},
        progress_bar=False,
        pool_size=1,
    )
    description = report.get_description()

    result = EnrichmentResult()
    result.infinite_columns = _extract_infinite_columns(df)
    result.near_constant_columns = _extract_near_constants(df)
    result.type_mismatches = _extract_type_mismatches(description, column_dtypes)
    result.correlated_pairs_mixed = _extract_phi_k_pairs(description)
    result.missingness_groups = _extract_missingness_groups(df)

    return result


def _extract_infinite_columns(df: pd.DataFrame) -> list[str]:
    """Find numeric columns containing inf/-inf values."""
    inf_cols = []
    for col in df.select_dtypes(include=[np.number]).columns:
        if np.isinf(df[col]).any():
            inf_cols.append(str(col))
    return inf_cols


def _extract_near_constants(df: pd.DataFrame) -> list[str]:
    """Find columns where one value dominates above threshold."""
    threshold = settings.ydata_near_constant_threshold
    near_const = []
    for col in df.columns:
        non_null = df[col].dropna()
        if len(non_null) == 0:
            continue
        top_freq = non_null.value_counts(normalize=True).iloc[0]
        if top_freq >= threshold:
            near_const.append(str(col))
    return near_const


def _extract_type_mismatches(
    description: dict, column_dtypes: dict[str, str] | None
) -> list[dict]:
    """Detect where ydata's inferred semantic type doesn't match stored dtype."""
    if column_dtypes is None:
        return []

    mismatches = []
    variables = description.get("variables", {})
    for col_name, var_info in variables.items():
        if col_name not in column_dtypes:
            continue
        inferred = var_info.get("type", "Unsupported")
        stored = column_dtypes[col_name]
        if (stored, inferred) not in _COMPATIBLE_PAIRS:
            mismatches.append({
                "column": col_name,
                "stored_as": stored,
                "detected_as": str(inferred),
            })
    return mismatches


def _extract_phi_k_pairs(description: dict) -> list[dict]:
    """Extract Phi_k correlation pairs above threshold."""
    threshold = settings.ydata_correlation_threshold
    pairs = []

    correlations = description.get("correlations", {})
    phi_k = correlations.get("phi_k", None)
    if phi_k is None:
        return pairs

    # phi_k is a DataFrame-like correlation matrix
    try:
        if hasattr(phi_k, "columns"):
            cols = list(phi_k.columns)
            for i, col_a in enumerate(cols):
                for j, col_b in enumerate(cols):
                    if j <= i:
                        continue
                    val = float(phi_k.iloc[i, j])
                    if val >= threshold:
                        pairs.append({
                            "column_a": col_a,
                            "column_b": col_b,
                            "phi_k": round(val, 3),
                        })
    except (TypeError, ValueError, IndexError):
        logger.debug("Failed to parse phi_k correlation matrix")

    return pairs


def _extract_missingness_groups(df: pd.DataFrame) -> list[list[str]]:
    """Find groups of columns that are null together (co-missing >80%)."""
    null_mask = df.isnull()
    null_cols = [col for col in df.columns if null_mask[col].any()]

    if len(null_cols) < 2:
        return []

    groups: list[list[str]] = []
    visited: set[str] = set()

    for i, col_a in enumerate(null_cols):
        if col_a in visited:
            continue
        group = [col_a]
        mask_a = null_mask[col_a]
        count_a = mask_a.sum()
        if count_a == 0:
            continue

        for col_b in null_cols[i + 1:]:
            if col_b in visited:
                continue
            mask_b = null_mask[col_b]
            both_null = (mask_a & mask_b).sum()
            # co-missing: when A is null, B is also null >80% of the time
            if both_null / count_a > 0.8:
                group.append(col_b)

        if len(group) > 1:
            groups.append(group)
            visited.update(group)

    return groups
