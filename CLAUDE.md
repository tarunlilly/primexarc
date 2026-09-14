# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> Read on every session. Follow without exception.
> This is the governance file for merging **PrimeData** (unstructured data platform) and **ARC** (structured data / AI Readiness Evaluator) into one product, one repo, one auth model - while keeping their engines separate.
> For the source-of-truth comparison that this merger is based on, see `primedata-vs-arc-platform-report.md` at repo root.

---

## 0. Current status and prerequisites

**Repo state (updated 2026-09-15):** All three apps are migrated and contain substantial codebases.
`packages/shared-ui` remains a placeholder, consistent with the "extract last" sequencing.

**Infra decision (locked 2026-09-08):** PrimeData's existing namespace (`primedata-dev`) and RDS instance (`primedata-db-dev`) are the baseline for the unified platform.
ARC gets a new `history_assessment` schema on that same RDS and equivalent resources inside `primedata-dev`, replacing its separate `ibu-ai-ready-data-dev` namespace over time.
See `docs/unification-runbook.md` for the step-by-step execution plan.

**Migration sequence** (confirmed - see `repo-migration-agent`):
1. Governance scaffold (done)
2. `apps/structured` - ARC imported from `ibu-ai-ready-data` (done)
3. `apps/unstructured` - PrimeData imported from `primedata-ui` + `primedata-backend` (done)
4. `apps/shell` - landing page, toggle, Help/Support built with Bouncer auth (done)
5. `packages/shared-ui` - extract shared tokens/chrome (pending - last, once both apps are stable)

**Prerequisites:**
- `jq` must be installed (`brew install jq` on macOS, `apt-get install jq` on Linux) - all five hooks depend on it. If missing, hooks fail *open* with a warning and guardrails go silently inert.
- Hook scripts must be executable: `chmod +x .claude/hooks/*.sh`
- Claude Code must run from the repo root (hook paths in `settings.json` are relative).

**Target runtime versions** (from source repos):
- Python 3.11+ (ARC requires 3.11; PrimeData runs 3.11/3.12)
- Node 20 (ARC CI uses 20; PrimeData's Dockerfile uses 18 but should align upward)

---

## 1. What PrimeXarc is

One landing experience, two engines:

- **Structured** = ARC, in `apps/structured/` (migrated from `ibu-ai-ready-data`). Assesses CSVs and DB schemas against a 9-dimension AI-readiness framework. **Never mutates user data.**
- **Unstructured** = PrimeData, in `apps/unstructured/` (migrated from `primedata-ui` + `primedata-backend`). Ingests, cleans, chunks, embeds, and indexes documents. **Actively transforms and stores derived data.**

These two engines have opposite risk profiles (see report §1–§3). The merger's job is to give them one front door and one identity, **not** to homogenize their internals. Where this file says "keep separate," that is not a style preference — it is because ARC's determinism and non-mutation guarantees are load-bearing product promises, and collapsing them into PrimeData's transform-and-persist model would break those guarantees silently.

## 2. Target architecture (proposed — confirm before large structural moves)

```
PrimeXarc/
├── apps/
│   ├── shell/           # landing page, split-screen toggle, Help, Support, auth bootstrap
│   ├── structured/       # ARC — migrated from ibu-ai-ready-data (frontend/ + backend/)
│   └── unstructured/     # PrimeData — migrated from primedata-ui + primedata-backend
├── packages/
│   └── shared-ui/        # design tokens, Help/Support content, shared layout chrome ONLY
├── docs/
└── .claude/
```

- **`apps/shell`** owns: the landing page, the toggle UI, Help Center, Support, and account/session bootstrap. It contains no assessment or pipeline logic of either product.
- **`packages/shared-ui`** may contain: design tokens, typography, the Help/Support page shell, nav chrome, auth session hook. It may **never** contain: scoring logic, pipeline logic, dimension/rule definitions, chunking/embedding code, or anything that imports from `core/`, `llm/`, `ingestion_pipeline/`, or `aird_stages/` in either app.
- Routing: each app keeps its own hostname (subdomain-per-service, matching PrimeData's existing CATS pattern). The shell links to each app's real hostname via plain `<a href>` tags - not path prefixes, not React Router `<Link>`. Production hostnames are injected at deploy time via `window.__ENV__`, not baked at build time. The `/api/v1/*` collision between the two backends is avoided because the three origins never overlap.

## 3. Hard rule: functional separation

1. **No cross-app imports.** Code in `apps/structured/**` may not import from `apps/unstructured/**` or vice versa, except through `packages/shared-ui`. Enforced by a `PreToolUse` hook (`enforce-boundary.sh`) — it is a hard block, not a request for review.
2. **ARC's existing Prime Directives survive the merge unchanged**, scoped to `apps/structured/`: scorer purity (no I/O, no LLM calls in `core/scorer.py`), the single LLM boundary (`llm/` package, `advise()` only, additive-only — never writes `score`/`tier`/`gated_by`), the `test_scorer_is_deterministic()` test, and the source-DB-credential non-persistence rule. ARC's own `.claude/agents/` (db-security-review, llm-security-guardrails, llm-anti-hallucination, testing-agent, etc.) migrate with it and keep authority over `apps/structured/`.
3. **PrimeData's pipeline model survives unchanged**, scoped to `apps/unstructured/`: Airflow DAG, chunking/embedding, vector-store-as-metadata-source-of-truth. Do not force it into ARC's no-I/O discipline — it is a different kind of product and that is intentional.
4. **Two different DB schema strategies must not collide.** ARC uses a fixed `history_assessment` schema (4 tables, provisioned out-of-band). PrimeData uses a parameterized `POSTGRES_SCHEMA` (default `public`, 20+ tables). When both land in one repo, they may share a Postgres instance but **must use distinct schemas** — never let PrimeData's `POSTGRES_SCHEMA` default to `history_assessment` or vice versa. Any DB change in either app requires the `db-security-review` gate (already wired for ARC; extend the same hook pattern to `apps/unstructured/**/db/**` before that app's first schema change lands).
5. **LLM boundaries are per-app, not shared.** ARC's LLM use is narration-only, additive, single-entry-point. PrimeData's LLM use transforms content mid-pipeline. Do not create a shared "LLM service" package that both call — that would either weaken ARC's containment or awkwardly constrain PrimeData. If both eventually call Cortex, they may share the *auth token acquisition* helper (OAuth client-credentials boilerplate) but not a shared prompt/inference wrapper.

## 4. Hard rule: one auth model

Goal (per product decision): **same authentication for the user, PrimeData's model and credentials primary.**

- PrimeData's current model: **Bouncer**, the CATS ingress auth proxy, handles the full Azure AD/OIDC flow and injects `X-USER-EMAIL` / `X-USER-NAME` / `X-UPN` headers. No in-app login, no MSAL.
- ARC's current model: in-app MSAL redirect flow + backend JWKS/RS256 validation of a bearer token.
- **Target state:** Bouncer becomes canonical for both. ARC's in-app MSAL flow is deprecated in favor of ingress-injected identity, matching PrimeData.
- **This is a security-sensitive migration, not a copy-paste.** ARC's backend currently does real cryptographic token verification; PrimeData's backend currently trusts ingress-injected headers. Trusting headers is only safe if the ingress network-isolates the app so a client can never set those headers directly (PrimeData's ingress does this today — confirm the same NetworkPolicy/ingress config applies to `apps/structured` before cutting ARC over). **Any change to auth flow in either app requires the `auth-unification-reviewer` agent before merging.**
- Do not delete ARC's MSAL code until the Bouncer-based replacement is verified end-to-end in a non-prod environment. Keep both paths available behind a flag during transition.
- Source-DB credentials (ARC) and connector credentials (PrimeData) are a **separate concern** from user auth — do not conflate them. ARC's rule (never persist user-supplied source-DB credentials in any form) does not change; PrimeData's connector-credential storage does not change either.

## 5. Hard rule: package management (org policy)

**Lilly requires JFrog Artifactory for all packages. Direct npm/PyPI is prohibited.** This is an org-wide instruction, not a project preference.

- ARC's CI already does this correctly (writes an Artifactory-scoped `.npmrc` in `ci.yml`).
- PrimeData's UI now has an Artifactory `.npmrc` in `apps/unstructured/frontend/` (previously a known gap - see platform report §7.4, now resolved during migration).
- The `artifactory-compliance` agent and the `enforce-artifactory.sh` hook block new `.npmrc` / `requirements.txt` / Dockerfile changes that reference a non-Artifactory registry.

## 6. Design system: shared, but only in `packages/shared-ui`

- Help, Support, and the landing/toggle page use ONE design language. ARC's tokens (Fraunces / Bricolage Grotesque / Apple system stack / JetBrains Mono, HSL CSS variables, `#C41A1A` red) are the intended baseline — they already follow Lilly-appropriate typography discipline and explicitly ban AI-default fonts (Inter, Roboto, Lato, Open Sans) and emoji in UI. PrimeData currently uses Inter and raw hex arbitrary values; **this is the piece that changes to match ARC, not the reverse**, when building `packages/shared-ui`.
- Each engine's *internal* pages (the assessment wizard, the pipeline dashboard) keep their own product-specific UI — only the shell chrome, Help, and Support must look identical.
- No hex colors outside CSS variables. No inline `style={{}}`. Tailwind utilities only. See `apps/structured`'s existing frontend rules (to be migrated into `packages/shared-ui`'s own CLAUDE.md) for the full standard.

## 7. Known pre-existing issues to fix during migration, not carry forward

From the platform comparison report — do not silently perpetuate these:

- PrimeData UI has zero tests; PrimeData's CI test job is commented out; the one active PrimeData test job runs Python 3.9 against 3.11/3.12 code.
- ARC's CI runs no tests at all despite 198 test functions existing.
- ARC has 14 documented doc-vs-code drifts (tier thresholds, phase status, route counts, archetype counts — see report §9). Do not copy stale docs verbatim into this repo's `docs/`; verify against code first.
- Two coexisting metadata-scoring formulas in ARC (`_r_dictionary_present` vs `_build_metadata_quality`) — flag to the user before extending either.

## 8. Mechanical enforcement (hooks)

Five `PreToolUse` hooks in `.claude/hooks/` fire automatically via `.claude/settings.json`:

| Hook | Triggers on | Blocks |
|------|-------------|--------|
| `enforce-boundary.sh` | `Edit`, `Write` | Any import path crossing between `apps/structured/**` and `apps/unstructured/**` |
| `enforce-artifactory.sh` | `Bash`, `Edit`, `Write` | `npm install`/`pip install` against public registries; Dockerfile `FROM` non-Artifactory images |
| `require-db-review.sh` | `Edit`, `Write` | DB migration/schema file changes until `db-security-review` agent runs (30-min TTL) |
| `require-merge-safety.sh` | `Bash` | `git commit`/`git push` until `merge-safety` skill has been run (30-min TTL) |
| `block-secrets.sh` | `Edit`, `Write` | Hardcoded secrets, API keys, passwords in source files |

TTL markers: `.claude/.last-validated` (merge-safety) and `.claude/.last-db-review` (db-review). These are gitignored runtime stamps, not checked in.

## 9. Working agreement (carried over from ARC, applies repo-wide)

1. **Think before coding.** State assumptions. If a request conflicts with this file, stop and ask.
2. **Simplicity first.** No speculative abstraction, no unrequested "flexibility."
3. **Surgical changes.** Touch only what the task requires. Don't refactor adjacent code.
4. **Goal-driven execution.** State a verification plan before multi-step work; loop until it's met.
5. **Writing conventions:** Never use em-dash (use "-" or ":"). In long Markdown, one sentence per line. Never auto-add an agent as commit co-author.
6. **Quality bar:** Prefer quality/robustness/maintainability over development speed. Fix lint failures and test flakiness on sight, even if unrelated to the current task. For UI work, be obsessed with pixel perfection.

## 10. Where to look

| You need | Read |
|---|---|
| Full technical comparison of both platforms | `primedata-vs-arc-platform-report.md` (repo root) |
| Architecture unification feasibility analysis | `docs/architecture-unification-plan.md` |
| Step-by-step unification runbook | `docs/unification-runbook.md` |
| Setup, placement, and first-commit instructions | `SETUP.md` (repo root, historical) |
| ARC's existing hard rules (scoring, LLM, DB, auth) | `apps/structured/CLAUDE.md` |
| ARC's existing specialized agents | `apps/structured/.claude/agents/` |
| Merger-specific agents | `.claude/agents/` (this repo) |
| Deterministic guardrails | `.claude/hooks/` + `.claude/settings.json` (see section 8 above) |
| Pre-push validation | Invoke the `merge-safety` skill |
| Portable rules for non-Claude tools | `AGENTS.md` (repo root) |

## 11. Definition of done for any merger PR

- [ ] `enforce-boundary.sh` passes (no cross-app imports)
- [ ] No non-Artifactory package registry introduced
- [ ] If DB touched: `db-security-review`-equivalent gate passed for the affected app
- [ ] If auth touched: `auth-unification-reviewer` signed off
- [ ] If shared UI touched: confirmed scope is chrome/Help/Support only, not product logic
- [ ] Both apps' existing test suites still pass (do not let one app's CI failure ship silently)
- [ ] `merge-safety` skill run before commit/push
