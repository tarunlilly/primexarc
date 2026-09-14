"""ScoringEngine tests.

The determinism test is the most important one in the entire codebase.
It runs the scorer 20× on the same input and asserts byte-identical output.
If this test ever fails, find and remove the non-determinism (random seeds,
dict ordering, set iteration order) before merging. Never delete this test.
"""
from __future__ import annotations

import pytest

from core.models import ColumnProfile, TableProfile
from core.scorer import GREEN_MIN, YELLOW_MIN, ScoringEngine


def _fixture_profile() -> TableProfile:
    """A representative profile: 1500 rows, 6 string columns, no datetimes —
    above the reference threshold (1000), should land in red/yellow tier."""
    cols = [
        ColumnProfile(name="trust_id", dtype="string",
                      null_count=0, null_pct=0.0, unique_count=1500,
                      sample_values=["T001", "T002", "T003"]),
        ColumnProfile(name="trust_name", dtype="string",
                      null_count=0, null_pct=0.0, unique_count=412,
                      sample_values=["Acme", "Beta", "Gamma"]),
        ColumnProfile(name="priority", dtype="string",
                      null_count=0, null_pct=0.0, unique_count=3,
                      sample_values=["high", "medium", "low"]),
        ColumnProfile(name="formulary_position", dtype="string",
                      null_count=12, null_pct=1.8, unique_count=4,
                      sample_values=["Tier1", "Tier2"]),
        ColumnProfile(name="position", dtype="string",
                      null_count=0, null_pct=0.0, unique_count=5,
                      sample_values=["A", "B", "C"]),
        ColumnProfile(name="indication", dtype="string",
                      null_count=120, null_pct=17.9, unique_count=8,
                      sample_values=["X", "Y"]),
    ]
    return TableProfile(
        name="taltz_trust_segmentation",
        row_count=1500,
        column_count=6,
        duplicate_row_count=0,
        missing_cells_pct=3.3,
        columns=cols,
    )


def test_scorer_is_deterministic():
    """Run the scorer 20× on the same input — every output must be identical.
    This is the bedrock guarantee CLAUDE.md demands."""
    engine = ScoringEngine()
    profile = _fixture_profile()
    runs = [engine.score_schema([profile]).model_dump() for _ in range(20)]
    first = runs[0]
    for i, run in enumerate(runs[1:], start=2):
        assert run == first, f"run {i} differed from run 1 — non-determinism detected"


def test_scorer_classifies_tier_correctly():
    engine = ScoringEngine()
    result = engine.score_schema([_fixture_profile()])
    assert 0 <= result.overall_score <= 100
    if result.overall_score >= GREEN_MIN:
        assert result.tier == "green"
    elif result.overall_score >= YELLOW_MIN:
        assert result.tier == "yellow"
    else:
        assert result.tier == "red"


def test_scorer_returns_all_nine_dimensions():
    engine = ScoringEngine()
    result = engine.score_schema([_fixture_profile()])
    assert len(result.dimensions) == 9
    ids = [d.id for d in result.dimensions]
    assert set(ids) == {
        "schema", "quality", "labels", "temporal", "features",
        "stats", "privacy", "metadata", "ops",
    }


def test_scorer_includes_top_priorities():
    engine = ScoringEngine()
    result = engine.score_schema([_fixture_profile()])
    # The taltz fixture has multiple red dimensions, so we expect priorities
    assert len(result.top_priorities) > 0
    for p in result.top_priorities:
        assert p.severity in ("high", "medium", "low")
        assert p.title  # non-empty


def test_scorer_handles_multiple_tables():
    engine = ScoringEngine()
    p1 = _fixture_profile()
    p2 = _fixture_profile()
    p2.name = "second_table"
    result = engine.score_schema([p1, p2])
    assert result.table_count == 2
    assert len(result.tables) == 2
    assert result.tables[0].table_name != result.tables[1].table_name


def test_scorer_requires_at_least_one_profile():
    engine = ScoringEngine()
    with pytest.raises(ValueError):
        engine.score_schema([])
