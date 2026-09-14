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

| Phase | Component       | State |
|-------|-----------------|-------|
| 0     | Prototype artifact (single-file React) | Complete |
| 1     | Production frontend scaffold | In progress |
| 2     | Backend (FastAPI + scorer + parser) | Not started |
| 3     | LLM integration (`llm/advisor.py`) | Not started |
| 4     | Assessment history | Future scope |

---

## Design decisions (do not revisit without good reason)

| Decision | Rationale |
|---|---|
| Scoring is deterministic Python in production | LLM-based scoring in the prototype was inconsistent run-to-run on the same CSV. Determinism was the explicit fix. |
| LLM only writes recommendations and the summary | Single responsibility: scoring is Python, language is the LLM. |
| LLM integration isolated to `llm/advisor.py` | One integration point for the operator to swap providers. |
| Tier thresholds: ≥65 green, 40–64 yellow, <40 red | Baked into spec and CLAUDE.md. |
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

## What's been built

**Phase 1 (in progress):**
- `app/frontend/` scaffold migrated to Tailwind 3 + shadcn/ui
- `pages/` (4 page files), `components/ui/` (7 shadcn primitives), `lib/` (api, dimensions, utils) — three subfolders only
- `globals.css` holds all design tokens as HSL CSS variables (brand + tier palettes)
- `tailwind.config.js` exposes the variables as utility classes
- Real Lilly logo at `public/lilly-logo.png`, CSS-recolored white on red surfaces
- Centered layouts on every page via Tailwind `container` class
- Medium-soft edges throughout (12px default, 16px cards, 10px inputs)
- Fraunces (display) / Bricolage Grotesque (body) / JetBrains Mono via Google Fonts
- Layout surface flip via `red-mode` / `crimson-mode` classes — tokens remap, shadcn auto-themes
- Full route flow runs, mock dashboard renders, support form submits with graceful "backend not wired" state
- `api.js` single fetch client with `ApiError` class and AbortController support
- `vite.config.js` proxies `/api/v1/*` → `localhost:8000` and configures `@/` path alias

**Phase 1 (still to do):**
- Real CSV parsing in `Assess.jsx` step 1 (PapaParse, browser-side)
- Recharts radar chart on the dashboard
- Linear accordion category breakdown with check-by-check expand
- Markdown export panel
- Playwright smoke tests
- A `handover-writer` skill (created via skill-creator) for future handoffs

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
