import { useEffect, useRef, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import { DIMENSIONS, TAG_STYLES } from '@/lib/dimensions.js';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

const CHAPTERS = [
  { id: 'dimensions', label: '9 Dimensions' },
  { id: 'scoring',    label: 'Scoring Math' },
  { id: 'flow',       label: 'How ARC Works' },
  { id: 'ai-layer',   label: 'AI Layer' },
  { id: 'glossary',   label: 'Glossary' },
];

// Static content keyed by dimension id
const DIMENSION_DETAIL = {
  schema: {
    why: 'Is the table structured in a stable, usable way? Strong schema design is the foundation for joinable, traceable datasets.',
    tags: ['Data', 'AI'],
    primaryTag: 'Data',
    checks: [
      { title: 'Every row should have a unique identifier. Example: patient_id is unique for every record and never blank.', severity: 'warning' },
      { title: 'The table should show when records were created or updated. Example: created_at and updated_at are present and populated.', severity: 'info' },
      { title: 'The table should not be unrealistically narrow or overly wide. Example: a 28-column claims table is reasonable; a 220-column table may need to be split.', severity: 'info' },
      { title: 'Column names should follow a clear naming standard. Example: use claim_date and member_id instead of "Claim Date" or "MemberID".', severity: 'info' },
    ],
  },
  quality: {
    why: 'Is the data sufficiently complete, large enough, and clean enough? Data quality issues propagate silently into models and distort predictions.',
    tags: ['Data', 'ML'],
    primaryTag: 'Data',
    checks: [
      { title: 'There should be enough rows to support modeling. Example: 24,500 rows is a much stronger modeling base than 120 rows.', severity: 'warning' },
      { title: 'The dataset should not have too many missing cells overall. Example: only 2% of all cells are blank across the table.', severity: 'warning' },
      { title: 'The dataset should not contain many exact duplicate rows. Example: no duplicate encounter records are found in the sample.', severity: 'warning' },
      { title: 'Individual columns should not be mostly empty. Example: secondary_phone is 82% null, so it may not be useful.', severity: 'warning' },
      { title: 'Missing data should be stored as real nulls, not placeholders. Example: replace -1, 999, or "N/A" with nulls.', severity: 'info' },
    ],
  },
  labels: {
    why: 'If this is for supervised ML, is there a usable target and is it trustworthy? Label leakage makes models appear accurate in testing but fail completely in production.',
    tags: ['ML', 'AI'],
    primaryTag: 'ML',
    checks: [
      { title: 'The dataset should clearly show what the model is trying to predict. Example: a column named readmission_target contains yes/no.', severity: 'warning' },
      { title: 'The target classes should not be too imbalanced. Example: 12% positive and 88% negative is workable; 1% positive is much harder.', severity: 'warning' },
      { title: 'Outcomes should be tied to a date or time. Example: outcome_recorded_at shows when the event actually happened.', severity: 'warning' },
      { title: 'Features should not accidentally contain the answer after the fact. Example: using final_claim_status to predict claim approval would leak the outcome.', severity: 'blocker' },
    ],
  },
  temporal: {
    why: 'Does the data include enough time information for trend-based or real-world modeling? Without proper timestamps, future information leaks into the training set.',
    tags: ['Data', 'ML', 'AI'],
    primaryTag: 'ML',
    checks: [
      { title: 'The table should include date or timestamp fields. Example: event_date and record_created_at are available.', severity: 'warning' },
      { title: 'The data should cover a meaningful span of time. Example: 18 months of history is stronger than 2 weeks.', severity: 'warning' },
      { title: 'The newest data should still be reasonably current. Example: the latest transaction is only 3 days old, not 14 months old.', severity: 'info' },
      { title: 'Time fields should make logical sense. Example: updated_at should never be earlier than created_at.', severity: 'info' },
      { title: 'Time fields should be aligned at compatible levels. Example: a per-second event timestamp should be deliberately aligned with a monthly reporting field.', severity: 'info' },
    ],
  },
  features: {
    why: 'Does the dataset contain usable predictive features? Feature-ready data reduces engineering time before training.',
    tags: ['ML', 'AI'],
    primaryTag: 'ML',
    checks: [
      { title: 'Category fields should not explode into too many distinct values. Example: product_serial_number has 80,000 unique values and needs special handling.', severity: 'warning' },
      { title: 'The dataset should include at least a few numeric features. Example: age, prior_visits_30d, and avg_claim_amount are usable numeric inputs.', severity: 'info' },
      { title: 'Columns should not be almost the same value everywhere. Example: country = US in 99.4% of rows adds almost no signal.', severity: 'warning' },
      { title: 'Numeric fields should not contain inf or -inf. Example: a ratio field becomes infinity because of division by zero upstream.', severity: 'warning' },
      { title: 'Storage types should match the real meaning of the data. Example: order_date is stored as text instead of a datetime.', severity: 'info' },
      { title: 'Groups of missing fields should not indicate a broken join or process. Example: city_code, postal_zone, and region_name are always null together.', severity: 'info' },
      { title: 'Categorical fields should not be redundant copies of each other. Example: department_name and department_code always move together 1:1.', severity: 'info' },
    ],
  },
  stats: {
    why: 'Are the numeric relationships stable and reasonable? Unknown distributions and missing drift baselines mean silent degradation discovered only after production failures.',
    tags: ['Data', 'ML'],
    primaryTag: 'ML',
    checks: [
      { title: 'Columns should not be constant across all rows. Example: source_system is "SAP" in every row and adds no value.', severity: 'info' },
      { title: 'Extreme values should be identified and understood. Example: one transaction is $10M while almost all others are under $500.', severity: 'info' },
      { title: 'There should be a baseline to compare future data against. Example: save today\'s averages and category frequencies so drift can be spotted later.', severity: 'info' },
      { title: 'Numeric fields should not be near-duplicates of each other. Example: weight_kg and weight_lb carry the same information.', severity: 'info' },
    ],
  },
  privacy: {
    why: 'Can the data be used safely and appropriately for AI? Datasets with unmasked PII cannot safely enter model training or be shared with downstream teams.',
    tags: ['AI', 'Data'],
    primaryTag: 'AI',
    checks: [
      { title: 'The schema should not directly expose obvious personal identifiers. Example: columns like email, ssn, or patient_name are high risk.', severity: 'blocker' },
      { title: 'Sample values should not contain personal information. Example: a notes field includes john.doe@company.com.', severity: 'warning' },
      { title: 'The dataset should show what it is allowed to be used for. Example: data_use_scope = approved_for_training is documented.', severity: 'warning' },
    ],
  },
  metadata: {
    why: 'Is the dataset documented well enough for governance and reuse? Without governance metadata, compliance teams cannot sign off regardless of technical quality.',
    tags: ['AI', 'Data'],
    primaryTag: 'AI',
    checks: [
      { title: 'The dataset should have a usable data dictionary, especially for governance. Example: a dictionary entry includes business definition, type, owner, PII flag, consent basis, and AI/ML approval.', severity: 'info' },
    ],
  },
  ops: {
    why: 'Is the data pipeline stable enough to support production AI? Unstable schemas, undocumented refresh schedules, and lack of incremental-load capability are the most common causes of model silent degradation after deployment.',
    tags: ['AI', 'Data', 'ML'],
    primaryTag: 'AI',
    checks: [
      { title: 'Column names should look final, not temporary. Example: revenue_tmp, status_v2, and old_score suggest the schema is still unstable.', severity: 'info' },
      { title: 'The refresh schedule should be documented. Example: "This table refreshes daily at 02:00 UTC; SLA by 04:00 UTC."', severity: 'info' },
      { title: 'A watermark column should exist for incremental loading. Example: created_at or an auto-increment id allows pipelines to load only new rows.', severity: 'info' },
      { title: 'Large tables (≥1M rows) should have a partition strategy. Example: partitioned by month so pipelines read only the relevant time window.', severity: 'info' },
    ],
  },
};

function severityBox(severity) {
  if (severity === 'blocker') return 'bg-tier-red-base';
  if (severity === 'warning') return 'bg-tier-amber-base';
  return 'bg-muted-foreground';
}

// Tag styling imported from @/lib/dimensions (single source of truth)

function TagPill({ label, isPrimary }) {
  return (
    <span
      className={cn(
        'font-nav text-[10px] font-medium px-1.5 py-0.5 rounded-sm',
        TAG_STYLES[label],
        isPrimary && 'ring-1 ring-current/20',
      )}
    >
      {label}
    </span>
  );
}

function ChapterHeading({ children }) {
  return (
    <div>
      <div className="w-8 h-px bg-accent mb-4" />
      <h2 className="font-display text-3xl font-light text-primary mb-8">{children}</h2>
    </div>
  );
}

function DimensionsChapter() {
  const [openId, setOpenId] = useState(null);

  return (
    <section id="dimensions">
      <ChapterHeading>9 Dimensions</ChapterHeading>
      <p className="text-muted-foreground mb-8 max-w-2xl">
        Each dataset is evaluated across nine readiness dimensions. Expand any dimension to see
        the plain-language checks ARC applies and what they look for in your data.
        Dimensions with an inapplicability predicate (like Labels) are excluded from scoring
        when they do not apply, and their weight is redistributed across the remaining active dimensions.
      </p>
      <div className="space-y-3">
        {DIMENSIONS.map((d) => {
          const detail = DIMENSION_DETAIL[d.id];
          const isOpen = openId === d.id;
          return (
            <div key={d.id} className="border rounded-xl overflow-hidden">
              <button
                className="w-full flex items-center justify-between px-5 py-4 text-left hover:bg-muted/30 transition-colors"
                onClick={() => setOpenId(isOpen ? null : d.id)}
                aria-expanded={isOpen}
              >
                <div className="flex items-center gap-2.5">
                  <span className="font-sans font-semibold text-[15px]">{d.label}</span>
                  {detail && detail.tags && (
                    <div className="flex items-center gap-1">
                      {detail.tags.map((tag) => (
                        <TagPill key={tag} label={tag} isPrimary={tag === detail.primaryTag} />
                      ))}
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-3 shrink-0">
                  <span className="font-mono text-[11px] bg-muted px-2 py-0.5 rounded-sm">
                    {d.weight}%
                  </span>
                  <ChevronDown
                    className={cn(
                      'w-4 h-4 text-muted-foreground transition-transform duration-200',
                      isOpen && 'rotate-180',
                    )}
                  />
                </div>
              </button>
              {isOpen && detail && (
                <div className="px-5 pb-5 space-y-4 animate-fade-in border-t pt-4">
                  <p className="text-sm text-muted-foreground">{detail.why}</p>
                  <div>
                    <p className="font-nav text-[11px] font-medium text-muted-foreground uppercase tracking-wide mb-2">
                      Checks
                    </p>
                    <ul className="space-y-2">
                      {detail.checks.map((chk, i) => (
                        <li key={i} className="flex items-start gap-2.5 text-sm">
                          <span
                            className={cn(
                              'w-2 h-2 rounded-sm shrink-0 mt-1',
                              severityBox(chk.severity),
                            )}
                          />
                          {chk.title}
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div className="flex items-center gap-4 pt-1">
                    <div className="flex items-center gap-1.5 text-[12px] text-muted-foreground">
                      <span className="w-2 h-2 rounded-sm bg-tier-red-base" />
                      Blocker
                    </div>
                    <div className="flex items-center gap-1.5 text-[12px] text-muted-foreground">
                      <span className="w-2 h-2 rounded-sm bg-tier-amber-base" />
                      Warning
                    </div>
                    <div className="flex items-center gap-1.5 text-[12px] text-muted-foreground">
                      <span className="w-2 h-2 rounded-sm bg-muted-foreground" />
                      Info
                    </div>
                    <span className="text-border mx-1">|</span>
                    <div className="flex items-center gap-1.5 text-[12px] text-muted-foreground">
                      <span className="px-1 py-px rounded-sm text-[9px] font-medium bg-tag-data-bg text-tag-data-text">Data</span>
                      Engineering
                    </div>
                    <div className="flex items-center gap-1.5 text-[12px] text-muted-foreground">
                      <span className="px-1 py-px rounded-sm text-[9px] font-medium bg-tag-ml-bg text-tag-ml-text">ML</span>
                      Modeling
                    </div>
                    <div className="flex items-center gap-1.5 text-[12px] text-muted-foreground">
                      <span className="px-1 py-px rounded-sm text-[9px] font-medium bg-tag-ai-bg text-tag-ai-text">AI</span>
                      Governance
                    </div>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}

function ScoringChapter() {
  return (
    <section id="scoring">
      <ChapterHeading>Scoring Math</ChapterHeading>
      <div className="space-y-6">
        {/* Per-dimension formula */}
        <Card>
          <CardHeader>
            <CardTitle className="font-sans text-base font-semibold">Per-Dimension Score</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="font-mono text-[13px] bg-muted rounded-md px-3 py-3 leading-relaxed">
              score = (pass×1 + warn×0.5 + fail×0) / counted_checks × 100
            </div>
            <p className="text-sm text-muted-foreground">
              <span className="font-semibold text-foreground">Deferred checks</span> are excluded from{' '}
              <span className="font-mono text-[12px]">counted_checks</span> entirely and surface in the
              attestation queue for human review.
            </p>
          </CardContent>
        </Card>

        {/* Overall score */}
        <Card>
          <CardHeader>
            <CardTitle className="font-sans text-base font-semibold">Overall Score</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Weighted average across <span className="font-semibold text-foreground">active dimensions only</span>.
              Dimensions that do not apply to a dataset are dropped, and the remaining weights renormalize to 100%.
            </p>
            <div className="space-y-2">
              {DIMENSIONS.map((d) => (
                <div key={d.id} className="flex items-center gap-3">
                  <div className="w-36 shrink-0 text-[12px] text-muted-foreground truncate">{d.label}</div>
                  <div className="flex-1 bg-muted rounded-full h-2">
                    <div
                      className="bg-accent/40 h-2 rounded-full"
                      style={{ width: `${d.weight}%` }}
                    />
                  </div>
                  <span className="font-mono text-[11px] text-muted-foreground w-8 text-right">{d.weight}%</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* Tier thresholds + blocker gating */}
        <Card>
          <CardHeader>
            <CardTitle className="font-sans text-base font-semibold">Tier Thresholds &amp; Blocker Gating</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <p className="font-nav text-[11px] font-medium text-muted-foreground uppercase tracking-wide mb-3">
                  Tiers
                </p>
                <div className="space-y-2.5">
                  <div className="flex items-center gap-2.5 text-sm">
                    <span className="w-2.5 h-2.5 rounded-sm bg-tier-green-base shrink-0" />
                    <span className="font-semibold">AI Ready</span>
                    <span className="text-muted-foreground ml-auto font-mono text-[12px]">≥ 80</span>
                  </div>
                  <div className="flex items-center gap-2.5 text-sm">
                    <span className="w-2.5 h-2.5 rounded-sm bg-tier-amber-base shrink-0" />
                    <span className="font-semibold">Conditional</span>
                    <span className="text-muted-foreground ml-auto font-mono text-[12px]">60 – 79</span>
                  </div>
                  <div className="flex items-center gap-2.5 text-sm">
                    <span className="w-2.5 h-2.5 rounded-sm bg-tier-red-base shrink-0" />
                    <span className="font-semibold">Needs Improvement</span>
                    <span className="text-muted-foreground ml-auto font-mono text-[12px]">&lt; 60</span>
                  </div>
                </div>
              </div>
              <div>
                <p className="font-nav text-[11px] font-medium text-muted-foreground uppercase tracking-wide mb-3">
                  Blocker Cap
                </p>
                <p className="text-sm text-muted-foreground leading-relaxed">
                  Any <span className="font-semibold text-foreground">fail</span> on a rule with{' '}
                  <span className="font-mono text-[12px]">severity="blocker"</span> caps the overall
                  table score at <span className="font-semibold text-foreground">59</span>, placing it
                  in Needs Improvement regardless of other dimension scores. The gating rule IDs are
                  reported in the assessment result.
                </p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </section>
  );
}

// group: 'raw' | 'profile' | 'ai'
const FLOW_STEPS = [
  { n: 1, label: 'Data Source',  desc: 'CSV upload or database connection',             group: 'raw' },
  { n: 2, label: 'Profile',      desc: 'Sample rows, extract column statistics',        group: 'profile' },
  { n: 3, label: 'Rules Engine', desc: 'Apply 9 dimensions of deterministic checks',   group: 'profile' },
  { n: 4, label: 'Score & Tier', desc: 'Weighted score, blocker gating, tier classification', group: 'profile' },
  { n: 5, label: 'Attestation',  desc: 'Human review of deferred and blocker decisions', group: 'ai' },
  { n: 6, label: 'LLM Layer',    desc: 'Narrative summary + Runbook remediation guide', group: 'ai' },
];

const FLOW_GROUP_STYLES = {
  raw:     { box: 'bg-flow-raw-bg border-flow-raw-border',         num: 'text-flow-raw-text',     label: 'text-flow-raw-text' },
  profile: { box: 'bg-flow-profile-bg border-flow-profile-border', num: 'text-flow-profile-text', label: 'text-flow-profile-text' },
  ai:      { box: 'bg-flow-ai-bg border-flow-ai-border',           num: 'text-flow-ai-text',      label: 'text-flow-ai-text' },
};

function FlowStep({ step }) {
  const s = FLOW_GROUP_STYLES[step.group];
  return (
    <div className={cn('rounded-xl border px-5 py-3.5 text-center w-full', s.box)}>
      <p className={cn('font-nav text-[11px] font-medium', s.num)}>0{step.n}</p>
      <p className={cn('font-sans font-semibold text-[14px] mt-0.5', s.label)}>{step.label}</p>
      <p className="text-[12px] text-muted-foreground mt-1 leading-snug">{step.desc}</p>
    </div>
  );
}

function Arrow({ vertical = false }) {
  return (
    <span className={cn('text-muted-foreground font-mono self-center', vertical ? 'my-1' : 'mx-1')}>
      {vertical ? '↓' : '→'}
    </span>
  );
}

function FlowChapter() {
  return (
    <section id="flow">
      <ChapterHeading>How ARC Works</ChapterHeading>

      {/* Vertical diagram - centered */}
      <div className="flex flex-col items-center w-full max-w-xs mx-auto">
        {FLOW_STEPS.map((s, i) => (
          <div key={s.n} className="flex flex-col items-center w-full">
            <FlowStep step={s} />
            {i < FLOW_STEPS.length - 1 && <Arrow vertical />}
          </div>
        ))}
      </div>

      <p className="text-sm text-muted-foreground mt-8 max-w-2xl">
        Each step is deterministic except the LLM layer, which is additive - it annotates results but
        never changes scores or tiers.
      </p>
    </section>
  );
}

const AI_CARDS = [
  {
    key: 'synthesizer',
    title: 'Synthesizer',
    label: 'Narrative writer',
    borderClass: 'border-l-accent/40',
    desc: 'Takes deterministic findings and writes the assessment summary and ranked recommendations. Never invents metrics or recomputes scores.',
  },
  {
    key: 'runbook',
    title: 'Runbook',
    label: 'Remediation guide',
    borderClass: 'border-l-[hsl(var(--tier-amber-base)/0.5)]',
    desc: 'Step-by-step instructions for data engineers: what to fix, where, and how to verify it is done. Prose actions only - no generated code.',
  },
  {
    key: 'adjudicator',
    title: 'Adjudicator',
    label: 'Human review (v1)',
    borderClass: 'border-l-muted-foreground/30',
    desc: 'Hybrid rules (PII detection, target leakage) route to the attestation queue for human confirmation before resolving. v2 will route these to an LLM adjudicator.',
  },
];

function AiLayerChapter() {
  return (
    <section id="ai-layer">
      <ChapterHeading>AI Layer</ChapterHeading>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        {AI_CARDS.map((c) => (
          <div
            key={c.key}
            className={cn(
              'rounded-xl border bg-card px-5 py-4 border-l-[3px]',
              c.borderClass,
            )}
          >
            <p className="font-sans font-semibold text-[15px]">{c.title}</p>
            <p className="font-nav text-[11px] text-muted-foreground mt-0.5 mb-3">{c.label}</p>
            <p className="text-sm text-muted-foreground leading-relaxed">{c.desc}</p>
          </div>
        ))}
      </div>
      <p className="text-sm text-muted-foreground max-w-2xl">
        The AI layer is additive - it never modifies scores, tiers, or gating. All numbers come from
        the deterministic rules engine.
      </p>
    </section>
  );
}

const GLOSSARY_TERMS = [
  {
    term: 'Tier',
    def: 'AI Ready (≥80), Conditional (60–79), or Needs Improvement (<60). Determined by the overall weighted score after blocker gating.',
  },
  {
    term: 'Blocker',
    def: 'A rule whose failure caps the overall score at 59 regardless of other scores. Designed for critical data issues that make a dataset unsafe for AI use.',
  },
  {
    term: 'Gated',
    def: 'A table whose score is capped because one or more blocker rules failed. The gating rule IDs are listed in the assessment result.',
  },
  {
    term: 'Deferred',
    def: 'A check that requires human decision before it can be scored. Excluded from scoring until the attestation decision is recorded.',
  },
  {
    term: 'Attestation',
    def: 'The process of reviewing deferred checks and blocker decisions. Applying an attestation decision rescores the affected dimension.',
  },
  {
    term: 'High Cardinality',
    def: 'A categorical column with more than 50 distinct values. High-cardinality columns require special encoding strategies (target encoding, embeddings) and can make ML engineering unpredictable.',
  },
  {
    term: 'Pseudonymization',
    def: 'Replacing direct identifiers (names, emails, SSNs) with indirect ones (hashes, tokens). ARC flags columns whose names suggest unmasked PII as blockers.',
  },
  {
    term: 'Surrogate Null',
    def: 'A sentinel value used in place of a true null (for example: −1, 999, "N/A", "unknown"). Surrogate nulls hide true missingness from imputation logic and distort column statistics.',
  },
  {
    term: 'Applicability',
    def: 'Some dimensions only apply to certain datasets. For example, Labels only applies if a target column is detected. Inapplicable dimensions are excluded from scoring and their weight is redistributed.',
  },
  {
    term: 'Weighted Average',
    def: 'The overall score is a weighted average across active dimensions. Weights total 100% after inactive (inapplicable) dimensions are dropped.',
  },
  {
    term: 'Cadence Detection',
    def: 'ARC checks whether the dataset has a documented refresh schedule (hourly, daily, weekly, batch, streaming) in the data dictionary. Without a known cadence, pipelines cannot determine when data is stale or alert on missed loads.',
  },
  {
    term: 'Watermark Column',
    def: 'A monotonically increasing column (such as created_at, load_date, or an auto-increment id) that enables incremental pipeline loads. Instead of reloading the entire table, pipelines query "WHERE watermark > last_loaded" to fetch only new rows.',
  },
  {
    term: 'Highly Correlated Pair',
    def: 'Two numeric columns whose Pearson correlation |r| ≥ 0.95. Example: systolic_bp and diastolic_bp. Redundant features inflate model complexity without adding independent signal - one should be dropped or the pair documented.',
  },
  {
    term: 'Drift',
    def: 'A statistically significant shift in a column\'s distribution between a reference snapshot and the current data. Drift causes model predictions to degrade silently over time because the data the model was trained on no longer represents what it is scoring.',
  },
  {
    term: 'data_use_scope',
    def: 'A metadata field (or column) that records what a dataset is permitted to be used for - for example "analytics only", "approved for model training", or "reporting - no ML use without re-consent". ARC flags datasets that lack this field as missing consent metadata.',
  },
  {
    term: 'snake_case',
    def: 'A naming convention where words are lowercase and separated by underscores: patient_id, created_at, blood_pressure_mmhg. ARC enforces snake_case for column names because spaces and mixed casing cause silent pipeline breakage when columns are referenced by exact name.',
  },
];

function GlossaryChapter() {
  return (
    <section id="glossary">
      <ChapterHeading>Glossary</ChapterHeading>
      <dl className="grid grid-cols-1 md:grid-cols-2 gap-x-12 gap-y-6">
        {GLOSSARY_TERMS.map(({ term, def }) => (
          <div key={term}>
            <dt className="font-semibold text-foreground">{term}</dt>
            <dd className="text-sm text-muted-foreground mt-0.5 leading-relaxed">{def}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

export default function HelpCenter() {
  const [activeId, setActiveId] = useState('dimensions');
  const sectionRefs = useRef({});

  useEffect(() => {
    const observers = [];
    CHAPTERS.forEach(({ id }) => {
      const el = document.getElementById(id);
      if (!el) return;
      sectionRefs.current[id] = el;
      const obs = new IntersectionObserver(
        ([entry]) => {
          if (entry.isIntersecting) setActiveId(id);
        },
        { rootMargin: '-20% 0px -60% 0px', threshold: 0 },
      );
      obs.observe(el);
      observers.push(obs);
    });
    return () => observers.forEach((o) => o.disconnect());
  }, []);

  return (
    <section className="container py-16 animate-card-rise">
      {/* Page header */}
      <p className="font-nav text-[14px] font-medium text-primary">Help Center</p>
      <h1 className="font-display text-5xl font-light text-primary mt-2">
        ARC Evaluator: Reference
      </h1>
      <p className="text-lg text-muted-foreground max-w-2xl mt-3">
        Five chapters covering dimensions, scoring, workflow, the AI layer, and a full glossary of terms
        used throughout the assessment report.
      </p>

      {/* Mobile chapter strip */}
      <div className="lg:hidden flex gap-2 flex-wrap mt-8 mb-0">
        {CHAPTERS.map((ch) => (
          <a
            key={ch.id}
            href={`#${ch.id}`}
            className={cn(
              'font-nav text-[12px] px-3 py-1.5 rounded-md border transition-colors',
              activeId === ch.id
                ? 'bg-primary text-primary-foreground border-primary'
                : 'text-muted-foreground border-border hover:text-primary hover:border-primary/40',
            )}
          >
            {ch.label}
          </a>
        ))}
      </div>

      <div className="mt-12 flex gap-10 items-start">
        {/* Sticky sidebar - lg+ only */}
        <nav className="hidden lg:block w-52 shrink-0 sticky top-24 self-start space-y-1">
          <p className="font-nav text-[11px] font-medium text-muted-foreground uppercase tracking-wide mb-3">
            Chapters
          </p>
          {CHAPTERS.map((ch) => (
            <a
              key={ch.id}
              href={`#${ch.id}`}
              className={cn(
                'block font-nav text-[13px] py-1.5 px-2 rounded-md transition-colors',
                activeId === ch.id
                  ? 'text-primary font-semibold bg-primary/5'
                  : 'text-muted-foreground hover:text-primary',
              )}
            >
              {ch.label}
            </a>
          ))}
        </nav>

        {/* Scrollable content */}
        <div className="flex-1 min-w-0 space-y-20">
          <DimensionsChapter />
          <ScoringChapter />
          <FlowChapter />
          <AiLayerChapter />
          <GlossaryChapter />
        </div>
      </div>
    </section>
  );
}
