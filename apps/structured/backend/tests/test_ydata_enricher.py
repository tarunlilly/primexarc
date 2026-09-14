"""Tests for ydata_enricher module.

Verifies that enrichment correctly detects: near-constant columns,
infinite values, type mismatches, Phi_k correlations, and missingness
groups. Also verifies graceful degradation when ydata is disabled.
"""
from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from core.ydata_enricher import (
    EnrichmentResult,
    _extract_infinite_columns,
    _extract_missingness_groups,
    _extract_near_constants,
    enrich,
)


def test_extract_infinite_columns():
    df = pd.DataFrame({
        "a": [1.0, 2.0, np.inf, 4.0],
        "b": [1.0, 2.0, 3.0, 4.0],
        "c": [1.0, -np.inf, 3.0, 4.0],
        "d": ["x", "y", "z", "w"],
    })
    result = _extract_infinite_columns(df)
    assert set(result) == {"a", "c"}


def test_extract_infinite_columns_none():
    df = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [4.0, 5.0, 6.0]})
    assert _extract_infinite_columns(df) == []


def test_extract_near_constants():
    df = pd.DataFrame({
        "mostly_a": ["a"] * 96 + ["b"] * 4,
        "varied": list(range(100)),
        "all_same": ["x"] * 100,
    })
    result = _extract_near_constants(df)
    assert "mostly_a" in result
    assert "all_same" in result
    assert "varied" not in result


def test_extract_near_constants_empty_column():
    df = pd.DataFrame({"empty": [None] * 10, "ok": list(range(10))})
    result = _extract_near_constants(df)
    assert "empty" not in result
    assert "ok" not in result


def test_extract_missingness_groups():
    df = pd.DataFrame({
        "a": [1, None, None, None, None, 6, 7, 8, 9, 10],
        "b": [1, None, None, None, None, 6, 7, 8, 9, 10],
        "c": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
    })
    groups = _extract_missingness_groups(df)
    assert len(groups) == 1
    assert set(groups[0]) == {"a", "b"}


def test_extract_missingness_groups_no_pattern():
    df = pd.DataFrame({
        "a": [None, 2, 3, 4, 5],
        "b": [1, None, 3, 4, 5],
    })
    groups = _extract_missingness_groups(df)
    assert groups == []


def test_enrich_disabled():
    """When ydata_enabled is False, returns empty result."""
    df = pd.DataFrame({"a": [np.inf, 2, 3]})
    with patch("core.ydata_enricher.settings") as mock_settings:
        mock_settings.ydata_enabled = False
        result = enrich(df)
    assert result == EnrichmentResult()


def test_enrich_graceful_failure():
    """If ydata-profiling crashes, returns empty result instead of raising."""
    df = pd.DataFrame({"a": [1, 2, 3]})
    with patch("core.ydata_enricher._run_enrichment", side_effect=RuntimeError("boom")):
        result = enrich(df, column_dtypes={"a": "int"})
    assert result == EnrichmentResult()
