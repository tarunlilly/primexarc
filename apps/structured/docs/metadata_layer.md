# EXECUTION_PLAN — Phase 2: Metadata (Ingest · Reconcile · Evaluate · Classify)

> Canonical Phase 2 spec for Claude Code context. Base text tightened from the working draft;
> two refinements folded in — (a) **governance-weighted** metadata-quality scoring instead of a
> flat category average, and (b) an explicit **Phase 5 dependency** for the PII-contradiction check.
>
> Scope: revise the **existing** metadata path. Do not rebuild it. Metadata is optional,
> manual-upload only, and never authoritative for score gating unless confirmed by observation or
> human attestation. A run must complete with or without metadata.

## Phase outcomes
1. Uploaded metadata is parsed into the existing metadata model, aligned to the finalized Standard.
2. Declared metadata is reconciled against observed profile facts and internal metadata consistency rules.
3. Metadata quality is scored as its own dimension using explicit category coverage plus reconciliation accuracy.
4. Reference/static tables can be excluded from scoring using deterministic classification plus engineer override.
5. Metadata semantics are carried forward for later LLM synthesis, but **no LLM dependency** is introduced in this phase.
6. No-metadata runs remain fully supported and deterministic.

---

## 2.0 Parser Alignment
Modify the existing parser and model; do not replace them.

**Build**
1. Map incoming columns to canonical Standard field names, including at minimum: `Definition`,
   `Data Type`, `Nullable`, `Valid Values/Range`, `Primary/Foreign Key`, `Entity Classification`,
   `Field Role`, `PII Flag`, `PII Category`, `Security Classification`, `Consent Basis / Permitted
   Use`, `AI/ML Usage Approval`, `Target/Label Indicator`, `Unit of Measure`, `Cardinality`,
   `Protected Attribute`, `Timezone/Temporal Semantics`, `lastSyncedAt`, `Grain`, `Data Owner`,
   `Data Steward`, `Lineage`, and `Usage Context`.
2. Attach a `source` attribute to every parsed value: `Authored`, `Measured`, `Derived`, or `System`.
3. If the file does not provide a source column, default each value source to `Authored` and emit a
   parser assumption note.
4. Accept both: standard-format metadata files, and generic dictionary CSVs that can be mapped into
   the canonical field set.
5. Preserve unknown columns as extension fields rather than dropping them.
6. Fail loudly on malformed files with field-level error messages.

**Acceptance**
1. A standard-format file parses successfully.
2. A generic dictionary CSV parses successfully.
3. Every parsed metadata value carries a `source`.
4. Unknown columns are preserved and surfaced in parser output.
5. Malformed input fails with clear, specific errors.

---

## 2.1 Reconciler
Add a deterministic reconciliation stage that compares declared metadata to observed profile facts
and checks metadata for internal contradictions.

**Build**
1. Compare declared `Data Type` to observed type.
2. Compare declared `Nullable` to observed null presence and null rate.
3. Compare declared `Valid Values/Range` to observed domain, with config-backed tolerance where needed.
4. Compare declared `Primary/Foreign Key` expectations to observed uniqueness and key-like behavior.
5. Compare declared `Cardinality` to observed distinct-count behavior using a config-backed relative
   drift tolerance.
6. Emit internal metadata consistency findings without requiring live data, including: invalid ranges
   such as min > max; incompatible `Data Type` and `Field Role`; stale `lastSyncedAt` beyond
   configured threshold; documented-as-usable fields observed 100% null.
7. Support governance contradiction findings as separate facts from the underlying
   data-quality/governance finding. Example: declared `PII Flag = N`, observed governance signal
   indicates likely PII → emit `metadata contradicts observed governance`.
8. If an observed signal required for a contradiction is unavailable in the current phase, mark the
   contradiction check `could not verify` rather than silently skipping it.

**Dependency (explicit).** The governance/PII contradiction in clause 7 consumes the PII +
protected-attribute detection signal produced in **Phase 5**. In the pipeline the reconciler runs
*before* the Phase 5 detector, so at Phase 2 time this signal is typically absent. Wire clause 7 to
the Phase 5 detector output and evaluate it when that signal exists (run the contradiction pass after
Phase 5, or re-evaluate it once detection is available), defaulting to `could not verify` until then.
**Do not** wire it to an always-null source and let it silently pass as "no contradiction" — that
would permanently hide real contradictions even after Phase 5 ships.

**Rules**
1. Reconciler outputs facts only.
2. Reconciler findings do not directly gate the score.
3. All reconciler outputs must be deterministic and reproducible.

**Acceptance**
1. A type mismatch produces a finding.
2. A `PII Flag = N` plus an observed likely-PII signal produces a separate contradiction finding;
   absent that signal, the check reports `could not verify` (never a silent pass).
3. Stale metadata produces a finding.
4. Invalid ranges like min > max produce a finding.
5. Re-running the same inputs yields identical reconciliation findings.

---

## 2.2 Metadata Quality Scoring
Replace the current metadata stub with a real **Metadata & Docs** dimension.

**Build**
1. Score metadata across four categories: Business, Technical, Operational, Governance.
2. Each category reports: status (`present` / `partial` / `absent`), percentage coverage, and missing
   required fields.
3. Minimum expected checks:
   - Business: `Definition`, `Usage Context`, `Grain`
   - Technical: `Data Type`, `Nullable`, `Valid Values/Range`, key semantics, `Cardinality`,
     units/timezone where applicable
   - Operational: `Data Owner` or `Data Steward`, `lastSyncedAt`, `Lineage`, refresh/SLA fields if
     present in the standard
   - Governance: `PII Flag`, `PII Category`, `Security Classification`, `Consent Basis / Permitted
     Use`, `AI/ML Usage Approval`, `Protected Attribute`
4. Treat governance values with `source = Derived` as `confirm required`, not satisfied.
5. Route confirm-required governance items into deferred/attestation output rather than pass.
6. Compute the Metadata & Docs dimension from both category coverage and reconciliation accuracy.
7. Treat naming conventions as a smaller documentation-quality signal, not as half the dimension by themselves.
8. Keep the formula explicit and bounded so missing metadata lowers only this dimension unless a
   separate observed rule fires elsewhere.

**Scoring contract (recommended; weights in config)**
1. Category coverage score: percent of required fields present and usable.
2. Category status: `present` if coverage ≥ 0.8; `partial` if 0.3 ≤ coverage < 0.8; `absent` if
   coverage < 0.3.
3. **Weighted category rollup (not a flat average).** Governance is weighted heaviest because this is
   a compliance-driven product — a product rich in business docs but missing PII / consent / AI-usage
   governance metadata must not score deceptively well. Recommended weights:
   ```
   weighted_coverage = 0.40 * Governance
                     + 0.25 * Technical
                     + 0.20 * Operational
                     + 0.15 * Business
   ```
4. Metadata core score: `0.7 * weighted_coverage + 0.3 * reconciliation_accuracy`.
5. Final Metadata & Docs dimension score: `0.8 * metadata_core_score + 0.2 * documentation_convention_score`,
   where `documentation_convention_score` comes from the naming-convention rule (`pass=100`, `warn=50`, `fail=0`).
6. If no metadata file exists: category coverage is zero; the metadata core score is `0`; the
   dimension remains `undocumented` and low, with only the smaller naming-convention contribution.

**Acceptance**
1. Metadata & Docs is computed rather than stubbed.
2. All four categories emit status plus percentage.
3. The rollup is governance-weighted, not a flat average (verify: a doc-rich, governance-poor product
   scores lower than a flat average would give it).
4. Derived governance values route to confirmation, not satisfaction.
5. Missing `Definition`, `Grain`, `Data Owner`/`Steward`, and `Lineage` surface as findings.
6. A no-metadata run lowers only Metadata & Docs and does not flip unrelated dimensions.

---

## 2.3 Classification
Add deterministic table classification for exclusion from scoring/action lists.

**Build**
1. Use `Entity Classification` as the primary signal.
2. Support classes at minimum: `fact`, `dimension`, `reference`, `staging`.
3. Add a config-backed row-threshold heuristic for likely static/reference tables, but treat it as a
   weak signal only.
4. Add engineer override as the final authority.
5. Produce a stated exclusion reason when a table is excluded.
6. Excluded tables do not affect overall score or recommendation prioritization, but still appear in
   the report as excluded entities.

**Decision order**
1. Engineer override
2. Valid explicit metadata classification
3. Weak heuristic from row-threshold and other static/reference signals
4. Default to **included**

**Guardrail**
1. Row threshold alone must not auto-exclude a table if stronger signals disagree.

**Acceptance**
1. `Entity Classification = reference` excludes the table with a stated reason.
2. A large table mislabeled `reference` can be overridden by an engineer.
3. Excluded tables do not affect score.
4. Excluded tables still appear in the report with reason.

**Recommended default**
1. Reference-row heuristic threshold: `1000` rows.
2. Treat this as advisory, not sufficient by itself.

---

## 2.4 Engine and LLM Seam Wiring
Integrate metadata findings and semantics without introducing LLM dependence here.

**Build**
1. Feed reconciler findings into the rules engine as deterministic facts.
2. Feed metadata quality findings into the rules engine as deterministic facts.
3. Expose metadata semantics for future synthesis payloads, at minimum: `Definition`, `Data Owner`,
   `Usage Context`, `Grain`, `Lineage`.
4. Carry governance fields forward with verification state attached.
5. Any governance field with `source = Derived` must remain non-authoritative until human-confirmed.
6. Gates that depend on metadata governance values must read: observed facts if available; otherwise
   human-confirmed metadata; never raw derived metadata alone.

**Acceptance**
1. Reconciler findings appear in the report.
2. Metadata quality findings appear in the report.
3. Metadata context is present in the future synthesis payload shape when metadata exists.
4. A derived `AI/ML Usage Approval` value does not gate until confirmed.

---

## 2.5 No-Metadata Path
Make missing metadata a first-class supported case.

**Build**
1. If no file is uploaded, the run still completes normally.
2. Reconciliation checks become `could not verify — no metadata`, not fail.
3. Metadata & Docs is scored as `undocumented`, low but not `N/A`.
4. Classification falls back to heuristic plus engineer override.
5. Future synthesis context falls back to generic table/profile-only context.
6. No other dimension changes solely because metadata is absent, **except** where a separate
   deterministic rule explicitly depends on confirmed governance input (e.g. the AI-usage gate simply
   does not engage when there is no confirmed value — this is a gate not firing, not a dimension drop).

**Acceptance**
1. A no-metadata run produces a full score.
2. Reconciliation outputs `could not verify`.
3. Metadata & Docs is `undocumented`.
4. Removing metadata from an otherwise identical run lowers only Metadata & Docs and converts
   reconciliation findings from concrete to unverified.

---

## Guardrails
1. Metadata is evaluated, not blindly trusted.
2. Declared and derived metadata are claims, not ground truth.
3. Metadata alone cannot create a blocker gate unless confirmed by observed evidence or human attestation.
4. Manual upload only. No API ingester in this phase.
5. Runs must be deterministic and reproducible with or without metadata.

## Config Defaults (reasonable starting values; tune in config)
1. Reference row-threshold heuristic: `1000`
2. Metadata staleness threshold: `90 days`
3. Declared-vs-observed null-rate tolerance: `0.02`
4. Declared-vs-observed cardinality relative drift tolerance: `0.10`
5. Metadata-quality category weights: Governance `0.40`, Technical `0.25`, Operational `0.20`, Business `0.15`

## Done When
1. Parser accepts both standard and generic metadata inputs and annotates every value with source.
2. Reconciler outputs deterministic contradiction and drift findings; the PII-contradiction check is
   wired to the Phase 5 detector (or deferred to `could not verify`), never silently passing.
3. Metadata & Docs is computed from governance-weighted category coverage plus reconciliation accuracy, with naming conventions contributing only a 20% adjustment.
4. Classification can exclude reference/static tables with explicit reasons.
5. Metadata findings flow into report-generation inputs.
6. No-metadata runs are fully supported and only reduce Metadata & Docs.
7. Tests pass and progress tracking is updated.
