"""
Example: Auth Token Decoder Endpoint

This demonstrates how to use the auth_token_decoder utility
to log and decode Bearer tokens in any endpoint.
"""

from fastapi import APIRouter, Request, Depends
from primedata.core.auth_token_decoder import (
    decode_request_token,
    print_token_details,
    extract_auth_token
)
from primedata.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/debug", tags=["Debug"])


@router.get("/token/decode")
async def decode_token_endpoint(request: Request):
    """
    DEBUG ENDPOINT: Decode and return auth token details.

    This endpoint extracts the Authorization header, decodes the JWT,
    and returns all token details for debugging purposes.

    **SECURITY WARNING:** Only enable in development!

    Usage:
        curl -X GET "http://localhost:8000/api/v1/debug/token/decode" \\
          -H "Authorization: Bearer <your_token>"
    """
    logger.info("🔐 GET /api/v1/debug/token/decode | Decoding auth token")

    # Extract token
    token = extract_auth_token(request)
    if not token:
        logger.warning("   ❌ No valid token found")
        return {
            "success": False,
            "error": "No Bearer token found in Authorization header"
        }

    # Decode and print details (logs to console)
    print("\n")  # Add newline for readability
    payload = print_token_details(token)

    if not payload:
        logger.error("   ❌ Failed to decode token")
        return {
            "success": False,
            "error": "Failed to decode token"
        }

    # Return decoded details
    return {
        "success": True,
        "token_decoded": True,
        "payload": payload,
        "header_info": {
            "Authorization header": "Present ✅",
            "Token type": "Bearer",
            "Token length": len(token)
        }
    }


@router.post("/token/verify-and-log")
async def verify_and_log_token(request: Request):
    """
    DEBUG ENDPOINT: Verify token and log comprehensive details.

    This endpoint:
    1. Extracts the Bearer token
    2. Decodes it (unverified)
    3. Prints detailed information to logs
    4. Returns formatted response

    Usage:
        curl -X POST "http://localhost:8000/api/v1/debug/token/verify-and-log" \\
          -H "Authorization: Bearer <your_token>"
    """
    logger.info("🔐 POST /api/v1/debug/token/verify-and-log | Verifying and logging token")

    payload = decode_request_token(request)

    if not payload:
        return {
            "success": False,
            "error": "Failed to extract or decode token"
        }

    # Extract key information
    user_id = payload.get('sub')
    email = payload.get('email')
    roles = payload.get('roles', [])
    exp = payload.get('exp')

    return {
        "success": True,
        "user": {
            "id": user_id,
            "email": email,
            "name": payload.get('name')
        },
        "authorization": {
            "roles": roles,
            "scopes": payload.get('scope', '').split() if payload.get('scope') else [],
            "permissions": payload.get('permissions', [])
        },
        "token_info": {
            "issuer": payload.get('iss'),
            "audience": payload.get('aud'),
            "issued_at": payload.get('iat'),
            "expires_at": payload.get('exp'),
            "not_before": payload.get('nbf')
        },
        "raw_payload": payload
    }


@router.get("/token/info")
async def get_token_info(request: Request):
    """
    DEBUG ENDPOINT: Get quick token info summary.

    This endpoint returns a condensed summary of token claims.

    Usage:
        curl -X GET "http://localhost:8000/api/v1/debug/token/info" \\
          -H "Authorization: Bearer <your_token>"
    """
    logger.info("🔐 GET /api/v1/debug/token/info | Getting token info summary")

    payload = decode_request_token(request)

    if not payload:
        return {"error": "No valid token"}

    import time
    current_time = int(time.time())
    exp = payload.get('exp')
    is_expired = exp and current_time > exp

    return {
        "user_id": payload.get('sub'),
        "email": payload.get('email'),
        "name": payload.get('name'),
        "roles": payload.get('roles', []),
        "issuer": payload.get('iss'),
        "audience": payload.get('aud'),
        "token_status": "EXPIRED" if is_expired else "VALID",
        "expires_at": payload.get('exp'),
        "time_until_expiry_seconds": exp - current_time if exp else None
    }


# Middleware version - add to app.py lifespan or main middleware
def auth_token_debug_middleware():
    """
    Middleware to debug auth tokens on every request.

    Usage in app.py:
        from primedata.core.auth_token_decoder import auth_token_debug_middleware_handler

        class DebugAuthMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request: Request, call_next):
                auth_token_debug_middleware_handler(request)
                response = await call_next(request)
                return response

        # Add after CORS middleware:
        app.add_middleware(DebugAuthMiddleware)
    """
    from starlette.middleware.base import BaseHTTPMiddleware
    from primedata.core.auth_token_decoder import auth_token_debug_middleware_handler

    class DebugAuthMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            # Log token if present
            auth_token_debug_middleware_handler(request)
            response = await call_next(request)
            return response

    return DebugAuthMiddleware
