// Display metadata for the 9 AI readiness dimensions.
// Source of truth for scoring: backend/core/dimensions.py.

export const DIMENSIONS = [
  { id: 'schema',   label: 'Schema Design & Structure',        weight: 10, summary: 'Primary keys, types, joinability.' },
  { id: 'quality',  label: 'Data Quality & Completeness',      weight: 20, summary: 'Nulls, duplicates, validity.' },
  { id: 'labels',   label: 'Labels, Targets & Ground Truth',   weight: 15, summary: 'Outcome columns, class balance.' },
  { id: 'temporal', label: 'Temporal Integrity',               weight: 15, summary: 'Timestamps, ordering, leakage.' },
  { id: 'features', label: 'Feature & Signal Readiness',        weight: 10, summary: 'Signal quality, constants, infinites, type alignment.' },
  { id: 'stats',    label: 'Statistical Properties',           weight: 10, summary: 'Distributions, outliers, skew.' },
  { id: 'privacy',  label: 'Privacy, Compliance & Ethics',     weight: 10, summary: 'PII, consent, regulatory fit.' },
  { id: 'metadata', label: 'Metadata & Documentation',         weight: 5,  summary: 'Column descriptions, lineage.' },
  { id: 'ops',      label: 'Operational & Pipeline Readiness', weight: 5,  summary: 'Refresh cadence, incremental load, schema stability.' },
];

// Lens metadata — three readiness perspectives computed by the backend.
export const LENSES = [
  { id: 'DQ', label: 'Data Quality',   color: 'text-blue-700',  bgColor: 'bg-blue-50' },
  { id: 'ML', label: 'ML Readiness',   color: 'text-purple-700', bgColor: 'bg-purple-50' },
  { id: 'AI', label: 'AI Readiness',   color: 'text-rose-700',  bgColor: 'bg-rose-50' },
];

// Tier → Tailwind utility lookup. No hex values escape this file.
// All class strings are static literals - required for Tailwind JIT to
// detect and generate them.

// Data/ML/AI tag metadata per dimension — matches the order shown in HelpCenter.
export const DIMENSION_TAGS = {
  schema:   { tags: ['Data', 'AI'],       primaryTag: 'Data' },
  quality:  { tags: ['Data', 'ML'],       primaryTag: 'Data' },
  labels:   { tags: ['ML', 'AI'],         primaryTag: 'ML' },
  temporal: { tags: ['Data', 'ML', 'AI'], primaryTag: 'ML' },
  features: { tags: ['ML', 'AI'],         primaryTag: 'ML' },
  stats:    { tags: ['Data', 'ML'],       primaryTag: 'ML' },
  privacy:  { tags: ['AI', 'Data'],       primaryTag: 'AI' },
  metadata: { tags: ['AI', 'Data'],       primaryTag: 'AI' },
  ops:      { tags: ['AI', 'Data', 'ML'], primaryTag: 'AI' },
};

// Tag pill styling — static class strings for Tailwind JIT detection.
export const TAG_STYLES = {
  Data: 'bg-tag-data-bg text-tag-data-text',
  ML:   'bg-tag-ml-bg text-tag-ml-text',
  AI:   'bg-tag-ai-bg text-tag-ai-text',
};

export const TIER_STYLES = {
  green: {
    badge:   'bg-tier-green-light text-tier-green-base border-tier-green-base/25',
    bar:     'bg-tier-green-base',
    text:    'text-tier-green-base',
    ring:    'ring-tier-green-base/30',
    border:  'border-tier-green-base/30',
    surface: 'bg-tier-green-light/40',
    heroBg:  'bg-tier-green-light',
  },
  yellow: {
    badge:   'bg-tier-amber-light text-tier-amber-base border-tier-amber-base/25',
    bar:     'bg-tier-amber-base',
    text:    'text-tier-amber-base',
    ring:    'ring-tier-amber-base/30',
    border:  'border-tier-amber-base/30',
    surface: 'bg-tier-amber-light/40',
    heroBg:  'bg-tier-amber-light',
  },
  red: {
    badge:   'bg-tier-red-light text-tier-red-base border-tier-red-base/25',
    bar:     'bg-tier-red-base',
    text:    'text-tier-red-base',
    ring:    'ring-tier-red-base/30',
    border:  'border-tier-red-base/30',
    surface: 'bg-tier-red-light/40',
    heroBg:  'bg-tier-red-light',
  },
};

export const TIER_LABELS = {
  green: 'AI Ready',
  yellow: 'Conditional',
  red: 'Needs Improvement',
};

// Single source of truth for tier classification (bands: 80/60).
// Import this everywhere - do not hardcode tier logic in components.
export const tierFor = (score) => (score >= 80 ? 'green' : score >= 60 ? 'yellow' : 'red');

// Severity styling for top-priority cards.
export const SEVERITY_STYLES = {
  high:   { bar: 'bg-tier-red-base',   pill: 'bg-tier-red-light text-tier-red-base' },
  medium: { bar: 'bg-tier-amber-base', pill: 'bg-tier-amber-light text-tier-amber-base' },
  low:    { bar: 'bg-tier-green-base', pill: 'bg-tier-green-light text-tier-green-base' },
};

// Status → color + label for individual rule checks.
// `box` is a Tailwind class for a small colored square indicator
// (no emoji - see CLAUDE.md frontend design rules).
export const CHECK_STATUS = {
  pass: { box: 'bg-tier-green-base', label: 'Pass',    text: 'text-tier-green-base' },
  warn: { box: 'bg-tier-amber-base', label: 'Warning', text: 'text-tier-amber-base' },
  fail: { box: 'bg-tier-red-base',   label: 'Fail',    text: 'text-tier-red-base' },
};

// ─── Mock assessment result ────────────────────────────────────────────────
// Matches the backend's AssessmentResult shape (see spec.md § 4.2). Will be
// replaced once api.assessCsv() is wired in Assess → LoadingScreen.
//
// `top_priorities` is derived server-side from each dimension's failing /
// warning checks ranked by weight × severity. Backend can compute this so
// the frontend can render it without business logic.

export const MOCK_RESULT = {
  overall_score: 58,
  tier: 'yellow',
  table_count: 1,
  summary:
    'Strong schema and privacy posture. Temporal coverage and outcome labelling need work before this dataset is model-ready.',
  top_priorities: [
    {
      severity: 'high',
      title: 'Define and document a target column with timestamps',
      dimension_id: 'labels',
      table_name: 'sample.csv',
    },
    {
      severity: 'high',
      title: 'Build data dictionary and register dataset owner and SLA',
      dimension_id: 'metadata',
      table_name: 'sample.csv',
    },
    {
      severity: 'medium',
      title: 'Generate distribution baselines and classify null mechanism',
      dimension_id: 'stats',
      table_name: 'sample.csv',
    },
  ],
  dimensions: _mockDimensions(),
  tables: [
    {
      table_name: 'sample.csv',
      row_count: 60,
      column_count: 6,
      overall_score: 58,
      tier: 'yellow',
      dimensions: _mockDimensions(),
      summary: 'sample.csv: Adequate (58/100). Focus area: Temporal Integrity.',
      recommendations: [],
    },
  ],
};

// Inline factory keeps the dimensions array out of the literal above.
function _mockDimensions() {
  return [
    { id: 'schema',   label: 'Schema Design & Structure',        weight: 10, score: 75, tier: 'green',  checks: [] },
    { id: 'quality',  label: 'Data Quality & Completeness',      weight: 20, score: 52, tier: 'yellow', checks: [] },
    { id: 'labels',   label: 'Labels, Targets & Ground Truth',   weight: 15, score: 22, tier: 'red',    checks: [] },
    { id: 'temporal', label: 'Temporal Integrity',               weight: 15, score: 18, tier: 'red',    checks: [] },
    { id: 'features', label: 'Feature & Signal Readiness',        weight: 10, score: 55, tier: 'yellow', checks: [] },
    { id: 'stats',    label: 'Statistical Properties',           weight: 10, score: 48, tier: 'yellow', checks: [] },
    { id: 'privacy',  label: 'Privacy, Compliance & Ethics',     weight: 10, score: 78, tier: 'green',  checks: [] },
    { id: 'metadata', label: 'Metadata & Documentation',         weight: 5,  score: 28, tier: 'red',    checks: [] },
    { id: 'ops',      label: 'Operational & Pipeline Readiness', weight: 5,  score: 42, tier: 'yellow', checks: [] },
  ];
}