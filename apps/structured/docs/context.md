# Project Context

> Refreshed handoff document. Replaces the original `context_file.md` from the
> artifact prototype thread. Paste this at the start of a new Claude thread to
> restore context, plus `CLAUDE.md` and `docs/spec.md`.

---

## What this project is

A Lilly-internal web application that evaluates CSV datasets and database
schemas for AI readiness. Scores data across 9 weighted dimensions, classifies
each into one of three tiers, and generates actionable recommendations.

**The app advises — it never modifies user data.** Data product owners decide
whether to act on the recommendations.

---

## Phase status

> Updated 2026-09-18 against actual code in this app (`apps/structured/`), not carried over from the pre-migration prototype doc. See "What's been built" below for detail. Note: this migrated copy lags the original `ibu-ai-ready-data` source repo by a small amount - a `lens_scores` recompute block in one rescore function in `scorer.py` exists in the source but not here yet. Worth a targeted sync if that function matters to current work.

| Phase | Component       | State |
|-------|-----------------|-------|
| 0     | Prototype artifact (single-file React) | Complete |
| 1     | Production frontend | Complete - 9 pages, 10 shadcn primitives (see below) |
| 2     | Backend (FastAPI + scorer + parser) | Complete - archetypes, capabilities, verdict engine added on top of the base scorer |
| 3     | LLM integration (`llm/` package) | Complete - `advise()` plus evidence/purpose narrators and an adjudicator stub |
| 4     | Assessment history | Complete - `History.jsx` is real and API-backed (`api.getHistory/clearHistory/deleteRun`), attestations table added (migration 0004) |

---

## Design decisions (do not revisit without good reason)

| Decision | Rationale |
|---|---|
| Scoring is deterministic Python in production | LLM-based scoring in the prototype was inconsistent run-to-run on the same CSV. Determinism was the explicit fix. |
| LLM writes narrative, recommendations, and (since Phase 3 additions) evidence/purpose narration - never a score | Single responsibility: scoring is Python, language is the LLM. Enforced as a hard rule in `apps/structured/CLAUDE.md` - `advise()` may never write `score`/`tier`/`gated_by`. |
| LLM integration isolated to the `llm/` package, `advise()` as the single public entry point | One integration point for the operator to swap providers. The package has grown (`advisor.py`, `annotator.py`, `evidence_narrator.py`, `purpose_narrator.py`, `synthesizer.py`, `adjudicator.py`, `guardrails.py`, `client.py`) but the one-entry-point contract still holds. |
| Tier thresholds: ≥80 green, 60-79 yellow, <60 red, blocker gating caps overall at 59 | Updated from the original prototype thresholds (≥65/40-64/<40). Verified current in `backend/core/scorer.py` (`GREEN_MIN=80`, `YELLOW_MIN=60`, `BLOCKER_CAP=59`) and matches `apps/structured/CLAUDE.md`. Baked into spec - don't change without updating `spec.md`. |
| Frontend is display-only | No scoring logic in React. All results come from the backend. |
| CSV parser caps at 500 rows, sends profile not rows | Privacy — raw data never leaves the parser. |
| Frontend `src/` uses `pages/`, `components/ui/`, `lib/` subdirs only | shadcn/ui convention; everything else stays flat. |
| All hex values in `globals.css` as CSS variables | Single source; Tailwind reads them via `hsl(var(--x))`. |
| Lilly-internal only, SSO-gated, behind firewall | Confirmed audience in Phase 1 planning. |

---

## The 9 scoring dimensions

See `docs/spec.md` § 3 for the full table including weights. Source of truth for
rules: `backend/core/dimensions.py` (Phase 2).

---

## Visual design system

All design tokens live as HSL CSS variables in `frontend/src/globals.css` and
are exposed to Tailwind via the config. Components consume them through
utility classes (`bg-primary`, `text-tier-red-base`, `bg-lilly-red`) — never
inline hex.

**Brand palette:**
- `--lilly-red` = `#C41A1A` — primary brand surface (Home, Assess steps 0–1)
- `--lilly-dred` = `#7F1111` — dark red, headings on white pages
- `--lilly-crimson` = `#8B0000` — crimson, loading screen only

**Surface flip:**
- Home, Assess steps 0–1 → `red-mode` class on Layout root
- Loading (step 2) → `crimson-mode`
- Dashboard, Support → default (no mode class, white background)

The mode classes remap the CSS variables (`--background`, `--foreground`,
`--primary`, `--border`) so every shadcn primitive theme-flips automatically.

**Tier palette** (used only on the dashboard):
- Green base `#15803D` / light `#DCFCE7`
- Amber base `#B45309` / light `#FEF3C7`
- Red base   `#C41A1A` / light `#FEE2E2`

Exposed as `bg-tier-green-base`, `text-tier-green-base`, `bg-tier-green-light`
and corresponding amber/red variants.

**Motion:** `animate-card-rise` keyframe (Tailwind config) — translateY(40px)
+ scale(0.96) + opacity 0 → rest, 600ms cubic-bezier(0.16, 1, 0.3, 1).
Applied to every route and step entry.

**Typography:**
- Display: **Fraunces** (variable serif, weights 300–900) — hero headings
- Body: **Bricolage Grotesque** (variable sans, weights 200–800) — paragraphs and UI
- Mono: **JetBrains Mono** — version strings, weights, code

Loaded via Google Fonts in `index.html`. Tailwind utility classes:
`font-display`, `font-sans` (default), `font-mono`.

**Radius:** Medium softness — `rounded-lg` (12px) default, `rounded-xl` (16px)
for cards, `rounded-md` (10px) for inputs.

**Logo:** `public/lilly-logo.png` is the real Lilly mark, red on transparent.
On red and crimson surfaces, the `.logo-white` CSS class applies
`filter: brightness(0) invert(1)` to render it pure white.

**Brand note:** Official Lilly red is `#D52B1E`. The current palette uses
`#C41A1A` preserved from the prototype. Coordinate with brand before any
public-facing deployment — change is **one line** in `globals.css`:

```css
--lilly-red: 4 73% 47%;   /* HSL of #D52B1E */
```

---

## Sample test data

```
File: taltz_trust_segmentation 2.csv
Rows: 671
Columns (6): TRUST_ID, TRUST_NAME, PRIORITY, FORMULARY_POSITION, POSITION, INDICATION
All columns: categorical type
No datetime columns, no numeric columns, no audit columns
```

This file consistently produces a **red / Needs Improvement** overall verdict
due to missing temporal columns, no PK-like column, and no audit columns.
It's the canonical fixture for `tests/test_scorer.py`.

---

## Known issues & fixes carried over from the prototype

| Issue | Root cause | Fix applied |
|---|---|---|
| `Unterminated string in JSON at position N` | `max_tokens:1000` too low; raw CSV rows sent to LLM | Production design: profile only sent to LLM; advisor uses 256 tokens for recommendations, 128 for summary |
| Inconsistent scores on same file | LLM non-determinism | Production fix: deterministic Python scorer |
| Download `.md` blocked | Artifact sandbox blocks `Blob` URL navigation | Production: real download via `Blob` works outside the artifact sandbox |
| JSON parse failure on truncated response | Naive brace-counting | Advisor wraps every parse in try/except → fallback path |

---

## Known issues (current, not prototype-era)

| Issue | Detail | Status |
|---|---|---|
| Two coexisting metadata-scoring code paths | `_r_dictionary_present` (`core/dimensions.py`) and `_build_metadata_quality` (`core/scorer.py`, called from two places) both score metadata quality. Not yet reconciled into one path. | Open - flag to the user before extending either; don't assume which one is authoritative. Also called out in root `CLAUDE.md` section 7. |
| Migrated copy lags the source repo slightly | `backend/core/scorer.py` here is missing a `lens_scores` recompute block (~4 lines) present in `ibu-ai-ready-data`'s current `scorer.py`, in a rescore/blocker-override function. | Open - minor, but worth a targeted sync if that rescore path is touched. |
| BOTL register was CSV-file-dependent (fixed pre-migration) | `_load_register()` resolved a path outside the Docker build context, raising `FileNotFoundError` on every DB assessment. | Fixed - the 44-field register is now a Python constant in `core/botl_register.py`, no file I/O at import time. |
| OOM on multi-file CSV upload (fixed pre-migration) | All uploaded files held in memory simultaneously during parsing. | Fixed - raw bytes released immediately after each file is parsed. |
| Redshift profiling gaps (fixed pre-migration) | `TABLESAMPLE` failed on small tables; column/table discovery missed views. | Fixed - `pg_catalog`-based discovery, `LIMIT` fallback when `TABLESAMPLE` fails, row cap lowered to 15k. |

---

## What's been built

> Rewritten 2026-09-18 by direct file inventory of `apps/structured/`, cross-checked against the equivalent update just made in the `ibu-ai-ready-data` source repo. The previous "Phase 1 in progress" framing was stale and had already been carried through the migration unchanged - all four phases are functionally complete; see "still open" below for what remains.

**Frontend** (`frontend/src/`):
- 9 pages: `Home`, `Assess`, `AssessRunView`, `Dashboard`, `HelpCenter`, `History`, `Console`, `Support`, `Account` (was 4 pages at the last update)
- 10 shadcn/ui primitives: `badge`, `button`, `card`, `checkbox`, `flip-card`, `input`, `label`, `progress`, `tabs`, `textarea` (was 7)
- `HelpCenter.jsx`: 5-chapter reference with a colorized flow diagram
- `History.jsx`: real, API-backed via `api.getHistory()` / `clearHistory()` / `deleteRun()` - not a stub
- Markdown export panel exists (`api.js` + `Dashboard.jsx`) - this was listed as "still to do" previously; it's done
- `globals.css` / `tailwind.config.js` / surface-flip / typography / logo system unchanged from what's documented above in this file

**Backend** (`backend/`):
- Core scorer, parser, and 9 dimensions from the original Phase 2 scope, now with metadata-aware rules (see "known issues" above for the two coexisting metadata-scoring paths)
- **Archetypes** (`core/archetypes/*.yaml` + `core/archetype_loader.py`): 12 use-case profiles - `agent_rag`, `batch_scoring`, `conformed_reference`, `feature_store`, `mcp_read`, `mcp_write`, `nl_query`, `reporting_analytics`, `semantic_search`, `supervised_classification`, `supervised_regression`, `time_series_forecast`
- **Capabilities** (`core/capabilities.py`): BOTL register-driven capability scoring, register itself in `core/botl_register.py` (44 fields, embedded as a Python constant - see known issues)
- **Verdict engine** (`core/verdict.py`): tier determination, separate from the per-dimension scorer
- **LLM package** (`llm/`) grew from just `advisor.py` to: `advisor.py`, `annotator.py`, `evidence_narrator.py` + `prompts/evidence_narrator.py`, `purpose_narrator.py` + `prompts/purpose_summary.py`, `synthesizer.py`, `adjudicator.py` (stub, per this app's `CLAUDE.md` hybrid-route note), `guardrails.py`, `client.py`, `exceptions.py` - `advise()` remains the one public entry point
- **Attestations**: new table via Alembic migration `0004_add_attestations_table.py` + matching `.sql` snapshot, `db/history_store.py` extended
- Dimension redesigns carried over from source: Ops (watermark + partition rules), Temporal Integrity (5 rules rebuilt for ML readiness), Engineer Runbook (criticality bands, evidence-first tone)
- Redshift profiling hardened (see known issues table)

**Still open / not done:**
- Recharts radar chart on the dashboard - not present (`grep` for `recharts`/`RadarChart` in `frontend/src` returns nothing)
- Client-side CSV parsing (PapaParse) in `Assess.jsx` - not added; `papaparse` isn't in `package.json`. Parsing still happens server-side only.
- Playwright smoke tests - no `.spec.*` files or `playwright.config` found anywhere in `frontend/`
- The `handover-writer` skill mentioned in the previous version of this doc - never created; not found anywhere in this app or the source repo
- Reconcile the two metadata-scoring code paths (`_r_dictionary_present` vs `_build_metadata_quality`) into one
- The small `lens_scores` delta vs the source repo noted at the top of this file

---

## How to continue

If you're starting a new Claude thread, paste **these three files** at the top:

1. `CLAUDE.md` — runtime rules
2. `docs/spec.md` — architecture
3. `docs/context.md` — this file

Then say: "I am continuing work on the ARC Evaluator. Read these
three files fully before responding."

Update `docs/context.md` at the end of every phase. The pattern: keep the
"what's been built" and "still to do" sections accurate; everything else
should rarely change.
