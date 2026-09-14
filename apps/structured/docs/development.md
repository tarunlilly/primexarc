# Development Workflow

Operational notes for running the app locally and in Docker. For architecture
read `spec.md`. For Claude Code's runtime rules read `../CLAUDE.md`.

---

## Phase status

| Phase | Component        | State       |
|-------|------------------|-------------|
| 1     | Frontend         | Scaffolded — wizard + stubs in place |
| 2     | Backend          | In progress |
| 3     | LLM advisor      | Not started |
| 4     | History (saved assessments) | Future scope |

---

## Frontend

```bash
cd app/frontend
npm install
npm run dev      # http://localhost:5173
npm run build    # → dist/
npm run preview  # serves the build
```

Vite proxies `/api/v1/*` → `http://localhost:8000` so the backend dev server
runs alongside without CORS configuration.

## Backend (Phase 2 onwards)

```bash
cd app/backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

## Full stack (Docker)

Run from the `app/` directory (where `docker-compose.yml` lives):

```bash
cd app
docker-compose up --build
```

Backend on `:8000`, frontend served by nginx on `:80`. SSO terminates at the
ingress in real deployments.

## Tests

```bash
# Backend
cd app/backend
pytest tests/ -v

# Frontend build validation
cd app/frontend
npm run verify-bundle
```

All tests must pass before any PR. Skip nothing to make a build green.

---

## Environment variables

Copy `app/backend/.env` from the local example variables below before running locally. All variables are read
through `backend/config.py` via `pydantic-settings`. Never hardcode secrets.

```
# Auth (MSAL — required for frontend login)
CLIENT_ID=your-azure-app-client-id
TENANT_ID=your-azure-tenant-id

# LLM
LLM_PROVIDER=anthropic          # anthropic | openai | cortex | bedrock
LLM_API_KEY=                    # leave empty for fallback path
LLM_MODEL=claude-sonnet-4-20250514

# Cortex LLM OAuth (Phase 3 — sourced from AWS secret ibu-arc-dev/.../cortex-llm)
CLIENT_ID_LLM=your-cortex-client-id-here
TENANT_ID_LLM=your-cortex-tenant-id-here
CLIENT_SECRET_LLM=your-cortex-client-secret-here
MODEL_CONFIG_NAME=your-cortex-model-config-name-here

# App
DEBUG=false
CORS_ORIGINS=["http://localhost:5173"]
DB_CONNECT_TIMEOUT=10

# History DB (ARC's own Postgres)
# Locally, leave DB_HOST empty to disable history persistence.
# In production, DB_HOST is set via ExternalSecret and the DB auto-enables.
# Set HISTORY_DB_ENABLED=false to explicitly disable even when DB_HOST is present.

# Only set these when you have a local Postgres available.
DB_HOST=
DB_PORT=5432
DB_NAME=your-db-name-here
DB_USER=your-db-user-here
DB_PASSWORD=your-db-password-here
DB_ROLE=your-db-role-here
DB_ROLE_PASSWORD=your-db-role-password-here

# SSO (Phase 2)
SSO_ISSUER=https://idp.internal.lilly.com
SSO_AUDIENCE=ai-readiness-evaluator
SSO_JWKS_URL=https://idp.internal.lilly.com/.well-known/jwks.json

# Support routing (Phase 2)
SUPPORT_SINK=email              # email | servicenow
SUPPORT_EMAIL_TO=ai-readiness@lilly.com
```

`.env` is gitignored. The example file holds placeholders only.

### Local history DB behavior

- Leave `DB_HOST` empty (or unset) for normal local development.
- With no host set, ARC skips user upserts, saved-run persistence, and history/admin DB reads.
- In production, `DB_HOST` is provided by the ExternalSecret and the DB auto-enables.
- Set `HISTORY_DB_ENABLED=false` to explicitly disable even when `DB_HOST` is present.

### Frontend environment variables (Vite)

Azure AD credentials are **no longer baked into the frontend bundle at build time**.
The frontend fetches `GET /api/config` from the backend at startup; the backend
returns `{clientId, tenantId}` from its own runtime environment. This eliminates
the class of cluster bugs where a stale frontend image had empty credentials.

**What this means for local dev:**
- `app/frontend/.env.local` no longer needs `VITE_CLIENT_ID` or `VITE_TENANT_ID`.
- Add `CLIENT_ID` and `TENANT_ID` to `app/backend/.env` instead.
- **The backend must be running** for the frontend to authenticate.

Add to `app/backend/.env`:

```
CLIENT_ID=your-azure-app-client-id
TENANT_ID=your-azure-tenant-id
```

In production/CI, these are set as runtime environment variables on the backend pod —
they are never passed as Docker build args.

### Local SSO testing

The Azure AD app registration includes `http://localhost:5173` as a redirect URI,
so the full login flow can be tested locally before pushing.

```bash
# 1. Ensure app/backend/.env has real CLIENT_ID and TENANT_ID
# 2. Start the backend
cd app/backend
uvicorn main:app --reload --port 8000

# 3. In a separate terminal, start the frontend dev server
cd app/frontend
npm run dev
# Open http://localhost:5173 — should redirect to Microsoft login
# Sign in with Lilly credentials → returns to app with your real name in the header
```

**Required before pushing any change to auth config, MSAL files, env vars,
`ci.yml`, or `Dockerfile`.**

Use the `deploy-safety` skill in Claude Code to run the full checklist
automatically: type "validate before push" in the prompt.

---

## Adding a new backend dependency

1. Add to `backend/requirements.txt` with a pinned minor version.
2. Rebuild the Docker image (`docker-compose build backend` from `app/`).
3. Mention it in the PR description.

## Adding a new frontend dependency

1. `npm install <pkg>` — npm updates `package.json` and the lockfile.
2. If it's a new top-level library (charting, routing, etc.), update
   `frontend/README.md`'s Tech line and `spec.md` § 5.

---

## Local SSO bypass

When developing without an IdP, `backend/dependencies.py` exposes a
`require_user` dependency that returns a fixture user when
`DEBUG=true` and no `Authorization` header is present. This bypass is
disabled in production by config.

---

## Logs

Use the `logging` module configured in `backend/main.py`. Levels:

- `INFO` — request received, assessment finished
- `WARNING` — LLM fallback triggered, DB introspection timed out
- `ERROR` — unhandled exception (paired with `HTTPException 500`)

DB passwords are masked as `***` in any log line. The masking is enforced in
`parser.py` and verified by `tests/test_parser.py`.

---

## Cluster image pinning

Deploy manifests must reference an **immutable sha-based tag** (e.g.
`ghcr.io/org/arc:main-sha-abc1234`) produced by `ci.yml`, never `:latest` or
a moving branch tag like `:main`.

Using a moving tag means a pod restart or rolling update can silently pull a
different image. With the current runtime-config architecture, the frontend
image is stateless (no credentials baked in), so stale frontend images no
longer cause the "Configuration Error" screen. However, if the **backend**
pod is missing `CLIENT_ID` / `TENANT_ID` env vars, `/api/config` returns 503
and the frontend will show the error.

**Diagnosis checklist when "Configuration Error" reappears in the cluster:**

```bash
# 1. Is the backend returning a valid /api/config response?
curl -s https://<cluster-host>/api/config  # should return {"clientId":"...","tenantId":"..."}

# 2. Are CLIENT_ID / TENANT_ID set on the backend pod?
kubectl exec <backend-pod> -- printenv CLIENT_ID

# 3. What digest is actually running?
kubectl get pod <backend-pod> -o jsonpath='{.status.containerStatuses[0].imageID}'
```

If `/api/config` returns 503, the backend env vars are missing from the
deployment manifest or secret binding. Fix the backend deployment — no image
rebuild needed.

