"""Runbook request builder — assembles the deterministic, masked payload
that the LLM runbook agent consumes.

No raw rows, no raw PII values — only column names + issue descriptors +
metadata context (definition, owner, grain, unit, PII category).

See the master hand-off §A4.
"""
from __future__ import annotations

from core.models import (
    RunbookFinding,
    RunbookRequest,
    RunbookTableInput,
    SchemaAssessment,
)


def _compute_criticality(severity: str, status: str) -> str:
    """Map severity + status to a criticality band.

    Critical = blocker (caps score at 59, gating)
    High     = non-blocker failure (direct score loss)
    Medium   = warning (partial score loss)
    Low      = info-level (minimal impact)
    """
    if severity == "blocker":
        return "Critical"
    if severity == "info":
        return "Low"
    if status == "fail":
        return "High"
    if status == "warn":
        return "Medium"
    return "Low"


def build_runbook_request(report: SchemaAssessment) -> RunbookRequest:
    """Build a masked, fact-only payload for the runbook agent.

    Only includes assessed (included) tables. For each table, collects
    non-pass findings with their metadata context where available.
    """
    tables: list[RunbookTableInput] = []

    for table in report.tables:
        if not table.included:
            continue

        findings: list[RunbookFinding] = []
        for dim in table.dimensions:
            for check in dim.checks:
                if check.status in ("pass", "deferred"):
                    continue
                # Build metadata context from evidence + any attached metadata
                meta_ctx: dict = {}
                if check.evidence:
                    for key in ("column", "candidates", "matched_pattern"):
                        if key in check.evidence:
                            meta_ctx[key] = check.evidence[key]

                findings.append(RunbookFinding(
                    rule_id=check.rule_id,
                    dimension=dim.id,
                    severity=check.severity,
                    issue=check.title,
                    detail=check.detail,
                    recommendation=check.recommendation or "",
                    target_columns=check.evidence.get("candidates", [])
                                   or ([check.evidence["column"]] if "column" in check.evidence else []),
                    metadata_context=meta_ctx,
                    evidence=check.evidence or {},
                    criticality=_compute_criticality(check.severity, check.status),
                ))

        if findings:
            # Per-dimension scores: id, label, weight, score
            dim_scores = [
                {"id": d.id, "label": d.label, "weight": d.weight, "score": d.score}
                for d in table.dimensions
            ]

            # Metadata coverage context — same logic as synthesizer
            meta_check = next(
                (c for d in table.dimensions for c in d.checks
                 if c.rule_id == "metadata_dictionary" and c.evidence),
                None,
            )
            metadata_coverage: dict | None = None
            if meta_check and meta_check.evidence.get("weighted_pct") is not None:
                e = meta_check.evidence
                metadata_coverage = {
                    "coverage_pct": e.get("weighted_pct", 0),
                    "governance_pct": e.get("governance", 0),
                    "technical_pct": e.get("technical", 0),
                    "operational_pct": e.get("operational", 0),
                    "business_pct": e.get("business", 0),
                }

            tables.append(RunbookTableInput(
                table_name=table.table_name,
                row_count=table.row_count,
                column_count=table.column_count,
                score=table.overall_score,
                tier=table.tier,
                klass=table.klass,
                dimension_scores=dim_scores,
                metadata_coverage=metadata_coverage,
                findings=findings,
            ))

    return RunbookRequest(
        schema_score=report.overall_score,
        schema_verdict=report.verdict,
        gated_by=report.gated_by,
        tables=tables,
    )
