"""Phase 3 scorer contract tests.

These lock in the new scoring model: blocker gating, applicability
renormalization, deferred-status routing, and the new tier bands. Each
test targets ONE invariant. If any of these fail, do not merge — they
encode hard guarantees from EXECUTION_PLAN_1.md and CLAUDE.md.
"""
from __future__ import annotations

from core.models import ColumnProfile, TableProfile
from core.scorer import BLOCKER_CAP, GREEN_MIN, YELLOW_MIN, ScoringEngine


def _col(**overrides) -> ColumnProfile:
    base = dict(
        name="x", dtype="string", null_count=0, null_pct=0.0,
        unique_count=10, sample_values=["a", "b", "c"],
    )
    base.update(overrides)
    return ColumnProfile(**base)


def _profile(name: str, columns: list[ColumnProfile], **overrides) -> TableProfile:
    base = dict(
        name=name, row_count=1000, column_count=len(columns),
        duplicate_row_count=0, missing_cells_pct=0.0, columns=columns,
    )
    base.update(overrides)
    return TableProfile(**base)


# ─── Tier bands (Phase 3: ≥80 / 60-79 / <60) ──────────────────────────────

def test_tier_bands_match_phase_3_spec():
    assert GREEN_MIN == 80
    assert YELLOW_MIN == 60
    assert BLOCKER_CAP == 59


# ─── Reproducibility ──────────────────────────────────────────────────────

def test_scorer_reproducible_three_runs():
    """Same input three times → byte-identical SchemaAssessment.

    Critical guarantee: the deterministic core MUST produce a stable result
    regardless of when it runs or how many times. Re-runs of the same data
    in history must compare cleanly.
    """
    profile = _profile("t1", [
        _col(name="id", dtype="int", unique_count=1000, sample_values=["1", "2"]),
        _col(name="target", dtype="int", unique_count=2, sample_values=["0", "1"]),
        _col(name="event_at", dtype="datetime", earliest="2024-01-01", latest="2024-12-31"),
    ])
    engine = ScoringEngine()
    runs = [engine.score_schema([profile]).model_dump() for _ in range(3)]
    assert runs[0] == runs[1] == runs[2]


# ─── Blocker gating ──────────────────────────────────────────────────────

def test_blocker_caps_score_when_pii_column_name_present():
    """Direct PII column name (severity=blocker) → score capped at 59 and
    rule_id appears in gated_by. The whole point of blocker gating is that
    a table with raw PII cannot look "mostly fine" no matter how many
    other checks pass."""
    profile = _profile("patients", [
        _col(name="id", dtype="int", unique_count=1000, sample_values=["1", "2"]),
        # `email` matches PII_NAME_RE → privacy_column_names rule fails as blocker
        _col(name="email", dtype="string", unique_count=900, sample_values=["a", "b"]),
        _col(name="event_at", dtype="datetime", earliest="2024-01-01", latest="2024-12-31"),
    ])
    result = ScoringEngine().score_schema([profile])
    assert result.overall_score <= BLOCKER_CAP
    assert result.base_score is not None
    assert result.base_score > result.overall_score
    assert "privacy_column_names" in result.gated_by
    # Gated tables must always read as red so the FE banner triggers.
    assert result.tier == "red"


def test_no_blocker_means_no_gating():
    """Without a blocker fail, gated_by is empty and the score is uncapped."""
    profile = _profile("clean", [
        _col(name="id", dtype="int", unique_count=1000, sample_values=["1", "2"]),
        _col(name="target", dtype="int", unique_count=2, sample_values=["0", "1"]),
        _col(name="event_at", dtype="datetime", earliest="2024-01-01", latest="2024-12-31"),
        _col(name="created_at", dtype="datetime", earliest="2024-01-01", latest="2024-12-31"),
    ])
    result = ScoringEngine().score_schema([profile])
    assert result.gated_by == []
    assert result.base_score == result.overall_score


# ─── Applicability renormalization ────────────────────────────────────────

def test_no_label_drops_labels_dimension_and_renormalizes():
    """A table with no target column has Labels marked N/A. Its 15% weight
    redistributes across the remaining 8 dimensions; the score is NOT
    penalized for the dropped Labels checks."""
    profile = _profile("no_target", [
        # No TARGET_NAME_RE match, no binary categorical → Labels N/A.
        _col(name="id", dtype="int", unique_count=1000, sample_values=["1", "2"]),
        _col(name="amount", dtype="float", unique_count=900, sample_values=["1.0"]),
        _col(name="event_at", dtype="datetime", earliest="2024-01-01", latest="2024-12-31"),
    ])
    result = ScoringEngine().score_schema([profile])
    # Labels must be marked inactive (weight=0 in the rolled-up view).
    labels_dim = next(d for d in result.dimensions if d.id == "labels")
    assert labels_dim.weight == 0
    # Active dimensions must NOT include labels.
    assert "labels" not in result.active_dimensions
    # The other 8 must all be active.
    assert len(result.active_dimensions) == 8


def test_labels_active_when_target_present():
    profile = _profile("with_target", [
        _col(name="id", dtype="int", unique_count=1000, sample_values=["1"]),
        _col(name="target", dtype="int", unique_count=2, sample_values=["0", "1"]),
        _col(name="event_at", dtype="datetime", earliest="2024-01-01", latest="2024-12-31"),
    ])
    result = ScoringEngine().score_schema([profile])
    assert "labels" in result.active_dimensions


# ─── Deferred (hybrid) routing ────────────────────────────────────────────

def test_pii_pattern_in_samples_is_deferred_not_failed():
    """Hybrid rule: email pattern in sample values → deferred for human
    attestation. Must NOT count as a fail in any dimension's score."""
    profile = _profile("notes_table", [
        _col(name="id", dtype="int", unique_count=1000, sample_values=["1"]),
        _col(name="notes", dtype="string", unique_count=900,
             sample_values=["normal", "user@example.com", "hello"]),
        _col(name="event_at", dtype="datetime", earliest="2024-01-01", latest="2024-12-31"),
    ])
    result = ScoringEngine().score_schema([profile])
    table = result.tables[0]
    # The deferred candidate must surface in TableAssessment.deferred[].
    deferred_ids = {c.rule_id for c in table.deferred}
    assert "privacy_values" in deferred_ids
    # And it MUST NOT appear as a fail in the privacy dimension's checks
    # (the check is rendered as deferred, not fail/warn).
    privacy = next(d for d in table.dimensions if d.id == "privacy")
    privacy_values = next(c for c in privacy.checks if c.rule_id == "privacy_values")
    assert privacy_values.status == "deferred"


def test_target_leakage_candidate_is_deferred():
    """Suspicious post-event-named column alongside target → deferred.

    Note: the suspect column name must NOT itself match TARGET_NAME_RE
    (which would classify it as a target candidate and exclude it from
    the leakage check). `treatment_outcome` ends in `_outcome` →
    POST_EVENT_NAME_RE matches; doesn't start with a target word →
    TARGET_NAME_RE doesn't match.
    """
    profile = _profile("leakage_candidate", [
        _col(name="id", dtype="int", unique_count=1000, sample_values=["1"]),
        _col(name="target", dtype="int", unique_count=2, sample_values=["0", "1"]),
        _col(name="treatment_outcome", dtype="string", unique_count=3,
             sample_values=["good", "bad", "tbd"]),
        _col(name="event_at", dtype="datetime", earliest="2024-01-01", latest="2024-12-31"),
    ])
    result = ScoringEngine().score_schema([profile])
    deferred_ids = {c.rule_id for c in result.tables[0].deferred}
    assert "labels_leakage" in deferred_ids


def test_deferred_checks_carry_severity_and_route():
    """Stamping contract: each RuleCheck must carry severity, executor, route,
    and dimension_id from the rule definition. Downstream consumers (FE,
    advisor, attestation queue) rely on these fields being populated."""
    profile = _profile("notes_table", [
        _col(name="id", dtype="int", unique_count=1000, sample_values=["1"]),
        _col(name="notes", dtype="string", unique_count=900,
             sample_values=["user@example.com"]),
    ])
    result = ScoringEngine().score_schema([profile])
    pii_check = next(c for c in result.tables[0].deferred
                     if c.rule_id == "privacy_values")
    assert pii_check.executor == "hybrid"
    assert pii_check.route == "human_attestation"
    assert pii_check.dimension_id == "privacy"
