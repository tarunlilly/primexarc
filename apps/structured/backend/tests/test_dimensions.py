"""Rule tests.

Strategy: test representative pass/warn/fail paths for high-value rules
explicitly, then a smoke test that every rule returns a well-formed
RuleCheck for a baseline profile. The full pass/fail/warn matrix per
rule (~80 cases) is covered indirectly by the scorer + parser tests.

Rules are accessed through their public IDs in DIMENSIONS — not by
importing the underscore-prefixed functions directly.
"""
from __future__ import annotations

import pytest

from core.dimensions import DIMENSIONS, Rule
from core.models import ColumnProfile, MetadataEntry, RuleCheck, TableProfile


def _rule(rule_id: str) -> Rule:
    for dim in DIMENSIONS:
        for r in dim.rules:
            if r.id == rule_id:
                return r
    raise KeyError(f"rule {rule_id} not in DIMENSIONS")


def _col(name="col", dtype="string", n_rows=100, n_unique=100, n_null=0,
         samples=None, mean=None, std=None, value_pattern_counts=None):
    return ColumnProfile(
        name=name, dtype=dtype,
        null_count=n_null, null_pct=round(n_null / max(n_rows, 1) * 100, 2),
        unique_count=n_unique,
        sample_values=samples or [],
        value_pattern_counts=value_pattern_counts or {},
        mean=mean, std=std,
    )


def _profile(columns, row_count=100, duplicates=0, missing_pct=0.0):
    return TableProfile(
        name="t", row_count=row_count, column_count=len(columns),
        duplicate_row_count=duplicates, missing_cells_pct=missing_pct,
        columns=columns,
    )


# ─── Schema: PK candidate ─────────────────────────────────────────────────

def test_pk_pass_when_unique_no_nulls():
    rule = _rule("schema_pk")
    profile = _profile([_col(name="id", n_rows=100, n_unique=100, n_null=0)])
    result = rule.evaluate(profile)
    assert result.status == "pass"


def test_pk_warn_when_nearly_unique():
    rule = _rule("schema_pk")
    profile = _profile([_col(name="id", n_rows=100, n_unique=99, n_null=0)])
    result = rule.evaluate(profile)
    assert result.status == "warn"


def test_pk_fail_when_no_unique_column():
    rule = _rule("schema_pk")
    profile = _profile([
        _col(name="status", n_rows=100, n_unique=3, n_null=0),
        _col(name="region", n_rows=100, n_unique=5, n_null=2),
    ])
    result = rule.evaluate(profile)
    assert result.status == "fail"
    assert result.recommendation is not None  # must carry remediation


# ─── Labels: target detection ─────────────────────────────────────────────

def test_target_passes_with_conventionally_named_column():
    rule = _rule("labels_target")
    profile = _profile([
        _col(name="id"),
        _col(name="target", n_unique=2),
    ])
    assert rule.evaluate(profile).status == "pass"


def test_target_warns_on_binary_categorical_unnamed():
    rule = _rule("labels_target")
    profile = _profile([
        _col(name="id"),
        _col(name="is_responsive", dtype="string", n_unique=2),
    ])
    assert rule.evaluate(profile).status == "warn"


def test_target_fails_when_no_candidate():
    rule = _rule("labels_target")
    profile = _profile([
        _col(name="name", dtype="string", n_unique=80),
        _col(name="region", dtype="string", n_unique=12),
    ])
    assert rule.evaluate(profile).status == "fail"


# ─── Privacy: PII column-name detection ───────────────────────────────────

@pytest.mark.parametrize(
    "name",
    [
        "email", "ssn", "phone", "first_name", "dob", "patient_id",
        "hcp_name", "provider_name", "physician_name",
    ],
)
def test_pii_column_names_fail_for_known_pii(name):
    rule = _rule("privacy_column_names")
    profile = _profile([_col(name=name, dtype="string")])
    assert rule.evaluate(profile).status == "fail"


def test_pii_column_names_pass_when_clean():
    rule = _rule("privacy_column_names")
    profile = _profile([
        _col(name="trust_id"),
        _col(name="region_code"),
        _col(name="created_at"),
    ])
    assert rule.evaluate(profile).status == "pass"


# ─── Privacy: PII value detection ─────────────────────────────────────────

def test_pii_values_defer_when_email_in_samples():
    # Phase 3: PII pattern matches in sample values are HYBRID candidates —
    # they need human attestation to confirm real-vs-synthetic before being
    # treated as a fail. The rule emits status="deferred", and the scorer
    # routes it into TableAssessment.deferred[] (excluded from scoring).
    rule = _rule("privacy_values")
    profile = _profile([
        _col(name="notes", dtype="string",
             samples=["normal text", "user@example.com", "another"]),
    ])
    assert rule.evaluate(profile).status == "deferred"


def test_pii_values_defer_when_ssn_in_samples():
    rule = _rule("privacy_values")
    profile = _profile([
        _col(name="notes", dtype="string", samples=["123-45-6789"]),
    ])
    assert rule.evaluate(profile).status == "deferred"


def test_pii_values_defer_when_person_names_detected_in_local_scan():
    rule = _rule("privacy_values")
    profile = _profile([
        _col(
            name="notes",
            dtype="string",
            samples=["alpha", "beta", "gamma"],
            value_pattern_counts={"scanned": 100, "person_name": 12},
        ),
    ])
    result = rule.evaluate(profile)
    assert result.status == "deferred"
    assert result.evidence["matched_patterns"] == ["person_name"]


def test_pii_values_pass_when_clean():
    rule = _rule("privacy_values")
    profile = _profile([
        _col(name="notes", dtype="string", samples=["alpha", "beta", "gamma"]),
    ])
    assert rule.evaluate(profile).status == "pass"


# ─── Temporal Integrity ────────────────────────────────────────────────────

def test_temporal_present_passes_with_datetime_column():
    rule = _rule("temporal_present")
    profile = _profile([
        _col(name="id"),
        ColumnProfile(name="event_date", dtype="datetime", null_count=0, null_pct=0,
                      unique_count=50, sample_values=[], earliest="2023-01-01", latest="2024-01-01"),
    ])
    assert rule.evaluate(profile).status == "pass"


def test_temporal_present_fails_without_datetime_column():
    rule = _rule("temporal_present")
    profile = _profile([
        _col(name="id"),
        _col(name="status", dtype="string"),
    ])
    assert rule.evaluate(profile).status == "fail"


def test_temporal_range_span_passes_with_wide_range():
    rule = _rule("temporal_range_span")
    profile = _profile([
        ColumnProfile(name="event_date", dtype="datetime", null_count=0, null_pct=0,
                      unique_count=100, sample_values=[],
                      earliest="2022-01-01", latest="2023-06-01"),
    ])
    assert rule.evaluate(profile).status == "pass"


def test_temporal_range_span_warns_with_narrow_range():
    rule = _rule("temporal_range_span")
    profile = _profile([
        ColumnProfile(name="event_date", dtype="datetime", null_count=0, null_pct=0,
                      unique_count=50, sample_values=[],
                      earliest="2023-01-01", latest="2023-02-15"),
    ])
    assert rule.evaluate(profile).status == "warn"


def test_temporal_range_span_fails_with_very_narrow_range():
    rule = _rule("temporal_range_span")
    profile = _profile([
        ColumnProfile(name="event_date", dtype="datetime", null_count=0, null_pct=0,
                      unique_count=10, sample_values=[],
                      earliest="2023-01-01", latest="2023-01-15"),
    ])
    assert rule.evaluate(profile).status == "fail"


def test_temporal_freshness_passes_when_recent():
    rule = _rule("temporal_freshness")
    profile = _profile([
        ColumnProfile(name="event_date", dtype="datetime", null_count=0, null_pct=0,
                      unique_count=50, sample_values=[],
                      earliest="2023-01-01", latest="2024-01-01",
                      days_since_latest=30),
    ])
    assert rule.evaluate(profile).status == "pass"


def test_temporal_freshness_warns_when_moderately_stale():
    rule = _rule("temporal_freshness")
    profile = _profile([
        ColumnProfile(name="event_date", dtype="datetime", null_count=0, null_pct=0,
                      unique_count=50, sample_values=[],
                      earliest="2023-01-01", latest="2024-01-01",
                      days_since_latest=200),
    ])
    assert rule.evaluate(profile).status == "warn"


def test_temporal_freshness_fails_when_very_stale():
    rule = _rule("temporal_freshness")
    profile = _profile([
        ColumnProfile(name="event_date", dtype="datetime", null_count=0, null_pct=0,
                      unique_count=50, sample_values=[],
                      earliest="2020-01-01", latest="2020-06-01",
                      days_since_latest=1500),
    ])
    assert rule.evaluate(profile).status == "fail"


def test_temporal_ordering_passes_when_consistent():
    rule = _rule("temporal_ordering")
    profile = _profile([
        ColumnProfile(name="created_at", dtype="datetime", null_count=0, null_pct=0,
                      unique_count=50, sample_values=[],
                      earliest="2023-01-01", latest="2023-12-01"),
        ColumnProfile(name="updated_at", dtype="datetime", null_count=0, null_pct=0,
                      unique_count=50, sample_values=[],
                      earliest="2023-01-02", latest="2024-01-01"),
    ])
    assert rule.evaluate(profile).status == "pass"


def test_temporal_ordering_warns_on_violation():
    rule = _rule("temporal_ordering")
    profile = _profile([
        ColumnProfile(name="created_at", dtype="datetime", null_count=0, null_pct=0,
                      unique_count=50, sample_values=[],
                      earliest="2023-06-01", latest="2023-12-01"),
        ColumnProfile(name="updated_at", dtype="datetime", null_count=0, null_pct=0,
                      unique_count=50, sample_values=[],
                      earliest="2023-01-01", latest="2024-01-01"),
    ])
    assert rule.evaluate(profile).status == "warn"


def test_temporal_ordering_passes_with_single_datetime():
    rule = _rule("temporal_ordering")
    profile = _profile([
        ColumnProfile(name="event_date", dtype="datetime", null_count=0, null_pct=0,
                      unique_count=50, sample_values=[],
                      earliest="2023-01-01", latest="2023-12-01"),
    ])
    assert rule.evaluate(profile).status == "pass"


def test_temporal_granularity_passes_when_compatible():
    rule = _rule("temporal_granularity")
    profile = _profile([
        ColumnProfile(name="created_at", dtype="datetime", null_count=0, null_pct=0,
                      unique_count=365, sample_values=[],
                      earliest="2023-01-01", latest="2024-01-01"),
        ColumnProfile(name="updated_at", dtype="datetime", null_count=0, null_pct=0,
                      unique_count=365, sample_values=[],
                      earliest="2023-01-01", latest="2024-01-01"),
    ])
    assert rule.evaluate(profile).status == "pass"


def test_temporal_granularity_warns_on_mismatch():
    rule = _rule("temporal_granularity")
    # One column has per-second granularity, other has monthly
    profile = _profile([
        ColumnProfile(name="event_ts", dtype="datetime", null_count=0, null_pct=0,
                      unique_count=31536000, sample_values=[],
                      earliest="2023-01-01", latest="2024-01-01"),
        ColumnProfile(name="report_month", dtype="datetime", null_count=0, null_pct=0,
                      unique_count=12, sample_values=[],
                      earliest="2023-01-01", latest="2024-01-01"),
    ])
    assert rule.evaluate(profile).status == "warn"


def test_schema_audit_passes_with_dt_aliases_even_before_type_inference():
    rule = _rule("schema_audit")
    profile = _profile([
        _col(name="created_dt", dtype="string"),
        _col(name="updated_dt", dtype="string"),
    ])
    assert rule.evaluate(profile).status == "pass"


def test_pk_candidate_uses_profiled_row_count_when_total_rows_are_larger():
    rule = _rule("schema_pk")
    profile = _profile([_col(name="id", n_rows=10, n_unique=10, n_null=0)], row_count=25_000)
    profile.profiled_row_count = 10

    result = rule.evaluate(profile)

    assert result.status == "pass"


def test_duplicate_rate_uses_profiled_row_count_when_total_rows_are_larger():
    rule = _rule("quality_duplicates")
    profile = _profile([_col(name="id", n_rows=10, n_unique=9)], row_count=25_000, duplicates=2)
    profile.profiled_row_count = 10

    result = rule.evaluate(profile)

    assert result.status == "fail"
    assert "20.00%" in result.detail


# ─── Quality: missing cells ──────────────────────────────────────────────

def test_missing_cells_rule_tiers_correctly():
    rule = _rule("quality_missing")
    cols = [_col(name="x")]
    assert rule.evaluate(_profile(cols, missing_pct=2.0)).status == "pass"
    assert rule.evaluate(_profile(cols, missing_pct=12.0)).status == "warn"
    assert rule.evaluate(_profile(cols, missing_pct=30.0)).status == "fail"


# ─── Smoke test: every rule returns a valid RuleCheck ────────────────────

def test_every_rule_evaluates_cleanly_on_baseline_profile():
    """Hand every rule the same baseline profile and ensure none crash and
    every output is a well-formed RuleCheck. Catches regressions where a
    rule starts raising on edge cases."""
    profile = _profile([
        _col(name="id", n_unique=100),
        _col(name="created_at", dtype="datetime"),
        _col(name="status", dtype="string", n_unique=3),
        _col(name="value", dtype="int", n_unique=80, mean=50.0, std=10.0),
    ])
    for dim in DIMENSIONS:
        for rule in dim.rules:
            result = rule.evaluate(profile)
            assert isinstance(result, RuleCheck), f"{rule.id} returned wrong type"
            assert result.status in ("pass", "warn", "fail")
            assert result.title
            assert result.detail
            if result.status != "pass":
                # Non-passing rules must offer a recommendation
                assert result.recommendation is not None, \
                    f"{rule.id} status={result.status} but no recommendation"


def test_rule_ids_are_unique_across_all_dimensions():
    """Catch copy-paste errors that would break the scorer's check aggregation."""
    seen: set[str] = set()
    for dim in DIMENSIONS:
        for rule in dim.rules:
            assert rule.id not in seen, f"duplicate rule id: {rule.id}"
            seen.add(rule.id)


def test_dimension_weights_sum_to_100():
    """If weights don't sum to 100, the schema overall_score formula is biased."""
    assert sum(d.weight for d in DIMENSIONS) == 100


# ─── Rule explanation validation ──────────────────────────────────────────

def test_all_rules_have_complete_explanations():
    """Every rule in DIMENSIONS must have a non-empty explanation with all
    three fields (what, why, example). This is the fail-loud validation for
    the static rule-pack authoring requirement."""
    from core.dimensions import DIMENSIONS
    for dim in DIMENSIONS:
        for rule in dim.rules:
            assert rule.explanation is not None, f"Rule {rule.id} missing explanation"
            assert rule.explanation.what, f"Rule {rule.id} has empty 'what'"
            assert rule.explanation.why, f"Rule {rule.id} has empty 'why'"
            assert rule.explanation.example, f"Rule {rule.id} has empty 'example'"


# ─── Feature & Signal Readiness: ydata-powered rules ─────────────────────

def test_near_constant_pass_when_empty():
    rule = _rule("features_near_constant")
    profile = _profile([_col(name="x")])
    profile.near_constant_columns = []
    assert rule.evaluate(profile).status == "pass"


def test_near_constant_warn_when_present():
    rule = _rule("features_near_constant")
    profile = _profile([_col(name="x")])
    profile.near_constant_columns = ["status", "country"]
    result = rule.evaluate(profile)
    assert result.status == "warn"
    assert "status" in result.detail


def test_infinites_pass_when_empty():
    rule = _rule("features_infinites")
    profile = _profile([_col(name="x", dtype="float")])
    profile.infinite_columns = []
    assert rule.evaluate(profile).status == "pass"


def test_infinites_warn_when_present():
    rule = _rule("features_infinites")
    profile = _profile([_col(name="x", dtype="float")])
    profile.infinite_columns = ["price_ratio"]
    result = rule.evaluate(profile)
    assert result.status == "warn"
    assert "price_ratio" in result.detail


def test_type_mismatch_pass_when_empty():
    rule = _rule("features_type_mismatch")
    profile = _profile([_col(name="x")])
    profile.type_mismatches = []
    assert rule.evaluate(profile).status == "pass"


def test_type_mismatch_info_when_present():
    rule = _rule("features_type_mismatch")
    profile = _profile([_col(name="x")])
    profile.type_mismatches = [{"column": "user_id", "stored_as": "string", "detected_as": "Numeric"}]
    result = rule.evaluate(profile)
    assert result.status == "warn"
    assert "user_id" in result.detail


def test_missingness_pattern_pass_when_empty():
    rule = _rule("features_missingness_pattern")
    profile = _profile([_col(name="x")])
    profile.missingness_groups = []
    assert rule.evaluate(profile).status == "pass"


def test_missingness_pattern_info_when_groups_found():
    rule = _rule("features_missingness_pattern")
    profile = _profile([_col(name="x")])
    profile.missingness_groups = [["col_a", "col_b", "col_c"]]
    result = rule.evaluate(profile)
    assert result.status == "warn"
    assert "col_a" in result.detail


def test_mixed_correlation_pass_when_empty():
    rule = _rule("features_mixed_correlation")
    profile = _profile([_col(name="x")])
    profile.correlated_pairs_mixed = []
    assert rule.evaluate(profile).status == "pass"


def test_mixed_correlation_info_when_pairs_found():
    rule = _rule("features_mixed_correlation")
    profile = _profile([_col(name="x")])
    profile.correlated_pairs_mixed = [{"column_a": "dept_name", "column_b": "dept_code", "phi_k": 0.95}]
    result = rule.evaluate(profile)
    assert result.status == "warn"
    assert "dept_name" in result.detail


def test_features_dimension_renamed():
    """Verify the features dimension now has the new name."""
    for dim in DIMENSIONS:
        if dim.id == "features":
            assert dim.label == "Feature & Signal Readiness"
            return
    pytest.fail("features dimension not found")


# ─── Operational & Pipeline Readiness ─────────────────────────────────────

def test_ops_stable_names_passes_with_clean_names():
    rule = _rule("ops_stable_names")
    profile = _profile([
        _col(name="patient_id"),
        _col(name="created_at", dtype="datetime"),
        _col(name="status", dtype="string"),
    ])
    assert rule.evaluate(profile).status == "pass"


def test_ops_stable_names_warns_with_tmp_suffix():
    rule = _rule("ops_stable_names")
    profile = _profile([
        _col(name="patient_id"),
        _col(name="score_tmp"),
        _col(name="old_value_bak"),
    ])
    result = rule.evaluate(profile)
    assert result.status == "warn"
    assert "score_tmp" in result.detail


def test_ops_cadence_passes_with_recognized_frequency():
    rule = _rule("ops_cadence")
    profile = _profile([_col(name="x")])
    profile.metadata_entries = [
        MetadataEntry(column_name="x", refresh_frequency="daily"),
    ]
    assert rule.evaluate(profile).status == "pass"


@pytest.mark.parametrize("cadence", ["weekly", "monthly", "hourly", "real-time",
                                      "streaming", "batch", "nightly", "quarterly"])
def test_ops_cadence_passes_various_recognized_terms(cadence):
    rule = _rule("ops_cadence")
    profile = _profile([_col(name="x")])
    profile.metadata_entries = [
        MetadataEntry(column_name="x", refresh_frequency=cadence),
    ]
    assert rule.evaluate(profile).status == "pass"


def test_ops_cadence_warns_with_unrecognized_format():
    rule = _rule("ops_cadence")
    profile = _profile([_col(name="x")])
    profile.metadata_entries = [
        MetadataEntry(column_name="x", refresh_frequency="whenever John feels like it"),
    ]
    result = rule.evaluate(profile)
    assert result.status == "warn"
    assert "not in a recognized format" in result.detail


def test_ops_cadence_warns_when_no_metadata():
    rule = _rule("ops_cadence")
    profile = _profile([_col(name="x")])
    profile.metadata_entries = []
    result = rule.evaluate(profile)
    assert result.status == "warn"
    assert "No refresh cadence" in result.detail


def test_ops_cadence_warns_when_refresh_frequency_empty():
    rule = _rule("ops_cadence")
    profile = _profile([_col(name="x")])
    profile.metadata_entries = [
        MetadataEntry(column_name="x", refresh_frequency=None),
    ]
    assert rule.evaluate(profile).status == "warn"


def test_ops_watermark_passes_with_datetime_watermark():
    rule = _rule("ops_watermark")
    profile = _profile([
        ColumnProfile(name="created_at", dtype="datetime", null_count=0, null_pct=0,
                      unique_count=100, sample_values=[]),
        _col(name="status", dtype="string"),
    ])
    assert rule.evaluate(profile).status == "pass"
    assert "created_at" in rule.evaluate(profile).detail


def test_ops_watermark_passes_with_integer_id():
    rule = _rule("ops_watermark")
    profile = _profile([
        _col(name="id", dtype="int", n_rows=100, n_unique=100, n_null=0),
        _col(name="status", dtype="string"),
    ])
    assert rule.evaluate(profile).status == "pass"
    assert "id" in rule.evaluate(profile).detail


def test_ops_watermark_warns_with_no_candidate():
    rule = _rule("ops_watermark")
    profile = _profile([
        _col(name="region", dtype="string", n_unique=5),
        _col(name="amount", dtype="float", n_unique=80),
    ])
    assert rule.evaluate(profile).status == "warn"


def test_ops_watermark_rejects_high_null_datetime():
    """A datetime column with >1% nulls shouldn't qualify as watermark."""
    rule = _rule("ops_watermark")
    profile = _profile([
        ColumnProfile(name="updated_at", dtype="datetime", null_count=5, null_pct=5.0,
                      unique_count=50, sample_values=[]),
        _col(name="status", dtype="string"),
    ])
    assert rule.evaluate(profile).status == "warn"


def test_ops_partition_passes_for_small_tables():
    rule = _rule("ops_partition")
    profile = _profile([_col(name="x")], row_count=500_000)
    assert rule.evaluate(profile).status == "pass"


def test_ops_partition_defers_for_large_tables():
    rule = _rule("ops_partition")
    profile = _profile([_col(name="x")], row_count=5_000_000)
    result = rule.evaluate(profile)
    assert result.status == "deferred"
    assert "5,000,000" in result.detail


def test_ops_dimension_can_reach_100():
    """Regression: the ops dimension must be able to score 100 (was capped at 75)."""
    rule_cadence = _rule("ops_cadence")
    rule_stable = _rule("ops_stable_names")
    rule_watermark = _rule("ops_watermark")

    profile = _profile([
        _col(name="id", dtype="int", n_rows=100, n_unique=100, n_null=0),
        _col(name="status", dtype="string"),
    ])
    profile.metadata_entries = [
        MetadataEntry(column_name="id", refresh_frequency="daily"),
    ]

    assert rule_stable.evaluate(profile).status == "pass"
    assert rule_cadence.evaluate(profile).status == "pass"
    assert rule_watermark.evaluate(profile).status == "pass"
