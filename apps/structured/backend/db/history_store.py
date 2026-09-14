"""History store — read/write surface for the history_assessment schema.

This is the ONLY module that core/ and api/ may import for DB I/O. No raw
SQL strings allowed elsewhere.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.schema import AssessmentRun, TableAssessment, User

logger = logging.getLogger(__name__)

# Keys whose presence in source_ref would constitute a credential leak.
_REDACTED_KEY_SUBSTRINGS = frozenset(
    ("password", "secret", "key", "token", "credential", "pwd")
)


def _sanitize_source_ref(source_ref: dict[str, Any] | None) -> dict[str, Any] | None:
    """Strip credential-like keys before persisting to JSONB.

    Keeps non-secret metadata only — host, db name, schema, bucket, key
    prefix. Drops any key whose lowercase name contains a red-flag substring.
    """
    if source_ref is None:
        return None
    cleaned = {
        k: v
        for k, v in source_ref.items()
        if not any(sub in k.lower() for sub in _REDACTED_KEY_SUBSTRINGS)
    }
    if len(cleaned) != len(source_ref):
        logger.warning(
            "source_ref had %d credential-like key(s) stripped before persistence.",
            len(source_ref) - len(cleaned),
        )
    return cleaned


async def upsert_user(
    session: AsyncSession,
    *,
    user_id: str,
    email: str | None = None,
    role: str | None = None,
    department: str | None = None,
) -> None:
    """Insert the user row on first sight; on subsequent calls, refresh
    last_seen and any non-NULL fields the caller passed.

    Idempotent — safe to call on every authenticated request.
    """
    stmt = pg_insert(User).values(
        user_id=user_id,
        email=email,
        role=role,
        department=department,
    )
    # Only overwrite fields the caller actually provided. last_seen always
    # ticks forward.
    update_cols: dict[str, Any] = {"last_seen": stmt.excluded.last_seen}
    if email is not None:
        update_cols["email"] = stmt.excluded.email
    if role is not None:
        update_cols["role"] = stmt.excluded.role
    if department is not None:
        update_cols["department"] = stmt.excluded.department
    stmt = stmt.on_conflict_do_update(
        index_elements=[User.user_id],
        set_=update_cols,
    )
    await session.execute(stmt)


async def record_run(
    session: AsyncSession,
    *,
    user_id: str,
    source_type: str,
    source_name: str,
    source_ref: dict[str, Any] | None,
    overall_score: int,
    tier: str,
    duration_ms: int | None,
    table_assessments: list[dict[str, Any]],
    table_group: str | None = None,
    result_json: dict[str, Any] | None = None,
) -> str:
    """Persist one assessment run + its per-table results. Returns run_id.

    `table_assessments` is a list of dicts shaped like:
      {"table_name": str, "table_group": str|None, "table_score": int,
       "tier": str, "dimension_scores": dict, "findings": list,
       "strengths": list, "recommendations": list}

    Caller is responsible for committing the session.
    """
    run = AssessmentRun(
        user_id=user_id,
        source_type=source_type,
        source_name=source_name,
        source_ref=_sanitize_source_ref(source_ref),
        table_group=table_group,
        overall_score=overall_score,
        tier=tier,
        duration_ms=duration_ms,
        result_json=result_json,
    )
    session.add(run)
    # Flush so Postgres assigns run_id via gen_random_uuid() RETURNING.
    # Both INSERTs stay in the same transaction — flush without commit.
    await session.flush()

    ta_rows = [
        TableAssessment(
            run_id=run.run_id,
            table_name=ta["table_name"],
            table_group=ta.get("table_group"),
            table_score=ta["table_score"],
            tier=ta["tier"],
            dimension_scores=ta["dimension_scores"],
            findings=ta["findings"],
            strengths=ta["strengths"],
            recommendations=ta["recommendations"],
        )
        for ta in table_assessments
    ]
    session.add_all(ta_rows)
    return str(run.run_id)


async def get_recent_runs(
    session: AsyncSession,
    *,
    user_id: str,
    limit: int = 5,
) -> list[AssessmentRun]:
    """Return the user's most recent runs, newest first."""
    capped = min(limit, 100)
    stmt = (
        select(AssessmentRun)
        .where(AssessmentRun.user_id == user_id)
        .order_by(AssessmentRun.created_at.desc())
        .limit(capped)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_run_detail(
    session: AsyncSession,
    *,
    run_id: str,
    user_id: str,
) -> tuple[AssessmentRun, list[TableAssessment]] | None:
    """Return one run plus all its table_assessments, scoped to user_id.

    Returns None when the run does not belong to the user (or doesn't exist).
    Caller raises 404 in that case.

    selectinload is used because SA 1.4 asyncio does not support lazy-loading
    relationships — deferred access outside the session raises MissingGreenlet.
    """
    try:
        run_uuid = uuid.UUID(run_id)
    except ValueError:
        return None

    stmt = (
        select(AssessmentRun)
        .where(
            AssessmentRun.run_id == run_uuid,
            AssessmentRun.user_id == user_id,
        )
        .options(selectinload(AssessmentRun.table_assessments))
    )
    result = await session.execute(stmt)
    run = result.scalar_one_or_none()
    if run is None:
        return None
    return run, list(run.table_assessments)


async def delete_run(
    session: AsyncSession,
    *,
    user_id: str,
    run_id: str,
) -> bool:
    """Delete a single assessment run owned by user_id. Returns True if deleted.

    Returns False when the run does not exist OR does not belong to user_id —
    callers raise 404 in both cases to avoid leaking existence.
    """
    try:
        run_uuid = uuid.UUID(run_id)
    except ValueError:
        return False
    stmt = (
        delete(AssessmentRun)
        .where(
            AssessmentRun.run_id == run_uuid,
            AssessmentRun.user_id == user_id,
        )
    )
    result = await session.execute(stmt)
    return result.rowcount > 0


async def delete_all_runs(
    session: AsyncSession,
    *,
    user_id: str,
) -> int:
    """Delete all assessment runs for user_id. Returns the number of rows removed."""
    stmt = delete(AssessmentRun).where(AssessmentRun.user_id == user_id)
    result = await session.execute(stmt)
    return result.rowcount


# ─── Admin / superuser queries ────────────────────────────────────────────

async def get_user_flag(
    session: AsyncSession,
    user_id: str,
    flag: str,
) -> bool:
    """Read a boolean flag from the users row. Returns False if user not found."""
    stmt = select(getattr(User, flag)).where(User.user_id == user_id)
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    return bool(row)


async def list_all_users(
    session: AsyncSession,
    *,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """Return all users (paginated) with their run count."""
    from sqlalchemy import func

    count_stmt = select(func.count()).select_from(User)
    total = (await session.execute(count_stmt)).scalar_one()

    stmt = (
        select(
            User.user_id,
            User.email,
            User.role,
            User.is_superuser,
            User.first_seen,
            User.last_seen,
            func.count(AssessmentRun.run_id).label("run_count"),
        )
        .outerjoin(AssessmentRun, AssessmentRun.user_id == User.user_id)
        .group_by(User.user_id)
        .order_by(User.last_seen.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    rows = [
        {
            "user_id": r.user_id,
            "email": r.email,
            "role": r.role,
            "is_superuser": r.is_superuser,
            "first_seen": r.first_seen.isoformat() if r.first_seen else None,
            "last_seen": r.last_seen.isoformat() if r.last_seen else None,
            "run_count": r.run_count,
        }
        for r in result.all()
    ]
    return rows, total


async def list_all_runs(
    session: AsyncSession,
    *,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """Return all assessment runs across all users (paginated)."""
    from sqlalchemy import func

    count_stmt = select(func.count()).select_from(AssessmentRun)
    total = (await session.execute(count_stmt)).scalar_one()

    stmt = (
        select(
            AssessmentRun.run_id,
            AssessmentRun.user_id,
            User.email,
            AssessmentRun.source_type,
            AssessmentRun.source_name,
            AssessmentRun.overall_score,
            AssessmentRun.tier,
            AssessmentRun.created_at,
        )
        .join(User, User.user_id == AssessmentRun.user_id)
        .order_by(AssessmentRun.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    rows = [
        {
            "run_id": str(r.run_id),
            "user_id": r.user_id,
            "email": r.email,
            "source_type": r.source_type,
            "source_name": r.source_name,
            "overall_score": r.overall_score,
            "tier": r.tier,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in result.all()
    ]
    return rows, total


async def set_superuser_flag(
    session: AsyncSession,
    *,
    user_id: str,
    is_superuser: bool,
) -> bool:
    """Set or unset the superuser flag. Returns True if user existed."""
    from sqlalchemy import update
    stmt = (
        update(User)
        .where(User.user_id == user_id)
        .values(is_superuser=is_superuser)
    )
    result = await session.execute(stmt)
    return result.rowcount > 0


# ─── Attestations ──────────────────────────────────────────────────────────

async def record_attestation(
    session: AsyncSession,
    *,
    run_id: str,
    finding_uid: str,
    rule_id: str,
    table_name: str,
    decision: str,
    justification: str,
    decided_by: str,
) -> str:
    """Record a human attestation decision. Returns the attestation_id."""
    from db.schema import Attestation
    att = Attestation(
        run_id=run_id,
        finding_uid=finding_uid,
        rule_id=rule_id,
        table_name=table_name,
        decision=decision,
        justification=justification,
        decided_by=decided_by,
    )
    session.add(att)
    await session.flush()
    return str(att.attestation_id)


async def get_attestations_for_run(
    session: AsyncSession,
    *,
    run_id: str,
) -> list[dict]:
    """Return all attestation decisions for a given run."""
    from db.schema import Attestation
    from sqlalchemy import select
    stmt = (
        select(Attestation)
        .where(Attestation.run_id == run_id)
        .order_by(Attestation.decided_at)
    )
    result = await session.execute(stmt)
    rows = result.scalars().all()
    return [
        {
            "attestation_id": str(r.attestation_id),
            "finding_uid": r.finding_uid,
            "rule_id": r.rule_id,
            "table_name": r.table_name,
            "decision": r.decision,
            "justification": r.justification,
            "decided_by": r.decided_by,
            "decided_at": r.decided_at.isoformat() if r.decided_at else None,
        }
        for r in rows
    ]
