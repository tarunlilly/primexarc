"""ARC backend — FastAPI entrypoint.

Run locally:
    uvicorn main:app --reload --port 8000

Production:
    uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1

NOTE: --workers must be 1 until JobStore moves to Redis. Multiple workers
would each have their own in-memory store, breaking job polling.
"""
from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api import admin, assess, config, connect, export, health, history, support
from config import settings
from core.job_store import job_store

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("arc")

_static_dir = Path(os.getenv("STATIC_DIR", ""))


# ─── Periodic background sweeper for expired jobs ─────────────────────────
async def _sweep_loop() -> None:
    """Drop completed jobs older than TTL every 60 seconds."""
    while True:
        try:
            await asyncio.sleep(60)
            removed = await job_store.sweep_expired()
            if removed:
                logger.info("Evicted %d expired jobs", removed)
        except asyncio.CancelledError:
            break
        except Exception:  # noqa: BLE001
            logger.exception("job sweeper error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    sweeper = asyncio.create_task(_sweep_loop())
    logger.info("ARC backend startup complete · debug=%s", settings.debug)
    try:
        yield
    finally:
        from llm.client import close_http_client

        sweeper.cancel()
        try:
            await sweeper
        except asyncio.CancelledError:
            pass
        await close_http_client()


# ─── App ──────────────────────────────────────────────────────────────────
app = FastAPI(
    title="ARC Evaluator",
    description="Internal Lilly tool. Evaluates datasets against 9 readiness dimensions.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# /api/config — unauthenticated; serves public MSAL identity to SPA
app.include_router(config.router,  prefix="/api")

# All routes under /api/v1
PREFIX = "/api/v1"
app.include_router(health.router,   prefix=PREFIX)
app.include_router(connect.router,  prefix=PREFIX)
app.include_router(assess.router,   prefix=PREFIX)
app.include_router(support.router,  prefix=PREFIX)
app.include_router(history.router,  prefix=PREFIX)
app.include_router(admin.router,    prefix=PREFIX)
app.include_router(export.router,   prefix=PREFIX)


@app.get("/health", include_in_schema=False)
async def health_probe():
    return {"status": "ok"}


@app.get("/")
async def root():
    if _static_dir.is_dir():
        return FileResponse(str(_static_dir / "index.html"))
    return {
        "name": "ARC Evaluator",
        "docs": "/docs",
    }


# ─── Static file serving (combined Docker image only) ────────────────────
if _static_dir.is_dir():
    _assets = _static_dir / "assets"
    if _assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(_assets)), name="static-assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def _spa_fallback(path: str):
        file_path = _static_dir / path
        if file_path.is_file() and ".." not in path:
            return FileResponse(str(file_path))
        return FileResponse(str(_static_dir / "index.html"))
