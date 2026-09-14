"""History endpoints — list, detail, and delete for a user's past assessment runs."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select

from db.history_store import delete_all_runs, delete_run, get_recent_runs, get_run_detail
from db.schema import TableAssessment as DBTableAssessment
from db.session import get_session, is_configured
from dependencies import CurrentUser, require_user
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/history", tags=["history"])


class HistoryRunSummary(BaseModel):
    run_id: str
    source_type: str
    source_name: str
    table_group: str | None
    overall_score: int
    tier: str
    created_at: datetime
    table_count: int


class HistoryTableResult(BaseModel):
    table_name: str
    table_group: str | None
    table_score: int
    tier: str
    dimension_scores: dict[str, Any]
    findings: list[Any]
    strengths: list[Any]
    recommendations: list[Any]


class HistoryRunDetail(BaseModel):
    run_id: str
    source_type: str
    source_name: str
    table_group: str | None
    overall_score: int
    tier: str
    duration_ms: int | None
    created_at: datetime
    table_count: int
    tables: list[HistoryTableResult]
    result: dict[str, Any] | None = None


class DeleteRunsResponse(BaseModel):
    deleted: int


def _db_available():
    if not is_configured():
        raise HTTPException(status_code=503, detail="History DB not configured.")


@router.get("", response_model=list[HistoryRunSummary])
async def list_runs(
    limit: int = Query(default=5, ge=1, le=50),
    user: CurrentUser = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> list[HistoryRunSummary]:
    """Return the user's recent assessment runs, newest first."""
    _db_available()
    runs = await get_recent_runs(session, user_id=user.user_id, limit=limit)
    if not runs:
        return []

    run_ids = [r.run_id for r in runs]
    count_result = await session.execute(
        select(DBTableAssessment.run_id, func.count().label("cnt"))
        .where(DBTableAssessment.run_id.in_(run_ids))
        .group_by(DBTableAssessment.run_id)
    )
    counts: dict = {row.run_id: row.cnt for row in count_result}

    return [
        HistoryRunSummary(
            run_id=str(run.run_id),
            source_type=run.source_type,
            source_name=run.source_name,
            table_group=run.table_group,
            overall_score=run.overall_score,
            tier=run.tier,
            created_at=run.created_at,
            table_count=counts.get(run.run_id, 0),
        )
        for run in runs
    ]


@router.get("/{run_id}", response_model=HistoryRunDetail)
async def get_run(
    run_id: str,
    user: CurrentUser = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> HistoryRunDetail:
    """Return the full detail of one assessment run, scoped to the caller."""
    _db_available()
    detail = await get_run_detail(session, run_id=run_id, user_id=user.user_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Assessment not found.")

    run, table_rows = detail
    tables = [
        HistoryTableResult(
            table_name=ta.table_name,
            table_group=ta.table_group,
            table_score=ta.table_score,
            tier=ta.tier,
            dimension_scores=ta.dimension_scores,
            findings=ta.findings,
            strengths=ta.strengths,
            recommendations=ta.recommendations,
        )
        for ta in table_rows
    ]
    return HistoryRunDetail(
        run_id=str(run.run_id),
        source_type=run.source_type,
        source_name=run.source_name,
        table_group=run.table_group,
        overall_score=run.overall_score,
        tier=run.tier,
        duration_ms=run.duration_ms,
        created_at=run.created_at,
        table_count=len(tables),
        tables=tables,
        result=run.result_json,
    )


@router.delete("/{run_id}", response_model=DeleteRunsResponse)
async def delete_run_handler(
    run_id: str,
    user: CurrentUser = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> DeleteRunsResponse:
    """Delete one assessment run owned by the caller."""
    _db_available()
    found = await delete_run(session, user_id=user.user_id, run_id=run_id)
    if not found:
        raise HTTPException(status_code=404, detail="Assessment not found.")
    await session.commit()
    return DeleteRunsResponse(deleted=1)


@router.delete("", response_model=DeleteRunsResponse)
async def delete_all_runs_handler(
    user: CurrentUser = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> DeleteRunsResponse:
    """Delete all assessment runs for the caller."""
    _db_available()
    count = await delete_all_runs(session, user_id=user.user_id)
    await session.commit()
    return DeleteRunsResponse(deleted=count)
