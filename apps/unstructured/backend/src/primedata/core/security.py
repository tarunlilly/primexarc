"""
Security utilities for JWT handling and user authentication.
"""

import time
from functools import lru_cache
from typing import Any, Callable, Dict, List, Optional

import jwt
from fastapi import Depends, HTTPException, Request, status

from primedata.utils.log_utils import get_logger
from primedata.core.jwt_keys import get_jwks

logger = get_logger(__name__)
from primedata.core.settings import get_settings


@lru_cache(maxsize=1)
def get_cached_jwks() -> Dict[str, Any]:
    """Retrieve and cache the JSON Web Key Set (JWKS) used for token verification.

    :return: Dictionary containing the JWKS keys.
    """
    logger.info(f"🔐 get_cached_jwks | retrieving JWKS (cache maxsize=1)")
    try:
        logger.debug(f"📋 get_cached_jwks checkpoint: fetching from get_jwks()")
        result = get_jwks()
        logger.info(f"✅ get_cached_jwks complete | keys_count={len(result.get('keys', []))}")
        return result
    except Exception as e:
        logger.error(f"❌ get_cached_jwks error: {type(e).__name__}: {e}", exc_info=True)
        raise


def verify_rs256_token(token: str) -> Optional[Dict[str, Any]]:
    """Verify an RS256 JWT token against the cached JWKS keys.

    :param token: The raw JWT token string to verify.
    :return: Decoded token payload dictionary if valid, None otherwise.
    """
    logger.info(f"🔐 verify_rs256_token | verifying RS256 token (length={len(token)})")
    settings = get_settings()

    try:
        # Get the header to find the key ID
        logger.debug(f"📋 verify_rs256_token checkpoint: extracting token header")
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")

        # Decode token without verification to see claims
        logger.debug(f"📋 verify_rs256_token checkpoint: unverified decode to check claims")
        unverified_payload = jwt.decode(token, options={"verify_signature": False})

        logger.debug(
            f"📋 verify_rs256_token checkpoint: token_kid={kid}, "
            f"iss={unverified_payload.get('iss')}, "
            f"aud={unverified_payload.get('aud')}, "
            f"exp={unverified_payload.get('exp')}, "
            f"expected_iss={settings.JWT_ISSUER}, "
            f"expected_aud={settings.JWT_AUDIENCE}"
        )

        if not kid:
            logger.error(f"❌ verify_rs256_token failed: token missing 'kid' in header")
            return None

        # Get JWKS and find the key
        logger.debug(f"📋 verify_rs256_token checkpoint: fetching JWKS and searching for kid={kid}")
        jwks = get_cached_jwks()
        key = None

        for jwk in jwks.get("keys", []):
            if jwk.get("kid") == kid:
                logger.debug(f"📋 verify_rs256_token checkpoint: found matching key, converting from JWK")
                key = jwt.algorithms.RSAAlgorithm.from_jwk(jwk)
                break

        if not key:
            available_kids = [k.get("kid") for k in jwks.get("keys", [])]
            logger.error(f"❌ verify_rs256_token failed: kid '{kid}' not found. available_kids={available_kids}, keys_count={len(jwks.get('keys', []))}")
            return None

        # Verify the token
        logger.debug(f"📋 verify_rs256_token checkpoint: verifying signature and claims with RS256")
        try:
            payload = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                audience=settings.JWT_AUDIENCE,
                issuer=settings.JWT_ISSUER,
                options={
                    "verify_exp": True,
                    "verify_iat": True,
                    "verify_nbf": True,
                    "verify_aud": True,
                    "verify_iss": True,
                },
            )
            logger.info(f"✅ verify_rs256_token complete | verified for user={payload.get('sub')}")
            return payload

        except jwt.ExpiredSignatureError as e:
            logger.error(f"❌ verify_rs256_token failed: token_expired: {e}. token_exp={unverified_payload.get('exp')}, current_time={int(time.time())}")
            return None

        except jwt.InvalidAudienceError as e:
            logger.error(
                f"❌ verify_rs256_token failed: invalid_audience: {e}. "
                f"expected={settings.JWT_AUDIENCE}, "
                f"got={unverified_payload.get('aud')}"
            )
            return None

        except jwt.InvalidIssuerError as e:
            logger.error(
                f"❌ verify_rs256_token failed: invalid_issuer: {e}. "
                f"expected={settings.JWT_ISSUER}, "
                f"got={unverified_payload.get('iss')}"
            )
            return None

        except jwt.InvalidSignatureError as e:
            logger.error(f"❌ verify_rs256_token failed: invalid_signature: {e}. token may be signed with different key")
            return None

        except jwt.InvalidTokenError as e:
            logger.error(f"❌ verify_rs256_token failed: invalid_token_error: {type(e).__name__}: {e}", exc_info=True)
            return None

        except Exception as e:
            logger.error(f"❌ verify_rs256_token failed: unexpected_error: {type(e).__name__}: {e}", exc_info=True)
            return None

    except Exception as e:
        logger.error(f"❌ verify_rs256_token error: {type(e).__name__}: {e}", exc_info=True)
        return None


def get_current_user(request: Request) -> Dict[str, Any]:
    """Extract the current authenticated user from request state or headers.

    Supports token-based auth (AuthMiddleware sets request.state.user) and
    header-based auth (x-user-id, x-user-email, x-user-name headers).

    :param request: FastAPI Request object containing auth state or headers.
    :return: User information dict with keys 'sub', 'email', and 'name'.
    :raises HTTPException: 401 if authentication fails.
    """
    logger.info(f"🔐 get_current_user | extracting user from request")
    try:
        # First, try to get user from headers
        user_id_header = request.headers.get("x-user-id")
        user_email_header = request.headers.get("x-user-email")
        user_name_header = request.headers.get("x-user-name")

        logger.debug(f"📋 get_current_user checkpoint: checking headers (x-user-id={user_id_header}, x-user-email={user_email_header})")

        if user_id_header and user_email_header:
            user_info = {
                "sub": user_id_header,
                "email": user_email_header,
                "name": user_name_header or "Unknown User",
            }
            logger.info(f"✅ get_current_user complete | authenticated via headers (user={user_id_header})")
            return user_info

        # Add logging for debugging (can be removed later if not needed)
        logger.debug(f"📋 get_current_user checkpoint: state.user exists={hasattr(request.state, 'user')}, value={getattr(request.state, 'user', None)}")

        user = getattr(request.state, "user", None)
        if not user:
            logger.error(f"❌ get_current_user failed: request.state.user missing or None. Middleware may not have authenticated the request.")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )

        logger.info(f"✅ get_current_user complete | authenticated via state (user={user.get('sub')})")
        return user
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ get_current_user error: {type(e).__name__}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication error",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_roles(required_roles: List[str]) -> Callable[..., Dict[str, Any]]:
    """Create a FastAPI dependency that enforces the user has at least one of the required roles.

    :param required_roles: List of role names, at least one of which the user must possess.
    :return: A dependency function that returns the authenticated user dict.
    """
    logger.info(f"🔐 require_roles | creating role checker for required_roles={required_roles}")

    def role_checker(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        logger.debug(f"📋 require_roles checkpoint: checking user roles against required_roles={required_roles}")
        user_roles = user.get("roles", [])

        if not any(role in user_roles for role in required_roles):
            logger.error(f"❌ require_roles failed: user roles {user_roles} do not contain required={required_roles}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Required roles: {required_roles}",
            )

        logger.info(f"✅ require_roles complete | user has required role (user={user.get('sub')})")
        return user

    logger.debug(f"📋 require_roles checkpoint: role_checker function created")
    return role_checker


def require_scopes(required_scopes: List[str]) -> Callable[..., Dict[str, Any]]:
    """Create a FastAPI dependency that enforces the user has at least one of the required scopes.

    :param required_scopes: List of scope names, at least one of which the user must possess.
    :return: A dependency function that returns the authenticated user dict.
    """
    logger.info(f"🔐 require_scopes | creating scope checker for required_scopes={required_scopes}")

    def scope_checker(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        logger.debug(f"📋 require_scopes checkpoint: checking user scopes against required_scopes={required_scopes}")
        user_scopes = user.get("scopes", [])

        if not any(scope in user_scopes for scope in required_scopes):
            logger.error(f"❌ require_scopes failed: user scopes {user_scopes} do not contain required={required_scopes}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Required scopes: {required_scopes}",
            )

        logger.info(f"✅ require_scopes complete | user has required scope (user={user.get('sub')})")
        return user

    logger.debug(f"📋 require_scopes checkpoint: scope_checker function created")
    return scope_checker
