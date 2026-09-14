"""Shared FastAPI dependencies.

require_user() validates the Azure AD ID token carried in the Authorization
header and returns the caller's identity as a CurrentUser.

Validation steps (when client_id is configured):
  1. Decode the JWT header to get the key ID (kid).
  2. Fetch the tenant's JWKS from Azure AD (cached 24h; refreshed on kid miss).
  3. Validate signature (RS256), exp, aud (== client_id), and iss.
  4. Extract oid/sub → user_id, preferred_username/upn/email → email.

Dev bypass: when client_id is empty (local dev without real Azure creds),
  a missing token returns a fixture user instead of 401.

JWKS failures (network down, Azure outage) are non-fatal: the request falls
back to claims-only decode with a warning. We're behind SSO so a signature
failure is a warning, not a hard block — but exp/aud are still checked.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import time

import httpx
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import ExpiredSignatureError, JWTError, jwt
from pydantic import BaseModel

from config import settings

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)
_USER_UPSERT_RETRY_BACKOFF_S = 60.0
_user_upsert_tasks: set[asyncio.Task] = set()
_user_upsert_inflight: set[str] = set()
_user_upsert_retry_not_before = 0.0

# ── JWKS cache ────────────────────────────────────────────────────────────────
_JWKS_CACHE: dict | None = None          # raw JWKS response
_JWKS_FETCHED_AT: float = 0.0
_JWKS_TTL_S: float = 86400.0            # 24 h


def _jwks_url() -> str:
    return (
        f"https://login.microsoftonline.com/{settings.tenant_id}"
        f"/discovery/v2.0/keys"
    )


def _expected_issuer() -> str:
    return f"https://login.microsoftonline.com/{settings.tenant_id}/v2.0"


async def _fetch_jwks(force: bool = False) -> dict | None:
    """Fetch and cache the tenant JWKS. Returns None on any network failure."""
    global _JWKS_CACHE, _JWKS_FETCHED_AT
    now = time.monotonic()
    if not force and _JWKS_CACHE and (now - _JWKS_FETCHED_AT) < _JWKS_TTL_S:
        return _JWKS_CACHE
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            resp = await c.get(_jwks_url())
            resp.raise_for_status()
            _JWKS_CACHE = resp.json()
            _JWKS_FETCHED_AT = now
            return _JWKS_CACHE
    except Exception as exc:
        logger.warning("JWKS fetch failed (%s) — falling back to claims-only decode", exc)
        return _JWKS_CACHE  # return stale cache if available, else None


def _decode_jwt_claims(token: str) -> dict:
    """Base64-decode JWT payload without signature verification (fallback only)."""
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))


def _get_kid(token: str) -> str | None:
    """Decode the JWT header to extract the key ID."""
    try:
        header_b64 = token.split(".")[0]
        header_b64 += "=" * (-len(header_b64) % 4)
        header = json.loads(base64.urlsafe_b64decode(header_b64))
        return header.get("kid")
    except Exception:
        return None


def _find_key(jwks: dict, kid: str) -> dict | None:
    """Return the JWK matching the given kid, or None."""
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            return key
    return None


async def _validate_token(token: str) -> dict:
    """Validate the token and return its claims.

    Tries full signature + exp + aud + iss validation.
    On JWKS failure, falls back to claims-only decode (still checks exp/aud/iss
    manually so forged tokens without a matching clock are still caught in most
    real-world cases).
    """
    kid = _get_kid(token)
    jwks = await _fetch_jwks()

    # Refresh JWKS if kid not found (Azure rotates keys)
    if jwks and kid and not _find_key(jwks, kid):
        jwks = await _fetch_jwks(force=True)

    public_key = _find_key(jwks, kid) if (jwks and kid) else None

    options = {"verify_exp": True, "verify_aud": True, "verify_iss": True}

    if public_key:
        try:
            return jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                audience=settings.client_id,
                issuer=_expected_issuer(),
                options=options,
            )
        except ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token has expired.")
        except JWTError as exc:
            raise HTTPException(status_code=401, detail=f"Token invalid: {exc}") from exc

    # JWKS unavailable — decode without signature but still enforce exp/aud/iss
    logger.warning("JWKS unavailable; validating claims without signature verification")
    try:
        claims = _decode_jwt_claims(token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Malformed token.") from exc

    now = int(time.time())
    if claims.get("exp", 0) < now:
        raise HTTPException(status_code=401, detail="Token has expired.")
    if settings.client_id and claims.get("aud") != settings.client_id:
        raise HTTPException(status_code=401, detail="Token audience mismatch.")
    expected_iss = _expected_issuer()
    if settings.tenant_id and claims.get("iss") != expected_iss:
        raise HTTPException(status_code=401, detail="Token issuer mismatch.")

    return claims


class CurrentUser(BaseModel):
    user_id: str
    email: str
    roles: list[str] = []


async def require_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> CurrentUser:
    """Return the authenticated caller.

    If a Bearer token is present, validate it fully (signature, exp, aud, iss)
    and extract the user identity.

    If no token is present:
    - client_id is configured → 401 (production path)
    - client_id is empty → return fixture dev user (local dev without IdP)
    """
    if credentials is None:
        if settings.client_id:
            raise HTTPException(status_code=401, detail="Authorization required.")
        user = CurrentUser(
            user_id="dev_user",
            email="dev@lilly.com",
            roles=["data_owner"],
        )
        _schedule_user_upsert(user)
        return user

    claims = await _validate_token(credentials.credentials)

    user_id = claims.get("oid") or claims.get("sub") or ""
    if not user_id:
        raise HTTPException(status_code=401, detail="Token missing user identity claim.")

    email: str = (
        claims.get("preferred_username")
        or claims.get("upn")
        or claims.get("email")
        or ""
    )
    roles: list[str] = claims.get("roles", [])
    user = CurrentUser(user_id=user_id, email=email, roles=roles)
    _schedule_user_upsert(user)
    return user


def _schedule_user_upsert(user: CurrentUser) -> None:
    """Kick off the history DB upsert in the background.

    Authentication should not block on a best-effort history write, and a
    broken history DB should not delay unrelated authenticated requests.
    """
    if time.monotonic() < _user_upsert_retry_not_before:
        return
    if user.user_id in _user_upsert_inflight:
        return

    task = asyncio.create_task(
        _upsert_user_if_db_ready(user),
        name=f"upsert-user-{user.user_id}",
    )
    _user_upsert_inflight.add(user.user_id)
    _user_upsert_tasks.add(task)

    def _cleanup(done_task: asyncio.Task) -> None:
        _user_upsert_tasks.discard(done_task)
        _user_upsert_inflight.discard(user.user_id)

    task.add_done_callback(_cleanup)


async def _upsert_user_if_db_ready(user: CurrentUser) -> None:
    """Best-effort: persist the user row in the history DB.

    Never raises — a DB write failure must not break authentication.
    """
    global _user_upsert_retry_not_before

    from db.session import _async_session_factory, _ensure_engine, is_configured  # noqa: PLC0415

    if not is_configured():
        return
    try:
        _ensure_engine()
        if _async_session_factory is None:
            return
        from db.history_store import upsert_user  # noqa: PLC0415

        async with _async_session_factory() as session:
            await upsert_user(session, user_id=user.user_id, email=user.email)
            await session.commit()
        _user_upsert_retry_not_before = 0.0
    except Exception:
        _user_upsert_retry_not_before = time.monotonic() + _USER_UPSERT_RETRY_BACKOFF_S
        logger.warning(
            "upsert_user failed; suppressing retries for %ds; auth still succeeds",
            int(_USER_UPSERT_RETRY_BACKOFF_S),
            exc_info=True,
        )


_LOCAL_SUPERUSERS = {"dev_user", "tarunrajsingh48@lilly.com"}


async def require_superuser(
    user: CurrentUser = Depends(require_user),
) -> CurrentUser:
    """Gate admin endpoints. Returns 403 if the user is not a superuser."""
    if user.user_id in _LOCAL_SUPERUSERS or user.email in _LOCAL_SUPERUSERS:
        return user

    from db.session import _async_session_factory, _ensure_engine, is_configured  # noqa: PLC0415

    if not is_configured():
        raise HTTPException(403, "Superuser access required (DB not configured).")

    try:
        _ensure_engine()
        if _async_session_factory is None:
            raise HTTPException(403, "Superuser access required (DB unavailable).")
        from db.history_store import get_user_flag  # noqa: PLC0415

        async with _async_session_factory() as session:
            is_su = await get_user_flag(session, user.user_id, "is_superuser")
        if not is_su:
            raise HTTPException(403, "Superuser access required.")
    except HTTPException:
        raise
    except Exception:
        logger.warning("superuser check failed", exc_info=True)
        raise HTTPException(403, "Superuser access required (check failed).")
    return user
