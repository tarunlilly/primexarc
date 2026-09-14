-- ARC migration: add result_json to assessment_runs
-- Revision: 0002_add_result_json_to_assessment_runs
-- Mirror of the matching Alembic revision in app/backend/db/migrations/versions/.
--
-- Apply after 0001_initial_history_assessment_schema.sql.
-- Operator runs: alembic upgrade head   (never auto-run on app boot)

ALTER TABLE history_assessment.assessment_runs
    ADD COLUMN result_json JSONB;

COMMENT ON COLUMN history_assessment.assessment_runs.result_json IS
    'Full SchemaAssessment JSON snapshot. NULL for runs persisted before this migration.';

-- End of revision 0002_add_result_json_to_assessment_runs.
