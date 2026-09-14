# PrimeXarc Architecture Unification: Feasibility and Implementation Plan

> Grounded in the actual current repo state as of 2026-09-08, not a blank-slate assumption.
> Source comparison: the 22-dimension ARC-vs-PrimeData table supplied by the user.
> Governance: root `CLAUDE.md`, `apps/structured/CLAUDE.md`, `apps/unstructured/CLAUDE.md`, `apps/shell/CLAUDE.md`.

---

## 0. Kubernetes manifest sources (confirmed)

PrimeData's Kubernetes manifests live in `LRL_light_k8s_infra_apps/projects/dev/primedata-dev/`. ARC's live in `LRL_light_k8s_infra_apps/projects/dev/ibu-ai-ready-data-dev/`. The two apps run in two entirely separate namespaces, on two entirely separate domains, with two entirely separate managed databases. This is a materially different starting point for the ingress/namespace parts of the unification plan than a single-namespace assumption would be.

---

## 1. What is actually true today (grounding)

The repo state described in root `CLAUDE.md` section 0 ("Governance scaffold only, no product code migrated") is stale.
Direct inspection of `apps/` shows all three apps already exist as real, substantial codebases:

| App | State |
|---|---|
| `apps/structured` (ARC) | Fully migrated. Backend still validates identity via Azure AD JWKS/RS256 in `dependencies.py` (`require_user()`). No Bouncer code present. Job execution is still `core/job_store.py`, in-process, no Airflow reference anywhere in the backend. |
| `apps/unstructured` (PrimeData) | Fully migrated. Backend auth already Bouncer-based per its own `CLAUDE.md`. Its own `.claude/agents/` now includes `db-security-review.md`, `connector-security.md`, `pipeline-safety.md`, `vector-store.md` — none of which existed in the source repo. These look like a direct response to the gaps flagged in the original comparison report. |
| `apps/shell` | Fully built, not a stub. Bouncer-only auth bootstrap (`src/lib/bouncer-auth.ts`, 50-minute TTL cache), a working `Landing.tsx` with the two-panel "doors" layout and a `md:border-l` divider between them (this matches the original "a line divides the screen in two" concept), routes for `/help`, `/support`, `/account`, ARC's design tokens already applied. |
| `packages/shared-ui` | Still just `NOTE.md`. Not extracted. Consistent with the documented "extract last" sequencing. |
| Root `.claude/agents/` | 14 files: the original 9 merger-specific agents plus 5 promoted from ARC's general-purpose set (`bug-finder`, `code-quality`, `maintainability`, `race-conditions`, `test-flakiness`). Reasonable, since those five are not ARC-specific reviewers. Worth a one-line confirmation with whoever ran the migration that root scope (not `apps/structured/`-scoped) was intentional, but not a conflict with any hard rule. |
| Git | Zero commits. `git log` returns "no commits yet" against ~33k files on disk. Flagged separately as urgent. |

This changes the shape of the answer below in two ways.
Auth unification and job-orchestration unification are not yet started in code, so both are still fully open decisions, not already-made ones to ratify.
And the `/api/v1/*` path collision the root `CLAUDE.md` warned about is confirmed real at the code level: `apps/structured/backend/main.py` mounts its routers at `PREFIX = "/api/v1"`, and `apps/unstructured/backend/src/primedata/api/*.py` defines routers like `APIRouter(prefix="/api/v1/acl")`, `APIRouter(prefix="/api/v1")` (chunks), etc.
Both apps use the same path space, so if they ever share one origin without host- or path-level separation, requests collide.
As of the real k8s manifests (section 1a below), this collision does not currently exist in production, because the two apps are not on one origin — but it will need a deliberate decision once the shell tries to present them as one experience.

### 1a. Real infrastructure, corrected (`primedata-dev` vs `ibu-ai-ready-data-dev`)

Direct inspection of both manifest repos, not the earlier assumption that PrimeData's manifests sit inside ARC's namespace:

| | **ARC** (`ibu-ai-ready-data-dev`) | **PrimeData** (`primedata-dev`) |
|---|---|---|
| Namespace | `ibu-ai-ready-data-dev` | `primedata-dev` |
| Cost center | (not re-verified this pass) | `100ARAS` |
| Public host(s) | `ibu-ard.bu.lilly.com`, path `/` | `primedata.apps.lrl.lilly.com` (auth) and `primedata-frontend.apps.lrl.lilly.com` (auth, appears duplicate/legacy) for frontend; `primedata-api.apps-api.lrl.lilly.com` for backend API |
| Internal/no-auth host(s) | none found | `primedata-frontend.apps-internal.lrl.lilly.com`, `primedata-internal.apps-internal.lrl.lilly.com` (both `ingress.class: ingress-noauth`) |
| Domain suffix | `.bu.lilly.com` | `.apps.lrl.lilly.com` / `.apps-api.lrl.lilly.com` / `.apps-internal.lrl.lilly.com` |
| Routing style | single host, path `/` | **subdomain-per-service**, not path-based — frontend, backend API, and Kibana each get their own hostname |
| Database | RDS Postgres, schema `history_assessment` (per `rds-postgres.yaml`) | **Separate RDS instance** `primedata-db-dev`, Postgres 17.2, `db.t3.small`, dbName `postgres` — not shared with ARC at all, not even the same server |
| Vector/search store | none (ARC has no vector store) | **Elasticsearch 7.16.1**, 3-node StatefulSet + Kibana — this is the actual deployed vector store, which contradicts `apps/unstructured/CLAUDE.md`'s statement that OpenSearch is primary. This is a live doc-vs-infra mismatch, not just the abstract "three coexisting vocabularies" risk noted in the original comparison report — flagging as an open question rather than guessing which one is authoritative. |
| Frontend runtime | Vite + React (per migrated code) | **Manifest env vars say Next.js** (`NEXTAUTH_URL`, `NEXTAUTH_SECRET`, `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_API_BASE`, deploy comment literally says `# FRONTEND (Next.js)`) — but `apps/unstructured/CLAUDE.md` explicitly says the migrated frontend is "Vite SPA, NOT Next.js despite similar structure." Another live doc-vs-infra (or infra-vs-migrated-code) mismatch, flagged rather than resolved by assumption. Possible explanations: the manifest is stale and predates a Vite migration, or prod still runs an older Next.js build than what got migrated into `apps/unstructured`. Needs a direct answer before any ingress/routing decision is finalized, since it changes what "the frontend" even serves. |
| Orchestration | none (in-process `job_store.py`) | Airflow webserver + scheduler + init Job are all defined in `deploy.yaml` — but every one of them sits under a comment block reading `# AIRFLOW (NOT USED IN CATS)`, repeated three times. The resources exist and are presumably deployed (webserver has real liveness/readiness probes, real resource limits), yet are explicitly commented as unused. This is a real, unresolved contradiction, not something to paper over: either these are dead weight (deployed but never actually receiving DAG traffic, e.g. PrimeData's real pipeline execution happens some other way), or the comments are stale. This directly affects step 7 of the implementation plan (routing ARC's assessments through Airflow) — that step should not proceed until this is answered, since building new dependency on infrastructure that "is not used in CATS" would be a mistake. |
| Resources (backend) | not re-verified this pass | requests 8 CPU / 32Gi memory, limits 16 CPU / 64Gi memory — very large for a FastAPI service, worth understanding why before using it as a sizing baseline for anything shared |
| Resources (frontend) | not re-verified this pass | requests 500m CPU / 1Gi memory, limits 1 CPU / 2Gi memory |
| Health probes | `/health` (per `deploy.yaml` line ~113/120) | backend `/health` on 8000; frontend `/` on 3000 (no dedicated health path); Airflow webserver `/health` on 8080 |
| Secrets | ExternalSecrets via AWS Secrets Manager (`secret.yaml`, already verified in the original comparison report) | `SecretStore` wired to AWS Secrets Manager; the actual `ExternalSecret`/`PushSecret` resources in `secrets.yaml` are commented out, and RDS credentials instead flow through `primedata-rds-secrets`, written by the `RDSInstance` Crossplane resource's `writeConnectionSecretToRef` — a different (also valid) mechanism, not a gap |

**Implication for the merger's ingress plan:** PrimeData's real pattern is subdomain-per-service, not the path-prefix scheme (`/structured`, `/unstructured`) assumed earlier in this document and in `apps/shell/CLAUDE.md`'s "App links" section. Section 3 (dimension 15) and step 2 of the implementation plan are corrected below to match the real pattern instead of introducing a new one.

---

## 2. Case for one unified platform, biased toward PrimeData, bounded by existing hard rules

PrimeData is the better default for anything that is genuinely infrastructure, not product logic: its auth model, its job orchestration substrate, its design-token consumption pattern (once shared-ui exists), and its general "always-on service with persistent state" posture are the more scalable shape for a merged platform that will keep growing.
Biasing toward PrimeData is the right call for: authentication, job orchestration substrate, observability approach, and general infra maturity (already has Docker Compose for dev, Airflow, OpenSearch — a fuller platform footprint than ARC's simpler stack).

It is the wrong call, and root `CLAUDE.md` already says so, for anything that is a safety property of ARC specifically: scorer determinism, the single-LLM-boundary/additive-only contract, and source-DB-credential non-persistence.
These are not stylistic differences to average out.
They are the reason ARC's outputs can be trusted as advisory rather than as another data-mutating pipeline.
Collapsing them into PrimeData's transform-and-persist model would not "unify" the platform, it would quietly turn ARC into a second PrimeData with worse guarantees.

So "bias toward PrimeData" is applied dimension by dimension below, not as a blanket direction.

---

## 3. Per-dimension feasibility

Legend: **Bias PrimeData** = adopt PrimeData's approach as the merged default. **Keep both / no change** = the difference is intentional and load-bearing; do not collapse it. **New shared layer** = neither app's current approach wins; build one for both.

| # | Dimension | Current state (verified) | Direction | Core-system impact | Recommendation |
|---|---|---|---|---|---|
| 1 | Auth | ARC: in-app MSAL redirect + backend JWKS/RS256 (`dependencies.py`, still present). PrimeData: Bouncer ingress headers + JWT validation, no in-app login. Shell: Bouncer only, already built. | Bias PrimeData | High. Security-sensitive; changes who can call ARC's API and how identity flows. | Already decided as the target in root `CLAUDE.md` section 4. Not yet started in ARC's code. Requires `auth-unification-reviewer` sign-off before cutover, and network-isolation verification that ARC's ingress strips client-supplied `X-USER-EMAIL`/`X-UPN` headers exactly as PrimeData's does today. Keep MSAL code path alive behind a flag until Bouncer is verified end-to-end in non-prod. |
| 2 | Frontend | ARC: Vite + React 18 + JS (not TS), Tailwind, shadcn/ui. PrimeData: Vite + React 18 + TypeScript strict, Tailwind, TanStack Query. Shell: Vite + React 18 + TypeScript strict, Tailwind. | Bias PrimeData (long-term) | Low to migrate incrementally; high if done as a rewrite. | TypeScript adoption for ARC is worth doing but is a large, low-urgency lift across ~500-line pages. Do not block the merger on it. Track as a follow-up epic, not part of this plan's critical path. |
| 3 | Backend | ARC: FastAPI, in-process job store, no async DB sessions confirmed. PrimeData: FastAPI, SQLAlchemy 2.0 sync sessions, repository pattern, 38 route modules. | Keep both / no change | Medium if forced together. | Both stay FastAPI (already aligned). Do not merge the two backends into one process or one deployable — root `CLAUDE.md` section 3 already forbids this implicitly via the boundary rule, and the risk profiles differ too much (see section 2 above). |
| 4 | ORM | ARC: SQLAlchemy ORM (`db/schema.py`) + Alembic, scoped to `history_assessment`. PrimeData: SQLAlchemy 2.0, 33 Alembic revisions, `POSTGRES_SCHEMA` configurable (default `public`). | Keep both / no change | Medium. Schema collision risk is the real issue, not ORM choice. | Both already use SQLAlchemy + Alembic; no version fight to resolve. The actual hard rule is schema isolation (dimension 5), not ORM alignment. |
| 5 | Database | ARC: fixed `history_assessment` schema, 4 tables, provisioned out-of-band, own RDS instance. PrimeData: configurable schema, default `public`, 20+ tables, 33 migrations, **its own separate RDS instance** (`primedata-db-dev`, Postgres 17.2) confirmed via `primedata-dev/rds.yml` — not the same server as ARC at all. | Keep both / no change | Low today, high if ever consolidated. | The schema-collision risk described in root `CLAUDE.md` section 3.4 is **not live today** — the two apps don't even share a database server, so there is zero real collision risk right now. That rule matters only if a future cost-saving decision consolidates both onto one RDS instance; keep the documented rule as a guardrail for that future decision, but do not spend effort on a runtime guard for a collision that cannot currently occur. |
| 6 | DB credentials (source data, not the apps' own DB) | ARC: source-DB/S3 credentials a user types in are never persisted, memory-only for one assessment. PrimeData: connector credentials are persisted per-connector, encrypted at rest, standard pattern. | Keep both / no change | High if collapsed. | These are different products of different risk categories, not a stylistic gap. ARC's non-persistence rule is a stated Prime Directive. Do not add persistence to satisfy consistency; do not remove PrimeData's persisted-connector pattern either, since PrimeData's connectors are meant to be reused across scheduled runs (that is the point of a connector). |
| 7 | Storage | ARC: no independent object storage; CSVs parsed in memory, capped, dropped. PrimeData: MinIO/S3 for raw and processed documents. | Keep both / no change | Low. | ARC's dimension has no PrimeData-shaped need to backfill; ARC intentionally never stores the source data. Nothing to unify here. |
| 8 | Data flow | ARC: profile in, score out, no mutation, no downstream store beyond assessment history. PrimeData: ingest to connector, preprocess, score, chunk, embed, index, persisted at every stage. | Keep both / no change | High if collapsed. | This is the core distinguishing feature of each product (advisory vs. transformative). Section 2 above covers why this cannot be unified without breaking ARC's value proposition. |
| 9 | Orchestration | ARC: `core/job_store.py`, in-process, no queue, no scheduler, confirmed via code search (`grep -r "airflow" apps/structured/backend` returns nothing). PrimeData: Airflow 2.7 DAG (`dag_primedata_simple.py`), 12 AIRD-stage tasks — **but** the real `primedata-dev/deploy.yaml` labels every Airflow resource (webserver, scheduler, init job) `# AIRFLOW (NOT USED IN CATS)`, repeated three times, while still defining full Deployments with real probes and resource limits for them. | **Open — do not decide yet** | Medium, contingent on resolving the contradiction first. | Do not route ARC's orchestration onto Airflow until it's confirmed whether Airflow is actually live in `primedata-dev` today. If it truly is not used in CATS, then PrimeData's own real pipeline execution happens some other way in production, and building ARC's orchestration on top of Airflow would mean building on infrastructure PrimeData itself doesn't rely on — the opposite of "optimized and simple." This is now an open question for the user/infra owner, not a recommendation, until answered. |
| 10 | LLM usage | ARC: narration-only, additive, single entry point (`llm/advise()`), never mutates score/tier/gating. PrimeData: mid-pipeline content transformation (cleaning, summarization, metadata extraction), mutates document content by design. | Keep both / no change | High if collapsed. | Root `CLAUDE.md` section 3.5 already forbids a shared LLM service package for exactly this reason. Both may eventually share Cortex OAuth client-credential acquisition (pure auth boilerplate) but never a shared prompt or inference wrapper. Nothing to change here beyond what is already documented. |
| 11 | Container | ARC: single Dockerfile per app (frontend, backend). PrimeData: single Dockerfile per app plus `docker-compose.yml` (dev) and `docker-compose.prod.yml`. Shell: no Dockerfile yet (static build, `dist/`). | Bias PrimeData | Low. | Give the shell a minimal Dockerfile (nginx serving `dist/`) matching the pattern already used by both apps' frontends, so all three are containerized the same way. Not urgent, but cheap and closes a real gap. |
| 12 | Namespace | **Corrected.** ARC lives in `ibu-ai-ready-data-dev`. PrimeData lives in its own separate namespace, `primedata-dev`, with its own cost center (`100ARAS`). They have never shared a namespace. | New shared layer, or keep separate + shell bridges | Medium. | Do not force both into one namespace — that would mean re-provisioning RDS, secrets, and service accounts for whichever app moves, for no functional benefit. Give `apps/shell` its own new namespace (or land it in whichever of the two existing namespaces is judged the "home" one) and have it reach both apps via their existing public hostnames. Namespace consolidation is not a prerequisite for the shell to work. |
| 13 | Resources (CPU/mem requests-limits) | **Corrected with real numbers.** PrimeData backend: requests 8 CPU / 32Gi memory, limits 16 CPU / 64Gi memory (`primedata-dev/deploy.yaml`) — large. PrimeData frontend: requests 500m CPU / 1Gi, limits 1 CPU / 2Gi. ARC: not re-verified this pass. | Keep both / no change | Low. | Resource sizing is a per-workload tuning question, not an architecture-unification question. The backend's 8-32Gi request in particular is worth understanding (is it actually using that much, or is it defensively over-provisioned) before using it as a sizing baseline for anything new, like the shell. |
| 14 | Health probes | **Corrected with real paths.** PrimeData backend: `/health` on 8000. PrimeData frontend: `/` on 3000 (no dedicated health path). Airflow webserver: `/health` on 8080 (see the "NOT USED IN CATS" contradiction, dimension 9). ARC: `/health`, matching pattern. | Keep both / no change | Low. | Add a liveness/readiness path for the shell once it has a real deployable container (see dimension 11) — following PrimeData's frontend pattern (`/`) is fine since the shell is also a static SPA. |
| 15 | Ingress | **Corrected — this is the row most changed by the new information.** ARC: single host `ibu-ard.bu.lilly.com`, path `/`. PrimeData: **subdomain-per-service**, not path-based — `primedata.apps.lrl.lilly.com` and `primedata-frontend.apps.lrl.lilly.com` (frontend, authenticated), `primedata-api.apps-api.lrl.lilly.com` (backend API), plus `-internal` no-auth variants of each and a separate Kibana host. There is no existing path-prefix convention (`/structured`, `/unstructured`) anywhere in the real infrastructure — that was an assumption in the original plan and in `apps/shell/CLAUDE.md`'s "App links" section, and it does not match how either app is actually deployed today. | New shared layer, matching PrimeData's existing pattern | High. | Give the shell its own hostname (e.g. `primexarc.apps.lrl.lilly.com` or similar, to be decided) and have its two "doors" link to the two apps' **existing real hostnames** (`ibu-ard.bu.lilly.com` and `primedata.apps.lrl.lilly.com`) exactly as plain `<a href>` tags — which is what `apps/shell/src/pages/Landing.tsx` already does structurally, it just needs `getStructuredUrl()`/`getUnstructuredUrl()` corrected to return the real hostnames instead of a `/structured` / `/unstructured` path assumption. This avoids inventing a new path-based ingress scheme neither app currently uses, and avoids the `/api/v1/*` collision entirely since the three origins never overlap. |
| 16 | K8s manifests | **Corrected.** Two separate manifest repos: `ibu-ai-ready-data-dev` for ARC, `primedata-dev` for PrimeData. Not one shared repo. | New manifests for the shell only | Low to medium, only for the shell's new manifest. | Add a new namespace + deployment + service + ingress set for `apps/shell` in whichever repo (or a new third one) is decided, per dimension 12. ARC's and PrimeData's existing manifests need no structural change — no path-prefix rewrite is needed now that dimension 15 no longer calls for path-based routing. |
| 17 | CI/CD | ARC: CI runs no tests despite 198 test functions existing (known gap, root `CLAUDE.md` section 7). PrimeData: test job commented out; the one active test job runs Python 3.9 against 3.11/3.12 code (known gap, same section). | New shared layer | Medium. Fixing these is independent per-app work; a shared pipeline shape is the only "unification" that applies. | Fix both gaps as part of this migration, per root `CLAUDE.md` section 7 — do not carry them forward. A shared GitHub Actions/Azure Pipelines template (lint, typecheck, test, build) parameterized per app is reasonable once both apps' individual CI is actually green; do not build the shared template first and paper over broken tests under it. |
| 17b | Testing | Same as above — ARC has tests that do not run in CI; PrimeData's active job targets the wrong Python version. | New shared layer | Medium. | Same fix as CI/CD; listed separately since the user's table separated the two. Sequence: fix ARC's CI to actually run `pytest`, fix PrimeData's CI to run on 3.11+, then add the shell's own lint/typecheck job (it currently has none configured at repo level). |
| 18 | Observability | Not yet independently verified in this pass for either app's current instrumentation depth. Root `CLAUDE.md` assigns an `observability-agent` at merger scope. | Bias PrimeData (once verified) | Low to medium. | Defer to the dedicated `observability-agent` rather than deciding here without re-reading both apps' current logging/metrics setup — avoid guessing at a dimension not directly inspected this pass. |
| 19 | Tenancy | ARC: single-tenant-per-request, no persistent multi-tenant billing concept. PrimeData: has a `billing_router` (`/api/v1/billing`) and `analytics_router`, implying product/tenant scoping exists. | Keep both / no change | Medium if forced. | Do not retrofit ARC with PrimeData's billing/tenancy model; ARC has no product concept that needs it. If the merged shell ever needs a single combined billing view, build that as a shell-level read-only aggregation, not by pushing ARC into PrimeData's tenancy model. |
| 20 | Governance (`.claude/` agents, hooks, CLAUDE.md) | Already unified at the root level; both apps additionally maintain their own scoped `.claude/agents/` (ARC: 6 files including `db-security-review.md`, `scorer-purity.md`; PrimeData: 5 files including its own new `db-security-review.md`, `connector-security.md`, `pipeline-safety.md`, `vector-store.md`). | Bias PrimeData structurally, content stays per-app | Low. | This dimension is in the best shape of all 22 — already executed well. The one open item is confirming the 5 root-promoted generic agents (`bug-finder`, `code-quality`, `maintainability`, `race-conditions`, `test-flakiness`) were meant for repo-wide scope rather than staying under `apps/structured/.claude/agents/`; flag for a one-line confirmation, not a required change. |
| 21 | Fonts / design tokens | ARC: Fraunces / Bricolage Grotesque / Apple system stack / JetBrains Mono, HSL variables, no Inter/emoji. PrimeData: Inter, raw hex arbitrary Tailwind values (per the original comparison report). Shell: already adopted ARC's tokens. | Bias ARC (not PrimeData) | Low for the shell (already done); medium for PrimeData's own internal pages if ever touched. | Root `CLAUDE.md` section 6 already states this reverses the "bias PrimeData" default: ARC's type/color system is the baseline for shared chrome, and the shell already follows it correctly. Do not change PrimeData's internal product pages as part of this plan — only `packages/shared-ui` and the shell need ARC's tokens, and the shell already has them. |
| 22 | Package management | ARC: Artifactory `.npmrc` correctly configured in both `apps/structured` frontend and CI. PrimeData: `.npmrc` now present in `apps/unstructured/frontend` and wired into its Dockerfile (`COPY .npmrc ./` before `npm ci`) — this was PrimeData's biggest documented gap (root `CLAUDE.md` section 5, "known, pre-existing violation") and it looks fixed. | Bias ARC's already-correct pattern | Low; already resolved. | No further action needed structurally. Separately: rotate the real tokens currently sitting in plaintext in all three `.npmrc` files (see the urgent note sent earlier) — that is a credential-hygiene issue, not an architecture one. |

---

## 4. Recommended target architecture (synthesis)

Two Postgres instances stay two Postgres instances — ARC's and PrimeData's (`primedata-db-dev`) are already fully separate RDS instances, not just separate schemas on one server, so there is no live collision to fix, only a documented guardrail to keep for if that ever changes.
Two CATS namespaces stay two namespaces (`ibu-ai-ready-data-dev`, `primedata-dev`); the shell gets its own namespace or a home in one of the two, and reaches both apps via their existing real hostnames rather than a new path-prefix scheme neither app uses today.
One auth model, Bouncer, already the stated target and already fully implemented in PrimeData and the shell; ARC's backend is the one piece of code that still needs the swap, behind a flag, verified in non-prod first.
One job substrate, Airflow, **on hold** as an orchestration target for ARC until the "NOT USED IN CATS" contradiction in PrimeData's own manifest is resolved — do not build new dependency on infrastructure whose own deployment labels it unused.
One design system, ARC's tokens, for shared chrome only, already correctly applied in the shell.
Two backends, two data-mutation postures, two LLM containment models, kept deliberately separate, because that separation is the actual product guarantee, not incidental complexity.
Two open doc-vs-infra mismatches inside PrimeData itself (Elasticsearch vs. documented OpenSearch; Next.js-shaped env vars vs. documented Vite SPA) that predate this merger and are worth resolving on their own, independent of the unification work.

---

## 5. Step-by-step implementation plan for Claude Code

Each step has an explicit verification gate. Do not start step *n+1* until step *n*'s gate passes. This is intentionally incremental, not a single large migration run.

### Step 0: Stop the bleeding (do this before anything else, unrelated to architecture)
1. Rotate the Artifactory tokens currently in `apps/structured/frontend/.npmrc`, `apps/unstructured/frontend/.npmrc`, `apps/shell/.npmrc`.
2. Run `git add -A && git commit -m "Initial import: governance scaffold + migrated apps/structured, apps/unstructured, apps/shell"` at the repo root, after confirming with `git status` that no `.env`, `.npmrc`, or other secret-bearing file is staged.
3. **Gate:** `git log --oneline -1` shows a commit; `git show --stat HEAD | grep -i npmrc` and `grep -i "\.env$"` return nothing.

### Step 1: Fix the CLAUDE.md status drift
1. Update root `CLAUDE.md` section 0 "Current status" to reflect that `apps/structured`, `apps/unstructured`, and `apps/shell` are migrated, not pending. Update the migration sequence note accordingly.
2. **Gate:** `CLAUDE.md` no longer claims "no product code has been migrated yet."

### Step 2: Point the shell at each app's real hostname (corrected — no shared-ingress path scheme needed)
1. Fix `apps/shell`'s `getStructuredUrl()` / `getUnstructuredUrl()` (`src/lib/config.ts` or equivalent) to return the real production hostnames — `https://ibu-ard.bu.lilly.com` for ARC and `https://primedata.apps.lrl.lilly.com` for PrimeData — instead of the assumed `/structured` / `/unstructured` path scheme that does not exist in either app's actual ingress.
2. Give the shell its own hostname and a namespace (new, or hosted inside one of the two existing ones — an open decision, see section 6). No changes are needed to ARC's or PrimeData's existing ingress rules; the three origins never overlap, so the `/api/v1/*` collision noted in section 1 never actually triggers as long as no one later tries to put all three behind one shared host.
3. **Gate:** clicking either door on the shell's landing page reaches the real ARC or PrimeData production URL; no new ingress rule was needed on either existing app.

### Step 3: Resolve PrimeData's two internal doc-vs-infra mismatches (independent of the merger, but blocking accurate planning)
1. Confirm whether Elasticsearch (deployed, per `primedata-dev/elastic.yaml`) or OpenSearch (documented in `apps/unstructured/CLAUDE.md`) is the real, current vector store, and correct whichever is stale.
2. Confirm whether the frontend actually runs as the migrated Vite SPA or as the Next.js build implied by `primedata-dev/deploy.yaml`'s env vars (`NEXTAUTH_URL`, `NEXT_PUBLIC_API_URL`), and correct whichever is stale.
3. **Gate:** `apps/unstructured/CLAUDE.md` and the real deployed manifest agree on both points; no downstream step (including step 2 above, which assumes the frontend really serves at `primedata.apps.lrl.lilly.com`) is built on an unresolved contradiction.

### Step 4: Give the shell a container and health probe
1. Add `apps/shell/Dockerfile` (nginx serving `dist/`, matching the existing pattern in the other two frontends) and a `.dockerignore`.
2. Add a liveness/readiness path (can be as simple as serving `index.html` at `/healthz`).
3. **Gate:** `docker build` succeeds; the container serves the landing page; a probe hits it successfully.

### Step 5: Fix the two pre-existing CI gaps (per root CLAUDE.md section 7 — do not carry these forward)
1. ARC: wire `pytest tests/ -v` into CI so the existing 198 test functions actually run.
2. PrimeData: change the active test CI job from Python 3.9 to 3.11+, and un-comment or replace the disabled test job.
3. **Gate:** both apps' CI pipelines show a passing (not skipped, not silently green) test stage.

### Step 6: Auth unification (ARC → Bouncer) — requires `auth-unification-reviewer` sign-off before this step, per root CLAUDE.md section 4
1. Add Bouncer-header-based identity extraction to ARC's backend, alongside (not replacing) the existing `require_user()` JWKS path, behind a feature flag.
2. Verify in a non-prod environment that ARC's ingress strips client-supplied `X-USER-EMAIL`/`X-USER-NAME`/`X-UPN` headers exactly as PrimeData's does — this is the security-critical precondition, not optional.
3. Once verified end-to-end, flip the flag; do not delete the MSAL/JWKS path until the flag has been live and stable for an agreed soak period.
4. **Gate:** `auth-unification-reviewer` sign-off recorded; a real Bouncer-authenticated request reaches ARC's API and resolves the correct user identity; a direct-to-pod request (bypassing ingress) with a forged header is rejected.

### Step 7: Orchestration unification (ARC assessments → Airflow) — **blocked pending an answer, do not start**
1. Before any code here: get a direct answer on whether the Airflow webserver/scheduler defined in `primedata-dev/deploy.yaml` are actually running and used in production, despite being labeled `NOT USED IN CATS`. If they are genuinely unused, either they should be removed from the manifest (separate cleanup, not part of this merger) or PrimeData's real pipeline trigger mechanism is something else entirely that needs to be identified first.
2. Only once that is resolved and Airflow is confirmed as PrimeData's real, live orchestration substrate: register a new DAG in `apps/unstructured/infra/airflow/dags/` that triggers an ARC assessment run and polls/reports completion, calling ARC's existing API rather than importing ARC's Python code directly (this also satisfies the no-cross-app-imports rule).
3. Leave `core/job_store.py` and `core/scorer.py` untouched; this step only changes how a job is triggered and tracked, never how it is scored.
4. **Gate:** the Airflow-usage question from sub-step 1 has a documented answer; `test_scorer_is_deterministic()` still passes unmodified; an assessment triggered via the new DAG produces an identical result to one triggered the old way, given the same input.

### Step 8: Extract `packages/shared-ui` (last, per the documented sequencing)
1. Only after steps 0-7 are stable, extract design tokens, the Help/Support page shell, nav chrome, and the Bouncer auth-session hook already proven out in `apps/shell` into `packages/shared-ui`.
2. Enforce via the existing `enforce-boundary.sh` hook that `shared-ui` never imports from either app's `core/`, `llm/`, `ingestion_pipeline/`, or `aird_stages/`.
3. **Gate:** both apps' frontends can import from `packages/shared-ui` for chrome only; `enforce-boundary.sh` blocks any attempt to import product logic into it.

---

## 6. Open decisions still needed from the user

1. **New, highest priority:** is Airflow in `primedata-dev` actually live, despite being labeled `NOT USED IN CATS` in its own manifest? Blocks step 7 (orchestration unification) entirely, and blocks trusting Airflow as a sizing/reliability baseline for anything else.
2. **New:** which is correct — Elasticsearch (deployed) or OpenSearch (documented) as PrimeData's real vector store? And which is correct — the migrated Vite SPA or the Next.js-shaped env vars in the real manifest — for PrimeData's frontend? Both block trusting `apps/unstructured/CLAUDE.md` as an accurate description of what's actually running.
3. **New:** what hostname and namespace should `apps/shell` get, given ARC and PrimeData are on two entirely separate namespaces/domains (`ibu-ard.bu.lilly.com` under `ibu-ai-ready-data-dev`; `primedata.apps.lrl.lilly.com` under `primedata-dev`) rather than one shared one.
4. Whether the 5 root-promoted generic `.claude/agents/` (`bug-finder`, `code-quality`, `maintainability`, `race-conditions`, `test-flakiness`) were intentionally scoped repo-wide, or should move under `apps/structured/.claude/agents/`.
5. Which Azure DevOps project (or other remote) this repo actually pushes to — still open since Phase 2 of this project and now more urgent given zero commits exist anywhere.
