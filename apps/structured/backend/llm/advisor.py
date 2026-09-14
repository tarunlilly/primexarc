"""Advisor — single integration seam for the LLM layer.

`advise(assessment)` is the ONLY function callers outside `llm/` should
import. It runs the synthesizer once per table in parallel, merges the
output additively into the `SchemaAssessment`, and stamps `LLMMetadata`
for audit/reproducibility.

Hard contract:
- `assessment.overall_score`, `assessment.tier`, `assessment.dimensions[*].score`,
  `assessment.tables[*].overall_score`, `assessment.tables[*].tier`, and
  `assessment.gated_by` are NEVER touched. The LLM is purely additive.
- On any failure (missing creds, network, schema invalid) the function
  still returns a valid assessment — the deterministic fallback fills
  narrative/strengths/recommendations.
"""
from __future__ import annotations

import asyncio
import logging
import time

from config import settings
from core.models import (
    LLMMetadata,
    Recommendation,
    SchemaAssessment,
    TableAssessment,
)
from llm.synthesizer import synthesize
from llm.schema import SynthesizerOutput

logger = logging.getLogger(__name__)

_L = "══ LLM ══"


def _to_recommendations(
    table: TableAssessment, out: SynthesizerOutput,
) -> list[Recommendation]:
    """Project SynthesizerOutput.recommendations onto core.Recommendation,
    filling dimension_id/table_name from the matching finding for FE
    convenience. Anti-hallucination filter already ran in the synthesizer
    so every finding_id here is known to exist."""
    finding_index: dict[str, str] = {}
    for d in table.dimensions:
        for c in d.checks:
            finding_index[c.rule_id] = d.id
    return [
        Recommendation(
            finding_id=r.finding_id,
            priority=r.priority,
            title=r.title,
            detail=r.detail,
            technical_note=r.technical_note,
            dimension_id=finding_index.get(r.finding_id),
            table_name=table.table_name,
        )
        for r in out.recommendations
    ]


def _enrich_table(table: TableAssessment,
                  out: SynthesizerOutput) -> TableAssessment:
    """Return a new TableAssessment with narrative/strengths/recs merged in.
    Score-bearing fields (overall_score, tier, dimensions, gated_by,
    deferred) are preserved exactly."""
    return table.model_copy(update={
        "narrative": out.narrative,
        "strengths": list(out.strengths),
        "prioritized_recommendations": _to_recommendations(table, out),
    })


async def _synthesize_timed(
    table: TableAssessment,
) -> tuple[SynthesizerOutput, str | None]:
    started = time.monotonic()
    out, reason = await synthesize(table)
    elapsed_ms = int((time.monotonic() - started) * 1000)
    logger.info(
        "%s advisor: table=%s elapsed_ms=%d fallback_reason=%s",
        _L,
        table.table_name,
        elapsed_ms,
        reason or "none",
    )
    return out, reason


async def advise(assessment: SchemaAssessment) -> SchemaAssessment:
    """Run the synthesizer for each table in parallel and merge results.

    Always returns a valid assessment. Stamps `assessment.llm` with the
    model_config_name on success or a fallback_reason on failure. Never
    raises — failure is observable but non-fatal.
    """
    if not assessment.tables:
        return assessment

    started = time.monotonic()

    # Fan out one synthesizer call per table. asyncio.gather preserves order
    # so we can zip back over `assessment.tables` afterward.
    results: list[tuple[SynthesizerOutput, str | None]] = await asyncio.gather(
        *(_synthesize_timed(t) for t in assessment.tables),
    )

    enriched_tables = [
        _enrich_table(t, out) for t, (out, _reason) in zip(assessment.tables, results)
    ]

    # If any table fell back, mark the whole run as fallback so the FE can
    # surface "rule-based output only" to the user. The first observed
    # reason wins (they are usually identical — same missing credential).
    fallback_reason: str | None = next(
        (reason for _out, reason in results if reason is not None), None,
    )
    used = fallback_reason is None
    llm_meta = LLMMetadata(
        used=used,
        model_config_name=settings.model_config_name if used else None,
        fallback_reason=fallback_reason,
    )
    elapsed_ms = int((time.monotonic() - started) * 1000)

    if used:
        logger.info("%s advisor: synthesized narrative for %d table(s) elapsed_ms=%d",
                    _L, len(enriched_tables), elapsed_ms)
    else:
        logger.info("%s advisor: FALLBACK path used (%s) for %d table(s) elapsed_ms=%d",
                    _L, fallback_reason, len(enriched_tables), elapsed_ms)

    return assessment.model_copy(update={
        "tables": enriched_tables,
        "llm": llm_meta,
    })
