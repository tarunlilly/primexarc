"""Admin/console endpoints — superuser-gated.

All endpoints in this module use `Depends(require_superuser)`. A non-
superuser calling any of them receives a 403. The frontend hides the
Console nav link based on the /me response, but the real gate is here.
"""
from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from config import settings
from dependencies import CurrentUser, require_superuser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


# ─── LLM connection test ─────────────────────────────────────────────────

@router.get("/llm-status")
async def llm_status(_user: CurrentUser = Depends(require_superuser)) -> dict:
    """Ping the Cortex LLM — acquires a token and fires a minimal query.
    Returns latency, model config, and connection status. Never exposes
    credentials."""
    from llm.client import ping
    return await ping()


# ─── All users ────────────────────────────────────────────────────────────

@router.get("/users")
async def admin_users(
    _user: CurrentUser = Depends(require_superuser),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """List all ARC users with run counts (paginated)."""
    from db.session import _async_session_factory, _ensure_engine, is_configured
    from db.history_store import list_all_users

    if not is_configured():
        return {"users": [], "total": 0, "note": "DB not configured"}
    _ensure_engine()
    if _async_session_factory is None:
        raise HTTPException(503, "DB unavailable")
    async with _async_session_factory() as session:
        users, total = await list_all_users(session, limit=limit, offset=offset)
    return {"users": users, "total": total}


# ─── All assessment runs ──────────────────────────────────────────────────

@router.get("/runs")
async def admin_runs(
    _user: CurrentUser = Depends(require_superuser),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """List all assessment runs across all users (paginated, most recent first)."""
    from db.session import _async_session_factory, _ensure_engine, is_configured
    from db.history_store import list_all_runs

    if not is_configured():
        return {"runs": [], "total": 0, "note": "DB not configured"}
    _ensure_engine()
    if _async_session_factory is None:
        raise HTTPException(503, "DB unavailable")
    async with _async_session_factory() as session:
        runs, total = await list_all_runs(session, limit=limit, offset=offset)
    return {"runs": runs, "total": total}


# ─── Toggle superuser ─────────────────────────────────────────────────────

class SuperuserToggle(BaseModel):
    is_superuser: bool


@router.patch("/users/{user_id}")
async def toggle_superuser(
    user_id: str,
    body: SuperuserToggle,
    _user: CurrentUser = Depends(require_superuser),
) -> dict:
    """Grant or revoke superuser flag for a user. Only existing superusers
    can call this."""
    from db.session import _async_session_factory, _ensure_engine, is_configured
    from db.history_store import set_superuser_flag

    if not is_configured():
        raise HTTPException(503, "DB not configured")
    _ensure_engine()
    if _async_session_factory is None:
        raise HTTPException(503, "DB unavailable")
    async with _async_session_factory() as session:
        ok = await set_superuser_flag(session, user_id=user_id, is_superuser=body.is_superuser)
        await session.commit()
    if not ok:
        raise HTTPException(404, f"User {user_id} not found")
    return {"user_id": user_id, "is_superuser": body.is_superuser}


# ─── System diagnostics ──────────────────────────────────────────────────

_BOOT_TIME = time.time()


@router.get("/system")
async def system_diagnostics(
    _user: CurrentUser = Depends(require_superuser),
) -> dict:
    """Non-secret system state: DB connectivity, pool stats, active jobs,
    uptime, and masked config values."""
    from core.job_store import job_store
    from db.session import _async_session_factory, _ensure_engine, is_configured

    db_ok = False
    pool_size = 0
    if is_configured():
        try:
            _ensure_engine()
            if _async_session_factory is not None:
                async with _async_session_factory() as session:
                    await session.execute(__import__("sqlalchemy").text("SELECT 1"))
                db_ok = True
                pool_size = settings.history_pool_size
        except Exception:
            pass

    active_jobs = len([
        j for j in job_store._jobs.values()
        if j.status in ("pending", "running", "cancelling")
    ])
    total_runs = len(job_store._jobs)

    return {
        "db_connected": db_ok,
        "db_pool_size": pool_size,
        "active_jobs": active_jobs,
        "total_jobs_in_memory": total_runs,
        "uptime_s": int(time.time() - _BOOT_TIME),
        "config": {
            "cortex_base_urls": settings.cortex_base_urls,
            "model_config_name": settings.model_config_name,
            "hybrid_route": settings.hybrid_route,
            "output_tokens": "128K ceiling set in Cortex model config (max_response_token_size)",
            "tier_bands": {"green": ">=80", "yellow": "60-79", "red": "<60"},
        },
    }
