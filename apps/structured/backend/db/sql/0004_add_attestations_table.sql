-- Migration 0004: Add attestations table
-- Stores human review decisions for governance audit trail.

CREATE TABLE history_assessment.attestations (
    attestation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES history_assessment.assessment_runs(run_id) ON DELETE CASCADE,
    finding_uid TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    table_name TEXT NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('approved','rejected','accepted_risk','dismissed')),
    justification TEXT NOT NULL,
    decided_by TEXT NOT NULL,
    decided_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_att_run ON history_assessment.attestations(run_id);
CREATE INDEX idx_att_finding ON history_assessment.attestations(finding_uid);
