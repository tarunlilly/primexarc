"""SQLAlchemy ORM for the history_assessment schema.

Mirrors the DDL in `app/backend/db/sql/0001_initial_history_assessment_schema.sql`.
Schema name and UUID-source flag come from `config.settings` so the same code
runs locally (with .env) and in prod (with ExternalSecret-derived env vars).

NOTE: pinned to SQLAlchemy 1.4 because requirements.txt holds <2.0 for
sqlalchemy-redshift compatibility. We use the 1.4 declarative API + the
asyncio extension (`sqlalchemy.ext.asyncio`).
"""
from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

from config import settings

Base = declarative_base()

# Schema name read once at import; overridable via env var so the same ORM
# can target a non-default schema name without code changes.
_SCHEMA = settings.history_db_schema


def _uuid_default():
    """Python-side UUID generator. Used only when history_uuid_source='python'.

    When 'postgres' (the default), the column server_default is gen_random_uuid()
    and Python doesn't generate the value — Postgres does.
    """
    return uuid.uuid4()


# server_default is set only for Postgres-side generation; otherwise the
# Python `default=` callable handles it. Configured at import time.
_uuid_server_default = (
    text("gen_random_uuid()") if settings.history_uuid_source == "postgres" else None
)
_uuid_python_default = (
    None if settings.history_uuid_source == "postgres" else _uuid_default
)


class User(Base):
    """One row per SSO user (`l02XXXX`). Created lazily on first login."""

    __tablename__ = "users"
    __table_args__ = {"schema": _SCHEMA}

    user_id = Column(Text, primary_key=True)
    role = Column(Text, nullable=True)
    email = Column(Text, nullable=True)
    department = Column(Text, nullable=True)
    is_superuser = Column(Boolean, nullable=False, server_default=text("false"))
    first_seen = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    last_seen = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    runs = relationship(
        "AssessmentRun",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class AssessmentRun(Base):
    """One row per click of "Assess." Sortable by created_at."""

    __tablename__ = "assessment_runs"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('csv','db','s3')", name="ck_runs_source_type"
        ),
        CheckConstraint(
            "tier IN ('green','yellow','red')", name="ck_runs_tier"
        ),
        CheckConstraint(
            "overall_score BETWEEN 0 AND 100", name="ck_runs_overall_score"
        ),
        Index(
            "idx_runs_user_recent",
            "user_id",
            "created_at",
            postgresql_using="btree",
            # DESC on created_at — encoded by passing a literal SQL fragment
            # via the index expression in the migration; the ORM index here
            # is enough for query planning, the migration handles the DESC.
        ),
        Index(
            "idx_runs_source_ref_gin",
            "source_ref",
            postgresql_using="gin",
        ),
        {"schema": _SCHEMA},
    )

    run_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=_uuid_server_default,
        default=_uuid_python_default,
    )
    user_id = Column(
        Text,
        ForeignKey(f"{_SCHEMA}.users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    source_type = Column(Text, nullable=False)
    source_name = Column(Text, nullable=False)
    source_ref = Column(JSONB, nullable=True)
    table_group = Column(Text, nullable=True)
    overall_score = Column(Integer, nullable=False)
    tier = Column(Text, nullable=False)
    duration_ms = Column(Integer, nullable=True)
    result_json = Column(JSONB, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    user = relationship("User", back_populates="runs")
    table_assessments = relationship(
        "TableAssessment",
        back_populates="run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class TableAssessment(Base):
    """One row per table within a run. Variable-shape leaves in JSONB."""

    __tablename__ = "table_assessments"
    __table_args__ = (
        CheckConstraint(
            "tier IN ('green','yellow','red')", name="ck_ta_tier"
        ),
        CheckConstraint(
            "table_score BETWEEN 0 AND 100", name="ck_ta_table_score"
        ),
        Index("idx_ta_run", "run_id"),
        Index(
            "idx_ta_dim_scores_gin",
            "dimension_scores",
            postgresql_using="gin",
        ),
        Index(
            "idx_ta_findings_gin",
            "findings",
            postgresql_using="gin",
            postgresql_ops={"findings": "jsonb_path_ops"},
        ),
        {"schema": _SCHEMA},
    )

    table_assessment_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=_uuid_server_default,
        default=_uuid_python_default,
    )
    run_id = Column(
        UUID(as_uuid=True),
        ForeignKey(f"{_SCHEMA}.assessment_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    table_name = Column(Text, nullable=False)
    table_group = Column(Text, nullable=True)
    table_score = Column(Integer, nullable=False)
    tier = Column(Text, nullable=False)
    dimension_scores = Column(JSONB, nullable=False)
    findings = Column(JSONB, nullable=False)
    strengths = Column(JSONB, nullable=False)
    recommendations = Column(JSONB, nullable=False)

    run = relationship("AssessmentRun", back_populates="table_assessments")


class Attestation(Base):
    """One attestation decision per finding per run. Persists human review decisions
    for governance audit trail."""

    __tablename__ = "attestations"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('approved','rejected','accepted_risk','dismissed')",
            name="ck_att_decision",
        ),
        Index("idx_att_run", "run_id"),
        Index("idx_att_finding", "finding_uid"),
        {"schema": _SCHEMA},
    )

    attestation_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=_uuid_server_default,
        default=_uuid_python_default,
    )
    run_id = Column(
        UUID(as_uuid=True),
        ForeignKey(f"{_SCHEMA}.assessment_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    finding_uid = Column(Text, nullable=False)
    rule_id = Column(Text, nullable=False)
    table_name = Column(Text, nullable=False)
    decision = Column(Text, nullable=False)
    justification = Column(Text, nullable=False)
    decided_by = Column(Text, nullable=False)
    decided_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
