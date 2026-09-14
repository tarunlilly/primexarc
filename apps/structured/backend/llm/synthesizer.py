"""Synthesizer — REDUCE step.

One LLM call per table. Inputs: the deterministic `TableAssessment` only —
score, tier, dimension scores, findings (rule outcomes with evidence). The
synthesizer never sees raw rows, sample values, or column-by-column data.
That bound is enforced by the function signature: `synthesize` takes a
`TableAssessment`, not a `TableProfile`.

Anti-hallucination contract enforced in two places:
1. The prompt prefix forbids inventing metrics or recomputing scores.
2. After the call, every returned `finding_id` is checked against the
   set of input rule_ids. Recommendations citing unknown ids are dropped.

Any failure (missing creds, network, schema invalid after retry) returns
a rule-based fallback so the assessment still completes — never propagates
to the API caller.
"""
from __future__ import annotations

import json
import logging

from core.models import RuleCheck, TableAssessment
from llm import client
from llm.exceptions import LLMSchemaError, LLMUnavailable
from llm.guardrails import wrap_untrusted
from llm.prompts.synthesizer import SYNTHESIZER_PREFIX
from llm.schema import SynthesizerOutput, SynthesizerRecommendation

logger = logging.getLogger(__name__)

_L = "══ LLM ══"


def _serialize_findings_for_prompt(table: TableAssessment) -> str:
    """Compact JSON-shaped view of the findings the synthesizer is allowed
    to see. Only `pass`/`warn`/`fail` go in; `deferred` is excluded so the
    LLM cannot adjudicate hybrid candidates in prose.

    Ordering is deterministic (dimension order from the engine, then rule
    order within each dimension) so prompt caching works on identical
    inputs.
    """
    payload: dict = {
        "table": {
            "name": table.table_name,
            "row_count": table.row_count,
            "column_count": table.column_count,
        },
        "score": {
            "overall": table.overall_score,
            "tier": table.tier,
            "dimensions": [
                {"id": d.id, "label": d.label, "weight": d.weight, "score": d.score}
                for d in table.dimensions
            ],
        },
        "findings": [],
    }
    for d in table.dimensions:
        for c in d.checks:
            if c.status == "deferred":
                continue
            payload["findings"].append({
                "finding_id": c.rule_id,
                "dimension_id": d.id,
                "title": c.title,
                "status": c.status,
                "severity": c.severity,
                "detail": c.detail,
            })

    # Metadata context — bounded summary when metadata was provided.
    meta_check = next(
        (c for d in table.dimensions for c in d.checks
         if c.rule_id == "metadata_dictionary" and c.evidence),
        None,
    )
    if meta_check and meta_check.evidence.get("weighted_pct") is not None:
        payload["metadata_context"] = {
            "has_metadata": True,
            "coverage_pct": meta_check.evidence.get("weighted_pct", 0),
            "governance_pct": meta_check.evidence.get("governance", 0),
            "technical_pct": meta_check.evidence.get("technical", 0),
            "operational_pct": meta_check.evidence.get("operational", 0),
            "business_pct": meta_check.evidence.get("business", 0),
        }

    return json.dumps(payload, indent=2, sort_keys=False)


def _allowed_finding_ids(table: TableAssessment) -> set[str]:
    """Set of rule_ids the LLM is allowed to cite in recommendations.

    Deferred checks are excluded — those are human-attestation-only.
    """
    return {
        c.rule_id
        for d in table.dimensions
        for c in d.checks
        if c.status != "deferred"
    }


def _drop_unknown_recommendations(
    out: SynthesizerOutput, allowed: set[str],
) -> SynthesizerOutput:
    """Anti-hallucination filter: silently drop any recommendation whose
    `finding_id` doesn't match an input finding. The narrative and
    strengths pass through unchanged — they are bounded by length and
    content review happens at the FE."""
    kept: list[SynthesizerRecommendation] = [
        r for r in out.recommendations if r.finding_id in allowed
    ]
    if len(kept) != len(out.recommendations):
        dropped = len(out.recommendations) - len(kept)
        logger.warning(
            "%s synthesizer: dropped %d recommendation(s) with unknown finding_id",
            _L, dropped,
        )
    return out.model_copy(update={"recommendations": kept})


def _fallback(table: TableAssessment) -> SynthesizerOutput:
    """Rule-based synthesizer output, used when the LLM is unavailable or
    its output cannot be parsed. The same anti-hallucination contract
    applies: recommendations cite real finding_ids; nothing is invented.
    """
    strengths: list[str] = []
    recs: list[SynthesizerRecommendation] = []

    # Walk findings deterministically so the fallback output is stable.
    for d in table.dimensions:
        for c in d.checks:
            if c.status == "pass":
                strengths.append(c.title)
            elif c.status in ("fail", "warn") and c.recommendation:
                priority = (
                    "high" if c.severity == "blocker" or c.status == "fail"
                    else "medium"
                )
                recs.append(SynthesizerRecommendation(
                    finding_id=c.rule_id,
                    priority=priority,
                    title=c.recommendation[:200],
                    detail=c.detail[:600],
                ))

    if table.gated_by:
        narrative = (
            f"{table.table_name} is gated at {table.overall_score}/100 — "
            f"{len(table.gated_by)} blocker(s) must be resolved before AI use."
        )
    elif table.tier == "green":
        narrative = (
            f"{table.table_name} scores {table.overall_score}/100 and is "
            f"AI-ready. Address the listed recommendations to keep it strong."
        )
    elif table.tier == "yellow":
        narrative = (
            f"{table.table_name} scores {table.overall_score}/100 — "
            f"conditional. Resolve the priority recommendations before "
            f"production AI use."
        )
    else:
        narrative = (
            f"{table.table_name} scores {table.overall_score}/100 — "
            f"requires remediation across multiple dimensions before AI use."
        )

    return SynthesizerOutput(
        narrative=narrative,
        strengths=strengths[:10],
        recommendations=recs[:7],
    )


async def synthesize(table: TableAssessment) -> tuple[SynthesizerOutput, str | None]:
    """Run the synthesizer on one table.

    Returns:
        (output, fallback_reason). On success, fallback_reason is None.
        On any failure the deterministic fallback is returned and
        fallback_reason names the cause (e.g. "missing_credentials").

    The function NEVER raises — failure is observable but non-fatal so
    the assessment still completes.
    """
    body = _serialize_findings_for_prompt(table)
    prompt = (
        f"{SYNTHESIZER_PREFIX}\n\n"
        f"{wrap_untrusted('table_findings', body)}\n"
    )

    try:
        out = await client.call_model(prompt, schema=SynthesizerOutput)
    except LLMUnavailable as e:
        return _fallback(table), str(e) or "unavailable"
    except LLMSchemaError as e:
        logger.warning("%s synthesizer: schema error, falling back: %s", _L, e)
        return _fallback(table), "schema_error"
    except Exception as e:  # noqa: BLE001 — fallback must always succeed
        logger.warning("%s synthesizer: unexpected error, falling back: %s",
                       _L, type(e).__name__)
        return _fallback(table), "unexpected_error"

    return _drop_unknown_recommendations(out, _allowed_finding_ids(table)), None
