"""DB connection probing and schema introspection.

Both endpoints are SYNCHRONOUS (request/response, ≤ 10-30s). They do not
spawn jobs — they are short, interactive operations the user runs while
filling out the DB credentials form.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from core.db_introspector import DBConnectionError, DBIntrospector
from core.models import (
    ConnectionTestRequest,
    ConnectionTestResponse,
    ListTablesRequest,
    ListTablesResponse,
)
from dependencies import CurrentUser, require_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/connect", tags=["connect"])
_introspector = DBIntrospector()


def _mask(value: str) -> str:
    """Return first 3 chars + *** to avoid leaking host/username in logs."""
    return value[:3] + "***" if len(value) > 3 else "***"


@router.post("/test", response_model=ConnectionTestResponse)
async def test_connection(
    req: ConnectionTestRequest,
    _user: CurrentUser = Depends(require_user),
) -> ConnectionTestResponse:
    """Attempt a connection within the configured timeout (default 10s).
    Always returns 200; the `ok` field tells the caller whether it succeeded.
    Failure codes: CONNECTION_TIMEOUT / AUTH_FAILED / HOST_UNREACHABLE /
    UNKNOWN_ERROR.
    """
    logger.info("connect.test engine=%s host=%s db=%s user=%s",
                req.credentials.engine, _mask(req.credentials.host),
                req.credentials.database, _mask(req.credentials.username))
    ok, code, detail, description, elapsed = await _introspector.test_connection(req.credentials)
    if not ok:
        logger.warning(
            "connect.test failed engine=%s code=%s detail=%s description=%s",
            req.credentials.engine,
            code,
            detail,
            description,
        )
    return ConnectionTestResponse(
        ok=ok,
        code=code,
        detail=detail,
        description=description,
        elapsed_ms=elapsed,
    )


@router.post("/tables", response_model=ListTablesResponse)
async def list_tables(
    req: ListTablesRequest,
    _user: CurrentUser = Depends(require_user),
) -> ListTablesResponse:
    """List tables in a schema. Used by the wizard's table-selection step.
    Raises 503 on connection failure (caller already passed /test, so a
    failure here indicates an environment issue worth surfacing).
    """
    try:
        tables = await _introspector.list_tables(req.credentials, req.schema_name)
    except DBConnectionError as exc:
        logger.warning(
            "connect.tables failed (%s): %s | description=%s",
            exc.code,
            exc.detail,
            exc.description,
        )
        raise HTTPException(
            status_code=503,
            detail={"detail": exc.detail, "code": exc.code, "description": exc.description},
        ) from exc
    return ListTablesResponse(schema=req.schema_name, tables=tables)
