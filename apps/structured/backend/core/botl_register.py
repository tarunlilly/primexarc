"""BOTL (Business, Operational, Technical, Lineage) metadata quality register.

Implements the UMS v2.0 standard. Loads the 44-field register from CSV at
import time. Pure module — no I/O at call time, no LLM.
"""
from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from core.models import MetadataEntry, TableProfile

logger = logging.getLogger(__name__)

# ───────────────────────────────────────────────────────────────────────────
# Data classes
# ───────────────────────────────────────────────────────────────────────────

_SEVERITY_POINTS = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}

_CSV_PATH = Path(__file__).parent.parent.parent / "docs" / "ums_v2_field_register.csv"


@dataclass(frozen=True)
class BOTLField:
    """One row in the UMS v2.0 field register."""
    id: str
    name: str
    category: str
    grain: str
    severity: str
    points: int
    escalation: str
    population_mode: str
    why: str


@dataclass
class FieldExtraction:
    """Result of extracting a single BOTL field from a TableProfile."""
    status: str  # "present" | "absent" | "na"
    value: str | None = None
    column_coverage: dict | None = None  # {"covered": int, "total": int}


# ───────────────────────────────────────────────────────────────────────────
# Register loading
# ───────────────────────────────────────────────────────────────────────────

def _load_register() -> list[BOTLField]:
    """Load and validate the 44-field register from CSV."""
    if not _CSV_PATH.exists():
        raise FileNotFoundError(f"UMS v2.0 register CSV not found: {_CSV_PATH}")

    fields: list[BOTLField] = []
    with _CSV_PATH.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            severity = row["severity"].strip().upper()
            points = int(row["points"].strip())
            expected_points = _SEVERITY_POINTS.get(severity)
            if expected_points is None:
                raise ValueError(f"Unknown severity '{severity}' for field {row['id']}")
            if points != expected_points:
                raise ValueError(
                    f"Field {row['id']}: severity {severity} must have "
                    f"points={expected_points}, got {points}"
                )
            fields.append(BOTLField(
                id=row["id"].strip(),
                name=row["field"].strip(),
                category=row["category"].strip(),
                grain=row["grain"].strip(),
                severity=severity,
                points=points,
                escalation=row.get("conditional_escalation", "").strip(),
                population_mode=row["population_mode"].strip(),
                why=row["why_this_severity"].strip(),
            ))

    if len(fields) != 44:
        raise ValueError(f"Expected 44 fields in register, got {len(fields)}")

    return fields


REGISTER: list[BOTLField] = _load_register()
REGISTER_BY_ID: dict[str, BOTLField] = {f.id: f for f in REGISTER}


# ───────────────────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────────────────

def _entries(profile: TableProfile) -> list[MetadataEntry]:
    """Get metadata entries attached to the profile."""
    return profile.metadata_entries


def _any_entry_has(profile: TableProfile, attr: str) -> FieldExtraction:
    """Check if any MetadataEntry has a non-empty value for the given attribute."""
    for entry in _entries(profile):
        val = getattr(entry, attr, None)
        if val and str(val).strip():
            return FieldExtraction(status="present", value=str(val).strip())
    return FieldExtraction(status="absent")


def _column_coverage(profile: TableProfile, attr: str) -> FieldExtraction:
    """Check per-column coverage for a given MetadataEntry attribute."""
    entries = _entries(profile)
    if not entries:
        return FieldExtraction(status="absent", column_coverage={"covered": 0, "total": profile.column_count})
    total = profile.column_count
    covered = 0
    for entry in entries:
        val = getattr(entry, attr, None)
        if val and str(val).strip():
            covered += 1
    if covered == 0:
        return FieldExtraction(status="absent", column_coverage={"covered": 0, "total": total})
    return FieldExtraction(
        status="present",
        column_coverage={"covered": covered, "total": total},
    )


# ───────────────────────────────────────────────────────────────────────────
# Extractors — one per field ID
# ───────────────────────────────────────────────────────────────────────────

def _extract_b1(profile: TableProfile) -> FieldExtraction:
    """B1: Business Name — check if any entry has a display name distinct from physical."""
    # We don't have a separate display_name field, so always absent
    return FieldExtraction(status="absent")


def _extract_b2(profile: TableProfile) -> FieldExtraction:
    """B2: Business Description."""
    for entry in _entries(profile):
        val = entry.definition or entry.description
        if val and str(val).strip():
            return FieldExtraction(status="present", value=str(val).strip())
    return FieldExtraction(status="absent")


def _extract_b3(profile: TableProfile) -> FieldExtraction:
    """B3: Column Definitions — per-column coverage."""
    return _column_coverage(profile, "definition")


def _extract_b4(profile: TableProfile) -> FieldExtraction:
    """B4: Business Domain — usage_context."""
    return _any_entry_has(profile, "usage_context")


def _extract_b5(profile: TableProfile) -> FieldExtraction:
    """B5: Data Owner — business_owner."""
    return _any_entry_has(profile, "business_owner")


def _extract_b6(profile: TableProfile) -> FieldExtraction:
    """B6: Data Steward."""
    return _any_entry_has(profile, "data_steward")


def _extract_b7(profile: TableProfile) -> FieldExtraction:
    """B7: Business Criticality — not in MetadataEntry."""
    return FieldExtraction(status="absent")


def _extract_b8(profile: TableProfile) -> FieldExtraction:
    """B8: Known Use Cases — usage_context."""
    return _any_entry_has(profile, "usage_context")


def _extract_b9(profile: TableProfile) -> FieldExtraction:
    """B9: Glossary Linkage — absent."""
    return FieldExtraction(status="absent")


def _extract_b10(profile: TableProfile) -> FieldExtraction:
    """B10: Synonyms — absent."""
    return FieldExtraction(status="absent")


def _extract_b11(profile: TableProfile) -> FieldExtraction:
    """B11: Related KPIs — absent."""
    return FieldExtraction(status="absent")


def _extract_b12(profile: TableProfile) -> FieldExtraction:
    """B12: Data Classification — security_classification."""
    return _any_entry_has(profile, "security_classification")


def _extract_b13(profile: TableProfile) -> FieldExtraction:
    """B13: Sensitive Flags — pii_flag per column."""
    return _column_coverage(profile, "pii_flag")


def _extract_b14(profile: TableProfile) -> FieldExtraction:
    """B14: Regulatory Scope — absent."""
    return FieldExtraction(status="absent")


def _extract_b15(profile: TableProfile) -> FieldExtraction:
    """B15: Access Control — absent."""
    return FieldExtraction(status="absent")


def _extract_b16(profile: TableProfile) -> FieldExtraction:
    """B16: Retention Policy."""
    return _any_entry_has(profile, "retention_policy")


def _extract_b17(profile: TableProfile) -> FieldExtraction:
    """B17: Protection Requirements — absent."""
    return FieldExtraction(status="absent")


def _extract_b18(profile: TableProfile) -> FieldExtraction:
    """B18: Certification Status — absent."""
    return FieldExtraction(status="absent")


def _extract_b19(profile: TableProfile) -> FieldExtraction:
    """B19: Sharing Constraints — absent."""
    return FieldExtraction(status="absent")


def _extract_b20(profile: TableProfile) -> FieldExtraction:
    """B20: Audit Requirements — absent."""
    return FieldExtraction(status="absent")


def _extract_b21(profile: TableProfile) -> FieldExtraction:
    """B21: Consent/Purpose — consent_basis or ai_ml_usage_approval."""
    for entry in _entries(profile):
        val = entry.consent_basis or entry.ai_ml_usage_approval
        if val and str(val).strip():
            return FieldExtraction(status="present", value=str(val).strip())
    return FieldExtraction(status="absent")


def _extract_o1(profile: TableProfile) -> FieldExtraction:
    """O1: Refresh Frequency."""
    return _any_entry_has(profile, "refresh_frequency")


def _extract_o2(profile: TableProfile) -> FieldExtraction:
    """O2: Freshness — last_synced_at."""
    return _any_entry_has(profile, "last_synced_at")


def _extract_o3(profile: TableProfile) -> FieldExtraction:
    """O3: Load Pattern — absent."""
    return FieldExtraction(status="absent")


def _extract_o4(profile: TableProfile) -> FieldExtraction:
    """O4: DQ Checks — absent."""
    return FieldExtraction(status="absent")


def _extract_o5(profile: TableProfile) -> FieldExtraction:
    """O5: SLA — absent."""
    return FieldExtraction(status="absent")


def _extract_o6(profile: TableProfile) -> FieldExtraction:
    """O6: Volume Metrics — always present if row_count > 0."""
    if profile.row_count > 0:
        return FieldExtraction(status="present", value=str(profile.row_count))
    return FieldExtraction(status="present", value="0")


def _extract_o7(profile: TableProfile) -> FieldExtraction:
    """O7: Pipeline IDs — absent."""
    return FieldExtraction(status="absent")


def _extract_o8(profile: TableProfile) -> FieldExtraction:
    """O8: Incident History — absent."""
    return FieldExtraction(status="absent")


def _extract_o9(profile: TableProfile) -> FieldExtraction:
    """O9: Usage Stats — absent."""
    return FieldExtraction(status="absent")


def _extract_t1(profile: TableProfile) -> FieldExtraction:
    """T1: Physical ID — always present (profile.name)."""
    return FieldExtraction(status="present", value=profile.name)


def _extract_t2(profile: TableProfile) -> FieldExtraction:
    """T2: Column Structure — data_type_declared + nullable_declared per column."""
    entries = _entries(profile)
    if not entries:
        return FieldExtraction(status="absent", column_coverage={"covered": 0, "total": profile.column_count})
    total = profile.column_count
    covered = 0
    for entry in entries:
        has_type = entry.data_type_declared and str(entry.data_type_declared).strip()
        has_null = entry.nullable_declared and str(entry.nullable_declared).strip()
        if has_type or has_null:
            covered += 1
    if covered == 0:
        return FieldExtraction(status="absent", column_coverage={"covered": 0, "total": total})
    return FieldExtraction(status="present", column_coverage={"covered": covered, "total": total})


def _extract_t3(profile: TableProfile) -> FieldExtraction:
    """T3: PK/UK — primary_foreign_key on any column."""
    for entry in _entries(profile):
        val = entry.primary_foreign_key
        if val and str(val).strip():
            return FieldExtraction(status="present", value=str(val).strip())
    return FieldExtraction(status="absent")


def _extract_t4(profile: TableProfile) -> FieldExtraction:
    """T4: Foreign Keys — primary_foreign_key with 'FK' value."""
    for entry in _entries(profile):
        val = entry.primary_foreign_key
        if val and "FK" in str(val).upper():
            return FieldExtraction(status="present", value=str(val).strip())
    return FieldExtraction(status="absent")


def _extract_t5(profile: TableProfile) -> FieldExtraction:
    """T5: Format/Encoding — absent."""
    return FieldExtraction(status="absent")


def _extract_t6(profile: TableProfile) -> FieldExtraction:
    """T6: Partitioning — absent."""
    return FieldExtraction(status="absent")


def _extract_t7(profile: TableProfile) -> FieldExtraction:
    """T7: Value Domains — valid_values_range per column."""
    return _column_coverage(profile, "valid_values_range")


def _extract_t8(profile: TableProfile) -> FieldExtraction:
    """T8: Schema Version — absent."""
    return FieldExtraction(status="absent")


def _extract_t9(profile: TableProfile) -> FieldExtraction:
    """T9: Cardinality — cardinality_declared per column."""
    return _column_coverage(profile, "cardinality_declared")


def _extract_l1(profile: TableProfile) -> FieldExtraction:
    """L1: Source System."""
    return _any_entry_has(profile, "source_system")


def _extract_l2(profile: TableProfile) -> FieldExtraction:
    """L2: Upstream Lineage."""
    return _any_entry_has(profile, "lineage")


def _extract_l3(profile: TableProfile) -> FieldExtraction:
    """L3: Transformation Summary — absent."""
    return FieldExtraction(status="absent")


def _extract_l4(profile: TableProfile) -> FieldExtraction:
    """L4: Column Lineage — absent."""
    return FieldExtraction(status="absent")


def _extract_l5(profile: TableProfile) -> FieldExtraction:
    """L5: Downstream Consumption — absent."""
    return FieldExtraction(status="absent")


EXTRACTORS: dict[str, Callable[[TableProfile], FieldExtraction]] = {
    "B1": _extract_b1,
    "B2": _extract_b2,
    "B3": _extract_b3,
    "B4": _extract_b4,
    "B5": _extract_b5,
    "B6": _extract_b6,
    "B7": _extract_b7,
    "B8": _extract_b8,
    "B9": _extract_b9,
    "B10": _extract_b10,
    "B11": _extract_b11,
    "B12": _extract_b12,
    "B13": _extract_b13,
    "B14": _extract_b14,
    "B15": _extract_b15,
    "B16": _extract_b16,
    "B17": _extract_b17,
    "B18": _extract_b18,
    "B19": _extract_b19,
    "B20": _extract_b20,
    "B21": _extract_b21,
    "O1": _extract_o1,
    "O2": _extract_o2,
    "O3": _extract_o3,
    "O4": _extract_o4,
    "O5": _extract_o5,
    "O6": _extract_o6,
    "O7": _extract_o7,
    "O8": _extract_o8,
    "O9": _extract_o9,
    "T1": _extract_t1,
    "T2": _extract_t2,
    "T3": _extract_t3,
    "T4": _extract_t4,
    "T5": _extract_t5,
    "T6": _extract_t6,
    "T7": _extract_t7,
    "T8": _extract_t8,
    "T9": _extract_t9,
    "L1": _extract_l1,
    "L2": _extract_l2,
    "L3": _extract_l3,
    "L4": _extract_l4,
    "L5": _extract_l5,
}


# ───────────────────────────────────────────────────────────────────────────
# Validators
# ───────────────────────────────────────────────────────────────────────────

_PLACEHOLDER_VALUES = {"tbd", "n/a", "todo", "-", "na", "none", "unknown", ""}


def _is_placeholder(value: str | None) -> bool:
    """Check if a value is a known placeholder or whitespace-only."""
    if value is None:
        return True
    return value.strip().lower() in _PLACEHOLDER_VALUES


def _default_validator(extraction: FieldExtraction, profile: TableProfile) -> tuple[bool, str]:
    """Default: non-empty, not a placeholder."""
    if extraction.status != "present":
        return False, "Field is absent"
    if _is_placeholder(extraction.value):
        return False, "Value is a placeholder"
    return True, "Valid"


def _validate_b2(extraction: FieldExtraction, profile: TableProfile) -> tuple[bool, str]:
    """B2: Business Description must be >= 120 chars."""
    if extraction.status != "present":
        return False, "Description is absent"
    if extraction.value is None or len(extraction.value.strip()) < 120:
        return False, f"Description too short ({len(extraction.value.strip()) if extraction.value else 0} chars, need >= 120)"
    if _is_placeholder(extraction.value):
        return False, "Description is a placeholder"
    return True, "Valid"


def _validate_column_grain(extraction: FieldExtraction, profile: TableProfile) -> tuple[bool, str]:
    """Column-grain validator: checks coverage fraction."""
    if extraction.status != "present":
        return False, "No column-level metadata present"
    cov = extraction.column_coverage
    if cov is None:
        return False, "No coverage data"
    total = cov["total"]
    covered = cov["covered"]
    if total == 0:
        return True, "No columns to cover"
    fraction = covered / total
    if fraction < 0.5:
        return False, f"Coverage too low ({covered}/{total} = {fraction:.0%})"
    return True, f"Coverage adequate ({covered}/{total} = {fraction:.0%})"


def _validate_t1(extraction: FieldExtraction, profile: TableProfile) -> tuple[bool, str]:
    """T1: Physical ID — always valid (table exists)."""
    return True, "Physical table identifier present"


def _validate_o6(extraction: FieldExtraction, profile: TableProfile) -> tuple[bool, str]:
    """O6: Volume Metrics — always valid (row count is present)."""
    return True, "Volume metrics present"


VALIDATORS: dict[str, Callable[[FieldExtraction, TableProfile], tuple[bool, str]]] = {
    "B2": _validate_b2,
    "B3": _validate_column_grain,
    "B13": _validate_column_grain,
    "T1": _validate_t1,
    "T2": _validate_column_grain,
    "T7": _validate_column_grain,
    "T9": _validate_column_grain,
    "O6": _validate_o6,
}


def validate_field(
    field_id: str,
    extraction: FieldExtraction,
    profile: TableProfile,
) -> tuple[bool, str]:
    """Validate a single field extraction. Returns (is_valid, reason)."""
    validator = VALIDATORS.get(field_id, _default_validator)
    return validator(extraction, profile)


# ───────────────────────────────────────────────────────────────────────────
# Escalation logic
# ───────────────────────────────────────────────────────────────────────────

@dataclass
class FieldResult:
    """Result of extracting + validating a single BOTL field."""
    field: BOTLField
    extraction: FieldExtraction
    valid: bool
    reason: str
    effective_severity: str | None = None  # set by escalation, None = use field.severity
    escalation_applied: str | None = None  # which ESC rule fired


def evaluate_escalations(field_results: list[FieldResult]) -> list[FieldResult]:
    """Apply ESC-1 through ESC-4 with fail-closed semantics.

    Fail-closed means: if the triggering field is absent, we assume the worst
    case and apply the escalation anyway.
    """
    results_by_id: dict[str, FieldResult] = {r.field.id: r for r in field_results}

    # ESC-1: If B13 has any column flagged with a sensitive type OR B13 is absent
    # → B17, B21 become HIGH
    b13 = results_by_id.get("B13")
    b13_triggers = False
    if b13 is None or b13.extraction.status == "absent":
        # Fail-closed: assume sensitive data exists
        b13_triggers = True
    elif b13.extraction.status == "present":
        # Check if any column has a sensitive flag value
        cov = b13.extraction.column_coverage
        if cov and cov["covered"] > 0:
            b13_triggers = True

    if b13_triggers:
        for target_id in ("B17", "B21"):
            target = results_by_id.get(target_id)
            if target:
                target.effective_severity = "HIGH"
                target.escalation_applied = "ESC-1"

    # ESC-2: If B7.value == "Critical" OR B7 is absent → O5 becomes HIGH
    b7 = results_by_id.get("B7")
    b7_triggers = False
    if b7 is None or b7.extraction.status == "absent":
        # Fail-closed: assume critical
        b7_triggers = True
    elif b7.extraction.status == "present" and b7.extraction.value:
        if b7.extraction.value.strip().lower() == "critical":
            b7_triggers = True

    if b7_triggers:
        o5 = results_by_id.get("O5")
        if o5:
            o5.effective_severity = "HIGH"
            o5.escalation_applied = "ESC-2"

    # ESC-3: If O3.load_pattern != "full_refresh" OR O3 is absent
    # → O3 watermark sub-check required (we escalate O3 itself)
    o3 = results_by_id.get("O3")
    if o3:
        if o3.extraction.status == "absent":
            # Fail-closed: watermark sub-check required
            o3.effective_severity = "MEDIUM"
            o3.escalation_applied = "ESC-3"
        elif o3.extraction.status == "present" and o3.extraction.value:
            if o3.extraction.value.strip().lower() != "full_refresh":
                o3.effective_severity = "MEDIUM"
                o3.escalation_applied = "ESC-3"

    # ESC-4: If B14.value != "none" (regulations apply) OR B14 is absent
    # → B20 becomes HIGH
    b14 = results_by_id.get("B14")
    b14_triggers = False
    if b14 is None or b14.extraction.status == "absent":
        # Fail-closed: assume regulations apply
        b14_triggers = True
    elif b14.extraction.status == "present" and b14.extraction.value:
        if b14.extraction.value.strip().lower() != "none":
            b14_triggers = True

    if b14_triggers:
        b20 = results_by_id.get("B20")
        if b20:
            b20.effective_severity = "HIGH"
            b20.escalation_applied = "ESC-4"

    return field_results


# ───────────────────────────────────────────────────────────────────────────
# Public evaluation entry point
# ───────────────────────────────────────────────────────────────────────────

def evaluate_profile(profile: TableProfile) -> list[FieldResult]:
    """Run all 44 extractors + validators against a TableProfile, then apply escalations.

    Returns field results with escalation-adjusted severities.
    """
    results: list[FieldResult] = []
    for field in REGISTER:
        extractor = EXTRACTORS[field.id]
        extraction = extractor(profile)
        valid, reason = validate_field(field.id, extraction, profile)
        results.append(FieldResult(
            field=field,
            extraction=extraction,
            valid=valid,
            reason=reason,
        ))

    return evaluate_escalations(results)
