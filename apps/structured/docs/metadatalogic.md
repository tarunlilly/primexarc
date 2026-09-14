# UMS v2.0 (BOTL) — Scoring & Assessment Logic Specification

Companion to `ums_v2_field_register.csv` (44 fields). This spec is deterministic:
two implementations given the same input MUST produce identical output.
Standard version: `2.0`. Point scale: HIGH=3, MEDIUM=2, LOW=1.

---

## 1. Inputs

### 1.1 Field register (CSV)
Columns: `id, field, category, grain, severity, points, conditional_escalation, population_mode, why_this_severity`

- `category` ∈ {business, operational, technical, lineage}
- `grain` ∈ {table, column, table+column}
- `severity` ∈ {HIGH, MEDIUM, LOW}; `points` ∈ {3, 2, 1}
- `conditional_escalation` ∈ {"", trigger:ESC-n, target:ESC-n, applicability:ESC-n}
- `population_mode` ∈ {declared, harvested, hybrid, config_harvested, system_generated}
- `why_this_severity` is documentation only — never used by the engine.

### 1.2 Asset metadata payload (what gets scored)
One JSON document per asset:

```json
{
  "asset_id": "platform.db.schema.table",
  "standard_version": "2.0",
  "columns": ["col_a", "col_b", "..."],
  "fields": {
    "<field_id>": {
      "status": "present | absent | na",
      "value": "<any>            // omitted when absent",
      "na_reason": "<string>     // REQUIRED when status = na",
      "column_coverage": {        // ONLY for grain = column fields
        "covered": 37, "total": 40
      }
    }
  }
}
```

Rules:
- A field_id missing from `fields` entirely ⇒ treat as `status: absent`. Absence is never N/A.
- `status: na` is valid ONLY for fields whose applicability rule (Section 3) permits it,
  and MUST carry `na_reason`. An unpermitted `na` ⇒ treat as `absent` and add a warning.
- Unknown field_ids in the payload ⇒ ignore, add a warning (forward compatibility).

---

## 2. Pipeline (strict order)

```
1. APPLICABILITY  → per field: applicable | not_applicable
2. VALIDITY       → per applicable field: valid | invalid   (present but invalid = failed)
3. ESCALATION     → compute effective_severity / effective_points per field
4. SCORING        → earned vs possible points, per category and overall
5. GATES/VERDICT  → RED / YELLOW / GREEN (gates override scores)
6. OUTPUT         → result JSON + ranked remediation list
```

Never reorder: escalation must run AFTER validity (triggers use validated values) and
BEFORE scoring and gates (both use effective severity).

---

## 3. Applicability

Default: every field is applicable to every asset. Exceptions (exhaustive list):

| Rule | Field | Not applicable when |
|---|---|---|
| APP-1 | O3 watermark sub-check | `O3.value.load_pattern == "full_refresh"` (ESC-3 inverse). O3 itself (load pattern) is ALWAYS applicable. |
| APP-2 | B19 | Never N/A — "no constraints" must be recorded as `value: "none"`, which counts as present. |
| APP-3 | B21 | Never N/A — "unrestricted purpose" recorded as `value: "unrestricted"`, counts as present. |

`not_applicable` fields are excluded from BOTH numerator and denominator, and from gates.
N/A must always be a recorded value with a reason — silence is absence.

---

## 4. Validity checks

`present` alone never earns points; the field must also be `valid`.
Minimum checks (extend, never weaken):

| Field(s) | Validity requirement |
|---|---|
| B1 | non-empty, != physical name (case-insensitive) |
| B2 | ≥ 120 chars, not a copy of B1 |
| B3, T2 | column-grain coverage (Section 4.1) |
| B4 | value ∈ enterprise domain taxonomy (closed list) |
| B5, B6 | resolves to an active identity/role in the directory |
| B7 | value ∈ {Critical, Important, Standard} |
| B12 | value ∈ classification taxonomy (closed list) |
| B13 | every column has an explicit flag (sensitive types list or "none") — coverage rule applies |
| B14 | list of regulation codes from controlled vocabulary, or "none" |
| B16 | contains retention duration AND disposal method |
| B18 | attestation timestamp within 12 months AND attester resolves to active identity |
| O1 | parseable cadence (cron/ISO-8601 duration/enum{streaming,static}) |
| O2 | timestamp; stale check: age ≤ 2 × O1 cadence ⇒ valid; else invalid (freshness breach) |
| O3 | load_pattern ∈ {full_refresh, incremental_append, merge_upsert, cdc}; if not full_refresh: watermark column(s) must exist in `columns` |
| O4 | ≥ 1 declared check with a result timestamp ≤ 7 days old; uniqueness check on T3 key REQUIRED |
| T1 | matches `platform.db.schema.table` pattern and equals `asset_id` |
| T3 | key column(s) exist in `columns` |
| L1, L2 | non-empty; L2 edges reference resolvable asset_ids |
| all others | non-empty / non-placeholder (reject: "TBD", "N/A", "todo", "-", whitespace) |

### 4.1 Column-grain fractional credit
For `grain = column` fields (B3, B13, B17, T2, T7, T9, L4):

```
coverage_fraction = covered / total          // from column_coverage
earned_points     = effective_points × coverage_fraction
```

- Gate participation (Section 6): a column-grain HIGH field passes its gate only if
  `coverage_fraction ≥ 0.95` for B3/T2 and `= 1.0` for B13 (sensitivity flags are all-or-nothing:
  one unflagged PII column is an exposure).
- `table+column` fields (B9, O4): score the table-level part as boolean; if column detail is
  provided, no bonus — table-level presence+validity earns full points.

---

## 5. Conditional escalations

Evaluate all four rules; multiple may fire on one asset. Escalated fields:
`effective_severity = HIGH`, `effective_points = 3`, and they join the RED gate.

| Rule | Trigger condition (on validated values) | Target(s) |
|---|---|---|
| ESC-1 | any column in B13 flagged with a sensitive type (≠ "none") | B17, B21 → HIGH |
| ESC-2 | B7.value == "Critical" | O5 → HIGH |
| ESC-3 | O3.value.load_pattern != "full_refresh" | O3 watermark sub-check becomes REQUIRED (part of O3 validity, not a separate field) |
| ESC-4 | B14.value != "none" (≥ 1 regulation applies) | B20 → HIGH |

Trigger-missing rule: if a TRIGGER field is absent/invalid, its escalation CANNOT be evaluated
⇒ apply the escalation anyway (fail-closed). Example: B13 absent ⇒ treat B17/B21 as HIGH.
Rationale: unknown sensitivity must be handled as sensitive. Record `"escalation_basis": "fail_closed"`.

---

## 6. Scoring

Let A = applicable fields, for each field f: `pts(f) = effective_points(f)`,
`earn(f) = pts(f) × credit(f)` where credit = 1.0 if present+valid (fractional for column grain,
0.0 if absent or invalid).

```
category_score(c) = Σ earn(f) / Σ pts(f)      over f ∈ A, category(f) = c     // ∈ [0,1]
overall_score     = mean(category_score(business, operational, technical, lineage))
enrichment_score  = Σ earn(f) / Σ pts(f)      over f ∈ A, base severity = LOW
```

Base maxima (all applicable, no escalations): business 50, operational 19, technical 19,
lineage 13 — total 101. Never hard-code these; always compute from the register
(escalations and N/A change the denominators).

Overall is the mean of category scores (not points-weighted across categories) so that a large
category (business, 21 fields) cannot mask a hollow one (lineage, 5 fields).

## 7. Gates and verdict (gates override scores — always)

```
RED    if ∃ f ∈ A with effective_severity = HIGH and credit(f) < gate_threshold(f)
YELLOW else if ∃ f ∈ A with effective_severity = MEDIUM and credit(f) < 1.0
GREEN  otherwise
```

gate_threshold: 1.0 for table-grain; 0.95 for B3/T2; 1.0 for B13 (Section 4.1).
A 0.97 overall_score with one failed HIGH field is still RED.
LOW fields never affect the verdict — they only feed enrichment_score.
YELLOW carries `remediation_deadline = assessment_date + 60 days`.

## 8. Output schema

```json
{
  "asset_id": "...",
  "standard_version": "2.0",
  "assessed_at": "ISO-8601",
  "verdict": "RED | YELLOW | GREEN",
  "scores": {
    "business": 0.0, "operational": 0.0, "technical": 0.0, "lineage": 0.0,
    "overall": 0.0, "enrichment": 0.0
  },
  "escalations_applied": [
    {"rule": "ESC-1", "targets": ["B17", "B21"], "basis": "triggered | fail_closed"}
  ],
  "fields": [
    {"id": "B2", "applicable": true, "status": "present", "valid": false,
     "reason": "below minimum length (120)", "effective_severity": "HIGH",
     "points_possible": 3, "points_earned": 0.0}
  ],
  "remediation": [
    {"id": "B2", "priority": 1, "points_recoverable": 3.0, "owner_route": "business"}
  ],
  "warnings": ["unknown field X ignored"]
}
```

Remediation ordering: (1) fields blocking the verdict (failed effective-HIGH first, then MEDIUM),
(2) within a tier, by points_recoverable desc, (3) tie-break by register order.
`owner_route`: business → business owner (B5); operational/technical/lineage → platform team.

## 9. Determinism & engineering constraints

1. Pure function: (register CSV, asset payload) → result JSON. No network, no clock except
   `assessed_at` and freshness checks, which take `now` as an injected parameter (testability).
2. Load the register at startup; validate it (44 rows, enum values, points match severity).
   Refuse to run on a malformed register.
3. Float handling: round scores to 4 dp only at serialization; compare gates on raw values.
4. All validity failures must produce a machine-readable `reason` string — the reason IS the
   remediation instruction.
5. Version pinning: result records `standard_version` from the register; never mix registers.

## 10. Acceptance test vectors

TV-1 Empty payload (all 44 absent) ⇒ RED; all category scores 0.0; ESC-1 applied fail_closed
     (B17, B21 effective HIGH); remediation lists all fields, HIGH first.
TV-2 All fields present+valid, B7="Standard", B13 all "none", B14="none",
     O3 load_pattern="full_refresh" ⇒ GREEN; no escalations; all scores 1.0;
     O3 watermark sub-check not applicable.
TV-3 As TV-2 but B13 flags one column "PII" and B17 absent ⇒ RED
     (ESC-1 fires, B17 effective HIGH and missing); business_score < 1.0.
TV-4 As TV-2 but B9 absent (MEDIUM, 2 pts) ⇒ YELLOW; business_score = 48/50 = 0.96;
     remediation_deadline set.
TV-5 As TV-2 but B3 coverage 0.90 ⇒ RED (below 0.95 gate threshold) even though
     business_score ≈ 0.994.
TV-6 As TV-2 but load_pattern="cdc" with no watermark column ⇒ RED (O3 invalid via ESC-3).