"""
Auth Token Decoder Utility

Decodes Authorization header (Bearer token) and prints decoded JWT values.
Supports both verified and unverified token decoding with detailed logging.

Usage:
  In any endpoint, inject this as a dependency or call directly
"""

import json
import time
from typing import Any, Dict, Optional
from datetime import datetime

import jwt
from fastapi import Request, HTTPException, status
from primedata.utils.logger import get_logger

logger = get_logger(__name__)


def extract_auth_token(request: Request) -> Optional[str]:
    """
    Extract Bearer token from Authorization header.

    Args:
        request: FastAPI Request object

    Returns:
        Token string if present, None otherwise
    """
    logger.info("🔐 extract_auth_token | extracting Bearer token from Authorization header")

    auth_header = request.headers.get("Authorization", "")
    logger.debug(f"   Authorization header present: {bool(auth_header)}")

    if not auth_header:
        logger.warning("   ⚠️ No Authorization header found")
        return None

    if not auth_header.startswith("Bearer "):
        logger.warning(f"   ⚠️ Authorization header doesn't start with 'Bearer ' (got: {auth_header[:20]}...)")
        return None

    token = auth_header.replace("Bearer ", "").strip()
    logger.info(f"   ✅ Token extracted (length={len(token)})")

    return token


def decode_token_unverified(token: str) -> Optional[Dict[str, Any]]:
    """
    Decode JWT token WITHOUT verification.

    SECURITY WARNING: Only use for debugging/inspection.
    Always verify tokens in production using verify_rs256_token().

    Args:
        token: JWT token string

    Returns:
        Decoded payload dict if valid JWT, None otherwise
    """
    logger.info("🔐 decode_token_unverified | decoding token WITHOUT verification")

    try:
        payload = jwt.decode(token, options={"verify_signature": False})
        logger.info(f"   ✅ Token decoded successfully (claims count={len(payload)})")
        return payload
    except jwt.DecodeError as e:
        logger.error(f"   ❌ Failed to decode token: {e}")
        return None
    except Exception as e:
        logger.error(f"   ❌ Unexpected error: {type(e).__name__}: {e}")
        return None


def get_token_header(token: str) -> Optional[Dict[str, Any]]:
    """
    Extract and decode JWT header (without verification).

    Args:
        token: JWT token string

    Returns:
        Header dict with 'typ', 'alg', 'kid', etc., or None if invalid
    """
    logger.info("🔐 get_token_header | extracting JWT header")

    try:
        header = jwt.get_unverified_header(token)
        logger.info(f"   ✅ Header extracted (fields={list(header.keys())})")
        return header
    except jwt.DecodeError as e:
        logger.error(f"   ❌ Failed to get header: {e}")
        return None
    except Exception as e:
        logger.error(f"   ❌ Unexpected error: {type(e).__name__}: {e}")
        return None


def format_timestamp(timestamp: Optional[int]) -> str:
    """Convert Unix timestamp to readable datetime."""
    if not timestamp:
        return "N/A"
    try:
        return datetime.fromtimestamp(timestamp).isoformat()
    except:
        return f"{timestamp} (invalid)"


def print_token_details(token: str, verify: bool = False) -> Optional[Dict[str, Any]]:
    """
    Decode and print complete JWT token details.

    Args:
        token: JWT token string
        verify: If True, attempt to verify signature (requires JWKS)

    Returns:
        Decoded payload dict
    """
    print("\n" + "="*100)
    print("🔐 JWT TOKEN DETAILS")
    print("="*100)

    # Extract and print header
    print("\n📋 TOKEN HEADER:")
    header = get_token_header(token)
    if header:
        print(f"   Type: {header.get('typ', 'N/A')}")
        print(f"   Algorithm: {header.get('alg', 'N/A')}")
        print(f"   Key ID (kid): {header.get('kid', 'N/A')}")
        print(f"   Other fields: {[k for k in header.keys() if k not in ['typ', 'alg', 'kid']]}")
    else:
        print("   ❌ Failed to extract header")
        return None

    # Decode payload (without verification)
    print("\n📋 TOKEN PAYLOAD (Claims):")
    payload = decode_token_unverified(token)
    if not payload:
        print("   ❌ Failed to decode payload")
        return None

    # Print standard claims
    print(f"\n   Subject (sub): {payload.get('sub', 'N/A')}")
    print(f"   Email: {payload.get('email', 'N/A')}")
    print(f"   Name: {payload.get('name', 'N/A')}")

    # Print timestamps
    iat = payload.get('iat')
    exp = payload.get('exp')
    nbf = payload.get('nbf')

    print(f"\n   Issued At (iat): {format_timestamp(iat)}")
    print(f"   Expires At (exp): {format_timestamp(exp)}")
    print(f"   Not Before (nbf): {format_timestamp(nbf)}")

    # Check if token is expired
    if exp:
        current_time = int(time.time())
        is_expired = current_time > exp
        time_remaining = exp - current_time
        status_icon = "❌" if is_expired else "✅"
        print(f"\n   {status_icon} Token Status: {'EXPIRED' if is_expired else 'VALID'}")
        if not is_expired:
            print(f"   ⏳ Expires in: {time_remaining} seconds ({time_remaining/3600:.2f} hours)")
        else:
            print(f"   ⏳ Expired: {-time_remaining} seconds ago")

    # Print issuer and audience
    print(f"\n   Issuer (iss): {payload.get('iss', 'N/A')}")
    print(f"   Audience (aud): {payload.get('aud', 'N/A')}")

    # Print roles and scopes if present
    if 'roles' in payload:
        print(f"   Roles: {payload.get('roles', [])}")
    if 'scope' in payload:
        print(f"   Scopes: {payload.get('scope', 'N/A')}")
    if 'permissions' in payload:
        print(f"   Permissions: {payload.get('permissions', [])}")

    # Print all other claims
    standard_claims = {'sub', 'email', 'name', 'iat', 'exp', 'nbf', 'iss', 'aud', 'roles', 'scope', 'permissions'}
    other_claims = {k: v for k, v in payload.items() if k not in standard_claims}

    if other_claims:
        print(f"\n   Other Claims:")
        for key, value in other_claims.items():
            if isinstance(value, (dict, list)):
                print(f"      {key}: {json.dumps(value, indent=8)}")
            else:
                print(f"      {key}: {value}")

    print("\n" + "="*100 + "\n")

    return payload


def decode_request_token(request: Request) -> Optional[Dict[str, Any]]:
    """
    Extract Bearer token from request and decode it.
    Prints all details to logs.

    Args:
        request: FastAPI Request object

    Returns:
        Decoded payload dict or None
    """
    logger.info("🔐 decode_request_token | processing Authorization header")

    token = extract_auth_token(request)
    if not token:
        logger.error("   ❌ No valid token found in Authorization header")
        return None

    payload = print_token_details(token)
    return payload


# Middleware-compatible version for app.py
def auth_token_debug_middleware_handler(request: Request) -> None:
    """
    Call this in middleware to decode and log auth tokens.

    Usage in middleware:
        async def middleware(request: Request, call_next):
            auth_token_debug_middleware_handler(request)
            response = await call_next(request)
            return response
    """
    logger.debug("🔐 Auth Token Debug Middleware | checking for Bearer token")

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.replace("Bearer ", "").strip()
        logger.info(f"📋 Found Bearer token (length={len(token)})")

        # Extract header
        try:
            header = jwt.get_unverified_header(token)
            logger.info(f"   Header: alg={header.get('alg')}, kid={header.get('kid')}, typ={header.get('typ')}")
        except Exception as e:
            logger.error(f"   ❌ Failed to extract header: {e}")

        # Extract payload (unverified)
        try:
            payload = jwt.decode(token, options={"verify_signature": False})
            logger.info(f"   Payload: sub={payload.get('sub')}, email={payload.get('email')}, aud={payload.get('aud')}")

            # Check expiration
            exp = payload.get('exp')
            if exp:
                current_time = int(time.time())
                is_expired = current_time > exp
                logger.info(f"   Status: {'EXPIRED' if is_expired else 'VALID'} (exp={exp})")
        except Exception as e:
            logger.error(f"   ❌ Failed to decode payload: {e}")


# Example: Decorator for logging decoded tokens
def with_token_logging(func):
    """
    Decorator to log decoded auth token for an endpoint.

    Usage:
        @router.get("/test")
        @with_token_logging
        async def test_endpoint(request: Request):
            return {"message": "ok"}
    """
    async def wrapper(request: Request, *args, **kwargs):
        logger.info("🔐 Endpoint called with token logging")
        payload = decode_request_token(request)
        if payload:
            logger.info(f"   User: {payload.get('sub')}")
            logger.info(f"   Email: {payload.get('email')}")
        return await func(request, *args, **kwargs)
    return wrapper
