# ARC Phase 3 — LLM Integration (Cortex, Synthesizer-Only First Cut)

> **Status:** built. The deterministic core, the LLM synthesizer, the FE
> report view, and the Phase 3 test suite are all merged. v2 adjudicator
> and attestation review UI remain deferred (named, not dropped).

## Context

Phase 3 introduces an LLM-powered narrative + recommendations layer that
runs *on top of* the deterministic scorer. The LLM does **not** compute
scores. It explains them, prioritizes the existing recommendations, and
extracts a list of strengths from `pass`-status findings.

Everything in this doc is governed by **The Prime Directive** (CLAUDE.md
+ EXECUTION_PLAN_1.md A2): the LLM never produces a number, metric, or
score. Python does. The LLM is purely additive.

---

## What's running

| Concern | Status | Where |
|---|---|---|
| Cortex OAuth client | Built | `app/backend/llm/client.py` |
| Synthesizer (one call/table) | Built | `app/backend/llm/synthesizer.py` |
| Anti-hallucination filter | Built | `synthesizer._drop_unknown_recommendations` |
| SECURITY_GUARDRAILS prefix | Built | `app/backend/llm/guardrails.py` |
| `wrap_untrusted` injection fence | Built | `app/backend/llm/guardrails.py` |
| Single integration seam | Built | `app/backend/llm/advisor.py` → `advise()` |
| Splice into both jobs | Built | `app/backend/api/assess.py` |
| New tier bands ≥80/60/<60 | Built | `app/backend/core/scorer.py` |
| Blocker gating | Built | `core/scorer.py`, `core/dimensions.py` |
| Applicability + renormalization | Built | `core/scorer.py` |
| Hybrid → deferred routing | Built | `core/dimensions.py` (`privacy_values`, `labels_leakage`) |
| FE gating banner / narrative / strengths / deferred | Built | `app/frontend/src/pages/Dashboard.jsx` |
| Phase 3 test suite | Built | `tests/test_scorer_phase3.py`, `tests/test_llm.py` |
| v2 adjudicator | **Stub only** | `app/backend/llm/adjudicator.py` |
| Attestation review UI + write API | **Deferred** | follow-up PR |
| `attestation_queue` DB table | **Deferred** | needs `db-security-review` |
| Bulk-tier model | Reserved env slot | `settings.model_config_name_bulk` |
| YAML rule packs | **Out of scope** | dimensions stay in Python |

---

## Cortex setup

Single model in v1: `ai-red-data` (Claude Opus 4.7, `temperature=0`,
`max_response_token_size=128000`). Set server-side in the Cortex
config — the client only carries the prompt text.

### OAuth flow

1. POST `https://login.microsoftonline.com/{TENANT_ID_LLM}/oauth2/v2.0/token`
   with `grant_type=client_credentials`, `scope=api://Cortex.lilly.com/.default`.
2. Returns a bearer token. Cached per-process until `exp - 60s`.

### Inference call

`GET {CORTEX_BASE_URL}/model/ask/{MODEL_CONFIG_NAME}?q=<prompt>` with
`Authorization: Bearer <token>`.

### Env vars

Sourced from AWS Secrets Manager `ibu-arc-dev/ibu-ai-ready-data/cortex-llm`
via the `ibu-ai-ready-data-cortex-llm` ExternalSecret in the K8s manifest
repo (`secret.yaml` + `deploy.yaml`):

| Env var | Settings field | Purpose |
|---|---|---|
| `CLIENT_ID_LLM` | `settings.client_id_llm` | Cortex SP App ID |
| `TENANT_ID_LLM` | `settings.tenant_id_llm` | Cortex SP Directory ID |
| `CLIENT_SECRET_LLM` | `settings.client_secret_llm` | Cortex SP secret |
| `MODEL_CONFIG_NAME` | `settings.model_config_name` | `ai-red-data` |
| `CORTEX_BASE_URL` | `settings.cortex_base_url` | Default: `https://gateway.apim.lilly.com/cortex` |
| `MODEL_CONFIG_NAME_BULK` | `settings.model_config_name_bulk` | Reserved for v2 |
| `HYBRID_ROUTE` | `settings.hybrid_route` | `human_attestation` (v1) or `adjudicator` (v2) |

When any of the four cred fields is empty, `client._acquire_token()`
raises `LLMUnavailable("missing_credentials")`. The synthesizer catches
this and returns a rule-based fallback. **The assessment always completes.**

---

## Pipeline

```
TableProfile + MetadataProfile (existing — no changes)
        │
        ▼
ScoringEngine.score_schema() →  SchemaAssessment
   - Applicability resolver drops N/A dimensions
   - Per-dimension score (pass=1 / warn=0.5 / fail=0; deferred excluded)
   - Weighted average across active dimensions (renormalized)
   - Blocker gating: blocker fail → cap at 59, append to gated_by
   - Hybrid rules → status=deferred, routed to TableAssessment.deferred[]
   - Tier band: ≥80 green / 60-79 yellow / <60 red
        │
        ▼
llm.advise(assessment) → SchemaAssessment (enriched, additive only)
   - asyncio.gather one synthesize() call per table
   - synthesize() input: TableAssessment ONLY (signature-bound)
   - Cacheable prompt prefix + wrap_untrusted'd findings tail
   - Schema-validated output (SynthesizerOutput); retry once on parse fail
   - Anti-hallucination filter drops recs citing unknown finding_ids
   - Fallback path on any failure (creds, net, schema)
   - Stamps assessment.llm = LLMMetadata(used, model_config_name, fallback_reason)
        │
        ▼
job_store.mark_done(assessment) → history persistence (existing)
        │
        ▼
FE Dashboard renders:
   - GatingBanner (if gated_by non-empty)
   - TierHero (existing)
   - NarrativeCard (narrative + strengths + LLM-used badge)
   - PrioritizedRecommendations (LLM list with finding_id evidence; falls
     back to top_priorities when LLM didn't run)
   - DeferredSection (collapsible — hybrid candidates awaiting attestation)
   - BreakdownSection (existing 9-dim view)
```

---

## Hybrid rules (deferred → human attestation)

v1 routes EVERY hybrid candidate to humans. The seam is fixed so v2 is a
config flip, not a refactor:

```python
# v1 — always human (current)
# v2 — flip via settings.hybrid_route = "adjudicator"
```

Tagged hybrid rules in v1:

| rule_id | Dimension | Severity | Trigger |
|---|---|---|---|
| `privacy_values` | privacy | warning | Email/SSN regex match in sample values |
| `labels_leakage` | labels | **blocker** | Post-event-named column (`*_outcome`, `_resolved`, `_followup`, …) alongside a target |

Deferred RuleChecks:
- **DO NOT** count toward pass/warn/fail in any dimension's score.
- **DO** appear in `TableAssessment.deferred[]`.
- **NEVER** reach the synthesizer prompt — `_serialize_findings_for_prompt`
  filters them out before LLM input is built.
- **NEVER** appear in `SynthesizerOutput.recommendations` — they are not in
  `_allowed_finding_ids()`, so the anti-hallucination filter would drop
  any rec citing them anyway.

---

## Anti-hallucination contract

Every `SynthesizerOutput.recommendations[i].finding_id` MUST match a
real `RuleCheck.rule_id` in the input `TableAssessment` whose status is
`pass | warn | fail`. Enforced in two places:

1. **Prompt prefix** instructs the model: "Every recommendation MUST cite
   a `finding_id` that appears in the input. If you cannot tie a
   suggestion to a finding, OMIT it. No free-form advice."
2. **Post-call filter** (`_drop_unknown_recommendations`) silently drops
   any recommendation whose finding_id isn't in the allowed set.

The narrative and strengths fields pass through unchanged but are
length-capped (1200 / 200 chars) and item-capped (10 / 10 / 7) in the
schema.

---

## Failure modes

| Cause | Result | Visible to user? |
|---|---|---|
| Missing creds | `LLMUnavailable("missing_credentials")` | Badge: "Rule-based fallback" |
| Network / Azure AD failure | `LLMUnavailable("oauth_failed")` | Badge: "Rule-based fallback" |
| Cortex 4xx/5xx | `LLMUnavailable("inference_failed")` | Badge: "Rule-based fallback" |
| Schema invalid after retry | `LLMSchemaError` → fallback | Badge: "Rule-based fallback" |
| Any unexpected exception | Caught, fallback runs | Badge: "Rule-based fallback" |

The fallback path is exercised in tests (`test_advisor_populates_narrative_via_fallback`)
and is the default in local development (`.env` typically has empty Cortex creds).

---

## Audit / reproducibility

Every assessment carries `SchemaAssessment.llm`:

```python
class LLMMetadata(BaseModel):
    used: bool                          # did the LLM actually run?
    model_config_name: str | None       # e.g. "ai-red-data"
    fallback_reason: str | None         # e.g. "missing_credentials"
```

Persisted to `history_assessment.assessment_runs` alongside the rest of
the assessment. Reproducibility test: `test_advisor_never_mutates_deterministic_fields`
locks in that score / tier / gated_by / dimensions / deferred are
byte-identical pre- and post-`advise()`.

---

## Out-of-scope for v1 (named, not dropped)

- **v2 adjudicator** — per-column hybrid rule resolution via LLM. Stub
  exists at `llm/adjudicator.py`; activate by flipping
  `settings.hybrid_route = "adjudicator"` once implemented.
- **Attestation review UI + write API** — v1 surfaces deferred items
  read-only. The DB table (`attestation_queue`) is also deferred to
  follow-up PR (requires `db-security-review` agent).
- **Bulk-tier model** — `MODEL_CONFIG_NAME_BULK` env slot reserved; no
  code path uses it until a second Cortex config exists.
- **YAML rule-pack migration** — dimensions stay in Python.
- **Formal PII masking gate** — ARC already does not send raw rows or
  sample values to the LLM (synthesizer takes `TableAssessment`, not
  `TableProfile`). A dedicated `pii/` module with quasi-identifier
  detection is a later phase.
