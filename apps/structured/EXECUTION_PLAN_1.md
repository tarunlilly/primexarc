# ARC v3 — Execution Plan

**Status:** Active. This document captures the durable invariants and phasing roadmap for the ARC evaluator restructure.

---

## Durable Invariants (never violated regardless of phase)

1. **Scorer purity** — `ScoringEngine` has zero LLM calls, zero I/O, zero randomness. Same input → same output.
2. **LLM boundary** — Only `app/backend/llm/` calls external LLMs. `advise()` is the single public entry point.
3. **Fallback always works** — When LLM credentials are empty, assessments complete with rule-based output.
4. **Privacy** — Raw CSV rows never leave `CSVParser`. Masked samples only (max 20 values/column, truncated at 40 chars).
5. **Determinism** — Every number in a rendered report traces to a rule record, profile fact, or computed simulation.
6. **Evidence bundles are immutable** — Once persisted, rescores reference the bundle by hash.
7. **LLM evidence is additive** — LLM claims can escalate findings but never clear, downgrade, or suppress one.
8. **Confidence gating** — Claims below threshold route to attestation only; they never affect scores.

---

## Architecture (v3)

```
PLANE 1  EVIDENCE   profiler facts · metadata claims · LLM annotations · attestations
                    → frozen EvidenceBundle

PLANE 2  JUDGMENT   deterministic rules + capability levelers consume the bundle
                    → findings, dimension scores, capability levels, gaps, gates

PLANE 3  LANGUAGE   LLM prioritizes + rationalizes per purpose (budgeted)
                    → narrative, strengths, recommendations (never computes numbers)
```

---

## Capability Model (14 capabilities, 0–4 levels)

SEM · JOIN · GOV · AGG · ACC · FRS · LBL · LKG · SIG · STA · TMP · VOL · LIN · TXT

Levels computed by pure functions over the evidence bundle → reproducible.
`readiness(purpose) = measured_vector ⊒ required_vector`. Every unmet cell is a gap.

---

## Purpose Model (3 layers)

1. **Family** — Agent Access · Retrieval · Model Dev · Serving
2. **Archetype** — 13 config-driven use-case patterns (YAML in `config/archetypes/`)
3. **Contract** — Archetype + declared constraints (freshness SLA, sensitivity ceiling, etc.)

---

## Phasing

| Phase | Scope |
|---|---|
| P1 Engine | Capabilities, lens tagging, archetypes, finding UIDs, verdict, attestation API |
| P2 Report IA | Lens cards, cross-linking, capability section, attestation UX, a11y |
| P3 Annotator | Shadow mode → promote to evidence |
| P4 Hardening | Export versioning, history deltas, governance |

---

## Verdict Decision Chain

```
fit-floor check (purpose mismatch?)
    → gates (unresolved blockers for this archetype?)
        → capability gaps (which capabilities fall below the floor?)
            → verdict: Ready | Conditional | At Risk | Purpose Mismatch
```

Lens scores (DQ/ML/AI) are progress indicators only — they never gate.
