"""Application configuration.

Read once at startup from environment / .env file via pydantic-settings.
Imported as `from config import settings` everywhere.
"""
from __future__ import annotations

from urllib.parse import quote_plus

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        protected_namespaces=(),
    )

    # ── Application ────────────────────────────────────────────────────────
    debug: bool = False
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    # ── Profiling limits ───────────────────────────────────────────────────
    max_rows_per_table: int = Field(default=150_000, ge=100, le=200_000)
    max_rows_per_db_table: int = Field(default=10_000, ge=100, le=200_000)
    max_rows_per_redshift_table: int = Field(default=10_000, ge=100, le=200_000)
    db_include_views: bool = Field(default=True, description="Include views in table listing")
    max_concurrent_profile_jobs: int = Field(default=1, ge=1, le=8)
    max_files_per_request: int = Field(default=20, ge=1, le=50)
    max_csv_bytes: int = Field(default=50 * 1024 * 1024, ge=1024)
    max_total_csv_bytes_per_request: int = Field(default=100 * 1024 * 1024, ge=1024)

    # Tables below this row count are treated as a WEAK reference signal.
    # Row threshold alone doesn't auto-exclude; see metadata_layer.md §2.3.
    reference_row_threshold: int = Field(default=1000, ge=1, le=100_000)

    # ── Temporal integrity thresholds ─────────────────────────────────────
    temporal_min_span_pass_days: int = Field(default=90, ge=1, le=3650)
    temporal_min_span_warn_days: int = Field(default=30, ge=1, le=365)
    temporal_freshness_pass_days: int = Field(default=90, ge=1, le=3650)
    temporal_freshness_warn_days: int = Field(default=365, ge=1, le=3650)

    # ── Metadata reconciliation tolerances ─────────────────────────────────
    metadata_staleness_days: int = Field(default=90, ge=1, le=365)
    metadata_null_rate_tolerance: float = Field(default=0.02, ge=0, le=1.0)
    metadata_cardinality_drift_tolerance: float = Field(default=0.10, ge=0, le=1.0)
    # Governance-weighted quality scoring (must sum to 1.0)
    metadata_weight_governance: float = Field(default=0.40, ge=0, le=1.0)
    metadata_weight_technical: float = Field(default=0.25, ge=0, le=1.0)
    metadata_weight_operational: float = Field(default=0.20, ge=0, le=1.0)
    metadata_weight_business: float = Field(default=0.15, ge=0, le=1.0)

    # ── ydata-profiling enrichment ────────────────────────────────────────
    ydata_enabled: bool = False
    ydata_timeout_seconds: int = Field(default=120, ge=10, le=600)
    ydata_near_constant_threshold: float = Field(default=0.95, ge=0.8, le=1.0)
    ydata_correlation_threshold: float = Field(default=0.80, ge=0.5, le=1.0)

    # ── Source-DB connection (user-supplied, per-request — NOT persisted) ──
    db_connect_timeout: int = Field(default=60, ge=1, le=120)
    db_query_timeout: int = Field(default=120, ge=1, le=300)

    # ── History-DB connection (ARC's own backend Postgres) ────────────────
    # These five env vars match the names used in deploy.yaml so the same
    # config code reads from .env locally and from the ExternalSecret in prod.
    db_host: str = ""
    db_port: int = 5432
    db_name: str = ""
    db_user: str = ""
    db_password: str = ""
    # Local default is disabled. When DB_HOST is set (production via
    # ExternalSecret), the history DB is auto-enabled unless explicitly
    # overridden to False.
    history_db_enabled: bool | None = None
    # Role credentials sourced from AWS secret ibu-arc-dev/ibu-ai-ready-data/db-role.
    db_role: str = ""
    db_role_password: str = ""

    # Postgres schema where ARC tables live. Provisioned out-of-band; the
    # migration does NOT run CREATE SCHEMA. Override only if the operator
    # deployed the schema under a different name.
    history_db_schema: str = "history_assessment"

    # 'postgres' uses gen_random_uuid() (requires pgcrypto extension);
    # 'python' uses uuid.uuid4() in the ORM and skips pgcrypto entirely.
    history_uuid_source: str = "postgres"

    # SQLAlchemy async pool sizing.
    history_pool_size: int = Field(default=5, ge=1, le=50)
    history_pool_max_overflow: int = Field(default=10, ge=0, le=50)

    # ── Jobs ───────────────────────────────────────────────────────────────
    job_ttl_seconds: int = Field(default=900, ge=60)

    # ── LLM (Phase 3) ──────────────────────────────────────────────────────
    llm_provider: str = "cortex"
    llm_api_key: str = ""
    llm_model: str = "claude-sonnet-4-20250514"
    # Cortex-specific OAuth credentials sourced from AWS secret
    # ibu-arc-dev/ibu-ai-ready-data/cortex-llm. When any of the four are
    # empty the synthesizer raises LLMUnavailable and the rule-based
    # fallback runs — the assessment still completes.
    client_id_llm: str = ""
    tenant_id_llm: str = ""
    client_secret_llm: str = ""
    model_config_name: str = ""
    # Cortex API gateway. The call path tries the dev endpoint first,
    # then the dev intranet fallback. Optional extra envs stay unset
    # until the downstream endpoint is actually provisioned.
    cortex_base_url: str = "https://gateway.apim-dev.lilly.com/cortex"
    cortex_base_url_fallback: str = "https://gateway-intranet.apim-dev.lilly.com/cortex"

    # Optional extra envs. Leave blank until ARC is provisioned there.
    cortex_base_url_qa: str = ""
    cortex_base_url_fallback_qa: str = ""

    # For Production, use the intranet as primary and public as fallback.
    # cortex_base_url: str = "https://gateway.apim.lilly.com/cortex"
    # cortex_base_url_fallback: str = "https://gateway-intranet.apim.lilly.com/cortex"
    # Reserved slot for a cheaper model used in the future v2 adjudicator
    # fan-out. v1 has no code path that reads this — it stays empty.
    model_config_name_bulk: str = ""
    # Routing for hybrid-rule candidates (executor=hybrid). v1 always
    # routes to humans; v2 will flip this to "adjudicator" once the
    # llm/adjudicator.py implementation lands.
    hybrid_route: str = "human_attestation"
    # Phase B: semantic annotator mode. "off" = disabled, "shadow" = runs but
    # doesn't affect scores (logged in result_json), "active" = Phase C.
    annotator_mode: str = "shadow"
    # Per-endpoint Cortex inference read timeout for normal LLM calls.
    llm_inference_timeout_seconds: int = Field(default=120, ge=5, le=300)
    # Runbook generation uses the same timeout budget as normal LLM calls —
    # large assessments (many tables/findings) need the headroom.
    llm_runbook_timeout_seconds: int = Field(default=120, ge=5, le=180)

    # ── Auth (MSAL) ────────────────────────────────────────────────────────
    client_id: str = ""
    tenant_id: str = ""

    # ── Support ────────────────────────────────────────────────────────────
    support_sink: str = "stub"
    support_email_to: str = "ai-readiness@lilly.com"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cortex_base_urls(self) -> list[str]:
        """Ordered Cortex endpoint chain with de-duplication."""
        urls = [
            self.cortex_base_url,
            self.cortex_base_url_fallback,
            self.cortex_base_url_qa,
            self.cortex_base_url_fallback_qa,
        ]
        ordered: list[str] = []
        for url in urls:
            normalized = url.strip()
            if normalized and normalized not in ordered:
                ordered.append(normalized)
        return ordered

    @computed_field  # type: ignore[prop-decorator]
    @property
    def history_db_url(self) -> str:
        """asyncpg URL assembled from the five DB_* env vars.

        Returns an empty string when the history DB is disabled or DB_HOST is
        unset — callers (e.g. history_store) treat that as "history
        persistence disabled" rather than a startup error, so the app still
        serves assessments without a configured history DB.
        """
        if not self.db_host:
            return ""
        if self.history_db_enabled is False:
            return ""
        # Quote user/password — passwords commonly contain @ : / # ? which
        # would otherwise corrupt the URL. db_name is quoted defensively too.
        user = quote_plus(self.db_user)
        password = quote_plus(self.db_password)
        name = quote_plus(self.db_name)
        return (
            f"postgresql+asyncpg://{user}:{password}"
            f"@{self.db_host}:{self.db_port}/{name}"
        )


settings = Settings()

