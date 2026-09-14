"""add is_superuser flag to users

Revision ID: 0003_add_is_superuser_to_users
Revises: 0002_add_result_json_to_assessment_runs
Create Date: 2026-06-11

Adds a NOT NULL boolean `is_superuser` column (default FALSE) to the users
table. Gates access to the developer console (/api/v1/admin/*). Only
existing superusers can grant the flag to others via the Console UI.

Mirror: app/backend/db/sql/0003_add_is_superuser_to_users.sql
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0003_add_is_superuser_to_users"
down_revision = "0002_add_result_json_to_assessment_runs"
branch_labels = None
depends_on = None

SCHEMA = "history_assessment"


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_superuser",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("users", "is_superuser", schema=SCHEMA)
