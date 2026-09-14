// 14 capability definitions — single source of truth for the frontend.
// Backend produces CapabilityMeasurement objects; this file provides
// display metadata (labels, one-line definitions, family groupings).

export const CAPABILITIES = [
  { id: 'SEM', label: 'Field meaning & definitions', definition: 'Can a consumer interpret every field without asking a human?' },
  { id: 'JOIN', label: 'Join keys & conformance',    definition: 'Can this table be reliably linked to others via keys?' },
  { id: 'GOV', label: 'Permission & privacy clearance', definition: 'Is PII handled, consent documented, and usage approved?' },
  { id: 'AGG', label: 'Small-group disclosure safety', definition: 'Can counts and sums be trusted without exposing individuals?' },
  { id: 'ACC', label: 'Programmatic access',         definition: 'Can pipelines consume this reliably and incrementally?' },
  { id: 'FRS', label: 'Freshness & delivery',        definition: 'Is the data current enough for the intended use?' },
  { id: 'LBL', label: 'Label quality',               definition: 'Is a supervised target present and usable?' },
  { id: 'LKG', label: 'Leakage safety',              definition: 'Are there no post-event features contaminating the target?' },
  { id: 'SIG', label: 'Feature signal',              definition: 'Are features informative, diverse, and free of noise?' },
  { id: 'STA', label: 'Statistical validity',        definition: 'Are distributions well-behaved (no constants, balanced spread)?' },
  { id: 'TMP', label: 'Time semantics',              definition: 'Are time-based operations possible (ordering, granularity)?' },
  { id: 'VOL', label: 'Volume & coverage',           definition: 'Is there enough data for the intended use case?' },
  { id: 'LIN', label: 'Lineage & reproducibility',   definition: 'Is the data traceable to its source system?' },
  { id: 'TXT', label: 'Retrievable content',         definition: 'Are free-text fields suitable for retrieval use?' },
];

// Archetype families with archetypes — for the purpose picker grouping.
// Aligned to lens cards: DQ ← baseline, ML ← model_dev, AI ← agent_access.
export const ARCHETYPE_FAMILIES = [
  {
    id: 'baseline', label: 'Baseline / DQ',
    description: 'Classic data quality for human consumers and reference.',
    archetypes: [
      { id: '', label: 'Baseline data quality' },
      { id: 'reporting_analytics', label: 'Human reporting & analytics' },
      { id: 'conformed_reference', label: 'Conformed reference / master data' },
    ],
  },
  {
    id: 'agent_access', label: 'Agent Access / AI',
    description: 'LLM agents reading data via MCP, NL, or retrieval.',
    archetypes: [
      { id: 'mcp_read', label: 'MCP tool access (read)' },
      { id: 'mcp_write', label: 'MCP tool access (read + write)', disabled: true, disabledReason: 'Requires write-safety evidence' },
      { id: 'nl_query', label: 'Conversational analytics (text-to-SQL)' },
      { id: 'agent_rag', label: 'BI / dashboard agent' },
      { id: 'semantic_search', label: 'RAG / knowledge retrieval' },
      { id: 'time_series_forecast', label: 'Fine-tuning' },
    ],
  },
  {
    id: 'model_dev', label: 'Model Development / ML',
    description: 'Training, scoring, and feature pipelines.',
    archetypes: [
      { id: 'supervised_classification', label: 'Supervised training' },
      { id: 'supervised_regression', label: 'Forecasting / time series' },
      { id: 'feature_store', label: 'Feature store source' },
      { id: 'batch_scoring', label: 'Feature serving / online inference' },
    ],
  },
];

// Level labels for capability progress display.
export const LEVEL_LABELS = ['unknown', 'weak', 'partial', 'solid', 'verified'];

// Lookup helper
export const capabilityById = (id) => CAPABILITIES.find(c => c.id === id);
