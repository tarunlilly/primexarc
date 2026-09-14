"""Capability measurement — 14 capabilities, each scored 0-4.

Pure function: receives a TableAssessment + TableProfile, returns measurements.
No I/O, no LLM, deterministic. Capabilities are a post-processing consumer of
scoring output — never injected into the scorer itself.

Level semantics:
  0 = Not present / critical failure
  1 = Minimal / detected but insufficient
  2 = Partial / functional but incomplete
  3 = Good / meets standard use-case needs
  4 = Excellent / production-grade, verified

Each capability maps to existing rule checks and profile facts.
"""
from __future__ import annotations

from core.models import (
    CapabilityId,
    CapabilityMeasurement,
    RuleCheck,
    TableAssessment,
    TableProfile,
)


def measure_capabilities(
    table: TableAssessment,
    profile: TableProfile,
) -> list[CapabilityMeasurement]:
    """Measure all 14 capabilities for a single table."""
    checks = _checks_by_rule(table)
    return [
        _measure_sem(checks, profile),
        _measure_join(checks, profile),
        _measure_gov(checks, profile),
        _measure_agg(checks, profile),
        _measure_acc(checks, profile),
        _measure_frs(checks, profile),
        _measure_lbl(checks, profile),
        _measure_lkg(checks, profile),
        _measure_sig(checks, profile),
        _measure_sta(checks, profile),
        _measure_tmp(checks, profile),
        _measure_vol(checks, profile),
        _measure_lin(checks, profile),
        _measure_txt(checks, profile),
    ]


# ── Helpers ──────────────────────────────────────────────────────────────

def _checks_by_rule(table: TableAssessment) -> dict[str, RuleCheck]:
    """Build a rule_id → RuleCheck lookup from all dimensions."""
    out: dict[str, RuleCheck] = {}
    for dim in table.dimensions:
        for c in dim.checks:
            out[c.rule_id] = c
    return out


def _status(checks: dict[str, RuleCheck], rule_id: str) -> str:
    """Get status for a rule, defaulting to 'missing' if not evaluated."""
    c = checks.get(rule_id)
    return c.status if c else "missing"


def _uid(checks: dict[str, RuleCheck], rule_id: str) -> str:
    """Get finding_uid for a rule, empty string if missing."""
    c = checks.get(rule_id)
    return c.finding_uid or "" if c else ""


def _uids_for(checks: dict[str, RuleCheck], *rule_ids: str) -> list[str]:
    """Collect non-empty finding_uids for the given rules."""
    return [_uid(checks, rid) for rid in rule_ids if _uid(checks, rid)]


# ── Capability levelers ──────────────────────────────────────────────────

def _measure_sem(checks: dict, profile: TableProfile) -> CapabilityMeasurement:
    """SEM — Semantic clarity: can a consumer interpret every field?"""
    meta_status = _status(checks, "metadata_dictionary")
    has_metadata = bool(profile.metadata_entries)
    meta_evidence = checks.get("metadata_dictionary")
    weighted_pct = (meta_evidence.evidence.get("weighted_pct", 0)
                    if meta_evidence and meta_evidence.evidence else 0)

    if not has_metadata:
        level = 0
    elif weighted_pct < 40:
        level = 1
    elif weighted_pct < 70:
        level = 2
    elif weighted_pct < 90:
        level = 3
    else:
        level = 4

    return CapabilityMeasurement(
        id="SEM", label="Semantic Clarity",
        level=level,
        evidence=_uids_for(checks, "metadata_dictionary"),
    )


def _measure_join(checks: dict, profile: TableProfile) -> CapabilityMeasurement:
    """JOIN — Joinability: can this table be reliably linked to others?"""
    pk_status = _status(checks, "schema_pk")

    if pk_status == "fail":
        level = 0
    elif pk_status == "warn":
        level = 1
    elif pk_status == "pass":
        # PK exists and is unique — check if multicollinearity flags hint at FK candidates
        if profile.multicollinearity_flags:
            level = 3  # FK candidates detected via correlation
        else:
            level = 2  # PK unique but no FK evidence
    else:
        level = 0

    return CapabilityMeasurement(
        id="JOIN", label="Joinability",
        level=level,
        evidence=_uids_for(checks, "schema_pk"),
    )


def _measure_gov(checks: dict, profile: TableProfile) -> CapabilityMeasurement:
    """GOV — Governance posture: PII handled, consent documented, approved for AI."""
    pii_names = _status(checks, "privacy_column_names")
    pii_values = _status(checks, "privacy_values")
    consent = _status(checks, "privacy_consent")

    if pii_names == "fail":
        level = 0  # Unresolved PII — critical
    elif pii_values == "deferred":
        level = 1  # PII flagged, awaiting attestation
    elif consent == "warn":
        level = 2  # No consent documentation
    elif consent == "pass" and pii_names == "pass":
        # Check for AI/ML usage approval in metadata
        has_approval = any(
            getattr(e, "ai_ml_usage_approval", None)
            for e in profile.metadata_entries
        )
        level = 4 if has_approval else 3
    else:
        level = 2

    return CapabilityMeasurement(
        id="GOV", label="Governance & Compliance",
        level=level,
        evidence=_uids_for(checks, "privacy_column_names", "privacy_values", "privacy_consent"),
    )


def _measure_agg(checks: dict, profile: TableProfile) -> CapabilityMeasurement:
    """AGG — Aggregation safety: can counts/sums be trusted?"""
    dup_status = _status(checks, "quality_duplicates")
    surr_status = _status(checks, "quality_surrogates")

    if dup_status == "fail":
        level = 0
    elif dup_status == "warn" or surr_status == "warn":
        level = 1
    elif dup_status == "pass" and surr_status == "pass":
        pk_status = _status(checks, "schema_pk")
        level = 3 if pk_status == "pass" else 2
    else:
        level = 2

    return CapabilityMeasurement(
        id="AGG", label="Aggregation Safety",
        level=level,
        evidence=_uids_for(checks, "quality_duplicates", "quality_surrogates", "schema_pk"),
    )


def _measure_acc(checks: dict, profile: TableProfile) -> CapabilityMeasurement:
    """ACC — Accessibility: can pipelines consume this reliably?"""
    watermark = _status(checks, "ops_watermark")
    partition = _status(checks, "ops_partition")
    cadence = _status(checks, "ops_cadence")

    passing = sum(1 for s in [watermark, partition, cadence] if s == "pass")
    if passing == 0:
        level = 0
    elif passing == 1:
        level = 1
    elif passing == 2:
        level = 2
    else:
        level = 3

    # Level 4 requires all ops passing + documented SLA
    if level == 3 and cadence == "pass":
        level = 4 if watermark == "pass" else 3

    return CapabilityMeasurement(
        id="ACC", label="Pipeline Accessibility",
        level=level,
        evidence=_uids_for(checks, "ops_watermark", "ops_partition", "ops_cadence"),
    )


def _measure_frs(checks: dict, profile: TableProfile) -> CapabilityMeasurement:
    """FRS — Freshness: is the data current enough?"""
    freshness = _status(checks, "temporal_freshness")
    span = _status(checks, "temporal_range_span")

    if _status(checks, "temporal_present") == "fail":
        level = 0
    elif freshness == "fail":
        level = 1
    elif freshness == "warn":
        level = 2
    elif freshness == "pass" and span == "pass":
        level = 4
    elif freshness == "pass":
        level = 3
    else:
        level = 2

    return CapabilityMeasurement(
        id="FRS", label="Freshness",
        level=level,
        evidence=_uids_for(checks, "temporal_freshness", "temporal_range_span", "temporal_present"),
    )


def _measure_lbl(checks: dict, profile: TableProfile) -> CapabilityMeasurement:
    """LBL — Label availability: is a supervised target present and usable?"""
    target = _status(checks, "labels_target")
    balance = _status(checks, "labels_balance")
    timestamps = _status(checks, "labels_timestamps")

    if target == "fail":
        level = 0
    elif target == "warn":
        level = 1
    elif target == "pass":
        if balance == "pass" and timestamps == "pass":
            level = 4
        elif timestamps == "pass":
            level = 3
        else:
            level = 2
    else:
        level = 0  # Labels dimension may be N/A

    return CapabilityMeasurement(
        id="LBL", label="Label Availability",
        level=level,
        evidence=_uids_for(checks, "labels_target", "labels_balance", "labels_timestamps"),
    )


def _measure_lkg(checks: dict, profile: TableProfile) -> CapabilityMeasurement:
    """LKG — Leakage safety: no post-event features contaminating the target."""
    leakage = _status(checks, "labels_leakage")

    if leakage == "deferred":
        level = 1  # Suspected, awaiting attestation
    elif leakage == "fail":
        level = 0  # Confirmed leakage
    elif leakage == "pass":
        level = 4  # Clean — no suspects
    else:
        level = 3  # Not applicable (no target) — safe by default

    return CapabilityMeasurement(
        id="LKG", label="Leakage Safety",
        level=level,
        evidence=_uids_for(checks, "labels_leakage"),
    )


def _measure_sig(checks: dict, profile: TableProfile) -> CapabilityMeasurement:
    """SIG — Signal quality: are features informative and clean?"""
    near_const = _status(checks, "features_near_constant")
    infinites = _status(checks, "features_infinites")
    cardinality = _status(checks, "features_cardinality")
    numeric = _status(checks, "features_numeric")

    problems = sum(1 for s in [near_const, infinites, cardinality]
                   if s in ("warn", "fail"))
    if problems >= 2:
        level = 0
    elif problems == 1:
        level = 1
    elif numeric == "fail":
        level = 1
    elif numeric == "warn":
        level = 2
    elif numeric == "pass" and near_const == "pass":
        level = 4 if infinites == "pass" else 3
    else:
        level = 3

    return CapabilityMeasurement(
        id="SIG", label="Signal Quality",
        level=level,
        evidence=_uids_for(checks, "features_near_constant", "features_infinites",
                           "features_cardinality", "features_numeric"),
    )


def _measure_sta(checks: dict, profile: TableProfile) -> CapabilityMeasurement:
    """STA — Statistical health: distributions are well-behaved."""
    constants = _status(checks, "stats_no_constants")
    outliers = _status(checks, "stats_outliers")
    multicol = _status(checks, "stats_multicollinearity")

    problems = sum(1 for s in [constants, outliers, multicol]
                   if s in ("warn", "fail"))
    if problems >= 2:
        level = 1
    elif problems == 1:
        level = 2
    elif constants == "pass" and outliers == "pass" and multicol == "pass":
        level = 4
    else:
        level = 3

    return CapabilityMeasurement(
        id="STA", label="Statistical Health",
        level=level,
        evidence=_uids_for(checks, "stats_no_constants", "stats_outliers", "stats_multicollinearity"),
    )


def _measure_tmp(checks: dict, profile: TableProfile) -> CapabilityMeasurement:
    """TMP — Temporal structure: time-based operations are possible."""
    present = _status(checks, "temporal_present")
    ordering = _status(checks, "temporal_ordering")
    granularity = _status(checks, "temporal_granularity")

    if present == "fail":
        level = 0
    elif ordering == "warn":
        level = 1
    elif granularity == "warn":
        level = 2
    elif present == "pass" and ordering == "pass" and granularity == "pass":
        level = 4
    else:
        level = 3

    return CapabilityMeasurement(
        id="TMP", label="Temporal Structure",
        level=level,
        evidence=_uids_for(checks, "temporal_present", "temporal_ordering", "temporal_granularity"),
    )


def _measure_vol(checks: dict, profile: TableProfile) -> CapabilityMeasurement:
    """VOL — Volume adequacy: enough data for the intended use."""
    rowcount = _status(checks, "quality_rowcount")

    if rowcount == "fail":
        level = 0
    elif rowcount == "warn":
        level = 1
    elif rowcount == "pass":
        # More rows = higher confidence
        if profile.row_count >= 10000:
            level = 4
        elif profile.row_count >= 5000:
            level = 3
        else:
            level = 2
    else:
        level = 2  # Not evaluated

    return CapabilityMeasurement(
        id="VOL", label="Volume Adequacy",
        level=level,
        evidence=_uids_for(checks, "quality_rowcount"),
    )


def _measure_lin(checks: dict, profile: TableProfile) -> CapabilityMeasurement:
    """LIN — Lineage clarity: provenance is traceable."""
    # Lineage comes from metadata — check if source_system or lineage fields populated
    has_lineage = any(
        getattr(e, "lineage", None) or getattr(e, "source_system", None)
        for e in profile.metadata_entries
    )
    has_owner = any(
        getattr(e, "business_owner", None) or getattr(e, "data_steward", None)
        for e in profile.metadata_entries
    )

    if not profile.metadata_entries:
        level = 0
    elif not has_lineage and not has_owner:
        level = 1
    elif has_lineage and not has_owner:
        level = 2
    elif has_lineage and has_owner:
        level = 3
    else:
        level = 2

    # Level 4 requires both lineage AND cadence documented
    if level >= 3 and _status(checks, "ops_cadence") == "pass":
        level = 4

    return CapabilityMeasurement(
        id="LIN", label="Lineage & Provenance",
        level=level,
        evidence=_uids_for(checks, "ops_cadence"),
    )


def _measure_txt(checks: dict, profile: TableProfile) -> CapabilityMeasurement:
    """TXT — Text/unstructured readiness: free-text fields are handled."""
    # Check if table has string columns that look like free text (high cardinality)
    text_cols = [
        c for c in profile.columns
        if c.dtype in ("string", "object") and c.unique_count > 50
    ]
    if not text_cols:
        # No free-text columns — capability is N/A, mark as level 3 (not blocking)
        return CapabilityMeasurement(
            id="TXT", label="Text Handling",
            level=3, evidence=[],
        )

    # Has free text — check type consistency
    type_status = _status(checks, "features_type_mismatch")
    missingness = _status(checks, "features_missingness_pattern")

    if type_status == "warn" or missingness == "warn":
        level = 1
    else:
        level = 2  # Free text present, no known issues

    return CapabilityMeasurement(
        id="TXT", label="Text Handling",
        level=level,
        evidence=_uids_for(checks, "features_type_mismatch", "features_missingness_pattern"),
    )
