-- ARC migration: add is_superuser flag to users table
-- Revision: 0003_add_is_superuser_to_users
-- Mirror of the matching Alembic revision.
-- Apply after 0002_add_result_json_to_assessment_runs.sql.

ALTER TABLE history_assessment.users
    ADD COLUMN is_superuser BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN history_assessment.users.is_superuser IS
    'App-level superuser flag. TRUE grants access to /api/v1/admin/* endpoints. Default FALSE.';

-- Bootstrap: flag yourself as the first superuser:
-- UPDATE history_assessment.users SET is_superuser = TRUE WHERE email = 'tarunrajsingh48@lilly.com';
