"""Purpose narrator — generates a 2-sentence executive summary for the selected purpose.

Called after purpose recomputation. Uses the purpose-summary prompt to produce
a concise explanation of what blocks/enables the declared purpose. Falls back
to a deterministic rule-based summary when LLM is unavailable.
"""
from __future__ import annotations

import json
import logging

from core.models import CapabilityMeasurement, SchemaAssessment
from llm.guardrails import wrap_untrusted

logger = logging.getLogger(__name__)

# Level index → word
_LEVEL_WORDS = ["unknown", "weak", "partial", "solid", "verified"]


def _build_purpose_input(
    assessment: SchemaAssessment,
    purpose_id: str,
    purpose_label: str,
    capabilities: list[CapabilityMeasurement],
    verdict: dict | None,
) -> str:
    """Build the JSON input for the purpose summary prompt."""
    gaps = []
    for cap in capabilities:
        if cap.gap:
            gaps.append({
                "capability": cap.label,
                "measured": _LEVEL_WORDS[cap.level] if cap.level < 5 else "verified",
                "required": _LEVEL_WORDS[cap.required] if cap.required < 5 else "verified",
            })

    # Find top action from action_groups
    top_action = ""
    if assessment.action_groups:
        blockers = [g for g in assessment.action_groups if g.severity == "blocker"]
        if blockers:
            top_action = blockers[0].recommended_fix or blockers[0].issue
        elif assessment.action_groups:
            top_action = assessment.action_groups[0].recommended_fix or assessment.action_groups[0].issue

    tables_gated = sum(1 for t in assessment.tables if t.included and t.gated_by)
    total_tables = sum(1 for t in assessment.tables if t.included)

    payload = {
        "purpose": purpose_label,
        "purpose_id": purpose_id,
        "verdict": verdict.get("verdict", "Conditional") if verdict else "Conditional",
        "fit_floor_failed": not (verdict.get("purpose_fit", True)) if verdict else False,
        "tables_gated": tables_gated,
        "total_tables": total_tables,
        "gaps": gaps,
        "top_action": top_action[:200] if top_action else "",
        "overall_score": assessment.overall_score,
    }
    return json.dumps(payload, indent=2)


def _fallback_summary(
    purpose_label: str,
    capabilities: list[CapabilityMeasurement],
    verdict: dict | None,
    assessment: SchemaAssessment,
) -> str:
    """Deterministic rule-based fallback when LLM is unavailable."""
    gaps = [cap for cap in capabilities if cap.gap]
    tables_gated = sum(1 for t in assessment.tables if t.included and t.gated_by)

    verdict_str = verdict.get("verdict", "Conditional") if verdict else "Conditional"

    if verdict and not verdict.get("purpose_fit", True):
        return (
            f"This data is the wrong fit for {purpose_label}: more than half "
            f"the required capabilities are at unknown level."
        )

    if verdict_str == "Ready":
        minor_count = sum(1 for cap in capabilities if not cap.gap and cap.required > 0)
        return (
            f"The data meets the required floors for {purpose_label}. "
            f"Remaining items are improvements, not gates."
        )

    parts = []
    if tables_gated:
        parts.append(f"{tables_gated} of {sum(1 for t in assessment.tables if t.included)} table(s) gated")

    gap_descs = []
    for g in gaps[:3]:
        measured = _LEVEL_WORDS[g.level] if g.level < 5 else "verified"
        required = _LEVEL_WORDS[g.required] if g.required < 5 else "verified"
        gap_descs.append(f"{g.label} is {measured} where {required} is required")

    if gap_descs:
        parts.append("; ".join(gap_descs))

    reason = ": ".join(parts) if parts else "capability gaps detected"

    # Top action
    top_action = ""
    if assessment.action_groups:
        blockers = [g for g in assessment.action_groups if g.severity == "blocker"]
        if blockers:
            top_action = blockers[0].recommended_fix or blockers[0].issue
        elif assessment.action_groups:
            top_action = assessment.action_groups[0].recommended_fix or assessment.action_groups[0].issue

    sentence1 = f"For {purpose_label}, the verdict is {verdict_str.lower()}: {reason}."
    sentence2 = top_action[:150] if top_action else "Address the highest-severity gaps first."

    return f"{sentence1} {sentence2}"


async def generate_purpose_summary(
    assessment: SchemaAssessment,
    purpose_id: str,
    purpose_label: str,
    capabilities: list[CapabilityMeasurement],
    verdict: dict | None,
) -> str:
    """Generate a 2-sentence purpose-specific executive summary.

    Falls back to deterministic output when LLM credentials are missing
    or the call fails.
    """
    from config import settings

    # Check LLM availability
    if not all([settings.client_id_llm, settings.tenant_id_llm,
                settings.client_secret_llm, settings.model_config_name]):
        return _fallback_summary(purpose_label, capabilities, verdict, assessment)

    try:
        from llm.client import call_model
        from llm.prompts.purpose_summary import PURPOSE_SUMMARY_PREFIX

        user_input = _build_purpose_input(
            assessment, purpose_id, purpose_label, capabilities, verdict,
        )
        prompt = (
            f"{PURPOSE_SUMMARY_PREFIX}\n\n"
            f"<untrusted-data>\n{wrap_untrusted(user_input)}\n</untrusted-data>"
        )

        raw = await call_model(prompt)
        # The response should be plain prose (2 sentences), not JSON
        summary = raw.strip().replace("```", "").strip()
        # Enforce length limit
        if len(summary) > 400:
            summary = summary[:397] + "..."
        return summary

    except Exception as exc:
        logger.warning(
            "Purpose narrator LLM call failed: %s — using fallback", str(exc)[:100]
        )
        return _fallback_summary(purpose_label, capabilities, verdict, assessment)
