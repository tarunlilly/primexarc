# PrimeXarc Unification Runbook (for Claude Code)

> Execution-only. No rationale, no restated background.
> Full analysis and reasoning: `docs/architecture-unification-plan.md`. Read that only if a step below is unclear.
> Hard rules (scorer purity, LLM boundary, credential handling, cross-app import ban) already live in root `CLAUDE.md` and the per-app `CLAUDE.md` files — do not re-derive them here, they auto-load.

**Assumption locked in by user (2026-09-08): infra consolidates onto one platform, not two.**
PrimeData's existing infra (namespace `primedata-dev`, RDS `primedata-db-dev`) is the baseline, per the standing "bias toward PrimeData" instruction.
ARC gets a new schema on that same RDS instance and equivalent resources (deployment, ingress host, secrets) inside that same namespace, replacing its own separate `ibu-ai-ready-data-dev` namespace and RDS instance over time.
**If this assumption is wrong** (i.e. ARC's infra is the intended baseline instead), stop and correct step 1 before proceeding — everything after it depends on which platform is "home."

---

## 0. Preconditions (block everything until done)

- [ ] Rotate the 3 exposed Artifactory tokens (`apps/structured/frontend/.npmrc`, `apps/unstructured/frontend/.npmrc`, `apps/shell/.npmrc`).
- [ ] `git add -A && git commit` at repo root. Confirm no `.env`/`.npmrc` staged first (`git status`).
- [ ] Get a direct answer, outside this repo, on whether `primedata-dev`'s Airflow webserver/scheduler are actually live despite the `NOT USED IN CATS` label in `deploy.yaml`. Blocks step 6.
- [ ] Get a direct answer on Elasticsearch vs. OpenSearch (real: Elasticsearch 7.16.1 per manifest) and Next.js vs. Vite (real: manifest env vars look Next.js) for PrimeData's frontend. Fix whichever of `apps/unstructured/CLAUDE.md` or the manifest is stale.

## 1. Lock the infra decision

1. Confirm with the user: PrimeData's namespace (`primedata-dev`) and RDS instance (`primedata-db-dev`) are the target for both apps. If confirmed, update root `CLAUDE.md` section 0 and section 4 to state this as decided, not open.
2. Update root `CLAUDE.md`'s stale "governance scaffold only, no code migrated" line — all three apps (`structured`, `unstructured`, `shell`) are already fully migrated.
**Gate:** `CLAUDE.md` reflects both facts correctly.

## 2. Add ARC's schema to PrimeData's RDS instance

0. Confirmed low-risk: ARC's own RDS (`ibu-ai-ready-data-rds`) and `primedata-db-dev` already share one VPC security group (`sg-0fc1ecf123aa058f0`) — same network, so reachability is not an open question. ARC's actual footprint is small (250m/256Mi request, 1000m/768Mi limit) against PrimeData's existing 8 CPU/32Gi request — no capacity upsizing expected on the target instance.
1. In `primedata-dev`'s RDS instance (`primedata-db-dev`, Postgres 17.2), provision a `history_assessment` schema alongside PrimeData's own (default `public`).
2. Point ARC's backend config (`apps/structured/backend/config.py`) at that RDS endpoint via env var, not hardcoded.
3. Do not touch ARC's ORM models, Alembic revisions, or `.sql` snapshots — same schema name, same tables, new physical host only.
4. **Before touching anything under `apps/structured/backend/db/**`, invoke the `db-security-review` agent** — the repo's own hook blocks the edit otherwise.
**Gate:** ARC's backend connects to the new host; `history_assessment` schema exists with all 4 expected tables; PrimeData's own schema/tables are untouched.

## 3. Move ARC into `primedata-dev`'s namespace

1. Add ARC's deployment/service to the `primedata-dev` manifest repo (same repo PrimeData's `deploy.yaml` lives in), reusing PrimeData's existing service-account/secrets patterns where they overlap (e.g. `aws-secretstore`).
2. Give ARC a hostname consistent with PrimeData's pattern (subdomain under `.apps.lrl.lilly.com`, not a path prefix) — e.g. `ibu-ard.apps.lrl.lilly.com`, replacing `ibu-ard.bu.lilly.com`.
3. Decommission the old `ibu-ai-ready-data-dev` namespace only after the new deployment is verified end-to-end (don't delete the safety net early).
4. Copy ARC's `secret.yaml` ExternalSecrets and `rds-postgres.yaml`-equivalent pattern into the new namespace context (values change, structure doesn't).
**Gate:** ARC's app is reachable at its new hostname inside `primedata-dev`; old namespace still exists as fallback; no manifest changes touch PrimeData's own resources beyond additions.

## 4. Point the shell at both apps' (new) real hostnames

1. Fix `apps/shell`'s `getStructuredUrl()` / `getUnstructuredUrl()` to return the post-migration hostnames from step 3 (both now under `primedata-dev`'s domain pattern).
2. Give the shell its own hostname in the same namespace.
**Gate:** both landing-page doors resolve to the correct, now-consolidated apps.

## 5. Auth unification (ARC → Bouncer)

1. Add Bouncer-header identity extraction to ARC's backend (`apps/structured/backend/dependencies.py`), alongside the existing JWKS path, behind a flag.
2. Verify ingress strips client-supplied identity headers before trusting them (same guarantee PrimeData's ingress already provides).
3. Requires `auth-unification-reviewer` sign-off before flipping the flag in any shared environment.
4. Don't delete the MSAL/JWKS path until the Bouncer path has soaked.
**Gate:** sign-off recorded; real Bouncer request resolves correct identity; forged-header direct-to-pod request rejected.

## 6. Orchestration (ARC → Airflow) — only after precondition on Airflow's real status is answered

1. If Airflow is confirmed live: register a DAG in `primedata-dev`'s Airflow (now shared, since ARC lives in the same namespace) that calls ARC's API to trigger/poll an assessment. No direct Python import of ARC's code.
2. Never touch `core/job_store.py` or `core/scorer.py` internals — only how a run is triggered/tracked.
**Gate:** `test_scorer_is_deterministic()` unmodified and passing; DAG-triggered run matches direct-API-triggered run bit-for-bit.

## 7. Fix pre-existing CI gaps (independent of the above, do in parallel)

1. ARC: wire `pytest tests/ -v` into CI (198 tests currently don't run).
2. PrimeData: fix CI test job's Python version (3.9 → 3.11+), un-skip the disabled test job.
**Gate:** both CI pipelines show a real, passing test stage.

## 8. Extract `packages/shared-ui` (last)

1. Only after steps 1-7 are stable: pull design tokens, Help/Support shell, nav chrome, and the Bouncer auth-session hook (already proven in `apps/shell`) into `packages/shared-ui`.
2. `enforce-boundary.sh` must block any product-logic import into it.
**Gate:** both frontends can import chrome-only from `packages/shared-ui`; hook blocks a deliberate product-logic import attempt.

---

## Still open (answer before or during the relevant step)

- Airflow real status in `primedata-dev` (blocks step 6).
- Elasticsearch vs. OpenSearch, Next.js vs. Vite for PrimeData's frontend (precondition 0).
- Root-scoped vs. `apps/structured`-scoped placement of `bug-finder`/`code-quality`/`maintainability`/`race-conditions`/`test-flakiness` agents (cosmetic, not blocking).
- Target remote repo (Azure DevOps project or other) — zero commits exist anywhere as of this writing.
