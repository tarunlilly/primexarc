# Cortex LLM Integration Reference

> **Status: built (Phase 3, v1).** Single integration seam at
> `app/backend/llm/advisor.py`. Rule-based fallback always works when
> Cortex creds are missing. Full architecture: `app/docs/phase3-llm-integration.md`.

## What is Cortex

Cortex (`cortex.lilly.com`) is Lilly's internal AI platform. It exposes LLM
models behind an Azure-AD-fronted gateway so internal applications can call
models without direct provider SDK dependencies and within Lilly's compliance
boundary.

**API documentation:** https://cortex.lilly.com/spe/documentation/api-and-sdks/api/apim/
(auth-walled — paste content into the conversation when needed)

## Model in use

`ai-red-data` — Claude Opus 4.7 (`temperature=0`, `max_response_token_size=128000`,
non-reasoning, non-multimodal in our usage). The Cortex config is set
server-side; we only carry the prompt text.

## Integration point in this repo

All LLM calls go through one package: `app/backend/llm/`. The only public
entry point outside the package is `advise()` (imported in `api/assess.py`).
This is a CLAUDE.md hard rule — no exceptions.

### File layout

| File | Purpose |
|---|---|
| `llm/__init__.py` | Public surface: `advise`, `LLMUnavailable`, `LLMSchemaError` |
| `llm/client.py` | Cortex OAuth + inference + structured-output retry |
| `llm/guardrails.py` | `SECURITY_GUARDRAILS` block; `wrap_untrusted()` fence |
| `llm/prompts/synthesizer.py` | Cacheable stable prefix for the synthesizer |
| `llm/schema.py` | `SynthesizerOutput` pydantic model |
| `llm/synthesizer.py` | One LLM call per table → narrative + strengths + recs |
| `llm/advisor.py` | Fans out per-table calls, merges output additively |
| `llm/adjudicator.py` | **v2 stub** — frozen interface, raises NotImplementedError |
| `llm/exceptions.py` | `LLMUnavailable`, `LLMSchemaError` |

## OAuth flow

```
POST https://login.microsoftonline.com/{TENANT_ID_LLM}/oauth2/v2.0/token
  grant_type=client_credentials
  client_id={CLIENT_ID_LLM}
  client_secret={CLIENT_SECRET_LLM}
  scope=api://Cortex.lilly.com/.default
```

Returns a bearer token. Cached per-process in `_token_cache` until
`exp - 60s`. Concurrent stale reads are acceptable (Cortex is idempotent
on token issuance).

## Inference call

```
GET {CORTEX_BASE_URL}/model/ask/{MODEL_CONFIG_NAME}?q=<url-encoded prompt>
  Authorization: Bearer <token>
```

`CORTEX_BASE_URL` defaults to `https://gateway.apim.lilly.com/cortex`
(intranet variant `https://gateway-intranet.apim.lilly.com/` works inside
the cluster). Response is parsed via the schema registered in
`call_model(prompt, schema=SynthesizerOutput)`. On parse failure, ONE
retry with a clarifying suffix; if that also fails, `LLMSchemaError` →
fallback.

## Env vars

Sourced from AWS Secrets Manager `ibu-arc-dev/ibu-ai-ready-data/cortex-llm`
via `ibu-ai-ready-data-cortex-llm` ExternalSecret in
`LRL_light_k8s_infra_apps/projects/dev/ibu-ai-ready-data-dev/secret.yaml`.
Mapped to the pod via individual `env:` entries in `deploy.yaml`.

| Env var | `Settings` field | Required? |
|---|---|---|
| `CLIENT_ID_LLM` | `client_id_llm` | Yes (or fallback) |
| `TENANT_ID_LLM` | `tenant_id_llm` | Yes (or fallback) |
| `CLIENT_SECRET_LLM` | `client_secret_llm` | Yes (or fallback) |
| `MODEL_CONFIG_NAME` | `model_config_name` | Yes (or fallback) |
| `CORTEX_BASE_URL` | `cortex_base_url` | No (defaults) |
| `HYBRID_ROUTE` | `hybrid_route` | No (`human_attestation` v1; `adjudicator` v2) |
| `MODEL_CONFIG_NAME_BULK` | `model_config_name_bulk` | No (reserved) |

When any of the four required cred fields is empty, the synthesizer
returns rule-based fallback output and stamps
`assessment.llm.fallback_reason="missing_credentials"`. The assessment
always completes.

## Rules (from CLAUDE.md — never override)

- The LLM never computes a number, metric, or score. Python does.
- The LLM is called from `app/backend/llm/` only. No exceptions.
- The synthesizer's input is `TableAssessment` only — never `TableProfile`,
  never per-column data, never raw rows or sample values.
- Every recommendation cites a real `finding_id` (anti-hallucination
  filter drops the rest).
- `SECURITY_GUARDRAILS` lives at the top of every system prompt.
  All data-derived text is wrapped via `wrap_untrusted()`.
- Output token ceiling is 128K, set in the Cortex model config (`max_response_token_size`). ARC does not pass a per-request cap — the model self-limits via the structured output schema instructions in the prompt.

## Local development

The Cortex creds are absent in `.env` by default. The fallback path is the
default local experience — narrative + strengths + recommendations come
from `synthesizer._fallback()`. The FE Dashboard renders a "Rule-based
fallback" badge in the Assessment Summary card.

To exercise the LLM path locally, paste real values into `app/backend/.env`:

```
CLIENT_ID_LLM=...
TENANT_ID_LLM=...
CLIENT_SECRET_LLM=...
MODEL_CONFIG_NAME=ai-red-data
```

Never commit those values. `.env` is in `.gitignore`; `.env.example`
contains placeholders only.
