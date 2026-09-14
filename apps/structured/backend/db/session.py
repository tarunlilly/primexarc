"""Async SQLAlchemy engine + sessionmaker for the history DB.

The engine is lazily created so the app starts cleanly when DB env vars are
unset (in which case `history_db_url` is empty and history persistence is
treated as a no-op by callers — the app still serves assessments).

SQLAlchemy 1.4 asyncio extension is used. The driver is asyncpg.
"""
from __future__ import annotations

import logging
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from config import settings

logger = logging.getLogger(__name__)

_engine = None
_async_session_factory = None


def _ensure_engine() -> None:
    """Create the engine + session factory on first use; idempotent."""
    global _engine, _async_session_factory
    if _engine is not None:
        return
    url = settings.history_db_url
    if not url:
        logger.warning(
            "history DB not configured (DB_HOST unset) — persistence disabled"
        )
        return
    _engine = create_async_engine(
        url,
        pool_size=settings.history_pool_size,
        max_overflow=settings.history_pool_max_overflow,
        pool_pre_ping=True,
        # Echo SQL only when DEBUG=true; never log password values.
        echo=settings.debug,
    )
    _async_session_factory = sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    logger.info(
        "History DB engine initialised (host=%s db=%s schema=%s)",
        settings.db_host,
        settings.db_name,
        settings.history_db_schema,
    )


def is_configured() -> bool:
    """True iff a history DB URL is available — used by callers to decide
    whether to attempt persistence."""
    return bool(settings.history_db_url)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: yield an AsyncSession for one request."""
    _ensure_engine()
    if _async_session_factory is None:
        raise RuntimeError(
            "History DB is not configured (DB_HOST is empty). "
            "Callers should check `is_configured()` before invoking."
        )
    async with _async_session_factory() as session:
        yield session


async def dispose_engine() -> None:
    """Close the engine and its pool. Called on app shutdown."""
    global _engine, _async_session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _async_session_factory = None
