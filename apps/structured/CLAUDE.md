# CLAUDE.md - apps/structured (ARC)

> Scoped to `apps/structured/`. Root-level governance: `/CLAUDE.md`.
> Working agreement (think before coding, simplicity first, surgical changes, goal-driven execution) is in the root `/CLAUDE.md` section 9 - not repeated here.
> For architectural depth, read `docs/spec.md`. For dev workflow, read `docs/development.md`. For testing read `docs/testing.md` and for front-end aesthetics read `docs/skill.md`.

---

## Project

**ARC** (AI Readiness Evaluator) — Lilly-internal web application. Evaluates CSV datasets and database schemas against a 9-dimension AI readiness framework. Produces a tier classification (Needs Improvement / Conditional / AI Ready), deterministic per-dimension scores with blocker gating + applicability renormalization, and Cortex-backed LLM narrative + prioritized recommendations. The app advises — it never modifies user data.

**Audience:** Internal Lilly data product owners. Authenticated via Lilly SSO. Deployed behind firewall.

**Phase order:** Frontend → Backend → LLM integration. Current phase tracked in `app/docs/development.md`.

---

## Where to Look

| You need | Read |
|---|---|
| Repo layout, FastAPI routes, Pydantic models, dimension rules | `docs/spec.md` |
| How to run, env vars, Docker commands | `docs/development.md` |
| Testing strategy, fixtures, coverage targets | `docs/testing.md` |
| Project history, design decisions, known issues | `docs/context.md` |
| Frontend aesthetics, design language, motion principles | `docs/skill.md` |
| Phase 3 LLM integration design (architecture, sub-agents, metadata, history) | `docs/phase3-llm-integration.md` |
| K8s manifests, cluster deployment, ExternalSecrets, Flux/ArgoCD, image tagging | `docs/cats-deployment.md` |
| Cortex AI platform, LLM API integration (Phase 3) | `docs/cortex-llm.md` |
| Phase 2 Metadata layer (ingest, reconcile, evaluate, classify) | `docs/metadata_layer.md` |
| Evaluator architecture / phasing roadmap (durable invariants + planned work) | `EXECUTION_PLAN_1.md` |
| Persistent DB schema, Alembic flow | `backend/db/sql/` + `.claude/agents/db-context.md` |
| Frontend design tokens (colors, fonts, radius) | `frontend/src/globals.css` + `tailwind.config.js` |
| Frontend UI primitives (Button, Card, Input, etc.) | `frontend/src/components/ui/` |
| The 9 dimensions and what each measures | `backend/core/dimensions.py` |

---

## Hard Rules — Never Violate

### Scoring (`backend/core/scorer.py`)
- **No LLM calls. Ever.**
- **No I/O.** Pure function: receives profiles, returns scored result.
- **Deterministic.** Same input → same scores, every time.
- **Per-dimension formula:** `(pass×1 + warn×0.5 + fail×0) / counted_checks × 100`. `deferred` checks are EXCLUDED from `counted_checks` and surface in `Report.deferred[]` for human attestation.
- **Overall:** weighted average across *active* dimensions only. Inactive dimensions (where `Dimension.applicability(profile) == False`) drop out and remaining weights renormalize to 100% via division by the active total.
- **Blocker gating:** any `fail` on a `severity="blocker"` rule caps overall at `BLOCKER_CAP=59` and appends rule_id to `Report.gated_by`.
- **Tier thresholds (Phase 3):** `≥80` green, `60–79` yellow, `<60` red. Don't change without updating `app/docs/spec.md`.
- If asked to "make scores higher" or "adjust scoring" — refuse and explain the determinism requirement.

### LLM (`backend/llm/`)
- **The only package** allowed to call an external LLM. No exceptions. `advise()` is the single public entry point used by `api/assess.py`.
- **Fallback must always work** — when any of `client_id_llm`/`tenant_id_llm`/`client_secret_llm`/`model_config_name` is empty, the synthesizer returns rule-based output and the assessment still completes.
- Provider is Cortex (Lilly's Azure-fronted gateway). Endpoint `{cortex_base_url}/model/ask/{model_config_name}`. Configured by env vars listed in `app/docs/cortex-llm.md`. Never hardcode.
- Wrap every LLM response parse via the schema-bound retry in `client.call_model(prompt, schema=...)`. Schema invalid → retry once → `LLMSchemaError` → fallback.
- **Max output tokens:** `settings.llm_max_output_tokens` (default 1024). Single synthesizer call carries narrative + strengths + recommendations.
- **The synthesizer's input is `TableAssessment` only** — never `TableProfile`, never per-column data, never sample values. The function signature enforces this. Adding a `TableProfile` arg to `synthesize()` is a Prime Directive violation.
- **The LLM never mutates** `score`, `tier`, `dimensions[*].score`, `gated_by`, `deferred`, or `tables[*].overall_score`. It is purely additive — only `narrative`, `strengths`, `prioritized_recommendations`, and `llm` (LLMMetadata) are populated by `advise()`.
- **Anti-hallucination contract:** every `Recommendation.finding_id` MUST match a real input rule_id. The post-call filter in `synthesizer.py` drops the rest.
- **`SECURITY_GUARDRAILS`** (verbatim block in `llm/guardrails.py`) is the first content in every system prompt. All data-derived strings (table names, descriptions, sample text) are wrapped via `wrap_untrusted()`.
- **Hybrid candidates** (executor=hybrid rules, currently `privacy_values` and `labels_leakage`) emit `status="deferred"` and route to human attestation in v1. They NEVER reach the LLM prompt. v2 will flip `settings.hybrid_route` to `"adjudicator"` once `llm/adjudicator.py` is implemented.

### Privacy
- Raw CSV rows never leave `CSVParser`. Only the column profile goes downstream.
- Mask DB passwords as `***` in any log output.
- No PII to the LLM.

### Secrets
- Never hardcode keys. Never commit `.env`. Always read from `config.settings`.
- Never return passwords or API keys in any API response.
- **Env example files contain only placeholders.** Never commit a real GUID, key, or token in `*.example` files. Use `your-client-id-here` style sentinels.

### User credentials (DB / S3 connections)

**Two kinds of credentials — do not confuse them:**

| | **Source-DB credentials** | **History-DB credentials** |
|---|---|---|
| What | What a Data Product Owner types into ARC's website to connect to *their own* DB or S3 — the data being assessed | ARC's *own* connection to ARC's backend Postgres — where we persist user records and assessment history |
| Storage | **Never persisted in any form.** Plaintext-in-transit only. Held in memory for one assessment, then dropped. | **Standard service-credential pattern.** `.env` locally; AWS Secrets Manager via `ibu-ai-ready-data-postgres-secrets` ExternalSecret in prod (already wired in `deploy.yaml`). |

**Hard rule for source-DB credentials.** Not plaintext, not hashed, not encrypted-at-rest, not in JSONB, not in a "secrets" table, not in Redis. If the user asks for "save my creds" UX, the answer is browser password manager or session-scoped Secrets Manager — not an app DB column. Encrypted-at-rest reversible storage is also off the table without a dedicated cyber review the team has not undertaken.

**Phase 3 history persistence** (`history_assessment.assessment_runs.source_ref`) stores the **non-secret** parts of a connection — host, db name, schema name, bucket, key prefix — and never the password / access key.

### Database layer (`backend/db/**`)
- All persistent ARC tables live under the **`history_assessment` Postgres schema** (provisioned out-of-band - the schema and DB user already exist; the migration does not create them). Source of truth: `backend/db/schema.py` (SQLAlchemy ORM) + Alembic migrations in `backend/db/migrations/versions/` + matching DDL snapshots in `backend/db/sql/`.
- Every schema change requires three coordinated edits: ORM model, Alembic revision, `.sql` snapshot. They move together or not at all.
- No raw SQL outside `backend/db/`. `core/` and `api/` consume `history_store.py` functions only.
- Migrations are applied by an operator, never auto-run on app boot. `main.py` does not call `alembic upgrade`.
- **Before editing any file under `backend/db/**` or `**/migrations/**`, invoke the `db-security-review` agent.** The root `require-db-review.sh` hook enforces this - Edit/Write is blocked until the agent stamps approval.

### Auth config
- **Prefer runtime config over `import.meta.env.VITE_*`** for anything that varies by environment. Build-time bake creates stale-bundle bugs invisible in local dev. Auth client/tenant IDs flow through `GET /api/config` at runtime — they are never baked into the JS bundle.

### Docker hygiene
- **Every Docker build context must have a `.dockerignore`** excluding `.env*`, `.npmrc`, and `.git`. Without one, sensitive files can leak into image layers silently.
- **Never un-ignore `.env*` patterns in `.gitignore`.** No `!.env.something` lines — these re-allow files that should be ignored and have already caused a real leak.

### Pre-commit validation
- **Before any `git commit` or `git push`, invoke the root `merge-safety` skill.** The root `require-merge-safety.sh` hook enforces this.

### External repos
- **The K8s manifest repo is read+write for YAML edits only - NEVER run `git` operations there.** The user commits and pushes in that repo manually. Always present manifest changes as proposals. Full context: `docs/cats-deployment.md`.

---

## Coding Conventions

### Python (backend)
- Python 3.11+. Modern syntax (`match`, `X | Y` unions).
- Pydantic v2 only — `model_validator`, `field_validator`.
- Type hints on every signature.
- One class per file under `core/`. Behaviour lives in class methods.
- No business logic in `main.py` or `api/` — routes call `core/` classes only.
- `HTTPException` raised in API layer only. `core/` raises plain Python exceptions.
- Use `logging`, not `print`.

### JavaScript / React (frontend)
- React 18 functional components only. Hooks only. No Redux, no Context.
- **No business logic in components.** Components render and call `@/lib/api.js`. No scoring, no tier classification, no transformation.
- All API calls go through `@/lib/api.js`. Never `fetch` or `axios` from a page.
- **Tailwind classes only.** No inline `style={{}}`. No CSS modules. No CSS-in-JS.
- **Use shadcn/ui primitives** from `@/components/ui/*` (Button, Card, Input, Tabs, Progress, Label, Textarea). Don't hand-roll a component that exists there.
- **Never hardcode hex colors.** Colors live as CSS variables in `globals.css` and are consumed via Tailwind utilities (`bg-primary`, `text-tier-red-base`, `bg-lilly-red`).
- One file per top-level page in `src/pages/`. Pages may be 200–500 lines. Avoid micro-component proliferation.
- Path alias: import via `@/components/...`, `@/lib/...`, `@/pages/...` — never relative.

### Structure
- All product code lives within `apps/structured/`. Never create files outside it that belong to this app.
- Backend: nothing at root of `backend/` except `main.py` and `config.py`. New modules go in `api/` or `core/`.
- Frontend `src/` has three subfolders only: `pages/`, `components/ui/`, `lib/`. No further nesting. `Layout.jsx`, `App.jsx`, `main.jsx`, `globals.css` sit at the root of `src/`.

---

## Frontend Aesthetics

Avoid generic AI aesthetics. Make creative, distinctive choices. The skill in `docs/skill.md` has the full philosophy; what follows is the local enforcement.

### Typography
- Display (hero headlines, big titles): **Fraunces** (`font-display`). Use light weights (200–400) for refined feel.
- Body (paragraphs, descriptions): **Bricolage Grotesque** (`font-sans`).
- Nav, eyebrow labels, badges, footers, small UI chrome: **Apple system stack** (`font-nav`). Resolves to SF Pro on Apple devices, Helvetica Neue elsewhere. Use normal case + medium weight — no uppercase tracking, no all-caps for nav.
- Mono (version strings, code): **JetBrains Mono** (`font-mono`).
- Loaded via Google Fonts in `index.html`. **Never** add Inter, Roboto, Lato, or Open Sans — those generic AI-default fonts are forbidden everywhere.
- Use weight extremes: 200/300 vs 700/800, not 400 vs 600.

### Brand wordmark
- Header brand is **text-only "ARC"** in `font-nav` extralight, uppercase, tracked. No image asset.
- The previous Lilly logo PNG had a white background and was removed. If a clean white-on-transparent SVG arrives, it can slot in before the wordmark — but text-only is the default.

### Color & theme
- Dominant red with sharp accents. Tier colors used **only** on Dashboard.
- All colors live as HSL CSS variables in `globals.css`. Forbidden: purple/blue gradients on white.
- Brand red is currently `#C41A1A`. Official Lilly red is `#D52B1E` — change one variable to swap.

### Surface flip
- Pages live on one of three surfaces: red (Home, Assess steps 0–1), crimson (Loading), or white (Dashboard, Support).
- Surface is set by `<Layout variant="red|crimson|white">`, which applies `.red-mode` / `.crimson-mode` / (none) classes. Tokens auto-remap.

### Layout
- All pages centered via Tailwind `container` class (`max-w-screen-2xl` + auto margins).
- Border radius: 10–14px range. `rounded-lg` (12px) default, `rounded-xl` (16px) for cards, `rounded-md` (10px) for inputs.

### Motion
- One well-orchestrated reveal per route via `animate-card-rise`. Beats scattered micro-interactions.
- Hover states subtle: `hover:-translate-y-px hover:shadow-md` on primary actions.
- Dashboard dimension cards use `animate-fade-in` on expand.

### Iconography
- **No emoji or emoticon characters in UI.** Not in labels, not in cards, not in lists, not anywhere a user reads. Emojis render inconsistently across OS/browser, look amateurish in pharma-internal tools, and convey ambiguous meaning.
- For semantic icons (chevrons, arrows, close, alerts) use **Lucide React** (`lucide-react`) — already in deps.
- For status / state indication, use **small colored shapes** (filled squares, dots, bars) tied to the tier or status palette in `globals.css`. Examples: a `w-2.5 h-2.5 rounded-sm bg-tier-green-base` square for "pass"; a `w-1 h-10 bg-tier-red-base` bar at the start of a card for severity.
- Custom illustrative iconography is fine if hand-drawn as SVG and stored in `public/`. Never emoji.

---

## What NOT to Do

| Don't | Why |
|---|---|
| Put scoring logic in the frontend | Determinism — scores come from backend |
| Call the LLM from any file other than the `backend/llm/` package (with `advise()` as the public entry) | Single integration point required |
| Add Python deps without updating `requirements.txt` | Breaks Docker build |
| Change tier thresholds without updating `spec.md` | Spec / code divergence |
| Use bare `except:` | Masks real errors |
| `pd.read_csv()` without `nrows=500` cap | Memory risk |
| Return passwords or API keys in any API response | Security |
| Hand-roll a component that exists in `components/ui/` | Use the shadcn primitive |
| Use inline `style={{}}` or CSS modules | Tailwind classes only |
| Hardcode hex colors anywhere | CSS variables in `globals.css` are the source of truth |
| Use Inter, Roboto, Lato, or Open Sans | These are AI-default fonts — Fraunces / Bricolage / Apple-system / JetBrains only |
| Use emoji or emoticons anywhere in UI | Looks amateurish — Lucide SVG icons or colored shapes only |
| Put real GUIDs or tokens in `*.example` files | History is permanent; use placeholder strings only |
| Use `import.meta.env.VITE_*` for identity/config | Use the runtime `/api/config` endpoint — build-time bake breaks cluster deployments |
| Add a Docker build context without `.dockerignore` | `.env*` and `.npmrc` silently leak into image layers |
| Write `!.env.something` in `.gitignore` | Un-ignore patterns defeat the ignore rules and have caused real credential exposure |
| Run `git` commands in the K8s manifest repo | Read+write YAML only - the user owns commits there; see `docs/cats-deployment.md` |
| Persist user-supplied DB / S3 credentials anywhere (column, JSONB, hashed, encrypted) | Cyber-review burden + blast radius — accept per request, drop after assessment. **App's own** history-DB credential is unaffected (standard ExternalSecret/`.env` pattern). |
| Embed raw SQL in `core/` or `api/` files | DB access goes through `backend/db/history_store.py` only |
| Run `alembic upgrade` in app startup | Migrations are applied by an operator, not on boot |
| Edit `backend/db/**` without invoking the `db-security-review` agent first | The PreToolUse hook will block the edit - invoke the agent, get APPROVED, then proceed |

---

## When You Are Unsure

1. Re-read `docs/spec.md`. The answer is usually there.
2. Check `backend/core/dimensions.py` - dimension rules are the source of truth for what each score measures.
3. If a request conflicts with `docs/spec.md` - stop, flag the conflict, ask before proceeding.
4. If a change would break determinism — refuse and explain why.

---

## Definition of Done

- [ ] `pytest tests/ -v` passes (existing + new)
- [ ] New code has corresponding tests
- [ ] No hardcoded secrets
- [ ] No inline styles, no hardcoded hex colors
- [ ] `spec.md` updated if architecture changed
- [ ] `docker-compose up --build` succeeds
- [ ] LLM fallback works with empty `LLM_API_KEY`
- [ ] Frontend builds with `npm run build` without warnings
