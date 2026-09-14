from __future__ import annotations

import time

import pytest

import dependencies
from config import settings
from dependencies import CurrentUser


@pytest.mark.asyncio
async def test_require_user_schedules_background_upsert(monkeypatch):
    scheduled: list[CurrentUser] = []

    monkeypatch.setattr(settings, "client_id", "")  # local dev — no real Azure app
    monkeypatch.setattr(dependencies, "_schedule_user_upsert", lambda user: scheduled.append(user))

    user = await dependencies.require_user(None)

    assert user.user_id == "dev_user"
    assert scheduled == [user]


@pytest.mark.asyncio
async def test_upsert_user_failure_sets_retry_backoff(monkeypatch):
    import db.history_store as history_store
    import db.session as db_session

    class FakeSession:
        async def commit(self) -> None:
            return None

    class FakeSessionContext:
        async def __aenter__(self) -> FakeSession:
            return FakeSession()

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

    async def failing_upsert(*args, **kwargs):
        raise ConnectionResetError("history db unavailable")

    monkeypatch.setattr(db_session, "is_configured", lambda: True)
    monkeypatch.setattr(db_session, "_ensure_engine", lambda: None)
    monkeypatch.setattr(db_session, "_async_session_factory", lambda: FakeSessionContext())
    monkeypatch.setattr(history_store, "upsert_user", failing_upsert)
    monkeypatch.setattr(dependencies, "_user_upsert_retry_not_before", 0.0)

    await dependencies._upsert_user_if_db_ready(CurrentUser(user_id="u1", email="u1@lilly.com"))

    assert dependencies._user_upsert_retry_not_before > time.monotonic()