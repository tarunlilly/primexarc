"""Evidence narrator — generates enriched_detail for each check in a table.

Called after scoring is complete. Uses the evidence narrator prompt to produce
richer prose from deterministic findings. Falls back gracefully (returns empty
dict) when LLM is unavailable or call fails — the deterministic detail remains.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from core.models import TableAssessment
from llm.guardrails import wrap_untrusted

logger = logging.getLogger(__name__)


def _build_input(table: TableAssessment) -> str:
    """Build the JSON input payload from a scored table's checks."""
    checks_payload: list[dict[str, Any]] = []
    for dim in table.dimensions:
        for c in dim.checks:
            if c.status == "deferred":
                continue
            entry: dict[str, Any] = {
                "rule_id": c.rule_id,
                "title": c.title,
                "detail": c.detail,
                "status": c.status,
            }
            if c.expected:
                entry["expected"] = c.expected
            if c.evidence:
                # Only include simple evidence keys, not huge objects
                entry["evidence"] = {
                    k: v for k, v in c.evidence.items()
                    if isinstance(v, (str, int, float, bool, list))
                }
            checks_payload.append(entry)

    payload = {
        "table_name": table.table_name,
        "checks": checks_payload[:40],  # Cap to avoid token overflow
    }
    return json.dumps(payload, indent=2)


def _parse_response(raw: str, table: TableAssessment) -> dict[str, str]:
    """Parse LLM JSON response into {rule_id: enriched_detail} mapping.

    Applies anti-hallucination filter: only keeps rule_ids present in input.
    """
    # Strip markdown fences if present
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        items = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Evidence narrator: failed to parse JSON response")
        return {}

    if not isinstance(items, list):
        return {}

    # Build allowed rule_ids set
    allowed = set()
    for dim in table.dimensions:
        for c in dim.checks:
            allowed.add(c.rule_id)

    result: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        rule_id = item.get("rule_id", "")
        enriched = item.get("enriched_detail", "")
        if rule_id in allowed and enriched and len(enriched) <= 400:
            result[rule_id] = enriched[:300]

    return result


async def narrate_evidence(table: TableAssessment) -> dict[str, str]:
    """Generate enriched detail text for each check in a table.

    Returns {rule_id: enriched_detail} mapping. Falls back to empty dict
    (no-op — deterministic detail stays as-is) when LLM unavailable.
    """
    from config import settings

    # Check LLM availability
    if not all([settings.client_id_llm, settings.tenant_id_llm,
                settings.client_secret_llm, settings.model_config_name]):
        return {}

    try:
        from llm.client import call_model
        from llm.prompts.evidence_narrator import EVIDENCE_NARRATOR_PREFIX

        user_input = _build_input(table)
        prompt = (
            f"{EVIDENCE_NARRATOR_PREFIX}\n\n"
            f"{wrap_untrusted('findings', user_input)}"
        )

        raw = await call_model(prompt)
        return _parse_response(raw, table)

    except Exception as exc:
        logger.warning(
            "Evidence narrator LLM call failed: %s — skipping enrichment",
            str(exc)[:100],
        )
        return {}
