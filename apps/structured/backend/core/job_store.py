"""JobStore — in-memory tracking for async assessment jobs.

LIMITATION: This is single-process state. Running uvicorn with multiple
workers (`--workers 4`) will silently fail because each worker has its
own JobStore. For Phase 2 we run a single worker. When the team needs
to scale, swap this for Redis-backed storage (the interface stays the same).

Lifecycle:
    pending → running → cancelling → cancelled
                    └──────────────→ done | failed

Eviction: terminal jobs are dropped after `settings.job_ttl_seconds`.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Optional

from config import settings
from core.models import JobError, JobStatus, JobStatusResponse, SchemaAssessment

logger = logging.getLogger(__name__)


class _JobRecord:
    """Internal storage record. Not exported."""
    __slots__ = ("job_id", "status", "progress", "phase", "created_at",
                 "updated_at", "result", "error", "task", "cancel_event")

    def __init__(self, job_id: str) -> None:
        now = datetime.now(timezone.utc)
        self.job_id: str = job_id
        self.status: JobStatus = "pending"
        self.progress: int = 0
        self.phase: str = ""
        self.created_at: datetime = now
        self.updated_at: datetime = now
        self.result: Optional[SchemaAssessment] = None
        self.error: Optional[JobError] = None
        self.task: Optional[asyncio.Task] = None
        self.cancel_event = threading.Event()


class JobStore:
    """Process-local job tracking. Use the module-level `job_store` singleton."""

    def __init__(self) -> None:
        self._jobs: dict[str, _JobRecord] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _to_response(rec: _JobRecord) -> JobStatusResponse:
        return JobStatusResponse(
            job_id=rec.job_id,
            status=rec.status,
            progress=rec.progress,
            phase=rec.phase,
            created_at=rec.created_at,
            updated_at=rec.updated_at,
            result=rec.result,
            error=rec.error,
        )

    @staticmethod
    def _is_terminal(status: JobStatus) -> bool:
        return status in ("done", "failed", "cancelled")

    @staticmethod
    def _mark_cancelling_locked(
        rec: _JobRecord,
        detail: str = "Assessment cancellation in progress.",
    ) -> None:
        rec.status = "cancelling"
        rec.phase = "cancelling"
        rec.error = JobError(code="JOB_CANCELLING", detail=detail)
        rec.updated_at = datetime.now(timezone.utc)
        rec.cancel_event.set()

    @staticmethod
    def _mark_cancelled_locked(
        rec: _JobRecord,
        detail: str = "Assessment cancelled by user.",
    ) -> None:
        rec.status = "cancelled"
        rec.phase = "cancelled"
        rec.error = JobError(code="JOB_CANCELLED", detail=detail)
        rec.updated_at = datetime.now(timezone.utc)
        rec.cancel_event.set()

    async def create(self) -> str:
        async with self._lock:
            jid = uuid.uuid4().hex
            self._jobs[jid] = _JobRecord(jid)
            return jid

    async def attach_task(self, job_id: str, task: asyncio.Task) -> None:
        async with self._lock:
            rec = self._jobs.get(job_id)
            if rec:
                rec.task = task

    async def mark_running(self, job_id: str, progress: int = 1) -> None:
        async with self._lock:
            rec = self._jobs.get(job_id)
            if not rec or self._is_terminal(rec.status) or rec.status == "cancelling":
                return
            rec.status = "running"
            rec.progress = max(progress, rec.progress)
            rec.updated_at = datetime.now(timezone.utc)

    async def update_progress(self, job_id: str, progress: int,
                              phase: str = "") -> None:
        async with self._lock:
            rec = self._jobs.get(job_id)
            if not rec or self._is_terminal(rec.status) or rec.status == "cancelling":
                return
            rec.progress = max(0, min(100, progress))
            if phase:
                rec.phase = phase
            rec.updated_at = datetime.now(timezone.utc)

    async def mark_done(self, job_id: str, result: SchemaAssessment) -> None:
        async with self._lock:
            rec = self._jobs.get(job_id)
            if not rec or self._is_terminal(rec.status):
                return
            rec.status = "done"
            rec.progress = 100
            rec.phase = "done"
            rec.result = result
            rec.error = None
            rec.updated_at = datetime.now(timezone.utc)

    async def mark_failed(self, job_id: str, code: str, detail: str,
                          description: str = "") -> None:
        async with self._lock:
            rec = self._jobs.get(job_id)
            if not rec or self._is_terminal(rec.status):
                return
            rec.status = "failed"
            rec.phase = "failed"
            rec.error = JobError(code=code, detail=detail, description=description)
            rec.updated_at = datetime.now(timezone.utc)

    async def mark_cancelled(
        self,
        job_id: str,
        detail: str = "Assessment cancelled by user.",
    ) -> None:
        async with self._lock:
            rec = self._jobs.get(job_id)
            if not rec or self._is_terminal(rec.status):
                return
            self._mark_cancelled_locked(rec, detail)

    async def request_cancel(self, job_id: str) -> tuple[Optional[JobStatusResponse], bool]:
        async with self._lock:
            rec = self._jobs.get(job_id)
            if not rec:
                return None, False
            if self._is_terminal(rec.status):
                return self._to_response(rec), False
            if rec.status == "cancelling":
                return self._to_response(rec), False

            self._mark_cancelling_locked(rec)
            response = self._to_response(rec)

        return response, True

    async def is_cancellation_requested(self, job_id: str) -> bool:
        async with self._lock:
            rec = self._jobs.get(job_id)
            return bool(rec and rec.status == "cancelling")

    async def get_cancel_event(self, job_id: str) -> threading.Event | None:
        async with self._lock:
            rec = self._jobs.get(job_id)
            return rec.cancel_event if rec else None

    async def get(self, job_id: str) -> Optional[JobStatusResponse]:
        async with self._lock:
            rec = self._jobs.get(job_id)
            if not rec:
                return None
            return self._to_response(rec)

    async def sweep_expired(self) -> int:
        """Drop completed jobs older than TTL. Returns count removed.
        Called periodically by a background task in main.py."""
        cutoff = datetime.now(timezone.utc).timestamp() - settings.job_ttl_seconds
        async with self._lock:
            stale = [
                jid for jid, rec in self._jobs.items()
                if rec.status in ("done", "failed", "cancelled")
                and rec.updated_at.timestamp() < cutoff
            ]
            for jid in stale:
                del self._jobs[jid]
            return len(stale)


# Module-level singleton — imported by api/* routes.
job_store = JobStore()
