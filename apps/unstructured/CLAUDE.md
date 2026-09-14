# CLAUDE.md - apps/unstructured (PrimeData)

> Scoped to `apps/unstructured/`. Root-level governance: `/CLAUDE.md`.
> Working agreement (think before coding, simplicity first, surgical changes, goal-driven execution) is in the root `/CLAUDE.md` section 9 - not repeated here.

---

## Project

**PrimeData** - Lilly-internal document intelligence platform.
Ingests, cleans, chunks, embeds, and indexes unstructured documents.
Produces AI-readiness scores, vector embeddings, and searchable metadata.
Unlike ARC (apps/structured), PrimeData **actively transforms and stores derived data** - this is intentional and load-bearing.

**Audience:** Internal Lilly data teams managing document pipelines.
Authenticated via Bouncer (CATS ingress proxy) with Azure AD.
Deployed on CATS Kubernetes.

---

## Architecture

```
frontend/     Vite + React 18 + TypeScript (strict) + TanStack Query + Tailwind
backend/      FastAPI + SQLAlchemy 2.0 + Pydantic v2 (port 7000, 4 uvicorn workers)
infra/        Docker Compose (dev + prod), Airflow 2.7 DAGs, OpenSearch, MinIO
```

### Data flow

1. **Connectors** (S3, Azure Blob, Google Drive, Web, Folder) ingest raw documents
2. **Airflow DAG** orchestrates the pipeline via AIRD stages:
   - preprocess -> scoring -> chunking -> fingerprint -> indexing
3. **Playbooks** (9 YAML configs) define per-domain processing rules (HEALTHCARE, LEGAL, FINANCIAL, etc.)
4. **OpenSearch** stores vector embeddings + metadata (source of truth for search)
5. **Postgres** stores product/pipeline state, connector configs, user data
6. **MinIO/S3** stores raw and processed documents

### Key services (backend)

| Layer | Location | Purpose |
|-------|----------|---------|
| API routes | `backend/src/primedata/api/` (38 modules) | REST endpoints |
| Pipeline | `backend/src/primedata/ingestion_pipeline/` | Airflow DAG tasks + AIRD stages |
| Connectors | `backend/src/primedata/connectors/` | External data source adapters |
| Indexing | `backend/src/primedata/indexing/` | OpenSearch + embeddings |
| DB | `backend/src/primedata/db/` | SQLAlchemy models + repository pattern |
| Services | `backend/src/primedata/services/` | Business logic (21 modules) |
| Governance | `backend/src/primedata/governance/` | Quality gates, alerts, policy engine |

---

## Where to Look

| You need | Read |
|---|---|
| API endpoints and routes | `backend/src/primedata/api/app.py` (registers all routers) |
| Pipeline DAG definition | `infra/airflow/dags/dag_primedata_simple.py` |
| AIRD stage implementations | `backend/src/primedata/ingestion_pipeline/aird_stages/` |
| Playbook configs (per-domain rules) | `backend/src/primedata/ingestion_pipeline/aird_stages/playbooks/*.yaml` |
| DB models (20+ tables) | `backend/src/primedata/db/models.py` |
| Alembic migrations (33 revisions) | `backend/alembic/versions/` |
| OpenSearch client + vector search | `backend/src/primedata/indexing/` |
| Connector implementations | `backend/src/primedata/connectors/` |
| Frontend API client (~70 methods) | `frontend/lib/api-client.ts` |
| Bouncer auth integration | `frontend/lib/bouncer-auth.ts` |
| Frontend page routes | `frontend/app/` (file-based routing pattern, Vite SPA) |
| UI primitives | `frontend/components/ui/` |
| Docker dev setup | `infra/docker-compose.yml` |
| Docker prod setup | `infra/docker-compose.prod.yml` |
| Curated documentation | `docs/` |

---

## Hard Rules - Never Violate

### Pipeline integrity
- **Stages must be idempotent.** Re-running a stage with the same input produces the same result without duplicating data. If a stage fails, retry is always safe.
- **No data loss on retry.** A failed pipeline run must not corrupt previously-indexed documents.
- **Playbook modifications require validation.** Changing a YAML playbook config changes processing behavior for ALL documents using that playbook. Test against representative documents before merging.
- **Chunking config changes require re-indexing.** If chunk size or overlap changes, existing indexed chunks are stale. Document this in the PR.

### Vector store (OpenSearch)
- **Vector metadata is source of truth** for search results. The Postgres DB is a secondary index for product state, not the authoritative store for document content.
- **Index mapping changes are breaking.** Adding or removing fields in the OpenSearch mapping requires a reindex plan.
- **Embedding model changes are breaking.** Switching models invalidates all existing embeddings. This is a major migration, not a config change.

### Database
- **Schema is configurable** via `POSTGRES_SCHEMA` env var (default: `public`).
- **NEVER set `POSTGRES_SCHEMA` to `history_assessment`** - that is ARC's schema (root CLAUDE.md section 3.4).
- **33 existing Alembic migrations** - forward-only. Never edit an applied migration.
- **Connector credentials are stored per-connector in DB** (standard encrypted pattern). This is different from ARC (which never persists user credentials). Both models are intentional.

### Auth
- **Bouncer ingress headers** (`X-USER-EMAIL`, `X-USER-NAME`, `X-UPN`) are the identity source.
- **No in-app MSAL.** Authentication happens entirely at the ingress layer.
- **Backend validates via JWT** from the Bouncer session endpoint.
- **Never trust identity headers if the request could bypass the ingress.** The NetworkPolicy must ensure direct pod access is impossible.

### LLM usage
- PrimeData uses LLMs for **content transformation mid-pipeline** (cleaning, summarization, metadata extraction). This is different from ARC's narration-only model.
- Cortex client is in `backend/src/primedata/services/cortex_client.py`.
- LLM calls may mutate document content - this is by design.

### Secrets
- Never hardcode keys. Connection strings from env vars / settings.
- Never log credentials (connector passwords, API keys, tokens).
- `.env.example` files contain only placeholder values.

---

## Coding Conventions

### Python (backend)
- Python 3.11+. Pydantic v2.
- SQLAlchemy 2.0 (sync sessions, not async).
- FastAPI routes delegate to service layer. No business logic in route handlers.
- Repository pattern for DB access (`backend/src/primedata/db/repository.py`).
- Logging via `primedata.utils.log_utils.get_logger(__name__)`.
- Requirements split across multiple files: base, analytics, cloud, ml, ci.

### TypeScript (frontend)
- TypeScript strict mode. Path alias `@/*` maps to project root.
- TanStack Query (React Query v5) for server state. No Redux.
- All API calls through `lib/api-client.ts` (~70 methods).
- Tailwind CSS. No inline styles.
- File-based routing pattern in `app/` (Vite SPA, NOT Next.js despite similar structure).
- Bouncer auth: identity from `lib/bouncer-auth.ts`, context via `lib/default-user-context.tsx`.

### Structure
- All product code lives within `apps/unstructured/`. Never create files outside it.
- Backend package is `src/primedata/` - all imports use `primedata.*`.
- Frontend has two source roots: `app/` (pages) and `components/` + `lib/` (shared).

---

## Running Locally

```bash
# Backend + infra (from apps/unstructured/)
cd infra && docker-compose up -d    # postgres, opensearch, minio, airflow
cd ../backend && pip install -r requirements.txt
uvicorn primedata.api.app:app --host 0.0.0.0 --port 7000 --reload

# Frontend (from apps/unstructured/)
cd frontend && npm install && npm run dev   # http://localhost:3000
```

Backend port: **7000**. Frontend port: **3000** (proxies /api/ to backend via nginx in Docker).

---

## What NOT to Do

| Don't | Why |
|---|---|
| Set `POSTGRES_SCHEMA` to `history_assessment` | That's ARC's schema - collision breaks both apps |
| Import from `apps/structured/**` | Cross-app imports forbidden (enforced by hook) |
| Change embedding model without a reindex plan | All existing vectors become incompatible |
| Edit an applied Alembic migration | Forward-only; write a new revision |
| Log connector credentials or API keys | Security - redact before logging |
| Use `npm ci` against public npm registry | Artifactory only (Lilly policy) |
| Run pipeline stages in a non-idempotent way | Data duplication / corruption on retry |
| Trust identity headers without ingress isolation | Header-based auth without NetworkPolicy = unauthenticated |
| Add Redux or other global state | TanStack Query handles server state |
| Run CI tests against Python 3.9 | Code requires 3.11+ |

---

## Definition of Done

- [ ] `pytest` passes (existing + new tests)
- [ ] `npm run lint` and `npm run type-check` pass
- [ ] No hardcoded secrets
- [ ] No inline styles, Tailwind classes only
- [ ] Playbook changes tested against representative documents
- [ ] Pipeline stages remain idempotent
- [ ] Docker builds succeed (`docker-compose build` from `infra/`)
- [ ] Bouncer auth flow works (identity headers populated)
