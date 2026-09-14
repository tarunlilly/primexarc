"""Health & identity endpoints."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from dependencies import CurrentUser, require_user

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/me")
async def me(user: CurrentUser = Depends(require_user)) -> dict:
    """Return the authenticated user's identity + superuser flag.

    The frontend calls this once on mount and caches the result to gate
    the Console nav link. Non-superusers see is_superuser=False and the
    Console link stays hidden.
    """
    from db.session import _async_session_factory, _ensure_engine, is_configured

    from dependencies import _LOCAL_SUPERUSERS

    is_superuser = False
    # Local dev bypass — same list as require_superuser()
    if user.user_id in _LOCAL_SUPERUSERS or user.email in _LOCAL_SUPERUSERS:
        is_superuser = True
    elif is_configured():
        try:
            _ensure_engine()
            if _async_session_factory is not None:
                from db.history_store import get_user_flag
                async with _async_session_factory() as session:
                    is_superuser = await get_user_flag(session, user.user_id, "is_superuser")
        except Exception:
            logger.warning("Failed to check superuser flag for /me", exc_info=True)

    return {
        "user_id": user.user_id,
        "email": user.email,
        "roles": user.roles,
        "is_superuser": is_superuser,
    }
