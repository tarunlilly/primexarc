"""Hybrid-rule adjudicator (v2 stub).

In v1 of Phase 3, every hybrid candidate (target leakage by correlation/
timing, PII confirmation, categorical standardization, missing-data
mechanism) is routed to human attestation. This module exists in v1 only
to freeze the seam so v2 wiring is a config flip, not a refactor:

    if settings.hybrid_route == "adjudicator":
        results = await adjudicate(candidates)

Anything beyond that signature is intentionally absent until v2.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class HybridCandidate(BaseModel):
    """A deferred RuleCheck plus enough context for the adjudicator to
    classify it. v2 will populate; v1 never instantiates."""
    rule_id: str
    table_name: str
    column_name: str | None = None
    detail: str
    evidence: dict


class AdjudicationResult(BaseModel):
    rule_id: str
    classification: Literal["confirmed", "rejected", "uncertain"]
    confidence: float
    rationale: str


async def adjudicate(_candidates: list[HybridCandidate]) -> list[AdjudicationResult]:
    """v2 only. v1 callers must check `settings.hybrid_route` first."""
    raise NotImplementedError(
        "Hybrid adjudication is a v2 feature. v1 routes hybrid candidates "
        "to the human attestation queue. Set settings.hybrid_route="
        "'adjudicator' once the v2 implementation lands."
    )
