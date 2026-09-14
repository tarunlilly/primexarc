# PrimeData vs. ARC — Comparative Platform Report

**Prepared:** 25 August 2026
**Scope:** `primedata-ui`, `primedata-backend`, `ibu-ai-ready-data` (ARC), and the CATS manifest trees at `ibu-ai-ready-data-dev`, `primedata-dev`
**Audience:** technical — architecture, versions, module names, and route paths are given verbatim

---

## 1. Executive framing

The two platforms occupy the same problem space — getting enterprise data into a state where AI systems can consume it — but they sit on opposite sides of a single dividing line: **PrimeData transforms data; ARC only judges it.**

PrimeData's own tagline, taken from `primedata-ui/index.html`, is *"Making Data AI-Ready"*, elaborated as *"Ingest, clean, chunk, embed & index. Test and export with confidence."* Its FastAPI service description reads *"AI-ready data from any source."* It is a pipeline product: you point it at a source, it runs an orchestrated multi-stage job, and it emits versioned artifacts — cleaned records, chunks, vectors, a promoted searchable index, and a trust report. The output is *new data you did not have before*.

ARC's controlling instruction, stated in its `CLAUDE.md`, is the inverse: *"The app advises — it never modifies user data."* You give it CSVs or a database schema, it profiles them, scores them against a fixed nine-dimension framework, and returns a tier verdict with a prioritized remediation list. The output is *an opinion about data you already have*.

That single difference propagates outward into every layer. It explains why ARC's scorer is a pure function with a hard no-I/O rule while PrimeData's pipeline is a twelve-task Airflow DAG. It explains why ARC pins its LLM to a single additive narration call that is forbidden from touching a number, while PrimeData uses an LLM mid-pipeline to rewrite document content. It explains why ARC has one Postgres schema with four tables and PrimeData has twenty-plus tables plus a vector store that is the declared source of truth for chunk metadata. And it explains the risk asymmetry: ARC's worst failure mode is a wrong score; PrimeData's is corrupted or mis-indexed derived data sitting in a promoted collection.

A useful shorthand: **ARC is a gate, PrimeData is a factory.** They are complementary rather than competing, and the natural composition — ARC assesses, PrimeData remediates, ARC re-assesses — is not currently wired up in either codebase.

---

## 2. Goals, side by side

### PrimeData

PrimeData positions itself, per `primedata-backend/docs/workflow.md`, as *"a comprehensive data quality and AI readiness platform."* The stated capability set is broad: multi-file ingest with checksum validation, document processing through AIRD stages (normalize, chunk, score), validation against configurable data-quality rules, vector indexing for semantic search, trust-score and AI-readiness reporting, governance via ACLs and audit logs and lineage, drill-down quality analysis, and recommendation generation. It explicitly targets multi-workspace multi-tenant operation with RBAC, and it carries commercial scaffolding — Stripe billing, plan limits, a pricing page, a checkout session endpoint.

The product model is *workspace → product → data source → pipeline run → version → promotion*. A "product" is a versioned data asset. Each pipeline run produces artifacts under `v/{version}/`, and `POST /api/v1/products/{product_id}/promote` flips a vector-store alias to point at a chosen version. That promote-and-alias pattern is the clearest expression of PrimeData's purpose: it is shipping something into production.

The de-facto product specification is not a markdown file. It lives inside `primedata-ui/app/help/page.tsx`, a 3,348-line React component that documents the AIRD pipeline, the AI Readiness Fingerprint, the AI Trust Score, fourteen seedable data-quality rules, and playbook auto-detection — including a hard deployment gate of Trust Score ≥ 50% and Security ≥ 90%.

### ARC

ARC (AI Readiness Evaluator, hosted at `ibu-ard.bu.lilly.com`) is scoped much more tightly. Per `CLAUDE.md`: it *"evaluates CSV datasets and database schemas against a 9-dimension AI readiness framework"* and produces *"a tier classification (Needs Improvement / Conditional / AI Ready), deterministic per-dimension scores with blocker gating + applicability renormalization, and Cortex-backed LLM narrative + prioritized recommendations."* Audience: internal Lilly data product owners, behind SSO, behind the firewall.

Its architectural ambition is expressed in `EXECUTION_PLAN_1.md` as a three-plane model — EVIDENCE → JUDGMENT → LANGUAGE — with eight durable invariants: scorer purity, a single LLM boundary, a fallback that always works, privacy containment, determinism, immutable evidence bundles, LLM output that is additive-only, and confidence gating. Layered on top is a fourteen-capability model (`SEM JOIN GOV AGG ACC FRS LBL LKG SIG STA TMP VOL LIN TXT`, each measured 0–4) and a purpose model of Family → Archetype → Contract, where an archetype such as `mcp_read` declares a `capability_floor` and a `gate_set`. The verdict chain is fit-floor → gates → capability gaps → verdict.

ARC has no billing, no tenancy, no user-generated content beyond support tickets, and no notion of promoting anything.

---

## 3. Distinguishing elements

Seven differences carry most of the architectural weight.

**Mutation posture.** PrimeData writes derived data — cleaned files, chunks, embeddings, PDF reports, promoted collections — into S3 and a vector store, and rewrites document content mid-pipeline via an LLM noise-reduction step. ARC's scorer is a pure function forbidden from any I/O, and its `CLAUDE.md` instructs the assistant to refuse requests to "make scores higher."

**Determinism.** ARC treats reproducibility as a first-class contract. There is a named critical test, `test_scorer_is_deterministic()`, which runs the scorer twenty times on a canonical fixture and asserts byte-identical output, with an explicit instruction never to delete it. PrimeData has no equivalent guarantee; its outputs depend on embedding model version, playbook routing heuristics, and LLM cleaning.

**LLM containment.** ARC allows exactly one package (`app/backend/llm/`) to reach an external model, with `advise()` as the single public entry point. The synthesizer receives a `TableAssessment` and never a `TableProfile` — the function signature enforces it, and adding a profile argument is described as a "Prime Directive violation." Every recommendation's `finding_id` must match a real input rule ID or a post-call filter drops it. A verbatim `SECURITY_GUARDRAILS` block leads every system prompt, and all data-derived strings pass through `wrap_untrusted()`. Fallback to rule-based output is mandatory when credentials are absent. PrimeData's LLM usage (Cortex, model `mm-business-meta-generator-consolidated-model`, endpoint `POST {base}/model/ask-with-custom-prompt/{model_id}`) sits inside the transformation path with no comparable containment contract.

**Credential handling.** ARC draws a sharp line between *source-DB credentials* (what a data owner types in to connect their own database — never persisted in any form, not hashed, not encrypted, held in memory for one assessment then dropped) and *history-DB credentials* (ARC's own Postgres connection, via standard ExternalSecret). `history_assessment.assessment_runs.source_ref` stores only non-secret connection facts. PrimeData persists data-source configuration and supports long-lived connectors (S3, Azure Blob, Google Drive, web), which is inherent to its function but a materially larger secret-handling surface.

**Scale of surface.** PrimeData exposes roughly 150 routes across 38 route modules and ~52,800 lines of Python. ARC exposes 28 routes across 8 routers. PrimeData's UI is ~27,500 lines across 79 TypeScript files; ARC's is nine JSX pages and ten UI primitives.

**Auth model.** ARC does full in-app token validation: MSAL redirect flow in the browser, JWKS fetched from `login.microsoftonline.com/{tenant}/discovery/v2.0/keys` and cached 24 hours, `jwt.decode` with RS256 and explicit audience and issuer checks, with a claims-only fallback that still enforces `exp`/`aud`/`iss`. PrimeData's UI delegates entirely to **Bouncer**, the CATS ingress auth proxy — no login page, no route guards, and `lib/default-user-context.tsx:27` hardcodes `role: 'admin'` for every user on the grounds that authorization is enforced at the ingress via `lilly.com/security_groups`. Its backend verifies RS256 JWTs against a JWKS and additionally re-implements NextAuth.js JWE key derivation (HKDF-SHA256, info string `"NextAuth.js Generated Encryption Key"`).

**Documentation discipline.** ARC maintains a curated `app/docs/` set — `spec.md`, `development.md`, `testing.md`, `context.md`, `metadata_layer.md`, `phase3-llm-integration.md`, `cortex-llm.md`, `cats-deployment.md` — plus a root `EXECUTION_PLAN_1.md`. PrimeData's backend has a one-line `README.md` stub, no `CLAUDE.md`, a curated `docs/` folder, and roughly eighty top-level session-note markdown files with names like `*_FIX.md` and `*_COMPLETE.md`. PrimeData's UI has no README, no CLAUDE.md, and no docs directory at all.

---

## 4. Tech stacks

### 4.1 Backends

| | **PrimeData backend** | **ARC backend** |
|---|---|---|
| Language | Python 3.11 / 3.12 | Python 3.11+ |
| Framework | `fastapi==0.104.1`, `uvicorn[standard]==0.24.0` | `fastapi[standard]>=0.115,<0.120` |
| Validation | `pydantic>=2.0.0,<3.0.0` | Pydantic v2 (via `fastapi[standard]`), `pydantic-settings>=2.4,<3.0` |
| ORM | `SQLAlchemy==2.0.23` (sync `create_engine`) | `SQLAlchemy>=1.4,<2.0` (async, `sqlalchemy.ext.asyncio`) |
| Migrations | `alembic==1.12.1`, 33 revisions | `alembic>=1.13,<2.0`, 4 revisions |
| DB driver | `psycopg2-binary==2.9.9` | `psycopg2-binary>=2.9,<3.0`, `asyncpg>=0.29,<0.31` |
| Orchestration | Apache Airflow 2.7.1, LocalExecutor | In-process `JobStore`, `--workers 1` |
| Profiling | — | `ydata-profiling==4.18.4`, `pandas>=2.1,<3.0`, `numpy>=1.26,<2.0` |
| Vector | `opensearch-py>=2.0,<3` (primary), `elasticsearch==8.12.0` (deprecated) | none |
| Embeddings | `sentence-transformers>=2.7.0,<3.0.0`, `openai>=1.0.0,<2.0.0` | none |
| Storage | `boto3==1.34.0`, `azure-storage-blob>=12.19.0,<13.0.0` | `redshift-connector>=2.1,<3.0`, `sqlalchemy-redshift>=0.8,<1.0` |
| Auth libs | `PyJWT>=2.8.0,<3.0.0`, `passlib[bcrypt]==1.7.4`, `cryptography==41.0.7` | `python-jose[cryptography]>=3.3,<4.0` |
| Billing | `stripe>=5.0.0,<6.0.0` | none |
| Docs | `pypdf==3.17.4`, `python-docx>=0.8.11,<1.0.0`, `reportlab>=4.0.0,<5.0.0` | none |
| Test | `pytest>=7.0.0,<8.0.0`, `pytest-cov>=4.0.0,<5.0.0`, `pytest-asyncio>=0.21.0,<1.0.0` | `pytest>=8.0`, `pytest-asyncio>=0.24`, `pytest-mock>=3.14` |
| Container port | 7000 | 8000 |

The SQLAlchemy split is worth noting: PrimeData is on 2.0 but uses it synchronously; ARC is pinned below 2.0 for `sqlalchemy-redshift` compatibility but uses the async extension. Neither is wrong, but they are non-interchangeable.

### 4.2 Frontends

| | **primedata-ui** | **ARC frontend** |
|---|---|---|
| Framework | `react@^18.2.0` + TypeScript `^5.3.2` (`strict: true`) | `react@^18.3.1`, JavaScript (JSX) |
| Build | `vite@^5.4.0` | `vite@^5.4.6` |
| Router | `react-router-dom@^6.28.0` | `react-router-dom@^6.26.2` |
| Server state | `@tanstack/react-query@^5.90.16` | none — direct `fetch` via `lib/api.js` |
| Client state | none (local `useState` + one Context) | none (hooks only; Redux and Context are explicitly banned) |
| Styling | `tailwindcss@^3.3.6` | `tailwindcss@^3.4.13` |
| Primitives | Radix `label` + `slot`, hand-rolled shadcn subset (11 files) | Radix `label`, `progress`, `slot`, `tabs`; shadcn subset (10 files) |
| Icons | `lucide-react@^0.294.0` | `lucide-react@^0.441.0` |
| Charts | none (`reactflow@^11.11.4` for lineage only) | `recharts@^2.12.7` |
| HTTP | native `fetch`, hand-rolled `ApiClient` (~70 methods, 932 lines) | native `fetch`, `lib/api.js` |
| Auth | none in-app — Bouncer ingress proxy | `@azure/msal-browser@^5.11.0`, `@azure/msal-react@^5.4.2` |
| Observability | Grafana Faro `^2.3.1` + OpenTelemetry (fetch/XHR instrumentation, OTLP-HTTP → `grafana-alloy.monitoring:4318` → Jaeger) | none |
| Onboarding | `react-joyride@^2.9.3` | none |
| Font | Inter (Google Fonts CDN) | Fraunces, Bricolage Grotesque, Apple system stack, JetBrains Mono |
| Brand color | `#C8102E` (`lilly-red`), often as raw arbitrary values | `#C41A1A` via HSL CSS variables; hex hardcoding forbidden |
| Tests | **zero** | Playwright suite documented but absent; `verify-bundle` script only |

The font choice is the sharpest visible divergence. ARC's `CLAUDE.md` explicitly forbids Inter, Roboto, Lato, and Open Sans as *"AI-default fonts"* and bans emoji anywhere in the UI. PrimeData uses Inter as its sole typeface. ARC also mandates CSS-variable colors and forbids inline `style={{}}`; PrimeData components routinely inline `text-[#C8102E]` and `bg-[#F5E6E8]` arbitrary values, bypassing their own Tailwind token.

Both frontends independently arrived at the same key decision — **runtime configuration over build-time baking** — for the same reason. ARC serves `GET /api/config` returning `{clientId, tenantId}`, with `CLAUDE.md` stating that build-time bake *"creates stale-bundle bugs invisible in local dev."* PrimeData loads `/config.js` (generated at container start by `docker/entrypoint.sh`) which sets `window.__ENV__`, read ahead of `import.meta.env` in every consumer. Same conclusion, different mechanism.

---

## 5. Architecture

### 5.1 PrimeData: the pipeline

The Airflow DAG is `primedata_simple`, defined in `backend/src/primedata/ingestion_pipeline/dag_primedata_v1.py`, manually triggered (`schedule_interval=None`). Task graph:

```
ingest_from_datasources → preprocess → score → fingerprint → policy
  → [validation, reporting] → chunk → embed → index
  → validate → validate_data_quality → finalize
```

Stages live in `ingestion_pipeline/aird_stages/`, each subclassing `AirdStage` and returning a `StageResult` carrying `stage_name`, `status`, `metrics`, and `artifacts`. Notable members: `baseline_assessment.py` captures raw quality *before* transformation so the platform can demonstrate before/after value; `augmentation.py` enriches chunks with external context and is contractually forbidden from failing the pipeline; `optimization/` holds chunk optimizers; `playbooks/` holds nine YAML domain playbooks (`ACADEMIC`, `ECOMMERCE`, `FINANCIAL`, `HEALTHCARE`, `LEGAL`, `REGULATORY`, `RETAIL`, `SCANNED`, `TECH`) plus a heuristic `router.py`.

Chunking strategies exposed via `GET /api/v1/config/chunking-strategies`: `fixed_size`, `semantic`, `sliding_window`, `sentence_based`, `document_boundary`. Defaults are `chunk_size=1000`, `chunk_overlap=200`, `min_chunk_size=100`, `max_chunk_size=2000`, strategy `fixed_size`; auto mode keys off detected `ContentType` with `confidence_threshold=0.7`.

S3 layout: `{S3_METADATA_PATH}ws/{workspace_id}/prod/{product_id}/v/{version}/{raw|clean|chunk|embed}/`.

Artifact retention is a first-class enum — `keep_forever`, `30_days`, `90_days`, `365_days`, `delete_on_promote`, `on_failure_keep_90` — enforced by `retention_job.py` and the archiver services.

### 5.2 ARC: the scorer

`app/backend/core/scorer.py` is the heart, and it is pure. `score_table()` runs seven steps: classify reference tables (metadata `entity_classification` in {reference, staging, lookup, enum}, else row count below `reference_row_threshold`, default 1000); filter dimensions by applicability; score each dimension; compute a weighted base score over active dimensions only, with implicit renormalization by dividing by the active weight total; apply blocker gating; collect deferred checks and cap recommendations at ten; assign a class.

Per-dimension formula, with deferred checks excluded from the denominator:

```
counted = [c for c in checks if c.status != "deferred"]
points  = sum(1.0 if pass else 0.5 if warn else 0.0 for c in counted)
score   = round((points / len(counted)) * 100)
```

Constants: `GREEN_MIN = 80`, `YELLOW_MIN = 60`, `BLOCKER_CAP = 59`. Any `fail` on a `severity="blocker"` rule appends its rule ID to `gated_by` and caps the overall score at 59.

The nine dimensions and their weights:

| id | label | weight |
|---|---|---|
| `schema` | Schema Design & Structure | 10 |
| `quality` | Data Quality & Completeness | 20 |
| `labels` | Labels, Targets & Ground Truth | 15 |
| `temporal` | Temporal Integrity | 15 |
| `features` | Feature & Signal Readiness | 10 |
| `stats` | Statistical Properties | 10 |
| `privacy` | Privacy, Compliance & Ethics | 10 |
| `metadata` | Metadata & Documentation | 5 |
| `ops` | Operational & Pipeline Readiness | 5 |

Forty rules total. Two blockers (`privacy_column_names`, `labels_leakage`). Three hybrid rules that emit `status="deferred"` and route to human attestation rather than the LLM: `labels_leakage`, `privacy_values`, `ops_partition`. The `labels` dimension carries an applicability predicate (`_has_target_or_binary`) and drops out entirely when no target column is present.

Each check is tagged with one or more lenses — DQ (Data Quality), ML (ML Readiness), AI (AI Readiness) — and lens scores are computed as pass-rate over non-deferred checks. `EXECUTION_PLAN_1.md` is emphatic that lens scores are *"progress indicators only — they never gate."*

Schema-level rollup averages assessed table scores per dimension, rolls checks up by worst status, unions the gating sets, and produces a verdict of `At Risk` / `AI Ready` / `Conditional`. It also builds `action_groups` — one entry per rule ID across tables — and runs `simulate_resolution()` on each to compute the score delta from fixing it, which is what powers the prioritized remediation view.

### 5.3 Structural contrast

PrimeData composes routers by side-effect import: sub-modules import the parent's `APIRouter` and attach routes, and the parent does a bottom-of-file `import ... # noqa: F401 - registers routes`. Import order is load-bearing. ARC forbids business logic in `api/` entirely — routes call `core/` classes, `HTTPException` is raised only in the API layer, and `core/` raises plain Python exceptions.

PrimeData's frontend is a Vite SPA wearing a Next.js costume: `app/**/page.tsx` with `[id]` bracket folders, a surviving `"use client"` directive in `app/providers.tsx:1`, but no Next.js. Every route must be manually registered in `src/App.tsx`; adding a `page.tsx` alone does nothing. ARC's frontend restricts `src/` to exactly three subfolders — `pages/`, `components/ui/`, `lib/` — with no further nesting.

---

## 6. Data layers

### 6.1 PrimeData

PostgreSQL via `postgresql+psycopg2`, schema parameterized by `POSTGRES_SCHEMA` (default `public`) — every model sets `__table_args__ = ({"schema": POSTGRES_SCHEMA},)` and every foreign key is templated, so the app deploys into a non-public schema without code changes.

ORM tables (`db/models.py`): `users`, `workspaces`, `workspace_members`, `products`, `data_sources`, `raw_files`, `acls`, `pipeline_runs`, `custom_playbooks`, `pipeline_artifacts`, `dq_violations`, `billing_profiles`, `eval_queries`, `eval_runs`, `user_audit_logs`.

Enterprise DQ tables (`db/models_enterprise.py`): `data_quality_rules`, `data_quality_rule_audit`, `data_quality_rule_sets`, `data_quality_rule_assignments`, `data_quality_compliance_reports`.

Additional tables in `CREATE_TABLES.sql` not present in the ORM: `chunks`, `embeddings` (both annotated as placeholders), `clean_files`, `data_quality_results`, `lineage_relationships`, `policies`, `versions`.

The load-bearing decision: `DocumentMetadata` and `VectorMetadata` models were **deliberately removed** (migration `bda98fc65abe_remove_document_and_vector_metadata_`). Chunk metadata now lives in vector-store payloads, not Postgres. The vector store is the declared single source of truth.

### 6.2 ARC

All persistent tables live under the `history_assessment` Postgres schema, provisioned out-of-band — the migration does not create it. Four tables:

- **`users`** — `user_id TEXT PK`, `role`, `email`, `department`, `is_superuser BOOLEAN NOT NULL DEFAULT false`, `first_seen`, `last_seen`
- **`assessment_runs`** — `run_id UUID PK`, `user_id` FK cascade, `source_type CHECK IN ('csv','db','s3')`, `source_name`, `source_ref JSONB` (non-secret connection facts only), `table_group`, `overall_score INT CHECK 0–100`, `tier CHECK IN ('green','yellow','red')`, `duration_ms`, `result_json JSONB`, `created_at`. Indexes `idx_runs_user_recent (user_id, created_at DESC)` and a GIN index on `source_ref`.
- **`table_assessments`** — `table_assessment_id UUID PK`, `run_id` FK cascade, `table_name`, `table_group`, `table_score`, `tier`, `dimension_scores JSONB`, `findings JSONB`, `strengths JSONB`, `recommendations JSONB`, with GIN indexes on `dimension_scores` and `findings`.
- **`attestations`** — `attestation_id UUID PK`, `run_id` FK cascade, `finding_uid`, `rule_id`, `table_name`, `decision CHECK IN ('approved','rejected','accepted_risk','dismissed')`, `justification`, `decided_by`, `decided_at`.

Four migrations, each paired with a matching `.sql` snapshot. Every schema change requires three coordinated edits — ORM model, Alembic revision, SQL snapshot — and a `PreToolUse` hook blocks any edit under `app/backend/db/**` until a `db-security-review` agent stamps approval. No raw SQL outside `app/backend/db/`; `core/` and `api/` consume `history_store.py` only. Migrations are applied by an operator, never on app boot.

---

## 7. Deployment

Both platforms deploy to the Lilly CATS platform on EKS in `us-east-2`, both push images to ECR account `283234040926`, and both are GitOps-driven by ArgoCD (namespace annotation `app.lilly.com/argo.automated: "true"`) with Flux image automation.

### 7.1 ARC — `ibu-ai-ready-data-dev`

Seven flat YAML files. Namespace `ibu-ai-ready-data-dev`, cost center `100A499`, ApplicationCI `CI00000126432038`, compute `hybrid`.

Deployment `ibu-ai-ready-data`, image `283234040926.dkr.ecr.us-east-2.amazonaws.com/ibu-ai-ready-data:dev-sha-503f1ea`, default 1 replica, requests 250m/256Mi, limits 1000m/768Mi. Liveness and readiness both `httpGet /health` on port 8000, `initialDelaySeconds: 10`, `periodSeconds: 15`, `timeoutSeconds: 2`. Flux policy `"283234040926;ibu-ai-ready-data;glob:*.*.*"` auto-commits new three-segment semver tags.

Service is ClusterIP 80 → 8000. Ingress host `ibu-ard.bu.lilly.com`, no TLS block (terminated upstream), annotation `lilly.com/security_groups: [{"Route": "/", "AllowAllUsers": true}]` and `lilly.com/user_info_headers` mapping email to `X-WEBAUTH-EMAIL`.

RDS is Crossplane-managed: `ibu-ai-ready-data-rds`, `db.t3.medium`, 40 GB, Postgres 17.5, encrypted, deletion-protected, writing connection secret `ibu-ai-ready-data-postgres-secrets`.

Cortex LLM configuration arrives as four env vars — `CLIENT_ID_LLM`, `TENANT_ID_LLM`, `CLIENT_SECRET_LLM`, `MODEL_CONFIG_NAME` — from secret `ibu-ai-ready-data-cortex-llm`. Azure AD identity comes from `ibu-ai-ready-data-azure-ad` (`client-id`, `tenant-id`).

Secrets are cleanly externalised. `secret.yaml` defines three ExternalSecrets (`backendType: secretsManager`), and `pgadmin.yaml` a fourth:

| K8s Secret | AWS Secrets Manager path | Keys |
|---|---|---|
| `ibu-ai-ready-data-azure-ad` | `ibu-arc-dev/ibu-ai-ready-data/azure-ad` | `client-id`, `tenant-id` |
| `ibu-ai-ready-data-db-role` | `ibu-arc-dev/ibu-ai-ready-data/db-role` | `db-role`, `db-role-password` |
| `ibu-ai-ready-data-cortex-llm` | `ibu-arc-dev/ibu-ai-ready-data/cortex-llm` | `client-id-llm`, `tenant-id-llm`, `client-secret-llm`, `model-config-name` |
| `pgadmin-secret` | `ibu-arc-dev/ibu-ai-ready-data/pgadmin` | `pgadmin-email`, `pgadmin-password` |

The fifth, `ibu-ai-ready-data-postgres-secrets`, is not an ExternalSecret — Crossplane writes it via `writeConnectionSecretToRef` in `rds-postgres.yaml`. Every secret the Deployment consumes is therefore accounted for, with no plaintext anywhere in the tree.

### 7.2 The PrimeData namespace

Namespace `primedata-dev`, the dedicated CATS deployment for PrimeData. Manifests live in `LRL_light_k8s_infra_apps/projects/dev/primedata-dev/` and include `namespace.yaml`, `deploy.yaml`, `secrets.yaml`, `rds.yml` (Crossplane-managed RDS), and `elastic.yaml` (Elasticsearch/OpenSearch). PrimeData's ingress uses subdomain-per-service: `primedata.apps.lrl.lilly.com` (frontend, authenticated), `primedata-api.apps-api.lrl.lilly.com` (backend API), plus `-internal` no-auth variants. The frontend, backend, and Airflow webserver/scheduler are all defined in `deploy.yaml`.

### 7.3 PrimeData's CATS deployment (confirmed)

PrimeData's Kubernetes manifests live in `LRL_light_k8s_infra_apps/projects/dev/primedata-dev/`. This was confirmed by direct inspection of the manifest repo. PrimeData's own CORS allowlist (`core/settings.py:94-106`) names `primedata-frontend.apps.lrl.lilly.com`, `primedata-internal.apps-internal.lrl.lilly.com`, `primedata-backend.apps-d.lrl.lilly.com`, `primedata.apps-d.lrl.lilly.com` - all matching the `primedata-dev` ingress definitions.

### 7.4 CI/CD

Both use the same LIGHT ECR push pattern via `docker/metadata-action@v5` and `docker/build-push-action`, with the same environment inference (PR ⇒ `dev`, branch push ⇒ `qa`, tag ⇒ `prod`).

ARC's `ci.yml` builds `./deployments/Dockerfile`, a three-stage build: `node:20-alpine` compiles the frontend, `python:3.11-slim` builds a venv, and a final `python:3.11-slim` runtime copies both, serving the SPA from `./static` behind the same uvicorn process. It writes `.npmrc` pointing at Artifactory (`@elilillyco:registry=https://elilillyco.jfrog.io/elilillyco/api/npm/Lilly-NPM/`) and verifies that `CLIENT_ID` and `TENANT_ID` secrets exist. **It runs no tests.**

PrimeData ships two separate images. `primedata-ui/Dockerfile` is `node:18-alpine` → `nginx:alpine` on port 3000, with `docker/entrypoint.sh` generating `config.js` and `envsubst` templating the nginx config. `primedata-backend/Dockerfile` is a two-stage `python:3.11-slim` build on port 7000 with a non-root `appuser` and four uvicorn workers. In `deploy-image.yaml` **the test job is entirely commented out**; the only active test job lives in `build-airflow-image.yaml` and runs on **Python 3.9** against a codebase targeting 3.11/3.12.

Note against the Artifactory policy: `primedata-ui/Dockerfile` runs `npm ci` against the default npm registry with nothing in the repo pointing at JFrog. ARC's CI does write an Artifactory `.npmrc`.

---

## 8. Where they are similar

Setting the differences aside, the convergence is substantial and mostly reflects shared platform gravity.

Both are FastAPI + Pydantic v2 backends serving a React 18 + Vite + Tailwind SPA, both use a hand-rolled shadcn/ui subset built on Radix primitives with `class-variance-authority` and `tailwind-merge`, both use `lucide-react` for icons, and both call their API through native `fetch` wrapped in a single client module rather than axios or a generated client. Neither uses Redux or any global client store.

Both deploy to CATS/EKS via ArgoCD and Flux, push to ECR `283234040926` in `us-east-2`, run Postgres 17.5, and use Crossplane-managed RDS. Both use pgAdmin `elilillyco-lilly-docker.jfrog.io/dpage/pgadmin4:6.17` behind a Traefik middleware injecting `x-forwarded-proto: https`.

Both integrate with **Lilly Cortex** for LLM inference using Azure AD client-credentials — ARC at `{cortex_base_url}/model/ask/{model_config_name}`, PrimeData at `{CORTEX_API_URL}/model/ask-with-custom-prompt/{model_id}` with `CORTEX_API_URL` defaulting to `https://chat.lilly.com`.

Both independently chose runtime configuration injection over build-time environment baking, and both hit and worked around the same FastAPI trailing-slash 307 problem — PrimeData with `redirect_slashes=False` globally plus client-side path normalization, ARC by consistent route definition.

Both use Alembic with an explicit no-auto-migrate-on-boot posture. Both score data quality and surface a trust/readiness metric with a deployment-gate threshold — PrimeData at Trust Score ≥ 50% and Security ≥ 90%, ARC at overall ≥ 80 for green with a hard cap of 59 on any blocker. Both make PII and privacy a named concern.

And both carry the same class of hygiene gap: documentation that has drifted from the code, and CI that builds and pushes without running the test suite.

---

## 9. Risks and drift worth acting on

Ordered roughly by exposure.

**CI without tests.** ARC's `ci.yml` has no test job at all despite 198 test functions across 13 files. PrimeData's `deploy-image.yaml` has its test job commented out with `needs: test` disabled, and its coverage gate (`--cov-fail-under=80`) is commented out in `pytest.ini`. The only active PrimeData test job runs on Python 3.9 against 3.11/3.12 code. `primedata-ui` has **zero tests** of any kind and its CI runs neither lint nor type-check.

**ARC documentation drift.** Fourteen concrete divergences between docs and code were identified. The material ones: `context.md:39` and `testing.md:66-67` still state tier thresholds of ≥65 green / 40–64 yellow / <40 red, contradicting the shipped 80/60; `context.md` and `development.md` both list Phase 3 as "Not started" when it is built; `spec.md` §4.1 documents 5 routes against an actual 28 and §4.2 documents models (`CSVAssessRequest`, `AssessmentResult`) that do not exist; the docs say two hybrid rules where the code has three; 13 archetypes are claimed everywhere but only 12 YAMLs exist on disk; `CLAUDE.md:120` references `settings.llm_max_output_tokens`, which is absent from `config.py`; and `cats-deployment.md:40` says no mutable `major.minor` tags are pushed while `release.yml:38` pushes exactly that.

**Two coexisting metadata formulas in ARC.** `_r_dictionary_present` in `dimensions.py:889-976` implements the governance-weighted 40/25/20/15 formula from `metadata_layer.md`, while `_build_metadata_quality` implements BOTL equal-weight-of-four and `_retune_metadata_dimension` **overwrites** the dimension score with the latter. Both are live; only one is authoritative.

**PrimeData's OpenSearch/Qdrant split.** OpenSearch is the primary vector store and Elasticsearch is deprecated "until Q2 2026," but Qdrant remains the naming and alias model throughout `aird_stages/indexing.py`, `api/playground.py`, and the promote logic in `api/products_chunking.py`, with `FEATURE_ENABLE_QDRANT_INDEXING = True` in `core/constants.py:362`. Three vector-store vocabularies coexist in one codebase.

**Stale artefacts in primedata-ui.** `app/page.tsx` (the marketing homepage) is never routed. `styles/globals.css` is a stale duplicate carrying the default shadcn blue (`--primary: 221.2 83.2% 53.3%`) and is not imported — editing it does nothing. `docker-entrypoint.sh` at the repo root claims the API URL is baked in at build time, directly contradicting the runtime-injection design that actually ships. The `.dark` theme block is unreachable — `darkMode: ["class"]` is configured but no toggle exists. And `.claude/settings.json` contains a hardcoded absolute path from a different developer's machine (`/Users/L043910/projects/play/primedata/ui/app/app/products/[id]/`), which will not resolve for anyone else and should be removed.

**Unpinned public images.** Both namespaces pin `bhgedigital/envsubst:latest` from DockerHub, and ARC's `aws-cli-deployment.yaml` uses `amazon/aws-cli:latest` (with a JFrog alternative noted in its own header comment). Under Lilly's Artifactory policy these should come from `elilillyco-lilly-docker.jfrog.io` with pinned tags.

**Availability.** Neither platform has an HPA, PDB, or NetworkPolicy in any namespace, and both application Deployments run at the implicit default of one replica. ARC additionally cannot scale horizontally without work: its `JobStore` is in-memory and `main.py:9` warns that multiple workers break job polling, which is why `--workers 1` is load-bearing in the standalone Dockerfile.

---

## 10. Summary matrix

| Axis | **PrimeData** | **ARC** |
|---|---|---|
| Verb | Transform | Assess |
| Mutates user data | Yes — cleaned files, chunks, vectors, reports | Never — stated Prime Directive |
| Core artifact | Promoted vector collection + trust report | Tier verdict + prioritized remediation |
| Determinism | Not guaranteed | Contractual, with a named 20-run test |
| Orchestration | Airflow 2.7.1, 12-task DAG | In-process JobStore, single worker |
| Storage | Postgres + S3/Azure Blob + OpenSearch | Postgres only (4 tables) |
| LLM role | Content transformation, mid-pipeline | Narration only, additive-only, post-scoring |
| LLM containment | Conventional | Single package, single entry point, ID-filtered, guardrailed |
| Auth | Bouncer ingress proxy; `role: 'admin'` hardcoded client-side | In-app MSAL + JWKS + RS256 validation |
| Backend routes | ~150 across 38 modules | 28 across 8 routers |
| Backend LOC | ~52,800 | ~1/10th scale |
| Frontend | TypeScript strict, 79 files, ~27,500 LOC | JavaScript JSX, 9 pages |
| Frontend tests | Zero | Documented but absent |
| Backend tests | 39 files, coverage gate disabled | 13 files, 198 test functions, no coverage tool |
| Commercial layer | Stripe billing, plans, limits | None |
| Tenancy | Multi-workspace, RBAC, ACLs, audit log | Single-tenant, superuser flag |
| Observability | Grafana Faro + OpenTelemetry | None |
| Docs posture | ~80 session notes + `docs/`; no README in UI | Curated `app/docs/` + `EXECUTION_PLAN_1.md`, drifted |
| Deployment | Two images (UI :3000, API :7000); k8s manifests in `primedata-dev` | One combined image :8000 at `ibu-ard.bu.lilly.com` |
| Governance rigor | Conventional | Enforced by PreToolUse hooks and review agents |

---

## 11. Recommended follow-ups

Three things are worth doing regardless of what else happens.

**Reconcile ARC's docs to its code.** The tier-threshold contradiction in `context.md` and `testing.md` is the highest-value fix — it is the number the whole product turns on, and two documents state it wrong.

Beyond that, the composition opportunity is real and cheap to explore: ARC's Phase 4 direction is an MCP server exposing `arc.list_assessments`, `arc.get_assessment`, `arc.list_failing_checks`, and `arc.compare_runs` over the `history_assessment` schema. That is exactly the interface PrimeData would need to consume an ARC verdict as a pre-pipeline gate — assess, remediate, re-assess — and neither team appears to have that connection on a roadmap.

---

## Sources

All findings are drawn from local repository inspection:

- `/Users/L027310/.../github/primedata-ui`
- `/Users/L027310/.../github/primedata-backend`
- `/Users/L027310/.../github/ibu-ai-ready-data`
- `/Users/L027310/.../LRL_light_k8s_infra_apps/projects/dev/ibu-ai-ready-data-dev`
- `/Users/L027310/.../LRL_light_k8s_infra_apps/projects/dev/primedata-dev`
