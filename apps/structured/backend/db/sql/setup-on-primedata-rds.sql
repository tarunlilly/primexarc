-- ==========================================================================
-- ARC schema setup on PrimeData's RDS (primedata-db-dev)
--
-- Run this as a privileged user (e.g. the RDS admin) on primedata-db-dev.
-- It creates the history_assessment schema and all 4 ARC tables.
-- PrimeData's own schema (public) is untouched.
--
-- After running this, create a DB role for ARC:
--   CREATE ROLE arc_app LOGIN PASSWORD '<password>';
--   GRANT USAGE ON SCHEMA history_assessment TO arc_app;
--   GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA history_assessment TO arc_app;
--   ALTER DEFAULT PRIVILEGES IN SCHEMA history_assessment
--     GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO arc_app;
-- ==========================================================================

-- 0. Schema
CREATE SCHEMA IF NOT EXISTS history_assessment;

-- 1. Extension (for gen_random_uuid)
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- 2. Users
CREATE TABLE history_assessment.users (
    user_id      TEXT        PRIMARY KEY,
    role         TEXT,
    email        TEXT,
    department   TEXT,
    is_superuser BOOLEAN     NOT NULL DEFAULT FALSE,
    first_seen   TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen    TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE history_assessment.users IS 'ARC user profiles, keyed by Azure AD OID';

-- 3. Assessment runs
CREATE TABLE history_assessment.assessment_runs (
    run_id        UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       TEXT        NOT NULL REFERENCES history_assessment.users(user_id) ON DELETE CASCADE,
    source_type   TEXT        NOT NULL CHECK (source_type IN ('csv','db','s3')),
    source_name   TEXT        NOT NULL,
    source_ref    JSONB,
    table_group   TEXT,
    overall_score INT         NOT NULL CHECK (overall_score BETWEEN 0 AND 100),
    tier          TEXT        NOT NULL CHECK (tier IN ('green','yellow','red')),
    duration_ms   INT,
    result_json   JSONB,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_runs_user_recent    ON history_assessment.assessment_runs (user_id, created_at DESC);
CREATE INDEX idx_runs_source_ref_gin ON history_assessment.assessment_runs USING GIN (source_ref);

COMMENT ON TABLE history_assessment.assessment_runs IS 'One row per ARC assessment execution';
COMMENT ON COLUMN history_assessment.assessment_runs.result_json IS 'Full assessment result payload (added in migration 0002)';

-- 4. Table assessments
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

COMMENT ON TABLE history_assessment.table_assessments IS 'Per-table dimension scores, findings, and recommendations';

-- 5. Attestations
CREATE TABLE history_assessment.attestations (
    attestation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id         UUID NOT NULL REFERENCES history_assessment.assessment_runs(run_id) ON DELETE CASCADE,
    finding_uid    TEXT NOT NULL,
    rule_id        TEXT NOT NULL,
    table_name     TEXT NOT NULL,
    decision       TEXT NOT NULL CHECK (decision IN ('approved','rejected','accepted_risk','dismissed')),
    justification  TEXT NOT NULL,
    decided_by     TEXT NOT NULL,
    decided_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_att_run     ON history_assessment.attestations(run_id);
CREATE INDEX idx_att_finding ON history_assessment.attestations(finding_uid);

COMMENT ON TABLE history_assessment.attestations IS 'User decisions on individual assessment findings';

-- 6. Verify
SELECT schemaname, tablename
  FROM pg_tables
 WHERE schemaname = 'history_assessment'
 ORDER BY tablename;
-- Expected output:
-- history_assessment | assessment_runs
-- history_assessment | attestations
-- history_assessment | table_assessments
-- history_assessment | users
