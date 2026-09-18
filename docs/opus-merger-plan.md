# PrimeXarc Merger Plan (for Claude Opus 4.6)

> Execution-oriented. Supersedes the infra direction in `docs/unification-runbook.md` and `docs/architecture-unification-plan.md` (both assumed PrimeData's RDS/namespace as home - reversed below, see section 0). Those two docs are still useful for background reasoning; this file is the current source of truth for what to build.
> Root `CLAUDE.md` hard rules (scorer purity, LLM boundary, no cross-app imports, credential handling) still apply and auto-load - not repeated here.

## 0. What changed vs. earlier plans (read this first)

The user has locked a different, narrower direction than the earlier "consolidate onto PrimeData's namespace/RDS" plan:

1. **No code relocation.** ARC's backend/frontend and PrimeData's backend/frontend all stay exactly where they are (`apps/structured/`, `apps/unstructured/`). The merger adds a thin layer on top - a unified home/Help/Support surface and a routing rule - it does not move or restructure either app's existing code.
2. **Routing is path-based on one domain**, not subdomain-per-service. `x.com/structured/*` -> ARC, `x.com/unstructured/*` -> PrimeData, `x.com/` -> new unified home. This reverses the "subdomain-per-service, matching PrimeData's real ingress pattern" conclusion in `architecture-unification-plan.md` section 3 (dimension 15) - that conclusion was based on how PrimeData happens to be deployed today, not on what the user actually wants long-term. Deliberately overridden here.
3. **Database home flips to ARC, not PrimeData.** Earlier plan said "PrimeData's RDS is home, ARC gets a schema there." User now wants the opposite: ARC's existing RDS (`ibu-ai-ready-data-rds`) becomes home, and PrimeData's schema/tables get created there "with exact flow" - i.e. run PrimeData's own 33 Alembic migrations against ARC's Postgres instance, don't hand-invent a new schema.
4. **LLM calls unify on ARC's Cortex credentials.** PrimeData's `cortex_client.py` keeps its own endpoint shape and prompt logic, but authenticates using ARC's `client_id_llm`/`tenant_id_llm`/`client_secret_llm` instead of its own.
5. **Backend stays separate, explicitly.** The user does not want backend logic touched beyond the DB-host and LLM-credential changes above - "backend can be separate as it might affect the core features of the platform." Do not refactor, merge, or restructure either backend beyond what sections 4 and 6 below require.
6. **Frontend JS framework converges to one**, without touching page/component logic - this is a build-tooling change, not a rewrite. See section 5 - this step is blocked on one open question that must be resolved first.

## 1. Open question - resolve before starting section 5

`apps/unstructured/CLAUDE.md` documents PrimeData's frontend as "Vite SPA, NOT Next.js despite similar structure." But the real `primedata-dev/deploy.yaml` env vars (`NEXTAUTH_URL`, `NEXTAUTH_SECRET`, `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_API_BASE`) are Next.js-shaped, and this was never resolved (see `architecture-unification-plan.md` section 1a). Before touching the frontend framework at all: check `apps/unstructured/frontend/package.json` directly for `next` vs `vite` as a dependency, and check which one actually builds `apps/unstructured/frontend/dist` or `.next`. Whichever is real determines the migration direction in section 5 - don't guess from docs that have already been shown to be wrong once.

## 2. Unified home page

1. Location: build this in `apps/shell` (already exists, already has Bouncer auth bootstrap and a two-panel `Landing.tsx` - see `apps/shell/CLAUDE.md`). Do not create a second new shell; extend the existing one.
2. Content: center brand reads "PRIMEDATA". Two selectable options labeled Structured and Unstructured (internal naming already used everywhere in this repo maps to ARC and PrimeData respectively - keep that mapping, don't invent new labels).
3. Remove ARC's own `Home.jsx` (`apps/structured/frontend/src/pages/Home.jsx`) and its route registration - the shell's landing page replaces it. Check `App.jsx`/router config in `apps/structured/frontend` for any other page that assumes `/` is Home (e.g. a redirect-after-login) and update those references to point at the app's new base path (`/structured`, see section 3).
4. PrimeData's frontend: check whether it has an equivalent standalone landing/home route serving `/` today. If so, same treatment - remove it, route registration updates to reflect the app now living under `/unstructured`.
**Gate:** hitting `x.com/` renders the new shell home, not either app's old landing page; neither app's own frontend still tries to own the bare `/` route.

## 3. Path-based routing on one domain

1. Both apps keep their current internal route structures unchanged - only their **base path** changes: ARC's frontend build gets `base: "/structured/"` (Vite config) and its router `basename="/structured"`; PrimeData's frontend gets the equivalent for whichever framework section 1 confirms (Vite `base` + router `basename`, or Next.js `basePath` config).
2. Backend API calls: prefer an ingress-level path-rewrite (strip `/structured` or `/unstructured` before forwarding to each backend service) over changing either backend's route prefixes - this keeps `apps/structured/backend`'s `PREFIX = "/api/v1"` and `apps/unstructured/backend`'s per-router `/api/v1/*` prefixes untouched, avoiding any backend code change for routing alone.
3. Implement the three path rules (`/`, `/structured/*`, `/unstructured/*`) as Kubernetes Ingress rules on one host, in whichever manifest repo becomes canonical (open question - not decided in this plan; ask before writing manifests, since it wasn't specified here and the two apps currently live in different namespaces/manifest repos entirely).
4. Do not use React Router `<Link>` or client-side navigation between `/structured` and `/unstructured` - they remain effectively separate SPAs sharing one domain and one ingress, not one merged single-page app. Plain `<a href="/structured">` / `<a href="/unstructured">` from the shell, matching what `apps/shell/src/pages/Landing.tsx` already does structurally (just correct the href values from the old subdomain assumption to the new path prefixes).
**Gate:** `x.com/structured/` loads ARC end-to-end (frontend assets resolve, API calls succeed) with no separate ARC hostname needed; same for `x.com/unstructured/`; no `/api/v1/*` collision since ingress-level path stripping means each backend only ever sees its own prefix removed, and the two backends are still on separate origins/services behind the one ingress.

## 4. Unified Help Center and Support

1. Build one Help Center and one Support page in `apps/shell`, covering both products' content (ARC's existing 5-chapter Help Center content plus PrimeData's equivalent, if it has one - check `apps/unstructured/frontend` for an existing Help/Support page before assuming it doesn't).
2. Remove `apps/structured/frontend/src/pages/HelpCenter.jsx` and `Support.jsx` (or whatever PrimeData's equivalents are named) once the shell versions cover the same content - don't leave two competing Help Centers live at once.
3. Any product-specific Help content (e.g. ARC's dimension explanations, PrimeData's connector setup) stays as sub-sections within the one shared Help Center, not as a separate per-app page.
**Gate:** one Help Center URL and one Support URL work for both products; neither `apps/structured` nor `apps/unstructured` still ships its own competing version.

## 5. Frontend framework convergence (blocked on section 1's answer)

1. Once section 1 confirms which framework PrimeData's frontend actually runs, converge both frontends onto the same one. Given ARC is confirmed Vite + React + JS today, and PrimeData is *either* already Vite (per docs) or Next.js (per infra):
   - If PrimeData is already Vite: nothing to converge here, skip to section 6. (worth double-checking there isn't some other JS-library split the user meant - see note below)
   - If PrimeData is actually Next.js: migrate it to Vite + React, keeping every page/component's logic and markup intact - this is a build-tool and routing-shim swap (Next's file-based router -> React Router, `next/image`/`next/link` -> plain equivalents), not a rewrite of business logic. Do not touch `apps/unstructured/backend` as part of this.
2. If the "two different JS libraries" the user meant is something other than Next.js vs. Vite (e.g. a state-management or data-fetching library), re-confirm with the user what specifically differs before picking a target - don't guess a second time on a point already gotten wrong once (Elasticsearch/OpenSearch, Next/Vite).
**Gate:** both frontends build with the same tool (`vite build`); `apps/unstructured/backend` diff is empty (confirming no backend logic was touched by this step).

## 6. Database: PrimeData's schema onto ARC's RDS

1. Target: ARC's existing RDS instance (`ibu-ai-ready-data-rds`, Postgres 17.5, `ibuarcdevdb`). ARC's own tables live under the `history_assessment` schema - PrimeData's tables should land in the default `public` schema on that same instance, which is what PrimeData's `POSTGRES_SCHEMA` already defaults to. No schema-name collision: `history_assessment` != `public`.
2. "With exact flow" = run PrimeData's own 33 Alembic migrations, unmodified, against the new host. Do not hand-write new DDL or attempt to recreate the schema by reading `models.py` and generating fresh SQL - point PrimeData's Alembic config at ARC's RDS connection string and run `alembic upgrade head` there, exactly as it would run against `primedata-db-dev` today.
3. Update PrimeData's backend config (env vars / secret references) to point at ARC's RDS endpoint and ARC's connection secret, replacing `primedata-rds-secrets`. Confirm network reachability first - recall ARC's RDS and PrimeData's RDS already share one VPC security group (`sg-0fc1ecf123aa058f0`), so this is not a new-network problem.
4. Before any `apps/unstructured/**/db/**` change: this repo's `db-security-review`-equivalent gate should run first, per root `CLAUDE.md` section 3.4's stated intent to extend that hook pattern to PrimeData once its first schema change lands - this is that moment.
5. Decommission `primedata-db-dev`'s RDS instance only after the migrated one is verified end-to-end - don't delete the fallback early.
**Gate:** `alembic upgrade head` succeeds against ARC's RDS with zero manual DDL edits; PrimeData's backend reads/writes correctly against the new host; ARC's `history_assessment` schema and its 4 tables are untouched; a query against `public.*` on ARC's RDS shows PrimeData's 20+ tables.

## 7. LLM calls: ARC's Cortex credentials for both apps

1. ARC's Cortex credentials live in the ExternalSecret `ibu-ai-ready-data-cortex-llm` (`client-id-llm`, `tenant-id-llm`, `client-secret-llm`, `model-config-name`), sourced from AWS Secrets Manager `ibu-arc-dev/ibu-ai-ready-data/cortex-llm`.
2. Point `apps/unstructured/backend/src/primedata/services/cortex_client.py`'s OAuth token acquisition at these same values instead of PrimeData's own Cortex credential set. This is exactly the "shared auth token acquisition helper" carve-out already permitted in root `CLAUDE.md` section 3.5 - it does not require creating a shared LLM package, and does not change PrimeData's endpoint shape (`{base}/model/ask-with-custom-prompt/{model_id}`, different from ARC's `{base}/model/ask/{model_config_name}`) or prompt logic.
3. Do not route PrimeData's LLM calls through ARC's `llm/advise()` - that stays ARC-only per the existing hard rule. This step only changes whose credentials PrimeData's own, unchanged LLM client authenticates with.
4. Confirm ARC's Cortex app registration/model-config actually grants access to whatever model PrimeData's mid-pipeline transformation calls need (embedding model, summarization model) - ARC's registration was scoped for its own narration use case and may not currently include PrimeData's models. This is worth a direct check with whoever owns the Cortex registration before assuming it just works.
**Gate:** PrimeData's backend successfully authenticates to Cortex using ARC's credentials in a non-prod test; PrimeData's own `llm/`-equivalent code path and prompt logic are otherwise unchanged (diff review, not just "it ran").

## 8. Definition of done for this merger phase

- [ ] Section 1's framework question answered from `package.json`/build output, not from either doc or the manifest (both have been wrong once each)
- [ ] `x.com/`, `x.com/structured/`, `x.com/unstructured/` all resolve correctly on one domain
- [ ] ARC's old `Home.jsx` and both apps' old Help/Support pages are removed, not just superseded-but-still-present
- [ ] Both frontends build with one framework/tool
- [ ] `apps/structured/backend` and `apps/unstructured/backend` have zero logic diffs beyond the DB-connection and LLM-credential changes in sections 6 and 7
- [ ] PrimeData's 20+ tables exist in `public` on ARC's RDS via unmodified Alembic migrations; `history_assessment` untouched
- [ ] PrimeData's LLM calls authenticate via ARC's Cortex credentials; endpoint/prompt shape unchanged
- [ ] `merge-safety` skill run before any commit/push
