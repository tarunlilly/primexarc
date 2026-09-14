"""HTTP-level tests using FastAPI TestClient.

Covers happy and error paths for every endpoint. CSV assessment kicks off
a real background job; the test polls the status briefly to verify the
job lifecycle (pending → running → done).

The tests that poll a job MUST be async (so asyncio.sleep drives the loop)
— time.sleep blocks the whole thread and the background task can't progress.

DB endpoints test the FAILURE paths only — we never expect a real
connection from the test environment.
"""
from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ─── Health & me ──────────────────────────────────────────────────────────

def test_health_returns_ok(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_me_returns_user_info(client):
    r = client.get("/api/v1/me")
    assert r.status_code == 200
    body = r.json()
    assert body["user_id"]
    assert body["email"]
    assert "is_superuser" in body


# ─── Config ───────────────────────────────────────────────────────────────

def test_config_returns_503_when_unset(client, monkeypatch):
    import config as cfg
    monkeypatch.setattr(cfg.settings, "client_id", "")
    monkeypatch.setattr(cfg.settings, "tenant_id", "")
    r = client.get("/api/config")
    assert r.status_code == 503


def test_config_returns_ids_when_set(client, monkeypatch):
    import config as cfg
    monkeypatch.setattr(cfg.settings, "client_id", "test-client-id")
    monkeypatch.setattr(cfg.settings, "tenant_id", "test-tenant-id")
    r = client.get("/api/config")
    assert r.status_code == 200
    body = r.json()
    assert body["clientId"] == "test-client-id"
    assert body["tenantId"] == "test-tenant-id"


# ─── Support ──────────────────────────────────────────────────────────────

def test_submit_ticket_returns_receipt(client):
    r = client.post("/api/v1/support/tickets", json={
        "name": "Alex",
        "email": "alex@lilly.com",
        "subject": "Question about scoring",
        "body": "How is the temporal score computed?",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["ticket_id"]
    assert body["sink"] in ("email", "servicenow", "stub")


def test_submit_ticket_rejects_empty_body(client):
    r = client.post("/api/v1/support/tickets", json={
        "name": "Alex",
        "email": "alex@lilly.com",
        "subject": "Hi",
        "body": "",
    })
    assert r.status_code == 422  # Pydantic validation error


# ─── CSV assessment lifecycle ─────────────────────────────────────────────

def test_assess_csv_rejects_no_files(client):
    r = client.post("/api/v1/assess/csv")
    assert r.status_code == 422  # FastAPI: missing required form field


def test_assess_csv_rejects_empty_file(client):
    r = client.post(
        "/api/v1/assess/csv",
        files=[("files", ("empty.csv", b"", "text/csv"))],
    )
    assert r.status_code == 400


def test_assess_csv_rejects_total_payload_over_limit(client, monkeypatch):
    from config import settings

    monkeypatch.setattr(settings, "max_total_csv_bytes_per_request", 10)
    r = client.post(
        "/api/v1/assess/csv",
        files=[
            ("files", ("first.csv", b"a,b\n1,2\n", "text/csv")),
            ("files", ("second.csv", b"a,b\n3,4\n", "text/csv")),
        ],
    )
    assert r.status_code == 400
    assert "Total upload size exceeds" in r.json()["detail"]


def test_assess_csv_returns_job_id(client, taltz_bytes):
    r = client.post(
        "/api/v1/assess/csv",
        files=[("files", ("taltz.csv", taltz_bytes, "text/csv"))],
    )
    assert r.status_code == 202
    body = r.json()
    assert "job_id" in body
    assert body["status"] in ("pending", "running")


@pytest.mark.asyncio
async def test_profile_slot_serializes_when_limit_is_one(monkeypatch):
    import api.assess as assess_api

    monkeypatch.setattr(assess_api.settings, "max_concurrent_profile_jobs", 1)
    assess_api._profile_semaphore = None
    assess_api._profile_semaphore_limit = None

    events: list[str] = []

    async def worker(name: str) -> None:
        async with assess_api._profile_slot(name, "test"):
            events.append(f"start-{name}")
            await asyncio.sleep(0)
            events.append(f"end-{name}")

    await asyncio.gather(worker("a"), worker("b"))

    assert events in (
        ["start-a", "end-a", "start-b", "end-b"],
        ["start-b", "end-b", "start-a", "end-a"],
    )


@pytest.mark.asyncio
async def test_assess_db_reuses_existing_job_for_duplicate_request(monkeypatch):
    import api.assess as assess_api
    from httpx import ASGITransport, AsyncClient

    hold = asyncio.Event()

    async def fake_run_db_job(job_id, *_args, **_kwargs):
        await assess_api.job_store.mark_running(job_id, progress=5)
        try:
            await hold.wait()
        finally:
            await assess_api.job_store.mark_cancelled(job_id, detail="Test cleanup.")
            await assess_api._release_active_job(job_id)

    monkeypatch.setattr(assess_api, "_run_db_job", fake_run_db_job)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {
            "credentials": {
                "engine": "postgres",
                "host": "db.internal.lilly.com",
                "port": 5432,
                "database": "analytics",
                "username": "reader",
                "password": "secret",
                "ssl": True,
            },
            "schema": "public",
            "tables": ["claims", "members"],
        }
        form = {"req": json.dumps(payload)}

        first = await ac.post("/api/v1/assess/db", data=form)
        second = await ac.post("/api/v1/assess/db", data=form)

    hold.set()

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["job_id"] == second.json()["job_id"]


def test_cancel_job_unknown_returns_404(client):
    r = client.post("/api/v1/assess/jobs/does-not-exist/cancel")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_profile_slot_wait_cancellation_marks_job_cancelled(monkeypatch):
    import api.assess as assess_api

    monkeypatch.setattr(assess_api.settings, "max_concurrent_profile_jobs", 1)
    assess_api._profile_semaphore = None
    assess_api._profile_semaphore_limit = None

    job_id = await assess_api.job_store.create()
    holder_acquired = asyncio.Event()
    release_holder = asyncio.Event()

    async def holder() -> None:
        async with assess_api._profile_slot("holder", "test"):
            holder_acquired.set()
            await release_holder.wait()

    async def waiter() -> None:
        with pytest.raises(assess_api.JobCancellationRequested):
            async with assess_api._profile_slot(job_id, "test"):
                pytest.fail("cancelled waiter should not acquire the profiling slot")

    holder_task = asyncio.create_task(holder())
    await asyncio.wait_for(holder_acquired.wait(), timeout=1)

    waiter_task = asyncio.create_task(waiter())
    await asyncio.sleep(0)

    snapshot, requested = await assess_api.job_store.request_cancel(job_id)

    await asyncio.wait_for(waiter_task, timeout=1)
    release_holder.set()
    await asyncio.wait_for(holder_task, timeout=1)

    current = await assess_api.job_store.get(job_id)
    assert requested is True
    assert snapshot is not None
    assert snapshot.status == "cancelling"
    assert current is not None
    assert current.status == "cancelled"


@pytest.mark.asyncio
async def test_profile_slot_fast_release_still_honors_cancellation(monkeypatch):
    import api.assess as assess_api

    monkeypatch.setattr(assess_api.settings, "max_concurrent_profile_jobs", 1)
    assess_api._profile_semaphore = None
    assess_api._profile_semaphore_limit = None

    job_id = await assess_api.job_store.create()
    holder_acquired = asyncio.Event()
    release_holder = asyncio.Event()

    async def holder() -> None:
        async with assess_api._profile_slot("holder", "test"):
            holder_acquired.set()
            await release_holder.wait()

    async def waiter() -> None:
        with pytest.raises(assess_api.JobCancellationRequested):
            async with assess_api._profile_slot(job_id, "test"):
                pytest.fail("cancelled waiter should not acquire the profiling slot")

    holder_task = asyncio.create_task(holder())
    await asyncio.wait_for(holder_acquired.wait(), timeout=1)

    waiter_task = asyncio.create_task(waiter())
    await asyncio.sleep(0)

    snapshot, requested = await assess_api.job_store.request_cancel(job_id)
    release_holder.set()

    await asyncio.wait_for(waiter_task, timeout=1)
    await asyncio.wait_for(holder_task, timeout=1)

    current = await assess_api.job_store.get(job_id)
    assert requested is True
    assert snapshot is not None
    assert snapshot.status == "cancelling"
    assert current is not None
    assert current.status == "cancelled"


@pytest.mark.asyncio
async def test_mark_failed_overrides_late_cancelling_state():
    from core.job_store import JobStore

    store = JobStore()
    job_id = await store.create()

    snapshot, requested = await store.request_cancel(job_id)
    await store.mark_failed(job_id, "TEST_FAILURE", "boom")
    current = await store.get(job_id)

    assert requested is True
    assert snapshot is not None
    assert snapshot.status == "cancelling"
    assert current is not None
    assert current.status == "failed"
    assert current.error.code == "TEST_FAILURE"


@pytest.mark.asyncio
async def test_mark_done_clears_late_cancelling_error_state():
    from core.job_store import JobStore
    from core.models import SchemaAssessment

    store = JobStore()
    job_id = await store.create()

    snapshot, requested = await store.request_cancel(job_id)
    result = SchemaAssessment.model_validate({
        "overall_score": 80,
        "tier": "green",
        "dimensions": [],
        "tables": [],
        "table_count": 0,
    })

    await store.mark_done(job_id, result)
    current = await store.get(job_id)

    assert requested is True
    assert snapshot is not None
    assert snapshot.status == "cancelling"
    assert current is not None
    assert current.status == "done"
    assert current.phase == "done"
    assert current.error is None


@pytest.mark.asyncio
async def test_cancel_assess_db_job_marks_job_cancelled(monkeypatch):
    import api.assess as assess_api
    from httpx import ASGITransport, AsyncClient

    started = asyncio.Event()
    finish_cancel = asyncio.Event()

    async def fake_run_db_job(job_id, *_args, **_kwargs):
        await assess_api.job_store.mark_running(job_id, progress=5)
        await assess_api.job_store.update_progress(job_id, 5, phase="profiling")
        started.set()
        try:
            while not await assess_api.job_store.is_cancellation_requested(job_id):
                await asyncio.sleep(0)
            await finish_cancel.wait()
            await assess_api.job_store.mark_cancelled(job_id)
        finally:
            await assess_api._release_active_job(job_id)

    monkeypatch.setattr(assess_api, "_run_db_job", fake_run_db_job)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {
            "credentials": {
                "engine": "postgres",
                "host": "db.internal.lilly.com",
                "port": 5432,
                "database": "analytics",
                "username": "reader",
                "password": "secret",
                "ssl": True,
            },
            "schema": "public",
            "tables": ["claims", "members"],
        }
        form = {"req": json.dumps(payload)}

        submit = await ac.post("/api/v1/assess/db", data=form)
        assert submit.status_code == 202
        job_id = submit.json()["job_id"]

        await asyncio.wait_for(started.wait(), timeout=1)

        cancel = await ac.post(f"/api/v1/assess/jobs/{job_id}/cancel")
        assert cancel.status_code == 200
        cancelled_job = cancel.json()

        poll = await ac.get(f"/api/v1/assess/jobs/{job_id}")
        assert poll.status_code == 200

        finish_cancel.set()

        final = None
        for _ in range(10):
            await asyncio.sleep(0)
            final = await ac.get(f"/api/v1/assess/jobs/{job_id}")
            if final.json()["status"] == "cancelled":
                break

    assert cancelled_job["status"] == "cancelling"
    assert cancelled_job["error"]["code"] == "JOB_CANCELLING"
    assert poll.json()["status"] == "cancelling"
    assert final is not None
    assert final.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cancelling_db_job_blocks_duplicate_until_cancel_finishes(monkeypatch):
    import api.assess as assess_api
    from httpx import ASGITransport, AsyncClient

    started = asyncio.Event()
    finish_by_job: dict[str, asyncio.Event] = {}

    async def fake_run_db_job(job_id, *_args, **_kwargs):
        await assess_api.job_store.mark_running(job_id, progress=5)
        try:
            finish_by_job[job_id] = asyncio.Event()
            started.set()
            while not await assess_api.job_store.is_cancellation_requested(job_id):
                await asyncio.sleep(0)
            await finish_by_job[job_id].wait()
            await assess_api.job_store.mark_cancelled(job_id)
        finally:
            await assess_api._release_active_job(job_id)

    monkeypatch.setattr(assess_api, "_run_db_job", fake_run_db_job)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        payload = {
            "credentials": {
                "engine": "postgres",
                "host": "db.internal.lilly.com",
                "port": 5432,
                "database": "analytics",
                "username": "reader",
                "password": "secret",
                "ssl": True,
            },
            "schema": "public",
            "tables": ["claims", "members"],
        }
        form = {"req": json.dumps(payload)}

        first = await ac.post("/api/v1/assess/db", data=form)
        assert first.status_code == 202
        first_job_id = first.json()["job_id"]

        await asyncio.wait_for(started.wait(), timeout=1)

        cancel = await ac.post(f"/api/v1/assess/jobs/{first_job_id}/cancel")
        assert cancel.status_code == 200
        assert cancel.json()["status"] == "cancelling"

        second = await ac.post("/api/v1/assess/db", data=form)
        assert second.status_code == 202
        second_job_id = second.json()["job_id"]
        assert second.json()["status"] == "cancelling"

        finish_by_job[first_job_id].set()

        for _ in range(10):
            await asyncio.sleep(0)
            poll = await ac.get(f"/api/v1/assess/jobs/{first_job_id}")
            if poll.json()["status"] == "cancelled":
                break

        third = await ac.post("/api/v1/assess/db", data=form)
        assert third.status_code == 202
        third_job_id = third.json()["job_id"]

        cleanup = await ac.post(f"/api/v1/assess/jobs/{third_job_id}/cancel")
        assert cleanup.status_code == 200
        finish_by_job[third_job_id].set()

    assert second_job_id == first_job_id
    assert third_job_id != first_job_id


# The next two tests submit a job and poll until completion. They MUST run
# under asyncio so `asyncio.sleep` actually drives the event loop between
# polls — `time.sleep` blocks the loop and the background task can't progress.
@pytest.mark.asyncio
async def test_assess_csv_job_completes_for_taltz_fixture(taltz_bytes):
    """Submit the fixture, poll, expect a done job."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        submit = await ac.post(
            "/api/v1/assess/csv",
            files=[("files", ("taltz.csv", taltz_bytes, "text/csv"))],
        )
        assert submit.status_code == 202
        job_id = submit.json()["job_id"]

        # Poll up to ~10s — the event loop now runs continuously
        final = None
        for _ in range(20):
            await asyncio.sleep(0.5)
            poll = await ac.get(f"/api/v1/assess/jobs/{job_id}")
            assert poll.status_code == 200
            final = poll.json()
            if final["status"] in ("done", "failed"):
                break

    assert final["status"] == "done", f"job ended with status {final['status']}"
    result = final["result"]
    assert result is not None
    assert 0 <= result["overall_score"] <= 100
    assert result["tier"] in ("green", "yellow", "red")
    assert result["table_count"] == 1
    # The 60-row fixture is below reference_row_threshold (100) so it's
    # classified as reference and excluded from dimension scoring.
    table = result["tables"][0]
    assert table["klass"] == "reference"
    assert result["reference_count"] == 1


@pytest.mark.asyncio
async def test_assess_csv_accepts_multiple_files(taltz_bytes):
    """Two copies of the fixture → schema with table_count=2."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        submit = await ac.post(
            "/api/v1/assess/csv",
            files=[
                ("files", ("first.csv", taltz_bytes, "text/csv")),
                ("files", ("second.csv", taltz_bytes, "text/csv")),
            ],
        )
        assert submit.status_code == 202
        job_id = submit.json()["job_id"]

        final = None
        for _ in range(20):
            await asyncio.sleep(0.5)
            poll = await ac.get(f"/api/v1/assess/jobs/{job_id}")
            final = poll.json()
            if final["status"] in ("done", "failed"):
                break

    assert final["status"] == "done"
    assert final["result"]["table_count"] == 2
    assert len(final["result"]["tables"]) == 2


# ─── Job lookup ───────────────────────────────────────────────────────────

def test_get_job_unknown_returns_404(client):
    r = client.get("/api/v1/assess/jobs/does-not-exist")
    assert r.status_code == 404


# ─── DB connect test: failure paths only ─────────────────────────────────
# We deliberately use a non-routable address so the timeout actually fires.
# 192.0.2.1 is RFC 5737 TEST-NET-1 — guaranteed never to be reachable.

def test_connect_test_returns_ok_false_when_host_unreachable(client, monkeypatch):
    """Verify the endpoint shape on failure. Uses a short timeout so the test
    doesn't take 10s."""
    from config import settings
    monkeypatch.setattr(settings, "db_connect_timeout", 2)

    r = client.post("/api/v1/connect/test", json={
        "credentials": {
            "engine": "postgres",
            "host": "192.0.2.1",   # RFC 5737 TEST-NET — never routes
            "port": 5432,
            "database": "x",
            "username": "x",
            "password": "x",
            "ssl": False,
        },
    })
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["code"] in ("CONNECTION_TIMEOUT", "HOST_UNREACHABLE", "UNKNOWN_ERROR")
    assert body["description"]
    assert "whitelist" in body["description"].lower() or "credentials" in body["description"].lower()
    assert body["elapsed_ms"] >= 0


def test_connect_test_rejects_invalid_payload(client):
    r = client.post("/api/v1/connect/test", json={"credentials": {"engine": "invalid"}})
    assert r.status_code == 422


def test_connect_tables_returns_description_on_connection_failure(client, mocker):
    import api.connect as connect_api
    from core.db_introspector import DBConnectionError

    mocker.patch.object(
        connect_api._introspector,
        "list_tables",
        side_effect=DBConnectionError(
            "HOST_UNREACHABLE",
            "Host could not be resolved.",
            "ARC could not reach the database. Common causes are missing whitelist access or invalid credentials.",
        ),
    )

    r = client.post("/api/v1/connect/tables", json={
        "credentials": {
            "engine": "postgres",
            "host": "db.internal.lilly.com",
            "port": 5432,
            "database": "x",
            "username": "x",
            "password": "x",
            "ssl": False,
        },
        "schema": "public",
    })

    assert r.status_code == 503
    detail = r.json()["detail"]
    assert detail["code"] == "HOST_UNREACHABLE"
    assert detail["description"]
    assert "whitelist" in detail["description"].lower() or "credentials" in detail["description"].lower()