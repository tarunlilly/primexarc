"""All Pydantic v2 models used across the API surface and core engine.

Naming convention:
- `*Request` — inputs to the API layer
- `*Response` / `*Result` — outputs of the API layer
- `Column/Table/SchemaProfile` — raw extracted from CSV/DB before scoring
- `RuleCheck / DimensionResult / TableAssessment / SchemaAssessment` — scoring outputs
- `Job` — async work tracking
- `DBCredentials` — connection details (never persisted)
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, SecretStr, ConfigDict


# ───────────────────────────────────────────────────────────────────────────
# Profile shapes — what comes OUT of the parser/introspector and INTO scorer
# ───────────────────────────────────────────────────────────────────────────

DType = Literal["int", "float", "string", "bool", "datetime", "object"]
TableKlass = Literal["reference", "ready", "conditional", "gated"]
SchemaVerdict = Literal["AI Ready", "Conditional", "At Risk"]


class ColumnProfile(BaseModel):
    """Profile for a single column.

    Sample values are truncated to 40 chars. Numeric stats are populated only
    for numeric columns. Datetime stats only for datetime columns.
    """
    name: str
    dtype: DType
    null_count: int = Field(ge=0)
    null_pct: float = Field(ge=0, le=100)
    unique_count: int = Field(ge=0)
    sample_values: list[str] = Field(default_factory=list, max_length=5)
    value_pattern_counts: dict[str, int] = Field(default_factory=dict)

    # Numeric stats
    mean: Optional[float] = None
    std: Optional[float] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    quartiles: Optional[list[float]] = None  # [q25, q50, q75]
    skew: Optional[float] = None
    kurtosis: Optional[float] = None

    # Datetime stats (ISO strings to keep wire-format simple)
    earliest: Optional[str] = None
    latest: Optional[str] = None
    # Freshness (computed at profiling time to preserve scorer determinism)
    days_since_latest: Optional[int] = None

    # Surrogate null detection
    surrogate_null_count: int = 0


class TableProfile(BaseModel):
    """Profile for a single table or CSV file."""
    name: str
    row_count: int = Field(ge=0)
    profiled_row_count: int = Field(default=0, ge=0)
    column_count: int = Field(ge=0)
    duplicate_row_count: int = Field(default=0, ge=0)
    missing_cells_pct: float = Field(default=0.0, ge=0, le=100)
    columns: list[ColumnProfile]
    multicollinearity_flags: list[dict] = Field(default_factory=list)
    error: str | None = None

    # ydata enrichment (populated by ydata_enricher, consumed by dimension rules)
    infinite_columns: list[str] = Field(default_factory=list)
    near_constant_columns: list[str] = Field(default_factory=list)
    type_mismatches: list[dict] = Field(default_factory=list)
    correlated_pairs_mixed: list[dict] = Field(default_factory=list)
    missingness_groups: list[list[str]] = Field(default_factory=list)

    # Attached by the assess flow before scoring when metadata is available.
    # Rules access metadata via this field — keeps evaluate(profile) signature.
    metadata_entries: list["MetadataEntry"] = Field(default_factory=list)


# ───────────────────────────────────────────────────────────────────────────
# Scoring outputs
# ───────────────────────────────────────────────────────────────────────────

# Phase 3: "deferred" is added for hybrid rules that require human attestation
# (or, in v2, the LLM adjudicator). Deferred checks do NOT contribute to
# pass/warn/fail scoring — they live in `Report.deferred[]` instead.
RuleStatus = Literal["pass", "warn", "fail", "deferred"]
Tier = Literal["green", "yellow", "red"]

# Severity drives blocker gating. A `fail` on a `blocker` rule caps the
# overall score (see scorer.BLOCKER_CAP) regardless of weighted total.
Severity = Literal["blocker", "warning", "info"]

# Executor tells the engine which subsystem evaluates the rule. "hybrid" rules
# emit a deferred candidate routed via Rule.hybrid_route.
Executor = Literal["profiler", "metadata", "hybrid", "human"]

# Where a hybrid candidate's resolution comes from. v1 always routes to
# human_attestation; v2 will introduce "adjudicator".
HybridRoute = Literal["human_attestation", "adjudicator"]

# Evidence basis: how the finding was derived. Determines confidence weight.
EvidenceBasis = Literal["exact", "sample", "pushdown", "dictionary", "language_model", "association"]


class RuleCheckExplanation(BaseModel):
    """Static plain-language explanation from the rule pack. Never LLM-generated."""
    what: str
    why: str
    example: str


class RuleCheck(BaseModel):
    """Output of a single Rule.evaluate() call."""
    rule_id: str
    status: RuleStatus
    title: str
    detail: str
    recommendation: Optional[str] = None  # populated when status != "pass"
    expected: Optional[str] = None  # human-readable threshold like "at most 5%"

    # ── Phase 3 additions ────────────────────────────────────────────────
    severity: Severity = "warning"
    executor: Executor = "profiler"
    route: Optional[HybridRoute] = None
    evidence: dict = Field(default_factory=dict)
    dimension_id: Optional[str] = None
    explanation: Optional[RuleCheckExplanation] = None
    finding_uid: Optional[str] = None  # v3: stable hash for cross-linking
    basis: EvidenceBasis = "exact"  # v3: how the finding was derived
    enriched_detail: Optional[str] = None  # LLM-enriched version of detail


class DimensionResult(BaseModel):
    """Per-dimension scoring outcome."""
    id: str
    label: str
    weight: int = Field(ge=0, le=100)
    score: int = Field(ge=0, le=100)
    tier: Tier
    checks: list[RuleCheck]


class LensScore(BaseModel):
    """Aggregated score for one readiness lens (DQ / ML / AI)."""
    lens: Literal["DQ", "ML", "AI"]
    label: str
    score: int = Field(ge=0, le=100)
    tier: Tier
    check_count: int
    pass_count: int


# ── Capability model (v3) ────────────────────────────────────────────────

CapabilityId = Literal[
    "SEM", "JOIN", "GOV", "AGG", "ACC", "FRS", "LBL",
    "LKG", "SIG", "STA", "TMP", "VOL", "LIN", "TXT",
]


class CapabilityMeasurement(BaseModel):
    """One of 14 capabilities measured 0-4 from evidence."""
    id: CapabilityId
    label: str
    level: int = Field(ge=0, le=4)
    required: int = 0  # filled when archetype selected
    gap: bool = False
    evidence: list[str] = Field(default_factory=list)  # finding_uids backing this level


ArchetypeFamily = Literal["agent_access", "baseline", "model_dev"]


class ArchetypeConfig(BaseModel):
    """One of 13 purpose archetypes loaded from YAML config."""
    id: str
    family: ArchetypeFamily
    label: str
    capability_floor: dict[str, int] = Field(default_factory=dict)
    gate_set: list[str] = Field(default_factory=list)


class Priority(BaseModel):
    """A cross-table top priority for the dashboard."""
    severity: Literal["high", "medium", "low"]
    title: str           # the recommendation text
    dimension_id: str
    table_name: Optional[str] = None  # which table the issue lives in


class Recommendation(BaseModel):
    """LLM-prioritized recommendation. Each entry MUST link to a finding via
    `finding_id` (a `RuleCheck.rule_id` from the deterministic Report) so prose
    stays evidence-anchored — the anti-hallucination contract."""
    finding_id: str
    priority: Literal["high", "medium", "low"]
    title: str
    detail: str
    technical_note: str = ""
    dimension_id: Optional[str] = None
    table_name: Optional[str] = None


class LLMMetadata(BaseModel):
    """Stamped onto every assessment when the LLM layer ran (or was skipped).
    Audit trail for reproducibility — never contains credentials."""
    model_config = ConfigDict(protected_namespaces=())

    used: bool = False                          # did the LLM actually run?
    model_config_name: Optional[str] = None     # e.g. "ai-red-data"
    fallback_reason: Optional[str] = None       # set when used=False, e.g. "missing_credentials"


class FieldIssue(BaseModel):
    """Per-field finding for the table inspector. Built by exploding multi-column
    findings into per-field entries. Table-level findings are excluded."""
    field: str
    dimension: str
    severity: Severity
    issue: str


class TableAssessment(BaseModel):
    """Assessment of a single table — one of N inside a SchemaAssessment."""
    table_name: str
    row_count: int
    column_count: int
    profiled_row_count: Optional[int] = None
    base_score: Optional[int] = Field(default=None, ge=0, le=100)
    overall_score: int = Field(ge=0, le=100)
    tier: Tier
    klass: TableKlass = "conditional"
    included: bool = True
    excluded_reason: Optional[str] = None
    dimensions: list[DimensionResult]
    dimension_scores: dict[str, Optional[int]] = Field(default_factory=dict)
    field_issues: list[FieldIssue] = Field(default_factory=list)
    summary: str = ""
    recommendations: list[str] = Field(default_factory=list)

    gated_by: list[str] = Field(default_factory=list)
    deferred: list[RuleCheck] = Field(default_factory=list)
    narrative: Optional[str] = None
    strengths: list[str] = Field(default_factory=list)
    prioritized_recommendations: list[Recommendation] = Field(default_factory=list)


class ActionTableDetail(BaseModel):
    """Per-table specifics for an action group — carries the data-aware finding."""
    table_name: str
    detail: str
    evidence: dict = Field(default_factory=dict)


class ActionGroup(BaseModel):
    """Consolidated finding grouped by rule across tables. Each action appears
    ONCE regardless of how many tables it affects."""
    rule_id: str
    issue: str
    severity: Severity
    dimension_id: str
    recommended_fix: str
    explanation: Optional[RuleCheckExplanation] = None
    affected_tables: list[str] = Field(default_factory=list)
    table_count: int = 0
    table_details: list[ActionTableDetail] = Field(default_factory=list)
    score_delta: Optional[int] = None  # v3: points gained if resolved


class DimensionDetail(BaseModel):
    """Per-dimension summary with the tables that pull it below par."""
    id: str
    label: str
    score: Optional[int] = None
    weak_tables: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)


class SchemaAssessment(BaseModel):
    """Top-level assessment rolling up N tables. Returned by both CSV and DB
    flows even when N=1 — the frontend handles both cases uniformly."""
    base_score: Optional[int] = Field(default=None, ge=0, le=100)
    overall_score: int = Field(ge=0, le=100)
    tier: Tier
    verdict: SchemaVerdict = "Conditional"
    summary: str = ""
    top_priorities: list[Priority] = Field(default_factory=list)
    dimensions: list[DimensionResult]
    tables: list[TableAssessment]
    table_count: int
    metadata_profile: Optional[MetadataProfile] = None

    gated_by: list[str] = Field(default_factory=list)
    active_dimensions: list[str] = Field(default_factory=list)
    llm: LLMMetadata = Field(default_factory=LLMMetadata)
    lens_scores: list["LensScore"] = Field(default_factory=list)

    # v3: purpose-aware assessment
    capabilities: list["CapabilityMeasurement"] = Field(default_factory=list)
    selected_archetype: Optional[str] = None
    purpose_verdict: Optional[dict] = None  # VerdictResult serialized

    # Part B additions
    action_groups: list[ActionGroup] = Field(default_factory=list)
    dimension_detail: list[DimensionDetail] = Field(default_factory=list)
    assessed_count: int = 0
    reference_count: int = 0
    reconciliation: list[ReconciliationFinding] = Field(default_factory=list)
    metadata_quality: Optional[MetadataQuality] = None

    # Phase B: shadow annotator claims (logged, not consumed by scorer)
    annotator_claims: list[dict] = Field(default_factory=list)


# ───────────────────────────────────────────────────────────────────────────
# Annotator models (Phase B)
# ───────────────────────────────────────────────────────────────────────────

class AnnotatorColumnClaim(BaseModel):
    """Per-column semantic classification from the annotator."""
    column_name: str
    semantic_type: str
    pii_class: Literal["direct", "quasi", "none"] = "none"
    pii_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    temporal_role: Literal["event", "load", "effective", "none"] = "none"
    surrogate_tokens: list[str] = Field(default_factory=list)
    note: str = ""


class AnnotatorOutput(BaseModel):
    """Output of one annotator call (one table)."""
    table_name: str
    source: Literal["llm", "heuristic"]
    grain: Optional[str] = None
    narrative: Optional[str] = None
    target: Optional[str] = None
    leakage_candidates: list[str] = Field(default_factory=list)
    columns: list[AnnotatorColumnClaim] = Field(default_factory=list)
    fell_back: bool = False
    error: Optional[str] = None


# ───────────────────────────────────────────────────────────────────────────
# Metadata profile — parsed from an optional data dictionary CSV upload
# ───────────────────────────────────────────────────────────────────────────

MetadataSource = Literal["authored", "measured", "derived", "system"]


class MetadataEntry(BaseModel):
    """One row in the data dictionary — describes a single column.
    Aligned to the Metadata Standard (see app/docs/metadata_layer.md §2.0)."""
    table_name: Optional[str] = None
    column_name: str
    # Original fields (backwards compatible)
    description: Optional[str] = None
    business_owner: Optional[str] = None
    data_steward: Optional[str] = None
    pii_classification: Optional[str] = None
    sensitivity_level: Optional[str] = None
    retention_policy: Optional[str] = None
    source_system: Optional[str] = None
    refresh_frequency: Optional[str] = None
    last_updated: Optional[str] = None
    # Standard fields (Phase 2)
    definition: Optional[str] = None
    data_type_declared: Optional[str] = None
    nullable_declared: Optional[str] = None
    valid_values_range: Optional[str] = None
    primary_foreign_key: Optional[str] = None
    entity_classification: Optional[str] = None
    field_role: Optional[str] = None
    pii_flag: Optional[str] = None
    pii_category: Optional[str] = None
    security_classification: Optional[str] = None
    consent_basis: Optional[str] = None
    ai_ml_usage_approval: Optional[str] = None
    target_label_indicator: Optional[str] = None
    unit_of_measure: Optional[str] = None
    cardinality_declared: Optional[str] = None
    protected_attribute: Optional[str] = None
    timezone_temporal: Optional[str] = None
    last_synced_at: Optional[str] = None
    grain: Optional[str] = None
    lineage: Optional[str] = None
    usage_context: Optional[str] = None
    source: MetadataSource = "authored"
    # Extension fields (unknown columns preserved from upload)
    extensions: dict = Field(default_factory=dict)


class MetadataProfile(BaseModel):
    """Parsed summary of an uploaded data dictionary CSV."""
    entries: list[MetadataEntry]
    total_columns: int = Field(ge=0)
    columns_with_metadata: int = Field(ge=0)
    coverage_pct: float = Field(ge=0, le=100)
    unknown_columns: list[str] = Field(default_factory=list)
    parser_notes: list[str] = Field(default_factory=list)


class ReconciliationFinding(BaseModel):
    """One declared-vs-observed contradiction or drift detected by the reconciler."""
    column_name: str
    field: str
    declared: str
    observed: str
    severity: Severity
    detail: str
    status: Literal["confirmed", "could_not_verify"] = "confirmed"


class MetadataQualityCategory(BaseModel):
    """DEPRECATED — kept for serialization compat. Use BOTLCategoryScore."""
    name: str
    status: Literal["present", "partial", "absent"]
    coverage_pct: float
    missing_fields: list[str] = Field(default_factory=list)


class BOTLFieldStatus(BaseModel):
    """Per-field scoring result in the BOTL assessment."""
    field_id: str
    field_name: str
    category: str
    status: Literal["present", "absent", "invalid"]
    valid: bool = False
    reason: str = ""
    effective_severity: Literal["HIGH", "MEDIUM", "LOW"] = "HIGH"
    points_possible: float = 0.0
    points_earned: float = 0.0
    column_coverage: dict | None = None
    escalation_applied: str | None = None
    why: str = ""


class BOTLCategoryScore(BaseModel):
    """Score for one of the 4 BOTL categories."""
    category: str
    score_pct: int = Field(ge=0, le=100)
    points_earned: float
    points_possible: float
    fields_total: int
    fields_present: int
    fields_valid: int


class BOTLRemediation(BaseModel):
    """One item in the ranked remediation list."""
    field_id: str
    field_name: str
    priority: int
    points_recoverable: float
    effective_severity: Literal["HIGH", "MEDIUM", "LOW"]
    category: str
    reason: str
    why: str
    owner_route: str


class MetadataQuality(BaseModel):
    """BOTL v2.0 metadata quality assessment."""
    # BOTL v2.0 fields
    standard_version: str = "2.0"
    verdict: Literal["RED", "YELLOW", "GREEN"] = "RED"
    scores: dict = Field(default_factory=dict)
    categories: list[BOTLCategoryScore] = Field(default_factory=list)
    fields: list[BOTLFieldStatus] = Field(default_factory=list)
    escalations_applied: list[dict] = Field(default_factory=list)
    remediation: list[BOTLRemediation] = Field(default_factory=list)
    # Backward compat (consumed by _retune_metadata_dimension)
    dimension_score: int = 0
    findings: list[str] = Field(default_factory=list)
    weighted_coverage: float = 0.0
    reconciliation_accuracy: float = 0.0


# ───────────────────────────────────────────────────────────────────────────
# Database credentials & introspection
# ───────────────────────────────────────────────────────────────────────────

DBEngine = Literal["postgres", "redshift"]


class DBCredentials(BaseModel):
    """Database connection details. Password handled as SecretStr — masked in
    repr / logs / model_dump unless `mode='json'` is asked explicitly."""
    model_config = ConfigDict(str_strip_whitespace=True)

    engine: DBEngine
    host: str = Field(min_length=1)
    port: int = Field(ge=1, le=65535)
    database: str = Field(min_length=1)
    username: str = Field(min_length=1)
    password: SecretStr
    ssl: bool = True  # default on, can disable for local dev only


class ConnectionTestRequest(BaseModel):
    credentials: DBCredentials


class ConnectionTestResponse(BaseModel):
    ok: bool
    code: Literal[
        "OK", "CONNECTION_TIMEOUT", "AUTH_FAILED",
        "HOST_UNREACHABLE", "UNKNOWN_ERROR"
    ]
    detail: str
    description: str = ""
    elapsed_ms: int


class ListTablesRequest(BaseModel):
    credentials: DBCredentials
    schema_name: str = Field(min_length=1, alias="schema")

    model_config = ConfigDict(populate_by_name=True)


class TableSummary(BaseModel):
    """Lightweight info returned by /connect/tables for the picker UI."""
    name: str
    estimated_row_count: Optional[int] = None
    column_count: int


class ListTablesResponse(BaseModel):
    schema_name: str = Field(alias="schema")
    tables: list[TableSummary]

    model_config = ConfigDict(populate_by_name=True)


# ───────────────────────────────────────────────────────────────────────────
# Assessment requests
# ───────────────────────────────────────────────────────────────────────────

class AssessDBRequest(BaseModel):
    credentials: DBCredentials
    schema_name: str = Field(min_length=1, alias="schema")
    tables: list[str] = Field(min_length=1, max_length=50)

    model_config = ConfigDict(populate_by_name=True)


# CSV requests are multipart — handled at the route layer, no model.


# ───────────────────────────────────────────────────────────────────────────
# Async jobs
# ───────────────────────────────────────────────────────────────────────────

JobStatus = Literal["pending", "running", "cancelling", "done", "failed", "cancelled"]


class JobError(BaseModel):
    code: str
    detail: str
    description: str = ""


class JobAck(BaseModel):
    """Returned immediately by POST endpoints that kick off async work."""
    job_id: str
    status: JobStatus = "pending"


class JobStatusResponse(BaseModel):
    """Returned by GET /assess/jobs/{job_id}."""
    job_id: str
    status: JobStatus
    progress: int = Field(default=0, ge=0, le=100)
    phase: str = ""
    created_at: datetime
    updated_at: datetime
    result: Optional[SchemaAssessment] = None
    error: Optional[JobError] = None


# ───────────────────────────────────────────────────────────────────────────
# Support
# ───────────────────────────────────────────────────────────────────────────

class TicketRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=200)
    subject: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=10_000)


class TicketReceipt(BaseModel):
    ok: bool
    ticket_id: str
    sink: str  # which sink handled it: "email" / "servicenow" / "stub"


# ───────────────────────────────────────────────────────────────────────────
# Runbook (Part 2§A4 / §C)
# ───────────────────────────────────────────────────────────────────────────

class RunbookFinding(BaseModel):
    """One finding in the runbook request — deterministic fact + metadata context."""
    rule_id: str
    dimension: str
    severity: Severity
    issue: str
    detail: str
    recommendation: str
    target_columns: list[str] = Field(default_factory=list)
    metadata_context: dict = Field(default_factory=dict)
    evidence: dict = Field(default_factory=dict)
    criticality: str = "Medium"  # Critical / High / Medium / Low


class RunbookTableInput(BaseModel):
    """Per-table input for the runbook agent."""
    table_name: str
    row_count: int
    column_count: int = 0
    score: int
    tier: str
    klass: str
    dimension_scores: list[dict] = Field(default_factory=list)
    metadata_coverage: dict | None = None
    findings: list[RunbookFinding]


class RunbookRequest(BaseModel):
    """Full input payload for the runbook agent. Built from the Report."""
    schema_score: int
    schema_verdict: str
    gated_by: list[str] = Field(default_factory=list)
    tables: list[RunbookTableInput]


class RunbookStep(BaseModel):
    """One remediation step in the runbook output."""
    issue: str
    recommendation: str
    verify: str = ""  # kept for backward compat; prompt no longer emphasizes it
    criticality: str = ""  # Critical / High / Medium / Low
    columns: list[str] = Field(default_factory=list)
    evidence_summary: str = ""


class RunbookTableOutput(BaseModel):
    """Per-table section of the runbook."""
    table_name: str
    steps: list[RunbookStep]


class RunbookSnapshot(BaseModel):
    """Header info stamped on the runbook."""
    score: int
    verdict: str
    gates: list[str] = Field(default_factory=list)
    generated_by: str = "runbook-agent"


class RunbookOutput(BaseModel):
    """Full structured output from the runbook agent."""
    snapshot: RunbookSnapshot
    tables: list[RunbookTableOutput]
