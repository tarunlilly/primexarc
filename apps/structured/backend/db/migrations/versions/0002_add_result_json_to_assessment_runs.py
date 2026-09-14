"""add result_json to assessment_runs

Revision ID: 0002_add_result_json_to_assessment_runs
Revises: 0001_initial_history_assessment_schema
Create Date: 2026-06-11

Adds a nullable JSONB column `result_json` to `assessment_runs`. Stores the
full SchemaAssessment Pydantic dict so the history detail page can render
complete dimension cards, checks, and top-priorities without loss.

The column is nullable — existing rows (pre-migration) retain NULL, and the
/history/{run_id} endpoint returns a graceful fallback for those rows.

Mirror: app/backend/db/sql/0002_add_result_json_to_assessment_runs.sql
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from config import settings

revision = "0002_add_result_json_to_assessment_runs"
down_revision = "0001_initial_history_assessment_schema"
branch_labels = None
depends_on = None

SCHEMA = settings.history_db_schema


def upgrade() -> None:
    op.add_column(
        "assessment_runs",
        sa.Column("result_json", JSONB(), nullable=True),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("assessment_runs", "result_json", schema=SCHEMA)
