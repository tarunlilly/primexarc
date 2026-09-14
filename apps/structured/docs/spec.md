# ARC Evaluator — Production Spec

> The architectural source of truth. `CLAUDE.md` holds the runtime rules and
> points here for depth. Update this file whenever the architecture changes;
> code and spec must not diverge.

---

## 1. Product

An internal Lilly web application that evaluates CSV datasets and database
schemas against a 9-dimension AI readiness framework. It produces:

- a **tier classification** (Needs Improvement / Adequate / AI Ready)
- a **deterministic per-dimension score** (0–100)
- a set of **LLM-generated recommendations** and a one-paragraph summary

The app **advises** — it never modifies user data.

**Audience.** Internal Lilly data product owners. Authenticated via Lilly SSO.
Deployed behind firewall.

**Phase order.** Frontend → Backend → LLM. Status tracked in
`docs/development.md`.

---

## 2. Repository Layout

```
app/
├── CLAUDE.md
├── spec.md
├── docs/
│   ├── development.md       # how to run, env vars, Docker
│   ├── testing.md           # pytest + Playwright strategies
│   └── context.md           # project history, decisions, known issues
│
├── backend/
│   ├── main.py              # FastAPI app, router mounts
│   ├── config.py            # pydantic-settings
│   ├── dependencies.py      # shared dependencies (auth, request scope)
│   ├── api/
│   │   ├── assess.py        # POST /assess/csv, POST /assess/db
│   │   ├── support.py       # POST /support/tickets
│   │   └── health.py        # GET /health, GET /me
│   ├── core/
│   │   ├── scorer.py        # ScoringEngine (deterministic, pure)
│   │   ├── dimensions.py    # The 9 dimensions and their rules
│   │   ├── parser.py        # CSVParser, DBIntrospector
│   │   └── models.py        # Pydantic v2 request/response models
│   ├── llm/
│   │   └── advisor.py       # LLMAdvisor — only file allowed to call an LLM
│   ├── requirements.txt
│   └── tests/
│       ├── test_scorer.py
│       ├── test_parser.py
│       └── test_api.py
│
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   ├── tailwind.config.js
│   ├── postcss.config.js
│   ├── jsconfig.json
│   ├── README.md
│   ├── public/
│   │   └── lilly-logo.png
│   └── src/
│       ├── main.jsx
│       ├── App.jsx
│       ├── Layout.jsx
│       ├── globals.css         # Tailwind layers + CSS variable tokens
│       ├── pages/
│       │   ├── Home.jsx
│       │   ├── Assess.jsx
│       │   ├── Dashboard.jsx
│       │   └── Support.jsx
│       ├── components/ui/      # shadcn primitives
│       │   ├── button.jsx
│       │   ├── card.jsx
│       │   ├── input.jsx
│       │   ├── label.jsx
│       │   ├── progress.jsx
│       │   ├── tabs.jsx
│       │   └── textarea.jsx
│       └── lib/
│           ├── api.js          # single fetch client
│           ├── dimensions.js   # 9-dim metadata, tier styles
│           └── utils.js        # cn() helper
│
├── .env.example
├── docker-compose.yml
├── Dockerfile.backend
└── Dockerfile.frontend
```

**Hard structural rules** (see `CLAUDE.md`): no files outside `app/`, one class
per file under `backend/core/`, frontend `src/` stays flat.

---

## 3. The 9 Scoring Dimensions

| ID       | Label                                  | Weight |
|----------|----------------------------------------|--------|
| schema   | Schema Design & Structure              | 10%    |
| quality  | Data Quality & Completeness            | 20%    |
| labels   | Labels, Targets & Ground Truth         | 15%    |
| temporal | Temporal Integrity                     | 15%    |
| features | Feature & Signal Readiness             | 10%    |
| stats    | Statistical Properties                 | 10%    |
| privacy  | Privacy, Compliance & Ethics           | 10%    |
| metadata | Metadata & Documentation               | 5%     |
| ops      | Operational & Pipeline Readiness       | 5%     |

**Score formula (Phase 3):** weighted average across dimensions that *apply*
to the table. Per-dimension score is `(pass×1 + warn×0.5 + fail×0) / counted_checks × 100`,
where `deferred` checks (hybrid rules awaiting human attestation) are
EXCLUDED from `counted_checks` — they live in `Report.deferred[]` instead.

**Metadata nuance:** the `Metadata & Documentation` dimension is not a flat
average of its two checks. Its core score comes from governance-weighted
metadata coverage plus reconciliation accuracy, and naming conventions add a
smaller 20% documentation adjustment so snake_case alone cannot produce a
healthy metadata score.

**Applicability + renormalization:** when a dimension's `applicability(profile)`
returns False (e.g. Labels when no target column exists), the dimension is
dropped from the weighted average. The remaining weights renormalize to 100%
implicitly via division by the active total — never by mutating
`Dimension.weight`.

**Blocker gating:** any `fail` on a `severity="blocker"` rule caps the table's
overall score at `BLOCKER_CAP=59` and appends the rule_id to
`TableAssessment.gated_by`. Schema-level `gated_by` is the union across
tables. The FE Dashboard renders a red banner above the score whenever
`gated_by` is non-empty.

**Tier thresholds (Phase 3):** `score ≥ 80` → green (AI Ready) ·
`60 ≤ score < 80` → yellow (Conditional) · `score < 60` → red
(Needs Improvement / Gated).

Rule implementations live in `backend/core/dimensions.py`. Each `Rule`
carries `severity` (`blocker | warning | info`), `executor`
(`profiler | metadata | hybrid | human`), and `hybrid_route`
(`human_attestation | adjudicator`). Hybrid rules emit
`status="deferred"` so the engine routes the candidate to the attestation
queue instead of failing the dimension. v1 always routes hybrid candidates
to humans; v2 will flip `settings.hybrid_route` to `"adjudicator"` once
`llm/adjudicator.py` lands.

---

## 4. Backend

### 4.1 FastAPI routes (`/api/v1` prefix)

| Method | Path                  | Body                  | Returns                  | Notes |
|--------|-----------------------|-----------------------|--------------------------|-------|
| GET    | `/health`             | —                     | `{status: "ok"}`         | Liveness probe |
| GET    | `/me`                 | —                     | `{user, email, roles[]}` | SSO; backend phase |
| POST   | `/assess/csv`         | `CSVAssessRequest`    | `AssessmentResult`       | Stateless |
| POST   | `/assess/db`          | `DBAssessRequest`     | `AssessmentResult`       | Stateless |
| POST   | `/support/tickets`    | `TicketRequest`       | `TicketReceipt`          | Forwards to ServiceNow / email |

**Error shape:** `{ "detail": "human-readable", "code": "SNAKE_CASE_CODE" }`.

**HTTP codes:** 400 bad input · 422 Pydantic validation · 500 unexpected
server error · 503 LLM or DB unreachable.

### 4.2 Pydantic models (`core/models.py`)

```python
class ColumnProfile(BaseModel):
    name: str
    dtype: Literal["int","float","string","bool","datetime","object"]
    null_pct: float = Field(ge=0, le=100)
    unique_count: int = Field(ge=0)
    samples: list[str] = Field(max_length=5)  # truncated to 40 chars each

class CSVAssessRequest(BaseModel):
    filename: str
    row_count: int = Field(ge=1, le=500)
    columns: list[ColumnProfile] = Field(min_length=1)

class DBAssessRequest(BaseModel):
    engine: Literal["postgres","mssql","oracle","mysql"]
    host: str
    port: int = Field(ge=1, le=65535)
    database: str
    schema: str = "public"
    username: str
    password: SecretStr   # masked in logs

class RuleCheck(BaseModel):
    rule_id: str
    status: Literal["pass","warn","fail","deferred"]  # Phase 3: deferred routes to attestation
    reason: str
    severity: Literal["blocker","warning","info"] = "warning"
    executor: Literal["profiler","metadata","hybrid","human"] = "profiler"
    route: Literal["human_attestation","adjudicator"] | None = None

class DimensionResult(BaseModel):
    id: str
    label: str
    weight: int
    score: int = Field(ge=0, le=100)
    tier: Literal["green","yellow","red"]
    checks: list[RuleCheck]

class AssessmentResult(BaseModel):
    overall_score: int = Field(ge=0, le=100)
    tier: Literal["green","yellow","red"]
    dimensions: list[DimensionResult]
    summary: str
    recommendations: list[str]
```

### 4.3 `ScoringEngine` (`core/scorer.py`)

**Rules:** no LLM calls, no I/O, pure function. Same input → same output. See
`CLAUDE.md` for the absolute constraints.

Signature:
```python
class ScoringEngine:
    def score(self, req: CSVAssessRequest) -> AssessmentResult: ...
    def _score_dimension(self, dim: Dimension, profile: Profile) -> DimensionResult: ...
```

### 4.4 `CSVParser` / `DBIntrospector` (`core/parser.py`)

Raw CSV rows never leave the parser. The parser caps at 500 rows and emits
`list[ColumnProfile]`. Sample values are `str(s)[:40]`.

`DBIntrospector` uses SQLAlchemy 2.0 reflection — table metadata only, no
data extraction beyond column-level statistics.

### 4.5 `LLMAdvisor` (`llm/advisor.py`)

The **only** file that may call an external LLM. See `CLAUDE.md` for the
hard rules: provider read from config, mandatory fallback path, 256 tokens
for recommendations / 128 for summary, no raw CSV ever sent.

```python
class LLMAdvisor:
    def recommend(self, dim: DimensionResult) -> list[str]: ...
    def summarise(self, result: AssessmentResult) -> str: ...
    def _fallback_recommendations(self, dim: DimensionResult) -> list[str]: ...
```

---

## 5. Frontend

### 5.1 File plan

`src/` has three intentional subfolders: `pages/`, `components/ui/`, `lib/`.
See `frontend/README.md` for the quickstart.

| Path | Role |
|------|------|
| `src/main.jsx`              | Entry · BrowserRouter |
| `src/App.jsx`               | Routes |
| `src/Layout.jsx`            | Header + footer + surface flip (red / crimson / white) via mode classes |
| `src/globals.css`           | Tailwind layers + CSS variable design tokens |
| `src/pages/Home.jsx`        | Landing (hero, 9-dim grid, how-it-works) |
| `src/pages/Assess.jsx`      | Wizard (Onboarding → Input → Loading → renders Dashboard) |
| `src/pages/Dashboard.jsx`   | Tier verdict + breakdown + export |
| `src/pages/Support.jsx`     | Ticket form + contact card |
| `src/components/ui/*.jsx`   | shadcn primitives — Button, Card, Input, Label, Progress, Tabs, Textarea |
| `src/lib/api.js`            | Single fetch client → `/api/v1` |
| `src/lib/dimensions.js`     | 9-dim display metadata + tier style lookup |
| `src/lib/utils.js`          | `cn()` — clsx + tailwind-merge |
| `public/lilly-logo.png`     | Brand mark; CSS-recolored to white on red surfaces |

### 5.2 Design system

- **Typography:** Fraunces (display serif), Bricolage Grotesque (body sans),
  JetBrains Mono (mono). Loaded via Google Fonts in `index.html`.
- **Palette:** brand red `#C41A1A` / dark red `#7F1111` / crimson `#8B0000`.
  All colors as HSL CSS variables in `globals.css`. Tier colours used **only**
  on Dashboard.
- **Surface flip:** the `<Layout variant>` prop applies `.red-mode` /
  `.crimson-mode` / no class. CSS variables remap, shadcn primitives auto-theme.
- **Radius:** 12px default (`rounded-lg`), 16px cards (`rounded-xl`), 10px
  inputs (`rounded-md`).
- **Motion:** `animate-card-rise` (600ms cubic-bezier) on every route/step
  reveal. Subtle hover lifts on primary actions.
- **All hex via CSS variables in `globals.css`** — never hardcoded in components.

### 5.3 Routing

| Path        | Variant per step                          |
|-------------|--------------------------------------------|
| `/`         | red                                        |
| `/assess`   | red (steps 0–1) → crimson (2) → white (3)  |
| `/support`  | white                                      |
| `*`         | white (404)                                |

`Assess.jsx` owns its own `<Layout>` because the variant flips internally.
Fixed-variant pages are wrapped by `App.jsx`.

### 5.4 SSO

The frontend is auth-blind until backend phase wires it. When SSO lands:
`Layout.jsx` calls `api.me()` on mount, displays the user's name in the
header. The IdP performs redirects; no React-side login screens.

---

## 6. Phase Plan & Deferred Work

### Phase 1 (current) — Frontend scaffold
- ✅ Tailwind + shadcn/ui scaffold with `pages/`, `components/ui/`, `lib/` structure
- ✅ Fraunces / Bricolage Grotesque / JetBrains Mono via Google Fonts
- ✅ CSS variable design tokens (brand + tier palettes) in `globals.css`
- ✅ Lilly logo with surface-aware white CSS recolor
- ✅ Routes wired (Home / Assess / Support / 404)
- ✅ Wizard step machine with mock dashboard fallback
- ✅ Support ticket form with graceful stub message when backend is absent

### Phase 2 — Backend
- `core/scorer.py`, `core/dimensions.py`, `core/parser.py`, `core/models.py`
- `api/assess.py`, `api/support.py`, `api/health.py`
- SSO middleware → `GET /me`
- Wire `api.assessCsv()` in `Assess.jsx` → replaces "Skip to Mock Dashboard"
- Wire `Support.jsx` ticket submission

### Phase 3 — LLM Integration
- `llm/advisor.py` provider switch (anthropic / openai / cortex / bedrock)
- Fallback path verified with empty `LLM_API_KEY`
- Recommendation streaming optional

### Phase 4 (future) — History
- `GET /assessments` + `GET /assessments/{id}`
- `History.jsx` page added to nav
- Saved-result route `/assess/:id`
- Requires authenticated user from SSO

---

## 7. Test Strategy

See `docs/testing.md` for full detail. Summary:

- **Backend:** pytest. `core/` covered by unit tests; `api/` by FastAPI
  TestClient. No real DB / no real LLM in tests — all external calls mocked.
  Deterministic scorer property tested by running the same request 20× and
  asserting identical output.
- **Frontend:** Playwright smoke run against `npm run dev` — home loads,
  wizard advances through 4 steps, mock dashboard renders, support form
  submits.

---

## 8. Open Questions

These are tracked here so they don't get lost between phases:

- **Ticket backend:** ServiceNow integration or plain SMTP relay? Decision
  needed before Phase 2 wires `POST /support/tickets`.
- **LLM provider:** Anthropic via Bedrock seems likely for Lilly-internal;
  confirm before Phase 3.
- **Brand red:** preserved palette uses `#C41A1A`. Official Lilly red is
  `#D52B1E`. Coordinate with brand team before deployment.
- **History storage:** Postgres alongside the FastAPI app, or push to an
  existing internal analytics store? Defer until Phase 4 scoping.
