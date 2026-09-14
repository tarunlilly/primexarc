"""Verdict computation — fit-floor → gates → gaps → verdict.

Pure function. No I/O, no LLM. Deterministic given the same inputs.

Decision chain:
  1. fit-floor: does the capability vector have enough signal for this purpose?
  2. gates: are any blocker-severity rules unresolved for this archetype?
  3. gaps: which capabilities fall below the archetype's floor?
  4. verdict: Ready | Conditional | At Risk | Purpose Mismatch
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from core.models import ArchetypeConfig, CapabilityMeasurement


class CapabilityGap(BaseModel):
    """One capability that falls below the archetype's required floor."""
    capability_id: str
    label: str
    measured: int
    required: int
    blocking_findings: list[str] = Field(default_factory=list)  # finding_uids


class VerdictResult(BaseModel):
    """The purpose-relative verdict for a table."""
    verdict: str  # "Ready" | "Conditional" | "At Risk" | "Purpose Mismatch"
    purpose_fit: bool
    gates_passed: bool
    gaps: list[CapabilityGap] = Field(default_factory=list)
    archetype_id: str = ""
    archetype_label: str = ""


def compute_verdict(
    capabilities: list[CapabilityMeasurement],
    archetype: ArchetypeConfig | None,
    gated_by: list[str],
) -> VerdictResult:
    """Compute a purpose-relative verdict.

    Without an archetype, returns a generic verdict based on gating only.
    With an archetype, evaluates: fit-floor → gates → gaps.
    """
    if archetype is None:
        # No purpose selected — generic verdict from gating
        if gated_by:
            return VerdictResult(
                verdict="At Risk", purpose_fit=True, gates_passed=False,
            )
        return VerdictResult(
            verdict="Conditional", purpose_fit=True, gates_passed=True,
        )

    cap_map = {c.id: c for c in capabilities}

    # ── Stage 1: Fit-floor check ────────────────────────────────────────
    # Does the data even have the structural shape for this purpose?
    # If more than half the required capabilities are at level 0, it's a mismatch.
    required_caps = archetype.capability_floor
    zero_count = sum(
        1 for cap_id in required_caps
        if cap_map.get(cap_id) and cap_map[cap_id].level == 0
    )
    if required_caps and zero_count > len(required_caps) / 2:
        return VerdictResult(
            verdict="Purpose Mismatch",
            purpose_fit=False,
            gates_passed=False,
            archetype_id=archetype.id,
            archetype_label=archetype.label,
            gaps=[
                CapabilityGap(
                    capability_id=cap_id,
                    label=cap_map[cap_id].label if cap_id in cap_map else cap_id,
                    measured=cap_map[cap_id].level if cap_id in cap_map else 0,
                    required=floor,
                    blocking_findings=cap_map[cap_id].evidence if cap_id in cap_map else [],
                )
                for cap_id, floor in required_caps.items()
                if cap_id in cap_map and cap_map[cap_id].level == 0
            ],
        )

    # ── Stage 2: Gates ──────────────────────────────────────────────────
    # Are any archetype-specific blocker rules unresolved?
    archetype_gates = set(archetype.gate_set)
    active_gates = [rid for rid in gated_by if rid in archetype_gates]
    gates_passed = len(active_gates) == 0

    # ── Stage 3: Gaps ───────────────────────────────────────────────────
    # Which capabilities fall below the archetype's floor?
    gaps: list[CapabilityGap] = []
    for cap_id, required_level in required_caps.items():
        measured = cap_map.get(cap_id)
        if not measured:
            continue
        if measured.level < required_level:
            gaps.append(CapabilityGap(
                capability_id=cap_id,
                label=measured.label,
                measured=measured.level,
                required=required_level,
                blocking_findings=measured.evidence,
            ))

    # ── Stage 4: Verdict ────────────────────────────────────────────────
    if not gates_passed:
        verdict = "At Risk"
    elif gaps:
        verdict = "Conditional"
    else:
        verdict = "Ready"

    return VerdictResult(
        verdict=verdict,
        purpose_fit=True,
        gates_passed=gates_passed,
        gaps=gaps,
        archetype_id=archetype.id,
        archetype_label=archetype.label,
    )
