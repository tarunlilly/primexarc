"""Runtime config endpoint — serves public MSAL identity to the frontend."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from config import settings

router = APIRouter()


@router.get("/config")
async def get_config() -> dict:
    if not settings.client_id or not settings.tenant_id:
        raise HTTPException(status_code=503, detail="Auth config not set on server")
    return {
        "clientId": settings.client_id,
        "tenantId": settings.tenant_id,
    }
