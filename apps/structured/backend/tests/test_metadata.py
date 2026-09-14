"""Phase 2 metadata layer tests.

Tests the parser expansion, reconciler, metadata quality scoring,
entity classification, and no-metadata path.
"""
from __future__ import annotations

import pytest

from core.metadata_parser import MetadataParser, MetadataParseError
from core.models import ColumnProfile, MetadataEntry, MetadataProfile, TableProfile
from core.reconciler import reconcile
from core.scorer import ScoringEngine


def _col(**overrides) -> ColumnProfile:
    base = dict(name="x", dtype="string", null_count=0, null_pct=0.0,
                unique_count=10, sample_values=["a", "b", "c"])
    base.update(overrides)
    return ColumnProfile(**base)


def _profile(name="t1", row_count=2000, columns=None, metadata=None) -> TableProfile:
    cols = columns or [
        _col(name="id", dtype="int", unique_count=2000),
        _col(name="event_at", dtype="datetime"),
    ]
    return TableProfile(
        name=name, row_count=row_count, column_count=len(cols),
        duplicate_row_count=0, missing_cells_pct=0.0, columns=cols,
        metadata_entries=metadata or [],
    )


# ─── Parser tests ─────────────────────────────────────────────────────────

def test_parser_standard_format():
    csv = b"column_name,Definition,Data Type,PII Flag,source\nid,Primary key,integer,N,authored\nemail,User email,varchar,Y,authored\n"
    result = MetadataParser().parse(csv, "standard.csv")
    assert len(result.entries) == 2
    assert result.entries[0].definition == "Primary key"
    assert result.entries[0].data_type_declared == "integer"
    assert result.entries[0].pii_flag == "N"
    assert result.entries[0].source == "authored"
    assert result.entries[1].pii_flag == "Y"


def test_parser_old_format_backwards_compatible():
    csv = b"column_name,description,business_owner\nid,Primary ID,Team A\nname,Full name,Team B\n"
    result = MetadataParser().parse(csv, "old.csv")
    assert len(result.entries) == 2
    assert result.entries[0].description == "Primary ID"
    assert result.entries[0].business_owner == "Team A"
    assert result.entries[0].source == "authored"
    assert "No 'source' column found" in result.parser_notes[0]


def test_parser_preserves_unknown_columns():
    csv = b"column_name,description,custom_field\nid,test,custom_value\n"
    result = MetadataParser().parse(csv, "ext.csv")
    assert "custom_field" in result.unknown_columns
    assert result.entries[0].extensions.get("custom_field") == "custom_value"


def test_parser_fails_without_column_name():
    csv = b"description,business_owner\ntest,owner\n"
    with pytest.raises(MetadataParseError, match="column_name"):
        MetadataParser().parse(csv, "bad.csv")


def test_parser_source_detection():
    csv = b"column_name,source\nid,derived\nemail,system\n"
    result = MetadataParser().parse(csv, "src.csv")
    assert result.entries[0].source == "derived"
    assert result.entries[1].source == "system"


# ─── Reconciler tests ─────────────────────────────────────────────────────

def test_reconciler_type_mismatch():
    profile = _profile(columns=[_col(name="age", dtype="string", unique_count=50)])
    meta = MetadataProfile(
        entries=[MetadataEntry(column_name="age", data_type_declared="integer")],
        total_columns=1, columns_with_metadata=1, coverage_pct=100.0,
    )
    findings = reconcile(profile, meta)
    type_findings = [f for f in findings if f.field == "data_type"]
    assert len(type_findings) == 1
    assert "integer" in type_findings[0].declared
    assert "string" in type_findings[0].observed


def test_reconciler_nullable_contradiction():
    profile = _profile(columns=[_col(name="id", dtype="int", null_count=5, null_pct=2.5)])
    meta = MetadataProfile(
        entries=[MetadataEntry(column_name="id", nullable_declared="N")],
        total_columns=1, columns_with_metadata=1, coverage_pct=100.0,
    )
    findings = reconcile(profile, meta)
    null_findings = [f for f in findings if f.field == "nullable"]
    assert len(null_findings) == 1
    assert "NOT NULL" in null_findings[0].declared


def test_reconciler_pii_contradiction_by_name():
    profile = _profile(columns=[_col(name="email", dtype="string")])
    meta = MetadataProfile(
        entries=[MetadataEntry(column_name="email", pii_flag="N")],
        total_columns=1, columns_with_metadata=1, coverage_pct=100.0,
    )
    findings = reconcile(profile, meta)
    pii_findings = [f for f in findings if f.field == "pii_flag" and f.status == "confirmed"]
    assert len(pii_findings) == 1
    assert "governance contradiction" in pii_findings[0].detail.lower()


def test_reconciler_pii_could_not_verify_when_no_name_match():
    profile = _profile(columns=[_col(name="notes", dtype="string")])
    meta = MetadataProfile(
        entries=[MetadataEntry(column_name="notes", pii_flag="N")],
        total_columns=1, columns_with_metadata=1, coverage_pct=100.0,
    )
    findings = reconcile(profile, meta)
    cnv = [f for f in findings if f.status == "could_not_verify"]
    assert len(cnv) == 1


def test_reconciler_range_inconsistency():
    profile = _profile(columns=[_col(name="score", dtype="int")])
    meta = MetadataProfile(
        entries=[MetadataEntry(column_name="score", valid_values_range="100-0")],
        total_columns=1, columns_with_metadata=1, coverage_pct=100.0,
    )
    findings = reconcile(profile, meta)
    range_f = [f for f in findings if f.field == "valid_values_range"]
    assert len(range_f) == 1
    assert "min" in range_f[0].detail.lower()


def test_reconciler_deterministic():
    profile = _profile(columns=[_col(name="id", dtype="string", null_count=3, null_pct=1.5)])
    meta = MetadataProfile(
        entries=[MetadataEntry(column_name="id", data_type_declared="integer", nullable_declared="N")],
        total_columns=1, columns_with_metadata=1, coverage_pct=100.0,
    )
    run1 = reconcile(profile, meta)
    run2 = reconcile(profile, meta)
    assert [f.model_dump() for f in run1] == [f.model_dump() for f in run2]


# ─── Metadata quality scoring ─────────────────────────────────────────────

def test_metadata_quality_undocumented_without_metadata():
    profile = _profile()
    result = ScoringEngine().score_schema([profile])
    meta_dim = next(d for d in result.tables[0].dimensions if d.id == "metadata")
    meta_check = next(c for c in meta_dim.checks if c.rule_id == "metadata_dictionary")
    assert meta_check.status == "warn"
    assert "undocumented" in meta_check.detail.lower()
    # BOTL: T1 (Physical ID) and O6 (Volume) are always present, so score > 0
    # but still very low (< 10) without any metadata uploaded
    assert meta_dim.score < 10
    assert result.metadata_quality is not None
    assert result.metadata_quality.verdict == "RED"
    assert result.metadata_quality.dimension_score < 10


def test_metadata_dimension_not_inflated_by_snake_case_alone():
    """snake_case naming now lives in Schema — metadata is purely docs quality."""
    profile = _profile(columns=[
        _col(name="order_id", dtype="int", unique_count=2000),
        _col(name="event_at", dtype="datetime"),
    ])
    result = ScoringEngine().score_schema([profile])
    meta_dim = next(d for d in result.tables[0].dimensions if d.id == "metadata")
    # BOTL: without metadata, score is very low (only T1/O6 auto-present)
    assert meta_dim.score < 10


def test_metadata_quality_pass_with_full_governance():
    entries = [
        MetadataEntry(
            column_name="id", definition="Primary key", data_type_declared="int",
            nullable_declared="N", pii_flag="N", consent_basis="analytics",
            ai_ml_usage_approval="approved", business_owner="Team A",
            source_system="ERP", lineage="raw.table",
        ),
        MetadataEntry(
            column_name="event_at", definition="Event timestamp",
            data_type_declared="datetime", nullable_declared="N",
            pii_flag="N", consent_basis="analytics",
            ai_ml_usage_approval="approved", business_owner="Team A",
            last_synced_at="2026-06-01T00:00:00Z",
        ),
    ]
    profile = _profile(metadata=entries)
    result = ScoringEngine().score_schema([profile])
    meta_dim = next(d for d in result.tables[0].dimensions if d.id == "metadata")
    meta_check = next(c for c in meta_dim.checks if c.rule_id == "metadata_dictionary")
    assert meta_check.status == "pass"


def test_metadata_quality_governance_weighted_not_flat():
    """A doc-rich but governance-poor product must score lower than a flat
    average would give it. This validates the governance-weighted rollup."""
    entries = [
        MetadataEntry(
            column_name="id", definition="PK", data_type_declared="int",
            nullable_declared="N", business_owner="Team A",
            source_system="ERP", lineage="raw",
            # NO governance fields: pii_flag, consent_basis, ai_ml_usage_approval
        ),
        MetadataEntry(
            column_name="event_at", definition="Timestamp",
            data_type_declared="datetime", business_owner="Team A",
            source_system="ERP",
        ),
    ]
    profile = _profile(metadata=entries)
    result = ScoringEngine().score_schema([profile])
    meta_check = next(
        c for d in result.tables[0].dimensions if d.id == "metadata"
        for c in d.checks if c.rule_id == "metadata_dictionary"
    )
    # Flat average would be ~75% (3/4 categories present). Governance-weighted
    # should pull it down because governance (40% weight) is 0%.
    assert meta_check.evidence.get("governance") == 0
    assert meta_check.status != "pass"


# ─── Classification tests ─────────────────────────────────────────────────

def test_entity_classification_reference_excludes():
    entries = [MetadataEntry(column_name="code", entity_classification="reference")]
    profile = _profile(name="status_codes", row_count=5000, metadata=entries)
    result = ScoringEngine().score_schema([profile])
    assert result.tables[0].klass == "reference"
    assert result.assessed_count == 0
    assert result.reference_count == 1


def test_row_threshold_heuristic_excludes_small_table():
    profile = _profile(name="lookup", row_count=50)
    result = ScoringEngine().score_schema([profile])
    assert result.tables[0].klass == "reference"


def test_large_table_not_excluded_by_threshold():
    profile = _profile(name="orders", row_count=5000)
    result = ScoringEngine().score_schema([profile])
    assert result.tables[0].klass != "reference"


# ─── No-metadata path ─────────────────────────────────────────────────────

def test_no_metadata_run_completes_with_full_score():
    profile = _profile()
    result = ScoringEngine().score_schema([profile])
    assert 0 <= result.overall_score <= 100
    # No-metadata run emits explicit "could not verify" findings (not empty)
    assert len(result.reconciliation) > 0
    assert all(f.status == "could_not_verify" for f in result.reconciliation)


def test_removing_metadata_only_lowers_metadata_dimension():
    entries = [
        MetadataEntry(
            column_name="id", definition="PK", pii_flag="N",
            consent_basis="ok", ai_ml_usage_approval="yes",
            data_type_declared="int", business_owner="A", source_system="X",
        ),
        MetadataEntry(
            column_name="event_at", definition="TS", pii_flag="N",
            consent_basis="ok", ai_ml_usage_approval="yes",
            data_type_declared="datetime", business_owner="A",
        ),
    ]
    with_meta = ScoringEngine().score_schema([_profile(metadata=entries)])
    without_meta = ScoringEngine().score_schema([_profile()])

    # Non-metadata dimensions should be identical
    for d_with, d_without in zip(with_meta.tables[0].dimensions, without_meta.tables[0].dimensions):
        if d_with.id != "metadata":
            assert d_with.score == d_without.score, f"{d_with.id} score differs"
    with_meta_dim = next(d for d in with_meta.tables[0].dimensions if d.id == "metadata")
    without_meta_dim = next(d for d in without_meta.tables[0].dimensions if d.id == "metadata")
    assert with_meta_dim.score > without_meta_dim.score
