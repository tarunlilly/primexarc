-- ARC initial history-DB schema — assessment history persistence
-- Revision: 0001_initial_history_assessment_schema
-- Authoritative DDL snapshot. Mirrors the matching Alembic revision in
-- app/backend/db/migrations/versions/.
--
-- Preconditions (handled out-of-band, NOT by this migration):
--   * Schema `history_assessment` already exists.
--   * The DB user (configured via DB_USER / DB_PASSWORD env vars) has CREATE
--     on the schema and SELECT/INSERT/UPDATE/DELETE on tables it creates.
--
-- pgcrypto is required only when history_uuid_source=postgres (the default).
-- If CREATE EXTENSION fails because the DB user lacks privilege, set
-- history_uuid_source=python in the env and the ORM will generate UUIDs
-- with uuid.uuid4(); the gen_random_uuid() defaults below become unused.

-- ---- 1. Extensions ---------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS "pgcrypto";   -- for gen_random_uuid()

-- ---- 2. Tables -------------------------------------------------------------

-- 2a. Users — one row per SSO user. Created lazily on first login.
CREATE TABLE history_assessment.users (
    user_id      TEXT        PRIMARY KEY,                   -- 'l02XXXX' verbatim
    role         TEXT,                                       -- nullable; from MS Graph
    email        TEXT,
    department   TEXT,
    first_seen   TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen    TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE  history_assessment.users IS 'SSO-authenticated users of ARC. user_id is the Lilly SSO subject claim.';
COMMENT ON COLUMN history_assessment.users.role IS 'Job role from MS Graph; populated lazily, may be NULL.';

-- 2b. Assessment runs — one row per click of "Assess".
CREATE TABLE history_assessment.assessment_runs (
    run_id        UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       TEXT        NOT NULL REFERENCES history_assessment.users(user_id) ON DELETE CASCADE,
    source_type   TEXT        NOT NULL CHECK (source_type IN ('csv','db','s3')),
    source_name   TEXT        NOT NULL,
    source_ref    JSONB,                                     -- non-secret connection facts
    table_group   TEXT,
    overall_score INT         NOT NULL CHECK (overall_score BETWEEN 0 AND 100),
    tier          TEXT        NOT NULL CHECK (tier IN ('green','yellow','red')),
    duration_ms   INT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_runs_user_recent
    ON history_assessment.assessment_runs (user_id, created_at DESC);

CREATE INDEX idx_runs_source_ref_gin
    ON history_assessment.assessment_runs USING GIN (source_ref);

COMMENT ON COLUMN history_assessment.assessment_runs.source_ref IS
    'Non-secret connection metadata only — host/db/schema/bucket/key. NEVER passwords or tokens.';

-- 2c. Per-table results within a run.
CREATE TABLE history_assessment.table_assessments (
    table_assessment_id UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id              UUID        NOT NULL REFERENCES history_assessment.assessment_runs(run_id) ON DELETE CASCADE,
    table_name          TEXT        NOT NULL,
    table_group         TEXT,
    table_score         INT         NOT NULL CHECK (table_score BETWEEN 0 AND 100),
    tier                TEXT        NOT NULL CHECK (tier IN ('green','yellow','red')),
    dimension_scores    JSONB       NOT NULL,
    findings            JSONB       NOT NULL,
    strengths           JSONB       NOT NULL,
    recommendations     JSONB       NOT NULL
);

CREATE INDEX idx_ta_run            ON history_assessment.table_assessments (run_id);
CREATE INDEX idx_ta_dim_scores_gin ON history_assessment.table_assessments USING GIN (dimension_scores);
CREATE INDEX idx_ta_findings_gin   ON history_assessment.table_assessments USING GIN (findings jsonb_path_ops);

-- End of revision 0001_initial_history_assessment_schema.
