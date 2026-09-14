"""Add attestations table.

Revision ID: 0004
Create Date: 2026-08-02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

_SCHEMA = "history_assessment"


def upgrade() -> None:
    op.create_table(
        "attestations",
        sa.Column("attestation_id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("run_id", UUID(as_uuid=True),
                  sa.ForeignKey(f"{_SCHEMA}.assessment_runs.run_id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("finding_uid", sa.Text(), nullable=False),
        sa.Column("rule_id", sa.Text(), nullable=False),
        sa.Column("table_name", sa.Text(), nullable=False),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("justification", sa.Text(), nullable=False),
        sa.Column("decided_by", sa.Text(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint(
            "decision IN ('approved','rejected','accepted_risk','dismissed')",
            name="ck_att_decision",
        ),
        schema=_SCHEMA,
    )
    op.create_index("idx_att_run", "attestations", ["run_id"], schema=_SCHEMA)
    op.create_index("idx_att_finding", "attestations", ["finding_uid"], schema=_SCHEMA)


def downgrade() -> None:
    op.drop_index("idx_att_finding", table_name="attestations", schema=_SCHEMA)
    op.drop_index("idx_att_run", table_name="attestations", schema=_SCHEMA)
    op.drop_table("attestations", schema=_SCHEMA)
