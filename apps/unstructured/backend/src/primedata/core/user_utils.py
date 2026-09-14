"""
User utility functions for handling user ID extraction in dev/prod modes.
"""

from typing import Any, Dict, Optional

from fastapi import HTTPException, Request, status

from primedata.utils.logger import get_logger
from .settings import get_settings

logger = get_logger(__name__)


def get_current_user_from_request(request: Request) -> Dict[str, Any]:
    """Extract the current user from a FastAPI request.

    Supports both header-based auth (x-user-id / x-user-email) and
    token-based auth (request.state.user set by auth middleware).

    :param request: The incoming FastAPI Request object.
    :return: Dictionary with at least 'sub', 'email', and 'name' keys.
    :raises HTTPException: 401 if no user identity can be determined.
    """
    user_id_header = request.headers.get("x-user-id")
    user_email_header = request.headers.get("x-user-email")
    user_name_header = request.headers.get("x-user-name")

    if user_id_header and user_email_header:
        logger.debug(f"get_current_user_from_request - using headers: id={user_id_header}")
        return {
            "sub": user_id_header,
            "email": user_email_header,
            "name": user_name_header or "Unknown User",
        }

    if not hasattr(request.state, "user") or not request.state.user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return request.state.user


def get_user_id(current_user: Optional[Dict[str, Any]] = None) -> str:
    """Get the current user ID from an authenticated user dictionary.

    :param current_user: Current user dictionary from authentication (may be None).
    :return: String user ID (supports both UUID and string formats like "L043910").
    :raises ValueError: If current_user is None or contains no user ID.
    """
    logger.debug(f"🔐 Extracting user ID from current_user")

    if not current_user:
        logger.error("❌ No authenticated user available")
        raise ValueError("No authenticated user available")

    # Try 'sub' first (JWT standard), then 'id' as fallback
    user_id_str = current_user.get("sub") or current_user.get("id")

    if not user_id_str:
        logger.error(f"❌ User ID not found in current_user. Keys: {list(current_user.keys())}")
        raise ValueError("User ID not found in current_user (neither 'sub' nor 'id' present)")

    result = str(user_id_str)
    logger.debug(f"✅ User ID extracted: {result}")
    return result


def get_user_id_safe(current_user: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """Get the current user ID safely, returning None if not available.

    Useful for optional user tracking where authentication is not required.

    :param current_user: Current user dictionary from authentication (may be None).
    :return: String user ID, or None if not available.
    """
    logger.debug(f"🔐 Safely extracting user ID from current_user")
    try:
        result = get_user_id(current_user)
        logger.debug(f"✅ User ID extracted safely: {result}")
        return result
    except (ValueError, TypeError) as e:
        logger.debug(f"⚠️ User ID extraction failed: {e}")
        return None
