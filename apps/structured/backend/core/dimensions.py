"""The 9 AI readiness dimensions and their rules.

Each rule is a pure function: `(TableProfile) -> RuleCheck`. Rules carry their
own recommendation text so the scorer can collect them without needing
the LLM. The LLM advisor (Phase 3) will REFINE these recommendations using
the same rule output — it doesn't replace them.

Source of truth: this file. The frontend's `lib/dimensions.js` is display-only.
Tier thresholds (≥80 green, 60-79 yellow, <60 red) live in `scorer.py`.

Phase 3 additions:
- `Rule.severity` — blocker | warning | info. A `fail` on a `blocker` rule
  caps the overall table score (see `scorer.BLOCKER_CAP`).
- `Rule.executor` — profiler | metadata | hybrid | human. "hybrid" rules
  emit `status="deferred"` checks that route to human attestation in v1
  (and, in v2, to the LLM adjudicator).
- `Rule.hybrid_route` — where the deferred candidate's resolution comes from.
- `Dimension.applicability` — predicate; when False the whole dimension is
  N/A for that table and its weight is redistributed across active dims.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Literal

from core.models import (
    ColumnProfile,
    Executor,
    HybridRoute,
    RuleCheck,
    Severity,
    TableProfile,
)

# Lens tagging: each rule contributes to one or more readiness lenses.
# DQ = Data Quality, ML = ML Readiness, AI = AI Readiness.
Lens = Literal["DQ", "ML", "AI"]


# ───────────────────────────────────────────────────────────────────────────
# Rule infrastructure
# ───────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class RuleExplanation:
    """Plain-language explanation for a non-technical data product owner.
    Static pack data — authored once, identical across runs, zero LLM tokens.
    Never tagged as AI; never generated per run."""
    what: str
    why: str
    example: str


@dataclass(frozen=True)
class Rule:
    """A single check applied to a table profile."""
    id: str
    title: str
    evaluate: Callable[[TableProfile], RuleCheck]
    explanation: RuleExplanation
    severity: Severity = "warning"
    executor: Executor = "profiler"
    hybrid_route: HybridRoute = "human_attestation"
    lens: frozenset[Lens] = field(default_factory=lambda: frozenset({"DQ"}))


def _always_applicable(_: TableProfile) -> bool:
    return True


@dataclass(frozen=True)
class Dimension:
    """One of the 9 readiness dimensions."""
    id: str
    label: str
    weight: int
    rules: tuple[Rule, ...]
    # Predicate gating whether this dimension applies to a given table. When
    # False the whole dimension is dropped and its weight is redistributed.
    applicability: Callable[[TableProfile], bool] = field(
        default=_always_applicable
    )


# ───────────────────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────────────────

# Column-name patterns for heuristic detection
AUDIT_NAME_RE = re.compile(
    r"^(create(?:d)?|update(?:d)?|modif(?:y|ied)|last(?:_.+)?)"
    r"(?:(?:_on|_at|_date|_time|_dt|_ts)|d)?$",
    re.I,
)
TARGET_NAME_RE = re.compile(r"^(label|target|outcome|class|y|status)(_.+)?$", re.I)
PII_NAME_RE = re.compile(
    r"(email|ssn|sin|phone|mobile|address|dob|birth|first_?name|last_?name|"
    r"full_?name|patient_?name|member_?name|employee_?name|contact_?name|"
    r"hcp_?name|provider_?name|prescriber_?name|physician_?name|doctor_?name|"
    r"clinician_?name|mrn|patient_id|insurance|credit_?card|npi)",
    re.I,
)
CONSENT_NAME_RE = re.compile(r"(consent|authorized|opt_?in|gdpr|hipaa)", re.I)
TMP_NAME_RE = re.compile(r"(_tmp$|_temp$|_v\d+$|_old$|_bak$|test_)", re.I)

# Patterns for sample-value scanning (PII detection on values, not names)
EMAIL_VALUE_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
SSN_VALUE_RE = re.compile(r"^\d{3}-\d{2}-\d{4}$")

# Names that suggest a column was populated AFTER the target event — a leakage
# candidate. Profiler surfaces; human attestation confirms.
POST_EVENT_NAME_RE = re.compile(
    r"(_outcome$|_result$|after_|post_|_resolved|_resolution|_followup|_final)",
    re.I,
)


def _numeric(c: ColumnProfile) -> bool:
    return c.dtype in ("int", "float")


def _datetime(c: ColumnProfile) -> bool:
    return c.dtype == "datetime"


def _profiled_rows(p: TableProfile) -> int:
    return p.profiled_row_count or p.row_count


def _matched_pii_value_patterns(c: ColumnProfile) -> list[str]:
    counts = c.value_pattern_counts or {}
    matched = [
        pattern
        for pattern in ("email", "ssn", "person_name")
        if counts.get(pattern, 0) > 0
    ]
    if matched:
        return matched

    fallback: list[str] = []
    for value in c.sample_values:
        if EMAIL_VALUE_RE.search(value) and "email" not in fallback:
            fallback.append("email")
        if SSN_VALUE_RE.search(value) and "ssn" not in fallback:
            fallback.append("ssn")
    return fallback


# ───────────────────────────────────────────────────────────────────────────
# Schema Design & Structure (weight 10)
# ───────────────────────────────────────────────────────────────────────────

def _r_pk_candidate(p: TableProfile) -> RuleCheck:
    rid, title = "schema_pk", "Primary key candidate exists"
    if p.row_count == 0:
        return RuleCheck(rule_id=rid, status="fail", title=title,
                         detail="Table is empty — cannot identify a primary key.",
                         recommendation="Populate the table or document why it is empty.",
                         expected="one unique, non-null key")
    profiled_rows = _profiled_rows(p)
    exact = [c for c in p.columns if c.null_count == 0 and c.unique_count == profiled_rows]
    if exact:
        return RuleCheck(rule_id=rid, status="pass", title=title,
                         detail=f"{exact[0].name}: 0% nulls, 100% unique",
                         expected="one unique, non-null key")
    near = [c for c in p.columns
            if c.null_pct < 1.0 and c.unique_count >= 0.99 * profiled_rows]
    if near:
        return RuleCheck(rule_id=rid, status="warn", title=title,
                         detail=f"{near[0].name} is nearly unique but not strict",
                         recommendation=f"Enforce uniqueness on {near[0].name} or designate a stricter primary key.",
                         expected="one unique, non-null key")
    return RuleCheck(rule_id=rid, status="fail", title=title,
                     detail="No column qualifies as a primary key (100% unique, 0% null).",
                     recommendation="Designate a primary key column with 100% unique values and 0 nulls.",
                     expected="one unique, non-null key")


def _r_audit_columns(p: TableProfile) -> RuleCheck:
    rid, title = "schema_audit", "Audit columns present"
    audit = [c for c in p.columns if AUDIT_NAME_RE.search(c.name) or _datetime(c)]
    if len(audit) >= 2:
        return RuleCheck(rule_id=rid, status="pass", title=title,
                         detail=f"{len(audit)} timestamp/audit columns present",
                         expected="at least 2 audit columns")
    if len(audit) == 1:
        return RuleCheck(rule_id=rid, status="warn", title=title,
                         detail=f"Only {audit[0].name} present — recommend created_at AND updated_at",
                         recommendation="Add a second audit column (e.g. updated_at) for change tracking.",
                         expected="at least 2 audit columns")
    return RuleCheck(rule_id=rid, status="fail", title=title,
                     detail="No created_*/updated_*/modified_* columns found.",
                     recommendation="Add created_at and updated_at columns at the source for lineage.",
                     expected="at least 2 audit columns")


def _r_column_count(p: TableProfile) -> RuleCheck:
    rid, title = "schema_col_count", "Column count reasonable"
    n = p.column_count
    if 5 <= n <= 100:
        return RuleCheck(rule_id=rid, status="pass", title=title,
                         detail=f"{n} columns — within healthy range (5–100)",
                         expected="between 3 and 120")
    if n < 5:
        return RuleCheck(rule_id=rid, status="warn", title=title,
                         detail=f"Only {n} columns — may lack features for modelling",
                         recommendation="Consider whether additional context columns could be joined in.",
                         expected="between 3 and 120")
    return RuleCheck(rule_id=rid, status="warn", title=title,
                     detail=f"{n} columns — high; consider splitting into related tables",
                     recommendation="Wide tables often hide multiple entities. Review normalization.",
                     expected="between 3 and 120")


# ───────────────────────────────────────────────────────────────────────────
# Data Quality & Completeness (weight 20)
# ───────────────────────────────────────────────────────────────────────────

def _r_row_count(p: TableProfile) -> RuleCheck:
    rid, title = "quality_rowcount", "Row count adequate for modelling"
    if p.row_count >= 1000:
        return RuleCheck(rule_id=rid, status="pass", title=title,
                         detail=f"{p.row_count:,} rows",
                         expected="at least 1,000 rows")
    if p.row_count >= 100:
        return RuleCheck(rule_id=rid, status="warn", title=title,
                         detail=f"Only {p.row_count:,} rows — limited modelling power",
                         recommendation="Aim for at least 1,000 rows; consider augmenting with related data.",
                         expected="at least 1,000 rows")
    return RuleCheck(rule_id=rid, status="fail", title=title,
                     detail=f"Only {p.row_count:,} rows — insufficient for most ML",
                     recommendation="Collect more data before pursuing model training.",
                     expected="at least 1,000 rows")


def _r_missing_cells(p: TableProfile) -> RuleCheck:
    rid, title = "quality_missing", "Missing-cell rate"
    pct = p.missing_cells_pct
    if pct < 5:
        return RuleCheck(rule_id=rid, status="pass", title=title,
                         detail=f"{pct:.1f}% missing cells overall",
                         expected="at most 5%")
    if pct < 20:
        return RuleCheck(rule_id=rid, status="warn", title=title,
                         detail=f"{pct:.1f}% missing cells — investigate cause",
                         recommendation="Identify which columns drive the missingness; decide impute vs drop strategy.",
                         expected="at most 5%")
    return RuleCheck(rule_id=rid, status="fail", title=title,
                     detail=f"{pct:.1f}% missing cells — severe gaps",
                     recommendation="Diagnose data pipeline before relying on this dataset for AI.",
                     expected="at most 5%")


def _r_duplicates(p: TableProfile) -> RuleCheck:
    rid, title = "quality_duplicates", "Duplicate row check"
    if p.duplicate_row_count == 0:
        return RuleCheck(rule_id=rid, status="pass", title=title,
                         detail="No exact duplicate rows",
                         expected="at most 0.5%")
    dup_pct = (p.duplicate_row_count / max(_profiled_rows(p), 1)) * 100
    if dup_pct < 1:
        return RuleCheck(rule_id=rid, status="warn", title=title,
                         detail=f"{p.duplicate_row_count} duplicate rows ({dup_pct:.2f}%)",
                         recommendation="Deduplicate before training; investigate whether duplicates are intentional.",
                         expected="at most 0.5%")
    return RuleCheck(rule_id=rid, status="fail", title=title,
                     detail=f"{p.duplicate_row_count} duplicate rows ({dup_pct:.2f}%) — significant",
                     recommendation="Dedupe at source; high duplication suggests pipeline replays or join explosion.",
                     expected="at most 0.5%")


def _r_column_nulls(p: TableProfile) -> RuleCheck:
    rid, title = "quality_col_nulls", "No column exceeds 50% nulls"
    bad = [c for c in p.columns if c.null_pct > 50]
    if not bad:
        return RuleCheck(rule_id=rid, status="pass", title=title,
                         detail="All columns under 50% null",
                         expected="no column exceeds 50% null")
    if len(bad) <= 2:
        return RuleCheck(rule_id=rid, status="warn", title=title,
                         detail=f"{len(bad)} columns >50% null: {', '.join(c.name for c in bad)}",
                         recommendation="Decide whether sparse columns add value or should be dropped.",
                         evidence={"candidates": [c.name for c in bad]},
                         expected="no column exceeds 50% null")
    return RuleCheck(rule_id=rid, status="fail", title=title,
                     detail=f"{len(bad)} columns >50% null — too many to be useful as features",
                     recommendation="Drop or impute the heavily-null columns before any modelling.",
                     evidence={"candidates": [c.name for c in bad]},
                     expected="no column exceeds 50% null")


def _r_surrogate_nulls(p: TableProfile) -> RuleCheck:
    rid, title = "quality_surrogates", "No surrogate null values"
    flagged = [(c.name, c.surrogate_null_count) for c in p.columns if c.surrogate_null_count > 0]
    if not flagged:
        return RuleCheck(rule_id=rid, status="pass", title=title,
                         detail="No sentinel placeholder values detected (e.g. -1, 999, 'N/A').",
                         expected="none")
    names = [f"{n} ({cnt})" for n, cnt in flagged[:4]]
    return RuleCheck(rule_id=rid, status="warn", title=title,
                     detail=f"Surrogate null values detected in {len(flagged)} column(s): {', '.join(names)}",
                     recommendation="Replace placeholder sentinels (-1, 999, 'N/A') with real NULLs so missing-data handling works correctly.",
                     evidence={"columns": [n for n, _ in flagged]},
                     expected="none")


# ───────────────────────────────────────────────────────────────────────────
# Labels, Targets & Ground Truth (weight 15)
# ───────────────────────────────────────────────────────────────────────────

def _r_target_column(p: TableProfile) -> RuleCheck:
    rid, title = "labels_target", "Target column identifiable"
    targets = [c for c in p.columns if TARGET_NAME_RE.match(c.name) and not _datetime(c)]
    if targets:
        return RuleCheck(rule_id=rid, status="pass", title=title,
                         detail=f"Target candidate found: {targets[0].name}",
                         expected="a defined outcome field")
    # Binary categorical with healthy population could be a target
    binary = [c for c in p.columns
              if c.unique_count == 2 and c.null_pct < 10 and not _numeric(c)]
    if binary:
        return RuleCheck(rule_id=rid, status="warn", title=title,
                         detail=f"Possible binary target column: {binary[0].name} — not named conventionally",
                         recommendation="Rename target columns to standard names (target / label / outcome) and document.",
                         expected="a defined outcome field")
    return RuleCheck(rule_id=rid, status="fail", title=title,
                     detail="No column identifiable as a prediction target.",
                     recommendation="Define and document a target column with explicit naming.",
                     expected="a defined outcome field")


def _r_class_balance(p: TableProfile) -> RuleCheck:
    rid, title = "labels_balance", "Target class balance"
    targets = [c for c in p.columns if TARGET_NAME_RE.match(c.name) and not _datetime(c)]
    if not targets:
        return RuleCheck(rule_id=rid, status="warn", title=title,
                         detail="No target column identified — class balance cannot be assessed.",
                         recommendation="Define a target column to enable class balance analysis.",
                         expected="at least ~100 rows per class")
    t = targets[0]
    if t.unique_count < 2:
        return RuleCheck(rule_id=rid, status="fail", title=title,
                         detail=f"Target {t.name} has only {t.unique_count} unique value(s)",
                         recommendation="A target needs at least 2 classes — collect more diverse labels.",
                         expected="at least ~100 rows per class")
    # Without the actual class distribution we can only flag for review
    return RuleCheck(rule_id=rid, status="warn", title=title,
                     detail=f"Target {t.name} has {t.unique_count} classes — verify minority class is ≥5%",
                     recommendation="Compute class proportions; minority class below 5% needs resampling strategy.",
                     expected="at least ~100 rows per class")


def _r_outcome_timestamps(p: TableProfile) -> RuleCheck:
    rid, title = "labels_timestamps", "Outcome timestamps present"
    if any(_datetime(c) for c in p.columns):
        return RuleCheck(rule_id=rid, status="pass", title=title,
                         detail="Datetime columns present — outcomes can be time-aligned",
                         expected="outcome timestamps present")
    return RuleCheck(rule_id=rid, status="fail", title=title,
                     detail="No timestamp columns — cannot place outcomes in time.",
                     recommendation="Capture the date each outcome was observed for temporal validation.",
                     expected="outcome timestamps present")


# ───────────────────────────────────────────────────────────────────────────
# Temporal Integrity (weight 15)
# ───────────────────────────────────────────────────────────────────────────

# Heuristic patterns for created/updated column detection
_CREATED_RE = re.compile(r"(creat|insert|open|start|register)", re.I)
_UPDATED_RE = re.compile(r"(updat|modif|chang|edit|last_)", re.I)


def _r_has_datetime(p: TableProfile) -> RuleCheck:
    """At least one datetime column exists (foundational gate)."""
    rid, title = "temporal_present", "Datetime columns present"
    dts = [c for c in p.columns if _datetime(c)]
    if dts:
        return RuleCheck(rule_id=rid, status="pass", title=title,
                         detail=f"{len(dts)} datetime column(s) present: "
                                f"{', '.join(c.name for c in dts[:3])}",
                         expected="at least 1 datetime column")
    return RuleCheck(rule_id=rid, status="fail", title=title,
                     detail="No datetime columns detected.",
                     recommendation="Add at minimum: record_created_at, event_date. "
                     "Without timestamps, temporal train/test splits and trend detection are impossible.",
                     expected="at least 1 datetime column")


def _r_temporal_range_span(p: TableProfile) -> RuleCheck:
    """Date range spans enough history for meaningful modeling."""
    from datetime import datetime as dt_cls

    from config import settings

    rid, title = "temporal_range_span", "Date range covers sufficient history"
    dts = [c for c in p.columns if _datetime(c) and c.earliest and c.latest]
    if not dts:
        return RuleCheck(rule_id=rid, status="fail", title=title,
                         detail="No datetime columns with range information available.",
                         recommendation="Populate datetime columns with actual values so temporal span can be assessed.",
                         expected="at least 30 days")

    # Find the widest span across all datetime columns
    max_span_days = 0
    best_col = dts[0]
    for col in dts:
        try:
            earliest_dt = dt_cls.fromisoformat(
                col.earliest.replace(" ", "T").split("+")[0].split("Z")[0])
            latest_dt = dt_cls.fromisoformat(
                col.latest.replace(" ", "T").split("+")[0].split("Z")[0])
            span = (latest_dt - earliest_dt).days
            if span > max_span_days:
                max_span_days = span
                best_col = col
        except (ValueError, TypeError):
            continue

    if max_span_days == 0:
        return RuleCheck(rule_id=rid, status="warn", title=title,
                         detail="Could not compute date span from available datetime columns.",
                         recommendation="Verify datetime columns contain valid, parseable date values.",
                         expected="at least 30 days")

    if max_span_days >= settings.temporal_min_span_pass_days:
        return RuleCheck(rule_id=rid, status="pass", title=title,
                         detail=f"{best_col.name} spans {max_span_days} days "
                                f"({best_col.earliest} to {best_col.latest})",
                         expected="at least 30 days")
    if max_span_days >= settings.temporal_min_span_warn_days:
        return RuleCheck(rule_id=rid, status="warn", title=title,
                         detail=f"{best_col.name} spans only {max_span_days} days -- "
                                f"may not capture seasonality or long-term trends",
                         recommendation=f"Aim for at least {settings.temporal_min_span_pass_days} days of history. "
                                        f"Current span ({max_span_days} days) may miss seasonal patterns.",
                         expected="at least 30 days")
    return RuleCheck(rule_id=rid, status="fail", title=title,
                     detail=f"{best_col.name} spans only {max_span_days} days -- "
                            f"insufficient for most time-dependent ML tasks",
                     recommendation=f"Collect at least {settings.temporal_min_span_warn_days} days of history. "
                                    f"Short windows prevent temporal validation and seasonality detection.",
                     expected="at least 30 days")


def _r_temporal_freshness(p: TableProfile) -> RuleCheck:
    """Most recent data is recent enough for modeling."""
    from config import settings

    rid, title = "temporal_freshness", "Data is recent enough for modeling"
    dts = [c for c in p.columns if _datetime(c) and c.days_since_latest is not None]
    if not dts:
        return RuleCheck(rule_id=rid, status="warn", title=title,
                         detail="No datetime freshness information available.",
                         recommendation="Ensure datetime columns are populated so data freshness can be assessed.",
                         expected="within 90 days")

    # Use the MINIMUM days_since_latest (the freshest column)
    freshest = min(dts, key=lambda c: c.days_since_latest)
    days_old = freshest.days_since_latest

    if days_old <= settings.temporal_freshness_pass_days:
        return RuleCheck(rule_id=rid, status="pass", title=title,
                         detail=f"Most recent data in {freshest.name} is {days_old} days old",
                         expected="within 90 days")
    if days_old <= settings.temporal_freshness_warn_days:
        return RuleCheck(rule_id=rid, status="warn", title=title,
                         detail=f"Most recent data in {freshest.name} is {days_old} days old -- "
                                f"may be growing stale for active modeling",
                         recommendation=f"Data older than {settings.temporal_freshness_pass_days} days may not reflect "
                                        f"current patterns. Verify refresh pipeline is active.",
                         expected="within 90 days")
    return RuleCheck(rule_id=rid, status="fail", title=title,
                     detail=f"Most recent data in {freshest.name} is {days_old} days old -- "
                            f"likely too stale for production modeling",
                     recommendation=f"Data over {settings.temporal_freshness_warn_days} days old is unlikely to "
                                    f"represent current conditions. Re-extract or confirm this is intentionally historical.",
                     expected="within 90 days")


def _r_temporal_ordering(p: TableProfile) -> RuleCheck:
    """Temporal columns with created/updated semantics are logically ordered."""
    from datetime import datetime as dt_cls

    rid, title = "temporal_ordering", "Temporal columns are logically ordered"
    dt_cols = [c for c in p.columns if _datetime(c) and c.earliest and c.latest]

    created_cols = [c for c in dt_cols if _CREATED_RE.search(c.name)]
    updated_cols = [c for c in dt_cols if _UPDATED_RE.search(c.name)]

    if not created_cols or not updated_cols:
        return RuleCheck(rule_id=rid, status="pass", title=title,
                         detail="No created/updated column pair detected -- ordering check not applicable.",
                         expected="updated_at >= created_at")

    violations: list[str] = []
    for created in created_cols:
        for updated in updated_cols:
            try:
                created_earliest = dt_cls.fromisoformat(
                    created.earliest.replace(" ", "T").split("+")[0].split("Z")[0])
                updated_earliest = dt_cls.fromisoformat(
                    updated.earliest.replace(" ", "T").split("+")[0].split("Z")[0])
                if updated_earliest < created_earliest:
                    violations.append(
                        f"{updated.name} earliest ({updated.earliest}) < "
                        f"{created.name} earliest ({created.earliest})")
            except (ValueError, TypeError):
                continue

    if not violations:
        return RuleCheck(rule_id=rid, status="pass", title=title,
                         detail=f"Created/updated ordering is consistent "
                                f"({created_cols[0].name} vs {updated_cols[0].name})",
                         expected="updated_at >= created_at")
    return RuleCheck(rule_id=rid, status="warn", title=title,
                     detail=f"Temporal ordering violation: {violations[0]}",
                     recommendation="Updated/modified timestamps should never precede created timestamps. "
                     "Investigate data pipeline for backdated inserts or clock skew.",
                     expected="updated_at >= created_at")


def _r_temporal_granularity(p: TableProfile) -> RuleCheck:
    """Datetime columns have compatible granularity."""
    from datetime import datetime as dt_cls

    rid, title = "temporal_granularity", "Datetime granularity is consistent"
    dt_cols = [c for c in p.columns if _datetime(c) and c.earliest and c.latest and c.unique_count > 1]

    if len(dt_cols) < 2:
        return RuleCheck(rule_id=rid, status="pass", title=title,
                         detail="Fewer than 2 datetime columns -- granularity consistency not applicable.",
                         expected="compatible granularity")

    granularities: list[tuple[str, float]] = []
    for col in dt_cols:
        try:
            earliest_dt = dt_cls.fromisoformat(
                col.earliest.replace(" ", "T").split("+")[0].split("Z")[0])
            latest_dt = dt_cls.fromisoformat(
                col.latest.replace(" ", "T").split("+")[0].split("Z")[0])
            span_seconds = (latest_dt - earliest_dt).total_seconds()
            if span_seconds > 0 and col.unique_count > 1:
                avg_interval = span_seconds / (col.unique_count - 1)
                granularities.append((col.name, avg_interval))
        except (ValueError, TypeError):
            continue

    if len(granularities) < 2:
        return RuleCheck(rule_id=rid, status="pass", title=title,
                         detail="Could not compute granularity for comparison.",
                         expected="compatible granularity")

    intervals = [g[1] for g in granularities]
    min_interval = min(intervals)
    max_interval = max(intervals)

    if min_interval <= 0:
        return RuleCheck(rule_id=rid, status="pass", title=title,
                         detail="Granularity calculation inconclusive -- skipping.",
                         expected="compatible granularity")

    ratio = max_interval / min_interval

    if ratio <= 100:
        labels = [(name, _granularity_label(secs)) for name, secs in granularities]
        return RuleCheck(rule_id=rid, status="pass", title=title,
                         detail=f"Datetime granularities are compatible: "
                                f"{', '.join(f'{n} (~{lbl})' for n, lbl in labels[:3])}",
                         expected="compatible granularity")
    fine_col = min(granularities, key=lambda g: g[1])
    coarse_col = max(granularities, key=lambda g: g[1])
    return RuleCheck(rule_id=rid, status="warn", title=title,
                     detail=f"Granularity mismatch: {fine_col[0]} (~{_granularity_label(fine_col[1])}) "
                            f"vs {coarse_col[0]} (~{_granularity_label(coarse_col[1])})",
                     recommendation="When joining tables or building features across these columns, "
                     "align granularities explicitly (e.g., truncate timestamps to daily).",
                     expected="compatible granularity")


def _granularity_label(avg_seconds: float) -> str:
    """Human-readable label for an average interval in seconds."""
    if avg_seconds < 60:
        return "sub-minute"
    if avg_seconds < 3600:
        return "minutes"
    if avg_seconds < 86400:
        return "hours"
    if avg_seconds < 604800:
        return "days"
    if avg_seconds < 2592000:
        return "weeks"
    return "months+"


# ───────────────────────────────────────────────────────────────────────────
# ───────────────────────────────────────────────────────────────────────────
# Feature & Signal Readiness (weight 10)
# ───────────────────────────────────────────────────────────────────────────

def _r_cardinality(p: TableProfile) -> RuleCheck:
    rid, title = "features_cardinality", "Categorical cardinality healthy"
    cat = [c for c in p.columns if c.dtype in ("string", "object", "bool")]
    if not cat:
        return RuleCheck(rule_id=rid, status="pass", title=title,
                         detail="No categorical columns — cardinality not applicable",
                         expected="2–500 unique per categorical")
    profiled_rows = _profiled_rows(p)
    high = [c for c in cat if c.unique_count > 50 and c.unique_count > 0.5 * profiled_rows]
    if not high:
        return RuleCheck(rule_id=rid, status="pass", title=title,
                         detail=f"All {len(cat)} categoricals under 50 distinct values or low-cardinality",
                         expected="2–500 unique per categorical")
    if len(high) == 1:
        return RuleCheck(rule_id=rid, status="warn", title=title,
                         detail=f"{high[0].name} has {high[0].unique_count} unique values",
                         recommendation=f"Choose an encoding for {high[0].name}: target encoding, embedding, or drop.",
                         evidence={"candidates": [c.name for c in high]},
                         expected="2–500 unique per categorical")
    return RuleCheck(rule_id=rid, status="fail", title=title,
                     detail=f"{len(high)} high-cardinality columns",
                     recommendation="High cardinality cripples most models — engineer encodings or drop.",
                     evidence={"candidates": [c.name for c in high]},
                     expected="2–500 unique per categorical")


def _r_numeric_features(p: TableProfile) -> RuleCheck:
    rid, title = "features_numeric", "Numeric features available"
    nums = [c for c in p.columns if _numeric(c)]
    if len(nums) >= 3:
        return RuleCheck(rule_id=rid, status="pass", title=title,
                         detail=f"{len(nums)} numeric column(s)",
                         expected="at least 1 numeric feature")
    if len(nums) >= 1:
        return RuleCheck(rule_id=rid, status="warn", title=title,
                         detail=f"Only {len(nums)} numeric column(s) — limits model choice",
                         recommendation="Engineer numeric features (counts, ratios, durations) from existing fields.",
                         expected="at least 1 numeric feature")
    return RuleCheck(rule_id=rid, status="fail", title=title,
                     detail="No numeric columns — purely categorical datasets limit model variety.",
                     recommendation="Engineer at least one numeric feature for model variety.",
                     expected="at least 1 numeric feature")


def _r_near_constant(p: TableProfile) -> RuleCheck:
    rid, title = "features_near_constant", "No near-constant columns"
    if not p.near_constant_columns:
        return RuleCheck(rule_id=rid, status="pass", title=title,
                         detail="All columns have meaningful value diversity",
                         expected="no near-constant columns")
    names = p.near_constant_columns[:5]
    return RuleCheck(rule_id=rid, status="warn", title=title,
                     detail=f"{len(p.near_constant_columns)} column(s) dominated by a single value (>95%): {', '.join(names)}",
                     recommendation="Near-constant columns carry almost zero predictive signal. Consider dropping or investigating.",
                     evidence={"candidates": p.near_constant_columns},
                     expected="no near-constant columns")


def _r_infinites(p: TableProfile) -> RuleCheck:
    rid, title = "features_infinites", "No infinite values"
    if not p.infinite_columns:
        return RuleCheck(rule_id=rid, status="pass", title=title,
                         detail="No columns contain inf/-inf values",
                         expected="no infinite values")
    names = p.infinite_columns[:5]
    return RuleCheck(rule_id=rid, status="warn", title=title,
                     detail=f"{len(p.infinite_columns)} column(s) contain infinite values: {', '.join(names)}",
                     recommendation="Infinite values break most ML models silently. Replace with NaN or cap at a domain maximum.",
                     evidence={"candidates": p.infinite_columns},
                     expected="no infinite values")


def _r_type_mismatch(p: TableProfile) -> RuleCheck:
    rid, title = "features_type_mismatch", "Storage types match semantic types"
    if not p.type_mismatches:
        return RuleCheck(rule_id=rid, status="pass", title=title,
                         detail="Column dtypes align with detected semantic types",
                         expected="inferred type matches declared")
    examples = p.type_mismatches[:3]
    detail_parts = [f"{m['column']} (stored as {m['stored_as']}, detected as {m['detected_as']})" for m in examples]
    return RuleCheck(rule_id=rid, status="warn", title=title,
                     detail=f"Type mismatches: {'; '.join(detail_parts)}",
                     recommendation="Columns with mismatched types may be engineered incorrectly. Cast to the correct type upstream.",
                     evidence={"mismatches": p.type_mismatches},
                     expected="inferred type matches declared")


def _r_missingness_pattern(p: TableProfile) -> RuleCheck:
    rid, title = "features_missingness_pattern", "No structured missingness"
    if not p.missingness_groups:
        return RuleCheck(rule_id=rid, status="pass", title=title,
                         detail="Missing values do not cluster across columns",
                         expected="no systematic gaps")
    groups_str = "; ".join([", ".join(g[:3]) + ("..." if len(g) > 3 else "") for g in p.missingness_groups[:2]])
    return RuleCheck(rule_id=rid, status="warn", title=title,
                     detail=f"Columns missing together: [{groups_str}]",
                     recommendation="Structured missingness usually signals a failed JOIN or optional data block. Imputation won't fix it -- investigate the pipeline.",
                     evidence={"groups": p.missingness_groups},
                     expected="no systematic gaps")


def _r_mixed_correlation(p: TableProfile) -> RuleCheck:
    rid, title = "features_mixed_correlation", "No categorical multicollinearity"
    if not p.correlated_pairs_mixed:
        return RuleCheck(rule_id=rid, status="pass", title=title,
                         detail="No highly correlated mixed-type pairs detected")
    pairs = p.correlated_pairs_mixed[:3]
    detail_parts = [f"{pr['column_a']} ~ {pr['column_b']} (Phi_k={pr['phi_k']})" for pr in pairs]
    return RuleCheck(rule_id=rid, status="warn", title=title,
                     detail=f"Correlated pairs: {'; '.join(detail_parts)}",
                     recommendation="Redundant categorical columns inflate dimensionality without adding signal. Drop one of each correlated pair.",
                     evidence={"pairs": p.correlated_pairs_mixed})


# ───────────────────────────────────────────────────────────────────────────
# Statistical Properties (weight 10)
# ───────────────────────────────────────────────────────────────────────────

def _r_no_constants(p: TableProfile) -> RuleCheck:
    rid, title = "stats_no_constants", "No constant columns"
    consts = [c for c in p.columns
              if c.unique_count <= 1 and p.row_count > 1
              and not AUDIT_NAME_RE.search(c.name)]
    if not consts:
        return RuleCheck(rule_id=rid, status="pass", title=title,
                         detail="All columns vary",
                         expected="no zero-variance columns")
    return RuleCheck(rule_id=rid, status="warn", title=title,
                     detail=f"{len(consts)} constant column(s): {', '.join(c.name for c in consts[:3])}",
                     recommendation="Drop or investigate constant columns — they carry zero signal.",
                     evidence={"candidates": [c.name for c in consts]},
                     expected="no zero-variance columns")


def _r_outlier_aware(p: TableProfile) -> RuleCheck:
    rid, title = "stats_outliers", "Numeric outlier exposure"
    nums = [c for c in p.columns if _numeric(c) and c.std is not None and c.mean is not None]
    if not nums:
        return RuleCheck(rule_id=rid, status="warn", title=title,
                         detail="No numeric columns — outlier policy not applicable",
                         recommendation="Establish outlier-handling once numeric features are introduced.",
                         expected="outlier-aware distributions")
    # Heuristic: large std relative to |mean| suggests heavy tails / outliers
    heavy = [c for c in nums if c.mean is not None and c.std is not None
             and abs(c.mean) > 0 and c.std > 3 * abs(c.mean)]
    if not heavy:
        return RuleCheck(rule_id=rid, status="pass", title=title,
                         detail=f"{len(nums)} numeric column(s); spread within expected range",
                         expected="outlier-aware distributions")
    return RuleCheck(rule_id=rid, status="warn", title=title,
                     detail=f"{len(heavy)} numeric column(s) show heavy spread — likely outliers",
                     recommendation="Document an outlier policy (cap, remove, or model explicitly).",
                     expected="outlier-aware distributions")


def _r_distribution_baseline(p: TableProfile) -> RuleCheck:
    rid, title = "stats_baseline", "Distribution baselines documented"
    # In Phase 2 (profile-only), we don't have a stored baseline. Always warn
    # until metadata integration lands.
    return RuleCheck(rule_id=rid, status="warn", title=title,
                     detail="No stored baseline — drift cannot be detected over time.",
                     recommendation="Generate distribution baselines and classify null mechanism.")


def _r_multicollinearity(p: TableProfile) -> RuleCheck:
    rid, title = "stats_multicollinearity", "No highly correlated feature pairs"
    flags = p.multicollinearity_flags
    if not flags:
        return RuleCheck(rule_id=rid, status="pass", title=title,
                         detail="No numeric column pairs with |r| >= 0.95.",
                         expected="no redundant collinear pairs")
    pairs = [f"{f['col_a']} ↔ {f['col_b']} ({f['abs_r']})" for f in flags[:3]]
    return RuleCheck(rule_id=rid, status="warn", title=title,
                     detail=f"{len(flags)} highly correlated pair(s): {'; '.join(pairs)}",
                     recommendation="Drop one column from each correlated pair or use PCA — redundant features inflate variance without adding signal.",
                     evidence={"pairs": flags},
                     expected="no redundant collinear pairs")


# ───────────────────────────────────────────────────────────────────────────
# Privacy, Compliance & Ethics (weight 10)
# ───────────────────────────────────────────────────────────────────────────

def _r_pii_column_names(p: TableProfile) -> RuleCheck:
    rid, title = "privacy_column_names", "No obvious PII column names"
    hits = [c.name for c in p.columns if PII_NAME_RE.search(c.name)]
    if not hits:
        return RuleCheck(rule_id=rid, status="pass", title=title,
                         detail="No direct PII column names detected",
                         expected="none")
    return RuleCheck(rule_id=rid, status="fail", title=title,
                     detail=f"PII-like columns: {', '.join(hits[:3])}",
                     recommendation="Pseudonymize or hash direct identifiers before ML use.",
                     evidence={"candidates": hits},
                     expected="none")


def _r_pii_values(p: TableProfile) -> RuleCheck:
    rid, title = "privacy_values", "No PII patterns in sample values"
    # Hybrid rule: regex-matched email/SSN samples are PII candidates that need
    # human confirmation before we declare the column tainted. The candidate
    # is deferred to attestation; v2 will route to the LLM adjudicator instead.
    # Only scan string/object columns — numeric and datetime values produce
    # false positives (e.g. a quantity matching a phone-number regex).
    for c in p.columns:
        if c.dtype not in ("string", "object"):
            continue
        matched_patterns = _matched_pii_value_patterns(c)
        if matched_patterns:
            return RuleCheck(
                rule_id=rid, status="deferred", title=title,
                detail=f"Possible PII in {c.name} based on a bounded local value scan — needs human confirmation.",
                recommendation="A human must confirm whether the detected values are real PII or synthetic. If real, strip or hash at source.",
                evidence={
                    "column": c.name,
                    "matched_patterns": matched_patterns,
                    "scanned_values": (c.value_pattern_counts or {}).get("scanned", len(c.sample_values)),
                },
                expected="no PII patterns detected",
            )
    return RuleCheck(rule_id=rid, status="pass", title=title,
                     detail="No PII patterns matched in sampled values",
                     expected="no PII patterns detected")


def _r_target_leakage(p: TableProfile) -> RuleCheck:
    """Hybrid rule — flag columns whose names suggest post-event population
    when a target column also exists. Profiler surfaces candidates; humans
    confirm they aren't legitimate features. Blocker if confirmed leakage."""
    rid, title = "labels_leakage", "No suspected target leakage"
    targets = [c for c in p.columns if TARGET_NAME_RE.match(c.name) and not _datetime(c)]
    if not targets:
        return RuleCheck(rule_id=rid, status="pass", title=title,
                         detail="No target column — leakage analysis not applicable.",
                         expected="no post-event features")
    suspects = [c.name for c in p.columns
                if POST_EVENT_NAME_RE.search(c.name)
                and not TARGET_NAME_RE.match(c.name)]
    if not suspects:
        return RuleCheck(rule_id=rid, status="pass", title=title,
                         detail="No post-event-named features detected alongside the target.",
                         expected="no post-event features")
    return RuleCheck(
        rule_id=rid, status="deferred", title=title,
        detail=f"Suspected leakage candidates: {', '.join(suspects[:3])} — names suggest post-event population.",
        recommendation="A human must confirm whether each candidate is computed before or after the target event. Drop or document any post-event features.",
        evidence={"candidates": suspects, "target": targets[0].name},
        expected="no post-event features",
    )


def _r_consent_metadata(p: TableProfile) -> RuleCheck:
    rid, title = "privacy_consent", "Consent metadata present"
    if any(CONSENT_NAME_RE.search(c.name) for c in p.columns):
        return RuleCheck(rule_id=rid, status="pass", title=title,
                         detail="Consent / authorization column present",
                         expected="documented")
    return RuleCheck(rule_id=rid, status="warn", title=title,
                     detail="No consent/authorization column found.",
                     recommendation="Attach a data-use scope to the dataset (analytics vs model-training).",
                     expected="documented")


# ───────────────────────────────────────────────────────────────────────────
# Metadata & Documentation (weight 5)
# ───────────────────────────────────────────────────────────────────────────

def _r_column_naming(p: TableProfile) -> RuleCheck:
    rid, title = "schema_naming", "Column names follow conventions"
    bad = [c.name for c in p.columns if not re.match(r"^[a-z][a-z0-9_]*$", c.name)]
    if not bad:
        return RuleCheck(rule_id=rid, status="pass", title=title,
                         detail="All column names follow snake_case",
                         expected="at least 90% consistent")
    if len(bad) <= 2:
        return RuleCheck(rule_id=rid, status="warn", title=title,
                         detail=f"{len(bad)} non-conforming column name(s): {', '.join(bad[:2])}",
                         recommendation="Rename columns to snake_case for consistency.",
                         evidence={"candidates": bad},
                         expected="at least 90% consistent")
    return RuleCheck(rule_id=rid, status="fail", title=title,
                     detail=f"{len(bad)} columns violate snake_case convention",
                     recommendation="Adopt a column naming convention (snake_case) across the schema.",
                     evidence={"candidates": bad},
                     expected="at least 90% consistent")


def _r_dictionary_present(p: TableProfile) -> RuleCheck:
    """Metadata & Docs quality scoring — governance-weighted.

    Formula (from metadata_layer.md §2.2):
      weighted_coverage = 0.40*Governance + 0.25*Technical + 0.20*Operational + 0.15*Business
      dimension_score = round(0.7 * weighted_coverage + 0.3 * reconciliation_accuracy)

    When no metadata is uploaded: returns "undocumented" (warn, not fail).
    """
    rid, title = "metadata_dictionary", "Metadata quality"

    if not p.metadata_entries:
        return RuleCheck(
            rule_id=rid, status="warn", title=title,
            detail="Undocumented — no data dictionary uploaded. Coverage cannot be assessed.",
            recommendation="Upload a data dictionary to enable metadata quality scoring.",
            evidence={"status": "undocumented"},
            expected="at least 80%",
        )

    entries = p.metadata_entries
    total = len(entries)
    if total == 0:
        return RuleCheck(
            rule_id=rid, status="warn", title=title,
            detail="Metadata file empty — no column entries found.",
            recommendation="Ensure the data dictionary has at least one row per column.",
            expected="at least 80%",
        )

    # Business: definition, usage_context, grain
    biz_score = sum(
        1 for e in entries
        if any(getattr(e, f, None) for f in ("definition", "description", "usage_context", "grain"))
    ) / total

    # Technical: data_type_declared, nullable_declared, valid_values_range, primary_foreign_key, cardinality_declared
    tech_score = sum(
        1 for e in entries
        if any(getattr(e, f, None) for f in ("data_type_declared", "nullable_declared", "valid_values_range"))
    ) / total

    # Operational: business_owner/data_steward, last_synced_at, lineage, source_system
    ops_score = sum(
        1 for e in entries
        if any(getattr(e, f, None) for f in ("business_owner", "data_steward", "last_synced_at", "lineage", "source_system"))
    ) / total

    # Governance: pii_flag, pii_category, security_classification, consent_basis, ai_ml_usage_approval, protected_attribute
    gov_score = sum(
        1 for e in entries
        if any(getattr(e, f, None) for f in ("pii_flag", "pii_category", "security_classification", "consent_basis", "ai_ml_usage_approval", "protected_attribute"))
    ) / total

    from config import settings
    weighted = (
        settings.metadata_weight_governance * gov_score
        + settings.metadata_weight_technical * tech_score
        + settings.metadata_weight_operational * ops_score
        + settings.metadata_weight_business * biz_score
    )
    # Reconciliation accuracy not available at the rule level (it runs
    # separately in the scorer). Use weighted_coverage alone here; the
    # scorer can adjust the final dimension score with reconciliation data.
    pct = round(weighted * 100)

    if pct >= 80:
        return RuleCheck(
            rule_id=rid, status="pass", title=title,
            detail=f"Metadata coverage: {pct}% (Gov {gov_score:.0%}, Tech {tech_score:.0%}, Ops {ops_score:.0%}, Biz {biz_score:.0%}).",
            evidence={"weighted_pct": pct, "governance": round(gov_score * 100), "technical": round(tech_score * 100), "operational": round(ops_score * 100), "business": round(biz_score * 100)},
            expected="at least 80%",
        )
    if pct >= 40:
        return RuleCheck(
            rule_id=rid, status="warn", title=title,
            detail=f"Partial metadata: {pct}% weighted coverage. Governance ({gov_score:.0%}) is the heaviest weight.",
            recommendation="Improve governance metadata (PII flags, consent, AI-usage approval) for the biggest score lift.",
            evidence={"weighted_pct": pct, "governance": round(gov_score * 100), "technical": round(tech_score * 100), "operational": round(ops_score * 100), "business": round(biz_score * 100)},
            expected="at least 80%",
        )
    return RuleCheck(
        rule_id=rid, status="fail", title=title,
        detail=f"Sparse metadata: {pct}% weighted coverage. Governance metadata is critically absent.",
        recommendation="Add PII classification, consent basis, and AI/ML usage approval to your data dictionary.",
        evidence={"weighted_pct": pct, "governance": round(gov_score * 100), "technical": round(tech_score * 100), "operational": round(ops_score * 100), "business": round(biz_score * 100)},
        expected="at least 80%",
    )


# ───────────────────────────────────────────────────────────────────────────
# Operational & Pipeline Readiness (weight 5)
# ───────────────────────────────────────────────────────────────────────────

def _r_stable_names(p: TableProfile) -> RuleCheck:
    rid, title = "ops_stable_names", "No transient column names"
    tmp = [c.name for c in p.columns if TMP_NAME_RE.search(c.name)]
    if not tmp:
        return RuleCheck(rule_id=rid, status="pass", title=title,
                         detail="No temporary or versioned column names detected",
                         expected="no temp/versioned names")
    return RuleCheck(rule_id=rid, status="warn", title=title,
                     detail=f"Transient names: {', '.join(tmp[:3])}",
                     recommendation="Rename _tmp / _v2 / _old columns before production handoff.",
                     expected="no temp/versioned names")


_CADENCE_RE = re.compile(
    r"(daily|weekly|monthly|hourly|real[- ]?time|streaming|batch|"
    r"every\s+\d+\s+(hour|minute|day|week)s?|"
    r"\d+x?\s*/?\s*(day|week|month|hour)|"
    r"cron|scheduled|nightly|bi-?weekly|quarterly|annual)",
    re.I,
)

_WATERMARK_NAME_RE = re.compile(
    r"(^(id|pk)$|_id$|_seq$|sequence$|batch_id|load_date|etl_|"
    r"insert(ed)?_(at|date|ts|time)|load(ed)?_(at|date|ts|time)|"
    r"ingestion_(date|time|ts)|created_(at|date|ts|time)|"
    r"updated_(at|date|ts|time)|modified_(at|date|ts|time))",
    re.I,
)


def _r_refresh_cadence(p: TableProfile) -> RuleCheck:
    """Check whether refresh cadence is documented via metadata dictionary."""
    rid, title = "ops_cadence", "Refresh cadence documented"
    entries = getattr(p, "metadata_entries", None) or []
    # Collect non-empty refresh_frequency values
    cadences = [
        e.refresh_frequency
        for e in entries
        if getattr(e, "refresh_frequency", None)
    ]
    if not cadences:
        return RuleCheck(rule_id=rid, status="warn", title=title,
                         detail="No refresh cadence documented in metadata.",
                         recommendation="Document refresh cadence and SLA in the data catalogue "
                                        "(e.g. 'daily', 'hourly', 'weekly').",
                         expected="documented refresh")
    # Take the first non-empty value (table-level metadata repeated per column)
    value = cadences[0].strip()
    if _CADENCE_RE.search(value):
        return RuleCheck(rule_id=rid, status="pass", title=title,
                         detail=f"Refresh cadence documented: '{value}'",
                         expected="documented refresh")
    return RuleCheck(rule_id=rid, status="warn", title=title,
                     detail=f"Refresh cadence documented ('{value}') but not in a recognized format.",
                     recommendation="Use a standard term: daily, weekly, monthly, hourly, "
                                    "streaming, batch, quarterly, or 'every N hours/days'.",
                     expected="documented refresh")


def _r_watermark_candidate(p: TableProfile) -> RuleCheck:
    """Detect columns suitable as a watermark for incremental loading."""
    rid, title = "ops_watermark", "Incremental load capability"
    for c in p.columns:
        if not _WATERMARK_NAME_RE.search(c.name):
            continue
        # Datetime watermark: named appropriately and mostly non-null
        if _datetime(c) and c.null_pct < 1:
            return RuleCheck(rule_id=rid, status="pass", title=title,
                             detail=f"Incremental load candidate: {c.name} (datetime, <1% null)",
                             expected="identified")
        # Integer watermark: named appropriately, unique, non-null
        if _numeric(c) and c.null_pct == 0:
            effective_rows = p.profiled_row_count or p.row_count or 0
            if effective_rows > 0:
                uniqueness = c.unique_count / effective_rows
                if uniqueness >= 0.99:
                    return RuleCheck(rule_id=rid, status="pass", title=title,
                                     detail=f"Incremental load candidate: {c.name} "
                                            f"(numeric, unique, non-null)",
                                     expected="identified")
    return RuleCheck(rule_id=rid, status="warn", title=title,
                     detail="No obvious watermark column for incremental loading.",
                     recommendation="Add a monotonically increasing column (created_at, load_date, "
                                    "or auto-increment id) to enable incremental pipeline loads.",
                     expected="identified")


def _r_partition_strategy(p: TableProfile) -> RuleCheck:
    """Hybrid rule — for large tables, surface a deferred attestation on
    whether a partition strategy is defined. Small tables pass automatically."""
    rid, title = "ops_partition", "Partition strategy defined"
    row_count = p.row_count or p.profiled_row_count or 0
    if row_count < 1_000_000:
        return RuleCheck(rule_id=rid, status="pass", title=title,
                         detail=f"Table has {row_count:,} rows — partitioning not critical at this scale.",
                         expected="documented strategy")
    return RuleCheck(
        rule_id=rid, status="deferred", title=title,
        detail=f"Table has {row_count:,} rows. At this volume, a partition strategy "
               f"is important for efficient pipeline reads.",
        recommendation="Confirm a partition strategy is defined (e.g. by date, region, or logical key). "
                       "Without partitioning, full-table scans on large datasets degrade pipeline performance.",
        evidence={"row_count": row_count},
        expected="documented strategy",
    )


# ───────────────────────────────────────────────────────────────────────────
# Applicability predicates
# ───────────────────────────────────────────────────────────────────────────

def _has_target_or_binary(p: TableProfile) -> bool:
    """Labels dimension applies when there's either a named target column or
    a plausible binary categorical that could be one. Otherwise the table
    isn't a supervised-learning candidate and Labels weight redistributes."""
    if any(TARGET_NAME_RE.match(c.name) and not _datetime(c) for c in p.columns):
        return True
    return any(
        c.unique_count == 2 and c.null_pct < 10 and not _numeric(c)
        for c in p.columns
    )


# ───────────────────────────────────────────────────────────────────────────
# v3 new rules (check catalog expansion)
# ───────────────────────────────────────────────────────────────────────────

def _r_pk_uniqueness(p: TableProfile) -> RuleCheck:
    """Verified primary key uniqueness (stricter than schema_pk candidate check)."""
    rid, title = "quality_pk_uniqueness", "Primary key verified unique"
    profiled_rows = _profiled_rows(p)
    exact = [c for c in p.columns if c.null_count == 0 and c.unique_count == profiled_rows]
    if exact:
        return RuleCheck(rule_id=rid, status="pass", title=title,
                         detail=f"{exact[0].name}: verified 100% unique across {profiled_rows:,} rows",
                         expected="100% unique on key")
    # Check if any candidate is >99.9% unique (near-PK)
    near = [c for c in p.columns if c.null_count == 0 and c.unique_count >= 0.999 * profiled_rows]
    if near:
        dup = profiled_rows - near[0].unique_count
        return RuleCheck(rule_id=rid, status="warn", title=title,
                         detail=f"{near[0].name}: {dup} duplicate(s) in {profiled_rows:,} rows",
                         recommendation="Investigate and deduplicate the PK column.",
                         expected="100% unique on key")
    return RuleCheck(rule_id=rid, status="fail", title=title,
                     detail="No column achieves >99.9% uniqueness with 0% nulls.",
                     recommendation="Ensure a true primary key exists with guaranteed uniqueness.",
                     expected="100% unique on key")


def _r_type_consistency(p: TableProfile) -> RuleCheck:
    """Check that declared types in metadata match observed profiled types."""
    rid, title = "quality_type_consistency", "Types consistent with metadata"
    if not p.metadata_entries:
        return RuleCheck(rule_id=rid, status="pass", title=title,
                         detail="No metadata — type consistency not assessable (pass by default).",
                         expected="types match metadata")
    mismatches = []
    for entry in p.metadata_entries:
        if not entry.data_type_declared:
            continue
        col = next((c for c in p.columns if c.name == entry.column_name), None)
        if not col:
            continue
        declared = entry.data_type_declared.lower().strip()
        observed = col.dtype
        # Simple type family check
        if declared in ("int", "integer", "bigint", "smallint") and observed not in ("int", "float"):
            mismatches.append(entry.column_name)
        elif declared in ("float", "double", "decimal", "numeric", "real") and observed != "float":
            mismatches.append(entry.column_name)
        elif declared in ("date", "datetime", "timestamp", "timestamptz") and observed != "datetime":
            mismatches.append(entry.column_name)
    if not mismatches:
        return RuleCheck(rule_id=rid, status="pass", title=title,
                         detail="All declared types consistent with observed.",
                         expected="types match metadata")
    return RuleCheck(rule_id=rid, status="warn", title=title,
                     detail=f"{len(mismatches)} type inconsistency(ies): {', '.join(mismatches[:3])}",
                     recommendation="Correct metadata declarations or cast columns to match.",
                     evidence={"candidates": mismatches},
                     expected="types match metadata")


def _r_class_absolute(p: TableProfile) -> RuleCheck:
    """Absolute minimum row count per class (not just ratio)."""
    rid, title = "labels_class_absolute", "Minimum rows per class"
    targets = [c for c in p.columns if TARGET_NAME_RE.match(c.name) and not _datetime(c)]
    if not targets:
        return RuleCheck(rule_id=rid, status="pass", title=title,
                         detail="No target column — class count not applicable.")
    t = targets[0]
    if t.unique_count < 2:
        return RuleCheck(rule_id=rid, status="fail", title=title,
                         detail=f"Target {t.name} has only {t.unique_count} class(es).",
                         recommendation="A target needs at least 2 classes with sufficient rows each.")
    # Estimate minimum class size: total_rows / unique_count gives average
    avg_per_class = p.row_count / max(t.unique_count, 1)
    if avg_per_class >= 100:
        return RuleCheck(rule_id=rid, status="pass", title=title,
                         detail=f"~{avg_per_class:.0f} rows per class on average (≥100 minimum)")
    if avg_per_class >= 30:
        return RuleCheck(rule_id=rid, status="warn", title=title,
                         detail=f"~{avg_per_class:.0f} rows per class — borderline for reliable training",
                         recommendation="Aim for ≥100 rows per class. Consider collecting more labeled data.")
    return RuleCheck(rule_id=rid, status="fail", title=title,
                     detail=f"~{avg_per_class:.0f} rows per class — too few for reliable ML",
                     recommendation="Collect more labeled data or combine rare classes.")


def _r_k_anonymity(p: TableProfile) -> RuleCheck:
    """Small-group disclosure risk — quasi-identifier combinations may be unique."""
    rid, title = "privacy_k_anonymity", "No small-group disclosure risk"
    # Heuristic: if multiple low-cardinality columns exist whose product of
    # distinct values exceeds row count, individuals may be identifiable.
    quasi_ids = [c for c in p.columns
                 if c.dtype in ("string", "object") and 2 <= c.unique_count <= 50
                 and not PII_NAME_RE.search(c.name)]
    if len(quasi_ids) < 2:
        return RuleCheck(rule_id=rid, status="pass", title=title,
                         detail="Insufficient quasi-identifiers for combination risk.")
    # Take top 3 by cardinality and multiply
    sorted_qi = sorted(quasi_ids, key=lambda c: c.unique_count, reverse=True)[:3]
    product = 1
    for c in sorted_qi:
        product *= c.unique_count
    if product > p.row_count * 2:
        return RuleCheck(rule_id=rid, status="warn", title=title,
                         detail=f"Quasi-identifier combination ({', '.join(c.name for c in sorted_qi)}) "
                                f"may identify individuals (product={product:,} vs {p.row_count:,} rows)",
                         recommendation="Consider suppression or generalization of quasi-identifiers.",
                         evidence={"candidates": [c.name for c in sorted_qi]})
    return RuleCheck(rule_id=rid, status="pass", title=title,
                     detail="Quasi-identifier combinations unlikely to identify individuals.")


def _r_outlier_skew(p: TableProfile) -> RuleCheck:
    """Flag extreme skewness (|skew| > 3) which indicates heavy-tailed distributions."""
    rid, title = "stats_outlier_skew", "No extreme skewness"
    nums = [c for c in p.columns if _numeric(c) and c.skew is not None]
    if not nums:
        return RuleCheck(rule_id=rid, status="pass", title=title,
                         detail="No numeric columns with skewness data.")
    skewed = [c for c in nums if abs(c.skew) > 3]
    if not skewed:
        return RuleCheck(rule_id=rid, status="pass", title=title,
                         detail=f"All {len(nums)} numeric columns have |skew| ≤ 3.")
    names = [f"{c.name} (skew={c.skew:.1f})" for c in skewed[:3]]
    return RuleCheck(rule_id=rid, status="warn", title=title,
                     detail=f"Extreme skew in {len(skewed)} column(s): {', '.join(names)}",
                     recommendation="Consider log-transform or winsorization for heavily skewed features.",
                     evidence={"candidates": [c.name for c in skewed]})


def _r_watermark_monotonic(p: TableProfile) -> RuleCheck:
    """Verify watermark candidate is monotonically increasing (not just present)."""
    rid, title = "ops_watermark_monotonic", "Watermark is monotonic"
    # Find datetime watermark candidates
    from core.dimensions import _WATERMARK_NAME_RE
    candidates = [c for c in p.columns
                  if _WATERMARK_NAME_RE.search(c.name) and _datetime(c) and c.null_pct < 1]
    if not candidates:
        return RuleCheck(rule_id=rid, status="warn", title=title,
                         detail="No watermark candidate column found.",
                         recommendation="Add a monotonically increasing timestamp for incremental loads.")
    # Heuristic: if unique_count == profiled_row_count, it's likely monotonic
    wm = candidates[0]
    profiled = _profiled_rows(p)
    if wm.unique_count >= 0.95 * profiled:
        return RuleCheck(rule_id=rid, status="pass", title=title,
                         detail=f"{wm.name}: {wm.unique_count}/{profiled} unique — likely monotonic")
    return RuleCheck(rule_id=rid, status="warn", title=title,
                     detail=f"{wm.name}: only {wm.unique_count}/{profiled} unique — may have duplicates",
                     recommendation="Verify monotonicity; duplicate timestamps prevent reliable incremental loads.")


def _r_metadata_recon_rate(p: TableProfile) -> RuleCheck:
    """Metadata reconciliation rate — how much of metadata aligns with observed data."""
    rid, title = "metadata_recon_rate", "Metadata reconciliation rate"
    if not p.metadata_entries:
        return RuleCheck(rule_id=rid, status="warn", title=title,
                         detail="No metadata — reconciliation not possible.",
                         recommendation="Upload a data dictionary to enable reconciliation checking.",
                         expected="types reconciled")
    # Check how many metadata columns actually match table columns
    table_cols = {c.name for c in p.columns}
    matched = sum(1 for e in p.metadata_entries if e.column_name in table_cols)
    total = len(p.metadata_entries)
    rate = matched / total if total else 0
    if rate >= 0.95:
        return RuleCheck(rule_id=rid, status="pass", title=title,
                         detail=f"{matched}/{total} metadata entries match table columns ({rate:.0%}).",
                         expected="types reconciled")
    if rate >= 0.70:
        return RuleCheck(rule_id=rid, status="warn", title=title,
                         detail=f"Only {matched}/{total} metadata entries match ({rate:.0%}).",
                         recommendation="Update metadata dictionary — some entries reference columns not in the table.",
                         expected="types reconciled")
    return RuleCheck(rule_id=rid, status="fail", title=title,
                     detail=f"Only {matched}/{total} metadata entries match ({rate:.0%}) — dictionary is stale.",
                     recommendation="Re-generate or update the data dictionary to match the current schema.",
                     expected="types reconciled")


def _r_consent_approval(p: TableProfile) -> RuleCheck:
    """Check AI/ML usage approval field in metadata."""
    rid, title = "metadata_consent_approval", "AI/ML usage approved"
    if not p.metadata_entries:
        return RuleCheck(rule_id=rid, status="warn", title=title,
                         detail="No metadata — AI/ML usage approval unknown.",
                         recommendation="Document AI/ML usage approval in the data dictionary.")
    approved = [e for e in p.metadata_entries if getattr(e, "ai_ml_usage_approval", None)]
    if approved:
        vals = {e.ai_ml_usage_approval.lower().strip() for e in approved}
        if vals & {"approved", "yes", "y", "true"}:
            return RuleCheck(rule_id=rid, status="pass", title=title,
                             detail="AI/ML usage explicitly approved in metadata.")
        if vals & {"denied", "no", "n", "false", "restricted"}:
            return RuleCheck(rule_id=rid, status="fail", title=title,
                             detail="AI/ML usage explicitly DENIED in metadata.",
                             recommendation="Obtain approval before using this data for AI/ML purposes.")
    return RuleCheck(rule_id=rid, status="warn", title=title,
                     detail="AI/ML usage approval not documented.",
                     recommendation="Add ai_ml_usage_approval field to metadata.")


def _r_doc_coverage(p: TableProfile) -> RuleCheck:
    """Fraction of columns that have ANY metadata entry."""
    rid, title = "metadata_doc_coverage", "Column documentation coverage"
    if not p.metadata_entries:
        return RuleCheck(rule_id=rid, status="fail", title=title,
                         detail="0% columns documented — no data dictionary.",
                         recommendation="Upload a data dictionary covering all columns.",
                         expected="at least 80% columns documented")
    documented = {e.column_name for e in p.metadata_entries}
    total = p.column_count
    coverage = len(documented) / total if total else 0
    if coverage >= 0.90:
        return RuleCheck(rule_id=rid, status="pass", title=title,
                         detail=f"{len(documented)}/{total} columns documented ({coverage:.0%}).",
                         expected="at least 80% columns documented")
    if coverage >= 0.50:
        return RuleCheck(rule_id=rid, status="warn", title=title,
                         detail=f"Only {len(documented)}/{total} columns documented ({coverage:.0%}).",
                         recommendation="Add metadata entries for undocumented columns.",
                         expected="at least 80% columns documented")
    return RuleCheck(rule_id=rid, status="fail", title=title,
                     detail=f"Only {len(documented)}/{total} columns documented ({coverage:.0%}).",
                     recommendation="Most columns lack documentation — critical for AI consumers.",
                     expected="at least 80% columns documented")


# ───────────────────────────────────────────────────────────────────────────
# Dimension registry
# ───────────────────────────────────────────────────────────────────────────

DIMENSIONS: tuple[Dimension, ...] = (
    Dimension("schema", "Schema Design & Structure", 10, (
        Rule("schema_pk", "Primary key candidate exists", _r_pk_candidate,
             explanation=RuleExplanation(
                 what="There's no single column that uniquely and permanently identifies each row.",
                 why="Without a stable ID you can't reliably join tables, remove duplicates, or point back to one specific record.",
                 example="Add an id column with a unique value per row (an integer or a UUID)."),
             severity="warning",
             lens=frozenset({"DQ", "AI"})),
        Rule("schema_audit", "Audit columns present", _r_audit_columns,
             explanation=RuleExplanation(
                 what="There's no record of when each row was created or last changed.",
                 why="Without timestamps you can't tell fresh data from stale, can't load only what changed, and can't trace where a value came from when something looks wrong.",
                 example="Add created_at and updated_at columns, filled automatically whenever a row is written."),
             severity="info",
             lens=frozenset({"DQ", "AI"})),
        Rule("schema_col_count", "Column count reasonable", _r_column_count,
             explanation=RuleExplanation(
                 what="The table has an unusually small or large number of columns.",
                 why="Too few columns may lack the features needed for modelling; too many often hide multiple entities crammed together, making joins and maintenance fragile.",
                 example="A 200-column table might be better split into a core table + a detail table joined by an ID."),
             severity="info",
             lens=frozenset({"DQ", "AI"})),
        Rule("schema_naming", "Column naming convention", _r_column_naming,
             explanation=RuleExplanation(
                 what="Column names use inconsistent casing, spaces, or special characters instead of a standard convention like snake_case.",
                 why="Pipelines reference columns by exact name; spaces and mixed casing cause silent breakage, make joins unreliable, and confuse downstream consumers.",
                 example="'Patient Name' → patient_name, 'Blood Pressure' → blood_pressure. Pick one convention, apply everywhere."),
             severity="info",
             lens=frozenset({"DQ", "AI"})),
    )),
    Dimension("quality", "Data Quality & Completeness", 20, (
        Rule("quality_rowcount", "Row count adequate", _r_row_count,
             explanation=RuleExplanation(
                 what="The table has very few rows relative to what most ML models need to learn patterns.",
                 why="Models trained on too little data overfit (memorize rather than generalize) and produce unreliable predictions.",
                 example="A classification model typically needs at least 1,000 rows per class to learn meaningful patterns."),
             severity="warning",
             lens=frozenset({"DQ", "ML"})),
        Rule("quality_missing", "Missing-cell rate", _r_missing_cells,
             explanation=RuleExplanation(
                 what="A significant percentage of cells across the table are empty (null).",
                 why="Missing data forces models to guess, biases results, and can silently exclude entire population segments if the gaps aren't random.",
                 example="If 20% of 'diagnosis_date' is null, any model that uses it loses 20% of its training data — or learns the wrong thing from the gap."),
             severity="warning",
             lens=frozenset({"DQ", "ML"})),
        Rule("quality_duplicates", "Duplicate rows", _r_duplicates,
             explanation=RuleExplanation(
                 what="Some rows are exact copies of other rows in the same table.",
                 why="Duplicates inflate counts, bias model training toward repeated examples, and often signal pipeline replays or join explosions.",
                 example="If patient A appears 3 times identically, the model over-weights patient A's pattern. Deduplicate at the source."),
             severity="warning",
             lens=frozenset({"DQ", "ML"})),
        Rule("quality_col_nulls", "Per-column null rates", _r_column_nulls,
             explanation=RuleExplanation(
                 what="One or more columns are more than half empty.",
                 why="A column that's mostly null carries almost no signal — it adds noise, increases storage, and complicates feature pipelines without contributing useful information.",
                 example="A 'secondary_phone' column that's 80% null rarely helps a model. Decide: impute, drop, or document why it's sparse."),
             severity="warning",
             lens=frozenset({"DQ", "ML"})),
        Rule("quality_surrogates", "No surrogate null values", _r_surrogate_nulls,
             explanation=RuleExplanation(
                 what="Some columns use placeholder values (-1, 999, 'N/A') instead of real NULLs to represent missing data.",
                 why="Surrogate nulls hide true missingness from imputation logic and distort statistics — mean, min, and distribution all become wrong.",
                 example="Replace -1 sentinels in 'Quantity' with NULL, then document the imputation strategy."),
             severity="info",
             lens=frozenset({"DQ", "ML"})),
        Rule("quality_pk_uniqueness", "Primary key verified unique", _r_pk_uniqueness,
             explanation=RuleExplanation(
                 what="Check: Primary key verified unique.",
                 why="Improves data readiness assessment coverage.",
                 example="Address this finding to improve your readiness score."),
             severity="warning",
             lens=frozenset({"DQ", "ML"})),
        Rule("quality_type_consistency", "Types consistent with metadata", _r_type_consistency,
             explanation=RuleExplanation(
                 what="Check: Types consistent with metadata.",
                 why="Improves data readiness assessment coverage.",
                 example="Address this finding to improve your readiness score."),
             severity="info",
             lens=frozenset({"DQ", "ML"})),
    )),
    Dimension("labels", "Labels, Targets & Ground Truth", 15, (
        Rule("labels_target", "Target identifiable", _r_target_column,
             explanation=RuleExplanation(
                 what="There's no column clearly identified as the prediction target (what the model should learn to predict).",
                 why="Without an explicit target, no supervised model can be trained — there's nothing to learn from.",
                 example="Rename the outcome column to 'target' or 'label' and document what it represents."),
             severity="warning",
             lens=frozenset({"ML", "AI"})),
        Rule("labels_balance", "Class balance", _r_class_balance,
             explanation=RuleExplanation(
                 what="The target column's classes may be heavily imbalanced (e.g. 95% 'no' vs 5% 'yes').",
                 why="Severe imbalance makes models predict the majority class almost always and miss the rare class entirely — which is often the one you care about most.",
                 example="If only 2% of claims are fraudulent, a naive model says 'not fraud' 100% of the time and scores 98% accuracy while catching zero fraud."),
             severity="warning",
             lens=frozenset({"ML", "AI"})),
        Rule("labels_timestamps", "Outcome timestamps", _r_outcome_timestamps,
             explanation=RuleExplanation(
                 what="There are no timestamp columns to place outcomes in time.",
                 why="Without time, you can't do a proper train/test split that respects chronology — you risk training on future data and getting falsely optimistic results.",
                 example="Capture when each outcome was observed so you can split at a date: train on everything before March, test on April."),
             severity="warning",
             lens=frozenset({"ML", "AI"})),
        Rule("labels_leakage", "Target leakage check", _r_target_leakage,
             explanation=RuleExplanation(
                 what="Some column names suggest they were filled in AFTER the target event happened — they may 'leak' the answer into the features.",
                 why="If a feature contains the answer (or a proxy for it), the model appears perfect in testing but fails completely in production because that information won't exist at prediction time.",
                 example="A 'resolution_date' column filled after a case is closed leaks the outcome. Remove it from features or confirm it's set before the event."),
             severity="blocker", executor="hybrid",
             hybrid_route="human_attestation",
             lens=frozenset({"ML", "AI"})),
        Rule("labels_class_absolute", "Minimum rows per class", _r_class_absolute,
             explanation=RuleExplanation(
                 what="Check: Minimum rows per class.",
                 why="Improves data readiness assessment coverage.",
                 example="Address this finding to improve your readiness score."),
             severity="warning",
             lens=frozenset({"ML", "AI"})),
    ), applicability=_has_target_or_binary),
    Dimension("temporal", "Temporal Integrity", 15, (
        Rule("temporal_present", "Datetime columns present", _r_has_datetime,
             explanation=RuleExplanation(
                 what="The table has no datetime columns at all.",
                 why="Without timestamps you can't order events, detect trends, do time-based splits, or build time-series features -- all critical for most AI use cases.",
                 example="Add at minimum: record_created_at (when the row was written) and event_date (when the thing happened)."),
             severity="warning",
             lens=frozenset({"DQ", "ML", "AI"})),
        Rule("temporal_range_span", "Sufficient temporal span", _r_temporal_range_span,
             explanation=RuleExplanation(
                 what="The date range in the data is too narrow to capture meaningful patterns.",
                 why="A date range that's too narrow (e.g. one week) may not capture seasonality, trends, or rare events the model needs to generalize. Most time-series models need at least 2-3 full cycles of the pattern they're learning.",
                 example="If your use case is forecasting monthly sales, you need at least 12-24 months of history, not 2 weeks."),
             severity="warning",
             lens=frozenset({"DQ", "ML", "AI"})),
        Rule("temporal_freshness", "Data freshness", _r_temporal_freshness,
             explanation=RuleExplanation(
                 what="The most recent data in the table is too old -- it may no longer represent current conditions.",
                 why="Models trained on stale data drift silently: the real world has moved on but the model still reflects old patterns. The older the data, the higher the risk of degraded performance in production.",
                 example="If your latest record is from 2 years ago, customer behavior, market conditions, and regulations may have all changed since then."),
             severity="info",
             lens=frozenset({"DQ", "ML", "AI"})),
        Rule("temporal_ordering", "Temporal ordering valid", _r_temporal_ordering,
             explanation=RuleExplanation(
                 what="Created and updated timestamps appear to be logically inconsistent -- some records show modification dates earlier than creation dates.",
                 why="Temporal ordering violations corrupt time-based features and invalidate temporal train/test splits. If updated_at < created_at, something is wrong in the pipeline.",
                 example="If a record was created on March 5 but shows updated_at as February 20, either there's clock skew, a data migration error, or the columns are mislabeled."),
             severity="info",
             lens=frozenset({"DQ", "ML", "AI"})),
        Rule("temporal_granularity", "Granularity consistency", _r_temporal_granularity,
             explanation=RuleExplanation(
                 what="Datetime columns in this table operate at very different time granularities -- one tracks seconds while another tracks months.",
                 why="Wildly different granularities complicate joins and feature engineering. A per-second event column joined to a monthly snapshot column without explicit alignment creates misleading features.",
                 example="If 'event_timestamp' is per-second and 'report_month' is monthly, document the intended join strategy (e.g., truncate event_timestamp to month)."),
             severity="info",
             lens=frozenset({"DQ", "ML", "AI"})),
    )),
    Dimension("features", "Feature & Signal Readiness", 10, (
        Rule("features_cardinality", "Categorical cardinality", _r_cardinality,
             explanation=RuleExplanation(
                 what="One or more text/category columns have a very large number of distinct values (high cardinality).",
                 why="Most models can't handle thousands of categories directly — they need encoding, which blows up memory or loses information if done naively.",
                 example="A 'product_id' column with 50,000 unique values needs embedding or target-encoding, not one-hot encoding (which would create 50,000 new columns)."),
             severity="warning",
             lens=frozenset({"ML", "AI"})),
        Rule("features_numeric", "Numeric features available", _r_numeric_features,
             explanation=RuleExplanation(
                 what="The table has very few (or no) numeric columns.",
                 why="Numeric features are the easiest for most models to consume. A purely categorical dataset limits you to tree-based models and requires heavy encoding work.",
                 example="Engineer at least one numeric feature: counts (order_count), ratios (return_rate), or durations (days_since_last_login)."),
             severity="info",
             lens=frozenset({"ML", "AI"})),
        Rule("features_near_constant", "No near-constant columns", _r_near_constant,
             explanation=RuleExplanation(
                 what="One or more columns are dominated by a single value (>95% of rows have the same value).",
                 why="A column that's 99% one value carries almost zero predictive signal. Including it adds noise and dimensionality without information gain.",
                 example="A 'country' column that's 99% 'US' won't help a model distinguish anything. Drop it or flag it as an invariant."),
             severity="warning",
             lens=frozenset({"ML", "AI"})),
        Rule("features_infinites", "No infinite values", _r_infinites,
             explanation=RuleExplanation(
                 what="One or more numeric columns contain infinite (inf/-inf) values.",
                 why="Most ML models crash or produce garbage when fed infinity. It usually results from a division-by-zero in an upstream calculation that went undetected.",
                 example="Replace inf values with NaN (then impute) or cap at a domain-appropriate maximum."),
             severity="warning",
             lens=frozenset({"ML", "AI"})),
        Rule("features_type_mismatch", "Storage types match semantic types", _r_type_mismatch,
             explanation=RuleExplanation(
                 what="Some columns are stored as a generic type (e.g. 'string') but contain data that is semantically a different type (e.g. UUIDs, URLs, dates).",
                 why="Type mismatches cause features to be engineered incorrectly. A UUID stored as string gets text-featurized (bag-of-words) when it should be treated as a foreign key.",
                 example="Cast date-like strings to datetime, and mark UUID/FK columns explicitly so pipelines don't featurize them as text."),
             severity="info",
             lens=frozenset({"ML", "AI"})),
        Rule("features_missingness_pattern", "No structured missingness", _r_missingness_pattern,
             explanation=RuleExplanation(
                 what="Groups of columns are consistently null together, forming a structured missingness pattern.",
                 why="When columns are always missing as a group, it signals a failed JOIN, an optional form section, or a broken pipeline branch. Simple imputation won't fix it because the data is structurally absent.",
                 example="If columns A, B, and C are always null together, investigate: is there a LEFT JOIN returning NULLs for a specific source?"),
             severity="info",
             lens=frozenset({"ML", "AI"})),
        Rule("features_mixed_correlation", "No categorical multicollinearity", _r_mixed_correlation,
             explanation=RuleExplanation(
                 what="Pairs of categorical or mixed-type columns are highly correlated (Phi_k coefficient above threshold).",
                 why="Redundant categorical columns inflate dimensionality without adding independent signal. They waste compute and can confuse interpretability.",
                 example="If 'department_name' and 'department_code' are perfectly correlated, keep one and drop the other."),
             severity="info",
             lens=frozenset({"ML", "AI"})),
    )),
    Dimension("stats", "Statistical Properties", 10, (
        Rule("stats_no_constants", "No constant columns", _r_no_constants,
             explanation=RuleExplanation(
                 what="One or more columns have the same value in every row.",
                 why="A constant column carries zero information — it can't help the model distinguish anything, wastes space, and can break some algorithms that expect variance.",
                 example="If 'country' is 'US' in every row, drop it or document it as a known invariant."),
             severity="info",
             lens=frozenset({"DQ", "ML"})),
        Rule("stats_outliers", "Outlier exposure", _r_outlier_aware,
             explanation=RuleExplanation(
                 what="Some numeric columns show extreme spread — the standard deviation is very large relative to the mean.",
                 why="Outliers can dominate model training, pulling predictions toward extreme cases. Without a documented policy, it's unclear whether they're real signals or data errors.",
                 example="A single $10M transaction in a table averaging $50 can skew everything. Decide: cap at a percentile, flag for review, or model separately."),
             severity="info",
             lens=frozenset({"DQ", "ML"})),
        Rule("stats_baseline", "Distribution baseline", _r_distribution_baseline,
             explanation=RuleExplanation(
                 what="There's no stored reference distribution to compare future data against.",
                 why="Without a baseline you can't detect drift — when the data silently changes shape over time and your model's predictions degrade without anyone noticing.",
                 example="Store today's column distributions (mean, percentiles, category frequencies) as a snapshot. Compare weekly and alert on significant shifts."),
             severity="info",
             lens=frozenset({"DQ", "ML"})),
        Rule("stats_multicollinearity", "No highly correlated features", _r_multicollinearity,
             explanation=RuleExplanation(
                 what="Two or more numeric columns are near-perfectly correlated (|r| >= 0.95).",
                 why="Redundant features inflate model complexity, increase variance in linear models, and waste compute. They don't add independent signal.",
                 example="If 'weight_kg' and 'weight_lb' both exist, drop one — they carry identical information."),
             severity="info",
             lens=frozenset({"DQ", "ML"})),
        Rule("stats_outlier_skew", "No extreme skewness", _r_outlier_skew,
             explanation=RuleExplanation(
                 what="Check: No extreme skewness.",
                 why="Improves data readiness assessment coverage.",
                 example="Address this finding to improve your readiness score."),
             severity="info",
             lens=frozenset({"DQ", "ML"})),
    )),
    Dimension("privacy", "Privacy, Compliance & Ethics", 10, (
        Rule("privacy_column_names", "PII column names", _r_pii_column_names,
             explanation=RuleExplanation(
                 what="Column names suggest they contain personal identifiers — names, emails, phone numbers, SSNs, or similar.",
                 why="If real personal data feeds AI, people's identities travel with the data. That's a serious privacy and compliance exposure (GDPR/HIPAA), and the dataset can't be safely shared or used for training.",
                 example="Replace jane.doe@email.com with a one-way token like USR_9F3A2B that can't be reversed back to the person."),
             severity="blocker",
             lens=frozenset({"AI", "DQ"})),
        Rule("privacy_values", "PII in sample values", _r_pii_values,
             explanation=RuleExplanation(
                 what="Sample values in a column match patterns that look like emails or Social Security Numbers.",
                 why="Even if the column isn't named 'email', the actual values may contain personal data that shouldn't reach a model or be shared.",
                 example="A 'notes' column containing 'Contact: john@company.com' leaks PII. A human must confirm whether these are real or synthetic."),
             severity="warning", executor="hybrid",
             hybrid_route="human_attestation",
             lens=frozenset({"AI", "DQ"})),
        Rule("privacy_consent", "Consent metadata", _r_consent_metadata,
             explanation=RuleExplanation(
                 what="There's no column or metadata indicating what this data is allowed to be used for.",
                 why="Using data for AI training without documented consent scope may violate regulations and internal policies — even if the data is technically available.",
                 example="Add a 'data_use_scope' field: 'approved for analytics and model training' vs 'reporting only — no ML use without re-consent'."),
             severity="warning",
             lens=frozenset({"AI", "DQ"})),
        Rule("privacy_k_anonymity", "No small-group disclosure risk", _r_k_anonymity,
             explanation=RuleExplanation(
                 what="Check: No small-group disclosure risk.",
                 why="Improves data readiness assessment coverage.",
                 example="Address this finding to improve your readiness score."),
             severity="info",
             lens=frozenset({"AI", "DQ"})),
    )),
    Dimension("metadata", "Metadata & Documentation", 5, (
        Rule("metadata_dictionary", "Metadata quality", _r_dictionary_present,
             explanation=RuleExplanation(
                 what="The dataset lacks a documented data dictionary or the one provided has poor coverage — especially in governance fields (PII classification, consent, AI-usage approval).",
                 why="Without governance metadata, compliance teams can't assess whether the data is safe for AI use. Governance coverage is weighted 40% of the metadata quality score because this is a compliance-driven product.",
                 example="Add PII_flag, consent_basis, and ai_ml_usage_approval columns to your data dictionary. Even partial governance documentation lifts the score significantly."),
             severity="info",
             lens=frozenset({"AI", "DQ"})),
        Rule("metadata_recon_rate", "Metadata reconciliation rate", _r_metadata_recon_rate,
             explanation=RuleExplanation(
                 what="Check: Metadata reconciliation rate.",
                 why="Improves data readiness assessment coverage.",
                 example="Address this finding to improve your readiness score."),
             severity="info",
             lens=frozenset({"AI", "DQ"})),
        Rule("metadata_consent_approval", "AI/ML usage approved", _r_consent_approval,
             explanation=RuleExplanation(
                 what="Check: AI/ML usage approved.",
                 why="Improves data readiness assessment coverage.",
                 example="Address this finding to improve your readiness score."),
             severity="warning",
             lens=frozenset({"AI", "DQ"})),
        Rule("metadata_doc_coverage", "Column documentation coverage", _r_doc_coverage,
             explanation=RuleExplanation(
                 what="Check: Column documentation coverage.",
                 why="Improves data readiness assessment coverage.",
                 example="Address this finding to improve your readiness score."),
             severity="warning",
             lens=frozenset({"AI", "DQ"})),
    )),
    Dimension("ops", "Operational & Pipeline Readiness", 5, (
        Rule("ops_stable_names", "Stable column names", _r_stable_names,
             explanation=RuleExplanation(
                 what="Some column names contain temporary suffixes like '_tmp', '_v2', '_old', or 'test_' that suggest they're not finalized.",
                 why="Production pipelines break when column names change. Temporary names signal the schema isn't stable enough for a model to depend on.",
                 example="Rename '_tmp' / '_v2' / '_old' columns to their final names before any production pipeline references them."),
             severity="info",
             lens=frozenset({"AI", "DQ", "ML"})),
        Rule("ops_cadence", "Refresh cadence documented", _r_refresh_cadence,
             explanation=RuleExplanation(
                 what="There's no documented schedule for how often this data is refreshed.",
                 why="A model trained on 'daily' data that actually arrives weekly will silently degrade. Without a documented SLA, no one knows when staleness becomes a problem.",
                 example="Document: 'This table refreshes daily at 02:00 UTC via the nightly ETL. SLA: data available by 04:00 UTC.'"),
             severity="info",
             lens=frozenset({"AI", "DQ", "ML"})),
        Rule("ops_watermark", "Incremental load capability", _r_watermark_candidate,
             explanation=RuleExplanation(
                 what="No column is suitable as a watermark for incremental data loading.",
                 why="Without a monotonically increasing column (timestamp or sequence), pipelines must reload the entire table on every refresh — expensive and slow at scale.",
                 example="Add a created_at timestamp or auto-increment id column. Pipelines then load only rows WHERE created_at > last_loaded."),
             severity="info",
             lens=frozenset({"AI", "DQ", "ML"})),
        Rule("ops_partition", "Partition strategy defined", _r_partition_strategy,
             explanation=RuleExplanation(
                 what="This large table (≥1M rows) has no confirmed partition strategy.",
                 why="Without partitioning, AI pipelines must scan the entire table for every training run or feature refresh — causing slow reads, high costs, and pipeline timeouts.",
                 example="Partition by date (e.g. monthly) or a logical key (region, tenant) so pipelines can read only the relevant subset."),
             severity="info", executor="hybrid",
             hybrid_route="human_attestation",
             lens=frozenset({"AI", "DQ", "ML"})),
        Rule("ops_watermark_monotonic", "Watermark is monotonic", _r_watermark_monotonic,
             explanation=RuleExplanation(
                 what="Check: Watermark is monotonic.",
                 why="Improves data readiness assessment coverage.",
                 example="Address this finding to improve your readiness score."),
             severity="info",
             lens=frozenset({"AI", "DQ", "ML"})),
    )),
)
