from __future__ import annotations

from api.export import _render_markdown
from core.models import ColumnProfile, TableProfile
from core.scorer import ScoringEngine


def _col(**overrides) -> ColumnProfile:
    base = dict(
        name="x",
        dtype="string",
        null_count=0,
        null_pct=0.0,
        unique_count=10,
        sample_values=["a", "b", "c"],
    )
    base.update(overrides)
    return ColumnProfile(**base)


def _profile(name: str, columns: list[ColumnProfile], **overrides) -> TableProfile:
    base = dict(
        name=name,
        row_count=1000,
        column_count=len(columns),
        duplicate_row_count=0,
        missing_cells_pct=0.0,
        columns=columns,
    )
    base.update(overrides)
    return TableProfile(**base)


def test_markdown_export_shows_governed_and_base_scores_for_gated_results():
    profile = _profile(
        "patients",
        [
            _col(name="id", dtype="int", unique_count=1000, sample_values=["1", "2"]),
            _col(name="email", dtype="string", unique_count=900, sample_values=["a", "b"]),
            _col(name="event_at", dtype="datetime", earliest="2024-01-01", latest="2024-12-31"),
        ],
    )

    assessment = ScoringEngine().score_schema([profile])
    markdown = _render_markdown(assessment)

    assert "**Governed score:**" in markdown
    assert "**Base readiness:**" in markdown
    assert "Governed | Base | Class" in markdown
    assert "blocker cap" in markdown