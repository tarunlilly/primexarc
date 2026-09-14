"""Assessment endpoints — CSV upload, DB schema assessment, job polling.

Async model:
  - POST endpoints validate input, kick off a background task, return a
    JobAck with the job_id immediately.
  - Frontend polls GET /assess/jobs/{job_id} every ~2s.
  - When status == "done", the response carries the full SchemaAssessment.

Task storage pattern (per Python docs):
  Tasks created via `asyncio.create_task` must be held by a strong reference
  or they can be garbage-collected mid-execution. We store them in a module-
  level set AND on the JobRecord, with a done-callback that removes them
  from the set once finished. Belt + suspenders.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from config import settings
from core.csv_parser import CSVParseError, CSVParser
from core.db_introspector import DBConnectionError, DBIntrospector
from core.job_store import job_store
from core.metadata_parser import MetadataParseError, MetadataParser
from core.models import (
    AssessDBRequest,
    JobAck,
    JobStatusResponse,
    SchemaAssessment,
    TableProfile,
)
from core.scorer import ScoringEngine, rescore_with_approvals
from llm import advise as llm_advise
from dependencies import CurrentUser, require_user
from pydantic import BaseModel as _BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assess", tags=["assess"])

_parser = CSVParser()
_introspector = DBIntrospector()
_engine = ScoringEngine()
_metadata_parser = MetadataParser()


def _attach_capabilities(
    result: SchemaAssessment,
    profiles: list[TableProfile],
    purpose_id: str,
) -> SchemaAssessment:
    """Post-scoring: measure capabilities, compute verdict, attach to result."""
    from core.archetype_loader import ARCHETYPES
    from core.capabilities import measure_capabilities
    from core.verdict import compute_verdict

    # Use the first assessed table for capabilities (single-table is the common case)
    assessed_tables = [t for t in result.tables if t.included]
    if not assessed_tables:
        return result

    # Match table to its profile
    profile_map = {p.name: p for p in profiles}
    table = assessed_tables[0]
    profile = profile_map.get(table.table_name)
    if not profile:
        return result

    # Measure capabilities
    caps = measure_capabilities(table, profile)

    # Load archetype if purpose selected
    archetype = ARCHETYPES.get(purpose_id) if purpose_id else None

    # If archetype selected, mark required levels and gaps on capabilities
    if archetype:
        for cap in caps:
            req = archetype.capability_floor.get(cap.id, 0)
            cap.required = req
            cap.gap = cap.level < req

    # Compute verdict
    verdict = compute_verdict(caps, archetype, table.gated_by)

    # Attach to result
    return result.model_copy(update={
        "capabilities": caps,
        "selected_archetype": purpose_id or None,
        "purpose_verdict": verdict.model_dump() if archetype else None,
    })

# Strong-reference set for background tasks. Without this, the asyncio task
# can be garbage-collected the moment the route handler returns, even though
# we also store a reference on the JobRecord.
_background_tasks: set[asyncio.Task] = set()
_profile_semaphore: asyncio.Semaphore | None = None
_profile_semaphore_limit: int | None = None
_active_request_jobs: dict[str, str] = {}
_job_request_keys: dict[str, str] = {}
_active_request_lock = asyncio.Lock()


class JobCancellationRequested(Exception):
    """Raised when a job is cancelled while waiting for a profiling slot."""


async def _enrich_evidence(result: SchemaAssessment) -> SchemaAssessment:
    """Run evidence narrator on each table — additive only, never mutates scores."""
    from llm.evidence_narrator import narrate_evidence

    enriched_tables = []
    for t in result.tables:
        enrichments = await narrate_evidence(t)
        if enrichments:
            new_dims = []
            for dim in t.dimensions:
                new_checks = [
                    c.model_copy(update={"enriched_detail": enrichments[c.rule_id]})
                    if c.rule_id in enrichments else c
                    for c in dim.checks
                ]
                new_dims.append(dim.model_copy(update={"checks": new_checks}))
            enriched_tables.append(t.model_copy(update={"dimensions": new_dims}))
        else:
            enriched_tables.append(t)
    return result.model_copy(update={"tables": enriched_tables})


def _spawn(coro, name: str) -> asyncio.Task:
    """Create a task, hold a strong reference, auto-remove on completion."""
    task = asyncio.create_task(coro, name=name)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


def _request_digest(parts: list[str]) -> str:
    payload = "\x1f".join(parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _bytes_digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _csv_request_key(
    user_id: str,
    payloads: list[tuple[str, bytes]],
    metadata_payload: tuple[str, bytes] | None,
) -> str:
    file_parts = [
        f"{name}:{_bytes_digest(content)}"
        for name, content in sorted(payloads)
    ]
    meta_part = (
        f"{metadata_payload[0]}:{_bytes_digest(metadata_payload[1])}"
        if metadata_payload else "-"
    )
    return _request_digest(["csv", user_id, *file_parts, meta_part])


def _db_request_key(
    user_id: str,
    req_obj: AssessDBRequest,
    metadata_payload: tuple[str, bytes] | None,
) -> str:
    meta_part = (
        f"{metadata_payload[0]}:{_bytes_digest(metadata_payload[1])}"
        if metadata_payload else "-"
    )
    return _request_digest([
        "db",
        user_id,
        req_obj.credentials.engine,
        req_obj.credentials.host,
        str(req_obj.credentials.port),
        req_obj.credentials.database,
        req_obj.credentials.username,
        req_obj.credentials.password.get_secret_value(),
        str(req_obj.credentials.ssl),
        req_obj.schema_name,
        ",".join(sorted(req_obj.tables)),
        meta_part,
    ])


async def _claim_active_job(request_key: str) -> tuple[str, str, bool]:
    async with _active_request_lock:
        existing_job_id = _active_request_jobs.get(request_key)
        if existing_job_id:
            existing_job = await job_store.get(existing_job_id)
            if existing_job and existing_job.status in ("pending", "running", "cancelling"):
                return existing_job_id, existing_job.status, True
            _active_request_jobs.pop(request_key, None)
            _job_request_keys.pop(existing_job_id, None)

        job_id = await job_store.create()
        _active_request_jobs[request_key] = job_id
        _job_request_keys[job_id] = request_key
        return job_id, "pending", False


async def _release_active_job(job_id: str) -> None:
    async with _active_request_lock:
        request_key = _job_request_keys.pop(job_id, None)
        if request_key and _active_request_jobs.get(request_key) == job_id:
            _active_request_jobs.pop(request_key, None)


async def _stop_if_cancellation_requested(job_id: str) -> bool:
    if not await job_store.is_cancellation_requested(job_id):
        return False

    logger.info("[job %s] cancellation acknowledged", job_id)
    await job_store.mark_cancelled(job_id)
    return True


def _get_profile_semaphore() -> asyncio.Semaphore:
    global _profile_semaphore, _profile_semaphore_limit

    limit = settings.max_concurrent_profile_jobs
    if _profile_semaphore is None or _profile_semaphore_limit != limit:
        _profile_semaphore = asyncio.Semaphore(limit)
        _profile_semaphore_limit = limit
    return _profile_semaphore


@asynccontextmanager
async def _profile_slot(job_id: str, source: str):
    semaphore = _get_profile_semaphore()
    wait_started = time.monotonic()
    logger.info("[job %s] waiting for profile slot (%s)", job_id, source)
    acquired = False

    try:
        while not acquired:
            try:
                await asyncio.wait_for(semaphore.acquire(), timeout=0.25)
                acquired = True
            except asyncio.TimeoutError:
                if await job_store.is_cancellation_requested(job_id):
                    logger.info(
                        "[job %s] cancellation acknowledged while waiting for profile slot (%s)",
                        job_id,
                        source,
                    )
                    await job_store.mark_cancelled(job_id)
                    raise JobCancellationRequested()

        if await job_store.is_cancellation_requested(job_id):
            logger.info(
                "[job %s] cancellation acknowledged immediately after profile slot acquire (%s)",
                job_id,
                source,
            )
            await job_store.mark_cancelled(job_id)
            semaphore.release()
            acquired = False
            raise JobCancellationRequested()

        wait_ms = int((time.monotonic() - wait_started) * 1000)
        logger.info("[job %s] acquired profile slot (%s) queue_wait_ms=%d",
                    job_id, source, wait_ms)
        yield
    finally:
        if acquired:
            semaphore.release()
            logger.info("[job %s] released profile slot (%s)", job_id, source)


async def _persist_run(
    user_id: str,
    result: SchemaAssessment,
    *,
    source_type: str,
    source_name: str,
    source_ref: dict | None,
    table_group: str | None,
    duration_ms: int | None,
) -> None:
    """Persist the assessment run to the history DB. Best-effort — never raises.

    A DB write failure must not affect the job result already in job_store.
    """
    from db.history_store import record_run  # noqa: PLC0415
    from db.session import _async_session_factory, _ensure_engine, is_configured  # noqa: PLC0415

    if not is_configured():
        return
    try:
        _ensure_engine()
        if _async_session_factory is None:
            return

        table_assessments_data = [
            {
                "table_name": ta.table_name,
                "table_group": table_group,
                "table_score": ta.overall_score,
                "tier": ta.tier,
                "dimension_scores": {d.id: d.score for d in ta.dimensions},
                "findings": [
                    {"rule_id": c.rule_id, "title": c.title, "detail": c.detail}
                    for d in ta.dimensions
                    for c in d.checks
                    if c.status == "fail"
                ],
                "strengths": [
                    {"rule_id": c.rule_id, "title": c.title}
                    for d in ta.dimensions
                    for c in d.checks
                    if c.status == "pass"
                ],
                "recommendations": ta.recommendations,
            }
            for ta in result.tables
        ]

        async with _async_session_factory() as session:
            await record_run(
                session,
                user_id=user_id,
                source_type=source_type,
                source_name=source_name,
                source_ref=source_ref,
                overall_score=result.overall_score,
                tier=result.tier,
                duration_ms=duration_ms,
                table_assessments=table_assessments_data,
                table_group=table_group,
                result_json=result.model_dump(mode="json"),
            )
            await session.commit()
        logger.info("history: persisted run for user=%s source=%s", user_id, source_name)
    except Exception as exc:
        logger.error(
            "history: record_run failed — %s (user=%s source=%s)",
            exc, user_id, source_name,
            exc_info=True,
        )


# ───────────────────────────────────────────────────────────────────────────
# Archetypes (purpose catalog)
# ───────────────────────────────────────────────────────────────────────────

@router.get("/archetypes")
async def list_archetypes(_user: CurrentUser = Depends(require_user)) -> list[dict]:
    """Return the 13 available purpose archetypes for the purpose picker."""
    from core.archetype_loader import ARCHETYPES
    return [
        {
            "id": cfg.id,
            "family": cfg.family,
            "label": cfg.label,
            "capability_floor": cfg.capability_floor,
            "gate_set": cfg.gate_set,
        }
        for cfg in ARCHETYPES.values()
    ]


# ───────────────────────────────────────────────────────────────────────────
# CSV upload (multipart, 1..N files)
# ───────────────────────────────────────────────────────────────────────────

@router.post("/csv", response_model=JobAck, status_code=202)
async def assess_csv(
    files: list[UploadFile] = File(...),
    metadata: UploadFile | None = File(None),
    purpose: str = Form(""),
    user: CurrentUser = Depends(require_user),
) -> JobAck:
    """Accept one or more CSVs and queue a profiling + scoring job.
    An optional data dictionary CSV may be uploaded as `metadata`.
    `purpose` is an archetype ID (e.g. "mcp_read"). Empty = no purpose.
    """
    if not files:
        raise HTTPException(status_code=400, detail="At least one CSV file required.")
    if len(files) > settings.max_files_per_request:
        raise HTTPException(
            status_code=400,
            detail=f"Too many files (max {settings.max_files_per_request}).",
        )

    logger.info("POST /assess/csv: %d file(s) received", len(files))

    # Read all files into memory BEFORE returning the ack — fail fast on
    # oversized uploads. Then the bytes ride along to the background worker.
    payloads: list[tuple[str, bytes]] = []
    total_bytes = 0
    for f in files:
        content = await f.read()
        if len(content) > settings.max_csv_bytes:
            raise HTTPException(
                status_code=400,
                detail=f"{f.filename}: exceeds {settings.max_csv_bytes} byte limit.",
            )
        if not content:
            raise HTTPException(status_code=400, detail=f"{f.filename}: empty file.")
        total_bytes += len(content)
        if total_bytes > settings.max_total_csv_bytes_per_request:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Total upload size exceeds "
                    f"{settings.max_total_csv_bytes_per_request} byte limit."
                ),
            )
        payloads.append((f.filename or "unnamed.csv", content))
        logger.info("  · %s: %d bytes", f.filename, len(content))

    metadata_payload: tuple[str, bytes] | None = None
    if metadata:
        meta_bytes = await metadata.read()
        if meta_bytes:
            metadata_payload = (metadata.filename or "metadata.csv", meta_bytes)
            logger.info("  · metadata: %s (%d bytes)", metadata.filename, len(meta_bytes))

    request_key = _csv_request_key(user.user_id, payloads, metadata_payload)
    job_id, status, reused = await _claim_active_job(request_key)
    if reused:
        logger.info("[job %s] duplicate CSV assessment request reused", job_id)
        return JobAck(job_id=job_id, status=status)

    logger.info("[job %s] created for CSV upload", job_id)

    # Validate purpose archetype if provided
    purpose_id = purpose.strip() if purpose else ""

    try:
        task = _spawn(_run_csv_job(job_id, payloads, metadata_payload, user.user_id, purpose_id), name=f"csv-{job_id}")
        await job_store.attach_task(job_id, task)
    except Exception:
        await _release_active_job(job_id)
        raise

    # Yield to the event loop so the task gets a chance to start before we
    # return. Without this, the task may not be scheduled until the next
    # event loop iteration — which in some test/server setups doesn't
    # happen until the next incoming request.
    await asyncio.sleep(0)

    logger.info("[job %s] scheduled, returning JobAck", job_id)
    return JobAck(job_id=job_id, status="pending")


async def _run_csv_job(
    job_id: str,
    payloads: list[tuple[str, bytes]],
    metadata_payload: tuple[str, bytes] | None = None,
    user_id: str = "",
    purpose_id: str = "",
) -> None:
    """Background worker: profile each CSV → score → store."""
    logger.info("[job %s] _run_csv_job entered with %d payload(s)", job_id, len(payloads))
    try:
        await job_store.mark_running(job_id, progress=5)
        await job_store.update_progress(job_id, 5, phase="profiling")
        logger.info("[job %s] marked running", job_id)

        if await _stop_if_cancellation_requested(job_id):
            return

        profiles: list[TableProfile] = []
        n = len(payloads)

        async with _profile_slot(job_id, "csv"):
            for i in range(n):
                name, content = payloads[i]
                logger.info("[job %s] parsing file %d/%d: %s (%d bytes)",
                            job_id, i + 1, n, name, len(content))
                # Release bytes immediately after handing to parser —
                # avoids holding all file contents in memory simultaneously.
                payloads[i] = (name, b"")
                try:
                    profile = await asyncio.to_thread(_parser.parse, name, content)
                    del content  # free before next iteration
                    profiles.append(profile)
                    logger.info("[job %s] parsed %s: %d rows × %d cols",
                                job_id, name, profile.row_count, profile.column_count)
                except CSVParseError as exc:
                    logger.warning("[job %s] failed to parse %s: %s", job_id, name, exc)
                    continue

                pct = 10 + int(((i + 1) / n) * 70)  # 10-80% during profiling
                await job_store.update_progress(job_id, pct)

                if await _stop_if_cancellation_requested(job_id):
                    return

        if not profiles:
            logger.warning("[job %s] no parseable files", job_id)
            await job_store.mark_failed(
                job_id, "NO_PARSEABLE_FILES",
                "None of the uploaded files could be parsed as CSV.",
            )
            return

        logger.info("[job %s] scoring %d profile(s)", job_id, len(profiles))

        # Attach metadata to profiles BEFORE scoring so rules can access it.
        meta_profile = None
        if metadata_payload:
            meta_name, meta_bytes = metadata_payload
            try:
                meta_profile = _metadata_parser.parse(meta_bytes, meta_name)
                logger.info("[job %s] metadata parsed: %d entries, %.1f%% coverage",
                            job_id, meta_profile.total_columns,
                            meta_profile.coverage_pct)
                # Attach entries to matching profiles by table_name (or all if no table_name)
                for p in profiles:
                    p_stem = os.path.splitext(p.name)[0].lower().strip()
                    matching = [
                        e for e in meta_profile.entries
                        if not e.table_name
                        or os.path.splitext(e.table_name)[0].lower().strip() == p_stem
                    ]
                    # Single-table fallback: user uploaded one CSV + one dictionary
                    if not matching and len(profiles) == 1:
                        matching = list(meta_profile.entries)
                    if matching:
                        p.metadata_entries = matching
                        logger.info("[job %s] attached %d metadata entries to %s",
                                    job_id, len(matching), p.name)
                    else:
                        logger.warning("[job %s] no metadata entries matched profile %s (stem=%s). "
                                       "Entry table_names: %s",
                                       job_id, p.name, p_stem,
                                       [e.table_name for e in meta_profile.entries[:5]])
            except MetadataParseError as exc:
                logger.warning("[job %s] metadata parse failed: %s", job_id, exc)

        if await _stop_if_cancellation_requested(job_id):
            return

        await job_store.update_progress(job_id, 85, phase="scoring")
        result = await asyncio.to_thread(_engine.score_schema, profiles)

        if meta_profile:
            result.metadata_profile = meta_profile

        # v3: Capability measurement + verdict
        result = _attach_capabilities(result, profiles, purpose_id)

        # Phase B: Shadow annotator (runs but doesn't affect scores)
        from config import settings as _settings
        if _settings.annotator_mode == "shadow":
            from llm.annotator import annotate as _annotate
            ann_results = []
            for _p in profiles:
                ann = await _annotate(_p)
                ann_results.append(ann.model_dump())
            result = result.model_copy(update={"annotator_claims": ann_results})

        if await _stop_if_cancellation_requested(job_id):
            return

        await job_store.update_progress(job_id, 92, phase="ai_reading")
        result = await llm_advise(result)
        logger.info("[job %s] advisor done — llm_used=%s reason=%s",
                    job_id, result.llm.used, result.llm.fallback_reason)

        # Evidence narrator — enriches check detail text (additive, never mutates scores)
        result = await _enrich_evidence(result)

        if await _stop_if_cancellation_requested(job_id):
            return

        await job_store.mark_done(job_id, result)
        logger.info("[job %s] DONE — overall=%d tier=%s",
                    job_id, result.overall_score, result.tier)

        if user_id:
            source_name = payloads[0][0] if len(payloads) == 1 else f"{len(payloads)} files"
            await _persist_run(
                user_id, result,
                source_type="csv",
                source_name=source_name,
                source_ref=None,
                table_group=None,
                duration_ms=None,
            )

    except Exception as exc:  # noqa: BLE001
        logger.exception("[job %s] CRASHED", job_id)
        await job_store.mark_failed(job_id, "INTERNAL_ERROR", str(exc))
    except JobCancellationRequested:
        return
    except asyncio.CancelledError:
        logger.info("[job %s] CANCELLED", job_id)
        await job_store.mark_cancelled(job_id)
        return
    finally:
        await _release_active_job(job_id)


# ───────────────────────────────────────────────────────────────────────────
# DB assessment (creds + selected tables)
# ───────────────────────────────────────────────────────────────────────────

@router.post("/db", response_model=JobAck, status_code=202)
async def assess_db(
    req: str = Form(...),
    metadata: UploadFile | None = File(None),
    purpose: str = Form(""),
    user: CurrentUser = Depends(require_user),
) -> JobAck:
    """Queue a job that connects, samples each selected table, and scores.
    `req` is a JSON-encoded AssessDBRequest. An optional data dictionary CSV
    may be uploaded as `metadata`. `purpose` is an archetype ID.
    """
    try:
        req_obj = AssessDBRequest.model_validate(json.loads(req))
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid request body: {exc}") from exc

    if not req_obj.tables:
        raise HTTPException(status_code=400, detail="No tables selected for assessment.")

    logger.info("POST /assess/db: schema=%s tables=%d",
                req_obj.schema_name, len(req_obj.tables))

    metadata_payload: tuple[str, bytes] | None = None
    if metadata:
        meta_bytes = await metadata.read()
        if meta_bytes:
            metadata_payload = (metadata.filename or "metadata.csv", meta_bytes)
            logger.info("  · metadata: %s (%d bytes)", metadata.filename, len(meta_bytes))

    request_key = _db_request_key(user.user_id, req_obj, metadata_payload)
    job_id, status, reused = await _claim_active_job(request_key)
    if reused:
        logger.info("[job %s] duplicate DB assessment request reused", job_id)
        return JobAck(job_id=job_id, status=status)

    logger.info("[job %s] created for DB assessment", job_id)
    purpose_id = purpose.strip() if purpose else ""

    try:
        task = _spawn(_run_db_job(job_id, req_obj, metadata_payload, user.user_id, purpose_id), name=f"db-{job_id}")
        await job_store.attach_task(job_id, task)
    except Exception:
        await _release_active_job(job_id)
        raise
    await asyncio.sleep(0)

    logger.info("[job %s] scheduled, returning JobAck", job_id)
    return JobAck(job_id=job_id, status="pending")


async def _run_db_job(
    job_id: str,
    req: AssessDBRequest,
    metadata_payload: tuple[str, bytes] | None = None,
    user_id: str = "",
    purpose_id: str = "",
) -> None:
    logger.info("[job %s] _run_db_job entered, %d tables to profile",
                job_id, len(req.tables))
    try:
        await job_store.mark_running(job_id, progress=5)
        await job_store.update_progress(job_id, 5, phase="profiling")
        logger.info("[job %s] marked running, beginning DB introspection", job_id)

        if await _stop_if_cancellation_requested(job_id):
            return

        try:
            cancel_event = await job_store.get_cancel_event(job_id)
            async with _profile_slot(job_id, "db"):
                profiles = await _introspector.profile_tables(
                    req.credentials, req.schema_name, req.tables, cancel_event=cancel_event,
                )
                logger.info("[job %s] profiled %d table(s)", job_id, len(profiles))
        except DBConnectionError as exc:
            logger.warning(
                "[job %s] DB error: %s (%s) | description=%s",
                job_id,
                exc.code,
                exc.detail,
                exc.description,
            )
            await job_store.mark_failed(job_id, exc.code, exc.detail, exc.description)
            return

        if await _stop_if_cancellation_requested(job_id):
            return

        if not profiles:
            logger.warning("[job %s] no profiles produced", job_id)
            await job_store.mark_failed(
                job_id, "NO_TABLES_PROFILED",
                "Could not profile any of the requested tables.",
            )
            return

        # Attach metadata to profiles BEFORE scoring.
        meta_profile = None
        if metadata_payload:
            meta_name, meta_bytes = metadata_payload
            try:
                meta_profile = _metadata_parser.parse(meta_bytes, meta_name)
                logger.info("[job %s] metadata parsed: %d entries, %.1f%% coverage",
                            job_id, meta_profile.total_columns,
                            meta_profile.coverage_pct)
                for p in profiles:
                    p_stem = os.path.splitext(p.name)[0].lower().strip()
                    matching = [
                        e for e in meta_profile.entries
                        if not e.table_name
                        or os.path.splitext(e.table_name)[0].lower().strip() == p_stem
                    ]
                    if not matching and len(profiles) == 1:
                        matching = list(meta_profile.entries)
                    if matching:
                        p.metadata_entries = matching
            except MetadataParseError as exc:
                logger.warning("[job %s] metadata parse failed: %s", job_id, exc)

        if await _stop_if_cancellation_requested(job_id):
            return

        await job_store.update_progress(job_id, 85, phase="scoring")
        result = await asyncio.to_thread(_engine.score_schema, profiles)

        if meta_profile:
            result.metadata_profile = meta_profile

        # v3: Capability measurement + verdict
        result = _attach_capabilities(result, profiles, purpose_id)

        # Phase B: Shadow annotator (runs but doesn't affect scores)
        from config import settings as _settings
        if _settings.annotator_mode == "shadow":
            from llm.annotator import annotate as _annotate
            ann_results = []
            for _p in profiles:
                ann = await _annotate(_p)
                ann_results.append(ann.model_dump())
            result = result.model_copy(update={"annotator_claims": ann_results})

        if await _stop_if_cancellation_requested(job_id):
            return

        await job_store.update_progress(job_id, 92, phase="ai_reading")
        result = await llm_advise(result)
        logger.info("[job %s] advisor done — llm_used=%s reason=%s",
                    job_id, result.llm.used, result.llm.fallback_reason)

        # Evidence narrator — enriches check detail text (additive, never mutates scores)
        result = await _enrich_evidence(result)

        if await _stop_if_cancellation_requested(job_id):
            return

        await job_store.mark_done(job_id, result)
        logger.info("[job %s] DONE — overall=%d tier=%s",
                    job_id, result.overall_score, result.tier)

        if user_id:
            await _persist_run(
                user_id, result,
                source_type="db",
                source_name=req.schema_name,
                source_ref={
                    "engine": req.credentials.engine,
                    "host": req.credentials.host,
                    "port": req.credentials.port,
                    "database": req.credentials.database,
                    "schema": req.schema_name,
                },
                table_group=req.schema_name,
                duration_ms=None,
            )

    except Exception as exc:  # noqa: BLE001
        logger.exception("[job %s] CRASHED", job_id)
        await job_store.mark_failed(job_id, "INTERNAL_ERROR", str(exc))
    except JobCancellationRequested:
        return
    except asyncio.CancelledError:
        logger.info("[job %s] CANCELLED", job_id)
        await job_store.mark_cancelled(job_id)
        return
    finally:
        await _release_active_job(job_id)


# ───────────────────────────────────────────────────────────────────────────
# Job polling
# ───────────────────────────────────────────────────────────────────────────

@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job(
    job_id: str,
    _user: CurrentUser = Depends(require_user),
) -> JobStatusResponse:
    """Poll a job's status. Returns 404 if the job_id is unknown
    (either invalid or evicted after TTL)."""
    job = await job_store.get(job_id)
    if not job:
        raise HTTPException(
            status_code=404,
            detail={"detail": "Job not found or expired.", "code": "JOB_NOT_FOUND"},
        )
    return job


@router.post("/jobs/{job_id}/cancel", response_model=JobStatusResponse)
async def cancel_job(
    job_id: str,
    _user: CurrentUser = Depends(require_user),
) -> JobStatusResponse:
    """Request cancellation for an active assessment job.

    Cancellation is cooperative: the job moves to `cancelling`, finishes its
    current blocking unit of work, then transitions to `cancelled` once the
    worker acknowledges the request.
    """
    job, cancel_requested = await job_store.request_cancel(job_id)
    if not job:
        raise HTTPException(
            status_code=404,
            detail={"detail": "Job not found or expired.", "code": "JOB_NOT_FOUND"},
        )

    if cancel_requested:
        logger.info("[job %s] cancellation requested", job_id)
    elif job.status == "cancelling":
        logger.info("[job %s] cancellation already in progress", job_id)
    else:
        logger.info("[job %s] cancel requested after terminal status=%s", job_id, job.status)

    return job

# ───────────────────────────────────────────────────────────────────────────
# Re-score after attestation approval
# ───────────────────────────────────────────────────────────────────────────

class RescoreRequest(_BaseModel):
    assessment: SchemaAssessment
    approved_rule_ids: list[str] = []
    acknowledged_blocker_ids: list[str] = []
    dismissed_rule_ids: list[str] = []


@router.post("/rescore", response_model=SchemaAssessment)
async def rescore(
    body: RescoreRequest,
    _user: CurrentUser = Depends(require_user),
) -> SchemaAssessment:
    """Re-compute the assessment with approved deferred items resolved to pass,
    acknowledged blockers removed from gating, and dismissed findings resolved
    to pass (only for DISMISSIBLE_RULES).

    Called by the FE when a user makes attestation decisions. The scorer
    reclassifies rules and recomputes gating + scores.
    Deterministic: same inputs → same result.
    """
    return rescore_with_approvals(
        body.assessment, body.approved_rule_ids, body.acknowledged_blocker_ids,
        body.dismissed_rule_ids,
    )


# ───────────────────────────────────────────────────────────────────────────
# Purpose recompute (client switches purpose on Dashboard)
# ───────────────────────────────────────────────────────────────────────────

class RecomputePurposeRequest(_BaseModel):
    assessment: SchemaAssessment
    purpose_id: str = ""


@router.post("/recompute-purpose")
async def recompute_purpose(
    body: RecomputePurposeRequest,
    _user: CurrentUser = Depends(require_user),
) -> dict:
    """Re-apply archetype floors and recompute verdict for a new purpose.

    The measured capability levels do NOT change — only `required`, `gap`,
    and the purpose_verdict are recalculated. Also generates a 2-sentence
    purpose-specific executive summary (LLM with fallback).
    """
    from core.archetype_loader import ARCHETYPES
    from core.verdict import compute_verdict
    from llm.purpose_narrator import generate_purpose_summary

    caps = body.assessment.capabilities or []
    if not caps:
        raise HTTPException(400, "Assessment has no capabilities to recompute.")

    purpose_id = body.purpose_id.strip()
    archetype = ARCHETYPES.get(purpose_id) if purpose_id else None

    # Reset all gaps/required, then re-apply
    for cap in caps:
        cap.required = 0
        cap.gap = False

    if archetype:
        for cap in caps:
            req = archetype.capability_floor.get(cap.id, 0)
            cap.required = req
            cap.gap = cap.level < req

    # Compute verdict using first assessed table's gated_by
    gated_by: list[str] = []
    for t in body.assessment.tables:
        if t.included:
            gated_by = t.gated_by or []
            break

    verdict = compute_verdict(caps, archetype, gated_by)
    verdict_dict = verdict.model_dump() if archetype else None

    # Generate purpose-aware summary
    purpose_label = archetype.label if archetype else "Baseline data quality"
    summary = await generate_purpose_summary(
        body.assessment, purpose_id, purpose_label, caps, verdict_dict,
    )

    return {
        "capabilities": [c.model_dump() for c in caps],
        "selected_archetype": purpose_id or None,
        "purpose_verdict": verdict_dict,
        "purpose_summary": summary,
    }


# ───────────────────────────────────────────────────────────────────────────
# Engineer Runbook (Part 2§C)
# ───────────────────────────────────────────────────────────────────────────

@router.post("/runbook")
async def generate_runbook_endpoint(
    assessment: SchemaAssessment,
    _user: CurrentUser = Depends(require_user),
) -> dict:
    """Generate an engineer-facing remediation runbook from the assessment.

    Returns both structured JSON (for the modal) and rendered markdown
    (for download). The runbook is AI-generated (advisory, tagged) and
    does not affect the score.
    """
    from core.runbook_builder import build_runbook_request
    from llm.runbook import generate_runbook_per_table, render_runbook_markdown

    request = build_runbook_request(assessment)
    output, error = await generate_runbook_per_table(request)

    if output is None:
        # Fallback: build a simple markdown from the request findings
        lines = [f"# Engineer Runbook — {request.schema_verdict}", ""]
        lines.append(f"**Score:** {request.schema_score}/100")
        if request.gated_by:
            lines.append(f"**Gates:** {', '.join(request.gated_by)}")
        lines.append("")
        for t in request.tables:
            lines.append(f"## {t.table_name}")
            for f in t.findings:
                lines.append(f"- **{f.issue}** ({f.severity}): {f.recommendation}")
            lines.append("")
        lines.append("---")
        lines.append("*Runbook generation unavailable — showing rule-based fallback.*")
        return {"markdown": "\n".join(lines), "structured": None, "error": error}

    md = render_runbook_markdown(output)
    return {"markdown": md, "structured": output.model_dump(), "error": None}
