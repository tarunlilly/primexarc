"""Reconciler — compare declared metadata against observed profile facts.

All outputs are deterministic facts. The reconciler never gates the score
directly — its findings feed the Metadata & Docs dimension and appear in
the report for transparency.

See app/docs/metadata_layer.md §2.1.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from config import settings
from core.models import (
    ColumnProfile,
    MetadataEntry,
    MetadataProfile,
    ReconciliationFinding,
    TableProfile,
)

logger = logging.getLogger(__name__)

# Type mapping: metadata declared type → expected profile dtype(s)
_TYPE_MAP: dict[str, set[str]] = {
    "int": {"int"},
    "integer": {"int"},
    "bigint": {"int"},
    "smallint": {"int"},
    "float": {"float"},
    "double": {"float"},
    "decimal": {"float"},
    "numeric": {"float", "int"},
    "number": {"float", "int"},
    "string": {"string", "object"},
    "varchar": {"string", "object"},
    "text": {"string", "object"},
    "char": {"string", "object"},
    "boolean": {"bool"},
    "bool": {"bool"},
    "date": {"datetime"},
    "datetime": {"datetime"},
    "timestamp": {"datetime"},
}


def reconcile(
    profile: TableProfile,
    metadata: MetadataProfile,
) -> list[ReconciliationFinding]:
    """Compare declared metadata against observed profile. Returns deterministic findings.

    When metadata is absent or empty, returns a single explicit "could not verify"
    finding (§2.5 — absence is never silent).
    """
    if not metadata or not metadata.entries:
        return [ReconciliationFinding(
            column_name="*",
            field="reconciliation",
            declared="(no metadata uploaded)",
            observed="(profile only)",
            severity="info",
            detail="Could not verify — no metadata dictionary provided. Upload one to enable reconciliation.",
            status="could_not_verify",
        )]

    col_index: dict[str, ColumnProfile] = {
        c.name.lower(): c for c in profile.columns
    }
    meta_index: dict[str, MetadataEntry] = {
        e.column_name.lower(): e for e in metadata.entries
        if e.column_name
    }

    findings: list[ReconciliationFinding] = []

    for col_name_lower, entry in meta_index.items():
        col = col_index.get(col_name_lower)
        if not col:
            continue

        # 1. Data type mismatch
        if entry.data_type_declared:
            declared_lower = entry.data_type_declared.strip().lower()
            expected_dtypes = _TYPE_MAP.get(declared_lower)
            if expected_dtypes and col.dtype not in expected_dtypes:
                findings.append(ReconciliationFinding(
                    column_name=col.name,
                    field="data_type",
                    declared=entry.data_type_declared,
                    observed=col.dtype,
                    severity="warning",
                    detail=f"Metadata declares type '{entry.data_type_declared}' but observed '{col.dtype}'.",
                ))

        # 2. Nullable contradiction
        if entry.nullable_declared:
            declared_nullable = entry.nullable_declared.strip().upper()
            if declared_nullable in ("N", "NO", "FALSE", "NOT NULL"):
                if col.null_count > 0:
                    rate = col.null_pct
                    findings.append(ReconciliationFinding(
                        column_name=col.name,
                        field="nullable",
                        declared="NOT NULL",
                        observed=f"{col.null_count} nulls ({rate:.1f}%)",
                        severity="warning",
                        detail=f"Metadata declares non-nullable but {col.null_count} nulls observed ({rate:.1f}%).",
                    ))

        # 3. Primary/Foreign Key vs uniqueness
        if entry.primary_foreign_key:
            pk_flag = entry.primary_foreign_key.strip().upper()
            if pk_flag in ("PK", "PRIMARY", "PRIMARY KEY"):
                if col.unique_count < profile.row_count and profile.row_count > 0:
                    findings.append(ReconciliationFinding(
                        column_name=col.name,
                        field="primary_key",
                        declared="PK",
                        observed=f"{col.unique_count}/{profile.row_count} unique",
                        severity="warning",
                        detail=f"Metadata declares PK but column is not fully unique ({col.unique_count}/{profile.row_count}).",
                    ))

        # 4. Cardinality drift
        if entry.cardinality_declared:
            try:
                declared_card = int(entry.cardinality_declared.strip())
                if declared_card > 0 and col.unique_count > 0:
                    drift = abs(col.unique_count - declared_card) / declared_card
                    if drift > settings.metadata_cardinality_drift_tolerance:
                        findings.append(ReconciliationFinding(
                            column_name=col.name,
                            field="cardinality",
                            declared=str(declared_card),
                            observed=str(col.unique_count),
                            severity="warning",
                            detail=f"Cardinality drift: declared {declared_card}, observed {col.unique_count} ({drift:.0%} drift, tolerance {settings.metadata_cardinality_drift_tolerance:.0%}).",
                        ))
            except ValueError:
                pass

        # 5. Documented-as-usable but 100% null
        if col.null_pct >= 100.0 and entry.field_role:
            role_lower = entry.field_role.strip().lower()
            if role_lower not in ("deprecated", "unused", "archived"):
                findings.append(ReconciliationFinding(
                    column_name=col.name,
                    field="field_role",
                    declared=entry.field_role,
                    observed="100% null",
                    severity="warning",
                    detail=f"Metadata documents this as '{entry.field_role}' but column is 100% null.",
                ))

        # 6. PII governance contradiction (Phase 5 dependency)
        # The full PII detection signal comes from Phase 5. Until that ships,
        # we check only the column-name heuristic (already available via the
        # privacy_column_names rule pattern). We explicitly mark "could not
        # verify" for value-level PII detection.
        if entry.pii_flag:
            pii_declared = entry.pii_flag.strip().upper()
            if pii_declared in ("N", "NO", "FALSE"):
                from core.dimensions import PII_NAME_RE
                if PII_NAME_RE.search(col.name):
                    findings.append(ReconciliationFinding(
                        column_name=col.name,
                        field="pii_flag",
                        declared="No PII",
                        observed=f"Column name '{col.name}' matches PII pattern",
                        severity="warning",
                        detail="Metadata declares no PII but column name suggests personal data. Governance contradiction.",
                        status="confirmed",
                    ))
                else:
                    # Value-level PII detection not available until Phase 5
                    findings.append(ReconciliationFinding(
                        column_name=col.name,
                        field="pii_flag_values",
                        declared="No PII",
                        observed="value-level detection not available (Phase 5)",
                        severity="info",
                        detail="PII Flag = N declared; value-level detection awaits Phase 5.",
                        status="could_not_verify",
                    ))

    # Internal metadata consistency checks (no live data needed)
    for entry in metadata.entries:
        if not entry.column_name:
            continue

        # min > max in valid_values_range
        if entry.valid_values_range:
            _check_range_consistency(entry, findings)

        # Stale lastSyncedAt
        if entry.last_synced_at:
            _check_staleness(entry, findings)

    return findings


def _check_range_consistency(
    entry: MetadataEntry, findings: list[ReconciliationFinding]
) -> None:
    """Check if valid_values_range has min > max (internal inconsistency)."""
    vr = entry.valid_values_range.strip()
    # Common formats: "0-100", "0..100", "min:0 max:100"
    for sep in ["-", "..", ","]:
        if sep in vr:
            parts = vr.split(sep, 1)
            try:
                lo = float(parts[0].strip())
                hi = float(parts[1].strip())
                if lo > hi:
                    findings.append(ReconciliationFinding(
                        column_name=entry.column_name,
                        field="valid_values_range",
                        declared=vr,
                        observed="(internal check)",
                        severity="warning",
                        detail=f"Range inconsistency: min ({lo}) > max ({hi}).",
                    ))
            except ValueError:
                pass
            break


def _check_staleness(
    entry: MetadataEntry, findings: list[ReconciliationFinding]
) -> None:
    """Check if lastSyncedAt is beyond the configured staleness threshold."""
    try:
        synced = datetime.fromisoformat(entry.last_synced_at.strip().replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        days_old = (now - synced).days
        if days_old > settings.metadata_staleness_days:
            findings.append(ReconciliationFinding(
                column_name=entry.column_name,
                field="last_synced_at",
                declared=entry.last_synced_at,
                observed=f"{days_old} days old",
                severity="warning",
                detail=f"Metadata is {days_old} days old (threshold: {settings.metadata_staleness_days} days).",
            ))
    except (ValueError, TypeError):
        pass
