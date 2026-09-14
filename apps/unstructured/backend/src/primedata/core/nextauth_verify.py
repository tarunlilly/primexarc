"""
NextAuth token verification module.
"""

import base64
import json
from typing import Any, Dict, Optional

import jwt
from primedata.core.settings import get_settings
from primedata.utils.log_utils import get_logger

logger = get_logger(__name__)

try:
    import hashlib
    import time

    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from jose import jwe
    from jose.constants import ALGORITHMS

    JWE_AVAILABLE = True
except ImportError:
    JWE_AVAILABLE = False


# NextAuth.js uses HKDF with this specific info string for JWE key derivation
NEXTAUTH_INFO = b"NextAuth.js Generated Encryption Key"


def _b64url_decode(s: str) -> bytes:
    """Decode base64url string to bytes."""
    logger.debug(f"📋 _b64url_decode(string_len={len(s)})")
    s = s + "=" * ((4 - len(s) % 4) % 4)
    result = base64.urlsafe_b64decode(s.encode("utf-8"))
    logger.debug(f"✓ Base64url decoded: {len(s)} chars -> {len(result)} bytes")
    return result


def derive_nextauth_jwe_key(secret: str, salt: str = "") -> bytes:
    """
    NextAuth derives the CEK using HKDF(SHA-256) with info 'NextAuth.js Generated Encryption Key'.
    This matches NextAuth.js's key derivation method exactly.
    """
    logger.debug(f"🗝️ derive_nextauth_jwe_key(secret_len={len(secret)}, salt='{salt}')")
    secret_bytes = secret.encode("utf-8")
    salt_bytes = salt.encode("utf-8") if salt else b""

    info = NEXTAUTH_INFO

    logger.debug(f"📋 Using HKDF-SHA256: secret_len={len(secret_bytes)}, salt_len={len(salt_bytes)}")
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,  # A256GCM needs 32 bytes
        salt=salt_bytes,
        info=info,
    )
    key = hkdf.derive(secret_bytes)
    logger.info(f"🗝️ ✅ HKDF key derived: {len(key)} bytes (32 bytes for A256GCM)")
    return key


def decrypt_nextauth_session_jwe(token: str, secret: str) -> Dict[str, Any]:
    """
    Decrypt NextAuth JWE (compact) and return payload dict.
    Tries common salt variants because deployments differ.
    """
    logger.info(f"🔐 decrypt_nextauth_session_jwe() - attempting decryption (token_len={len(token)})")

    # Common salt candidates
    salt_candidates = [
        "",  # often works
        "next-auth.session-token",
        "__Secure-next-auth.session-token",
        "authjs.session-token",
        "__Secure-authjs.session-token",
    ]

    last_err = None
    for salt in salt_candidates:
        try:
            logger.debug(f"📋 Trying salt variant: '{salt}'")
            key = derive_nextauth_jwe_key(secret, salt=salt)

            # Try python-jose directly first
            logger.debug(f"📋 Attempting JWE decryption with salt='{salt}'")
            plaintext = jwe.decrypt(token, key)  # returns bytes
            try:
                payload = json.loads(plaintext.decode("utf-8"))
                logger.info(f"✅ JWE decrypted successfully with salt: '{salt}'")
                logger.debug(f"📋 Decrypted payload keys: {list(payload.keys())}")
                return payload
            except json.JSONDecodeError:
                # In rare cases plaintext might be another JWT string
                txt = plaintext.decode("utf-8", errors="ignore")
                logger.warning(f"⚠️ Decrypted payload is not JSON, treating as raw text")
                return {"_raw": txt}
        except Exception as e:
            logger.debug(f"❌ Decryption failed with salt '{salt}': {type(e).__name__}: {str(e)}")
            last_err = e

    logger.error(f"❌ All HKDF salt variants failed (tried {len(salt_candidates)} variants)", exc_info=True)
    raise last_err if last_err else Exception("All HKDF salt variants failed")


def verify_nextauth_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Verify HS256 NextAuth token using NEXTAUTH_SECRET.

    Args:
        token: The JWT token to verify

    Returns:
        Normalized claims dict with email, name, picture, provider
        or None if verification fails
    """
    logger.info(f"🔐 verify_nextauth_token() - token_length={len(token)}")

    settings = get_settings()

    # Validate that NEXTAUTH_SECRET is set and not default
    if (
        not settings.NEXTAUTH_SECRET
        or settings.NEXTAUTH_SECRET == "REPLACE_WITH_64_CHAR_RANDOM_STRING_FOR_PRODUCTION_USE_ONLY"
    ):
        logger.error(f"❌ NEXTAUTH_SECRET not set or using default value")
        logger.error(f"⚠️ The NEXTAUTH_SECRET must match between backend .env and ui/.env.local")
        return None

    # Log secret info for debugging (first 10 chars only for security)
    logger.debug(f"📋 NEXTAUTH_SECRET info - length={len(settings.NEXTAUTH_SECRET)}, first_10={settings.NEXTAUTH_SECRET[:10]}..., last_10=...{settings.NEXTAUTH_SECRET[-10:]}")

    try:
        # Check token format - JWT has 3 parts, JWE has 5 parts
        if not token:
            logger.error(f"❌ Token is empty")
            return None

        token_parts = token.split(".")
        num_parts = len(token_parts)
        logger.debug(f"📋 Token structure - parts={num_parts}")

        # Decode the header to determine token type
        try:
            header_part = token_parts[0]
            # Add padding if needed for base64 decoding
            padding = 4 - len(header_part) % 4
            if padding != 4:
                header_part += "=" * padding

            header_json = base64.urlsafe_b64decode(header_part)
            header = json.loads(header_json)

            token_algorithm = header.get("alg")
            token_encryption = header.get("enc")

            logger.info(f"🔐 Token type detected - parts={num_parts}, alg={token_algorithm}, enc={token_encryption}")
            logger.debug(f"📋 Token header: {header}")

            # Check if this is a JWE (encrypted JWT) - NextAuth v4+ uses encrypted tokens
            if token_encryption or token_algorithm == "dir":
                logger.info(f"🔐 Token is JWE (encrypted). Attempting HKDF decryption...")

                if not JWE_AVAILABLE:
                    logger.error(f"❌ python-jose not available. Cannot decrypt JWE tokens.")
                    logger.error(f"⚠️ Please install: pip install python-jose[cryptography]")
                    return None

                # Decrypt the JWE token using HKDF (NextAuth.js standard)
                try:
                    payload = decrypt_nextauth_session_jwe(token, settings.NEXTAUTH_SECRET)
                    logger.debug(f"📋 JWE decrypted - payload_keys={list(payload.keys())}")

                    # Validate expiration
                    import time
                    now = int(time.time())
                    exp = payload.get("exp")
                    if exp and int(exp) < now:
                        logger.warning(f"⚠️ Token has expired - exp={exp}, now={now}")
                        return None

                    # Extract claims directly from JSON payload
                    claims = {
                        "email": payload.get("email"),
                        "name": payload.get("name"),
                        "picture": payload.get("picture"),
                        "provider": payload.get("provider"),
                        "sub": payload.get("sub"),
                        "iat": payload.get("iat"),
                        "exp": payload.get("exp"),
                        "iss": payload.get("iss"),
                    }

                    # Validate required fields
                    if not claims["email"]:
                        logger.warning(f"⚠️ Token decoded but missing required 'email' field")
                        return None

                    logger.info(f"✅ JWE token verified successfully - user={claims['email']}")
                    return claims

                except Exception as e:
                    logger.error(f"❌ JWE DECRYPTION FAILED - error={type(e).__name__}: {e}", exc_info=True)
                    logger.error(f"⚠️ Possible causes: secret mismatch, format not supported, encrypted with different secret")
                    logger.debug(f"📋 Debug info: secret_length={len(settings.NEXTAUTH_SECRET)}, token_parts={len(token.split('.'))}")
                    return None

            # Verify non-JWE tokens (regular JWT)
            logger.debug(f"📋 Processing as JWT (not JWE)")
            # Check token format - JWT has 3 parts
            if num_parts != 3:
                logger.error(f"❌ Token doesn't appear to be valid JWT (expected 3 parts, got {num_parts})")
                logger.debug(f"📋 Token preview: {token[:50]}...")
                return None

            # Get the algorithm from the token
            unverified_header = jwt.get_unverified_header(token)
            token_algorithm = unverified_header.get("alg")
            logger.debug(f"📋 JWT algorithm: {token_algorithm}")

            # Check if algorithm is supported (NextAuth uses HS256)
            if token_algorithm not in ["HS256", "HS384", "HS512"]:
                logger.error(f"❌ Unsupported algorithm: {token_algorithm} (expected HS256/HS384/HS512)")
                logger.debug(f"📋 Token header: {unverified_header}")
                return None

        except Exception as e:
            logger.error(f"❌ Failed to decode token header: {type(e).__name__}: {e}")
            logger.error(f"⚠️ Token might not be valid JWT or JWE")
            logger.debug(f"📋 Token preview: {token[:100]}...")
            return None

        # Decode and verify the token
        logger.debug(f"📋 Verifying JWT signature and claims with {token_algorithm}")
        # NextAuth uses HS256 by default, but we'll try multiple algorithms for compatibility
        # Try the algorithm from the token header first, then fallback to HS256
        allowed_algorithms = []
        if token_algorithm in ["HS256", "HS384", "HS512"]:
            allowed_algorithms = [token_algorithm]
        else:
            # If algorithm is not in expected list, try all HMAC algorithms
            allowed_algorithms = ["HS256", "HS384", "HS512"]
            logger.warning(f"⚠️ Token algorithm '{token_algorithm}' not in expected list, trying all HMAC algorithms")

        payload = jwt.decode(
            token,
            settings.NEXTAUTH_SECRET,
            algorithms=allowed_algorithms,
            options={
                "verify_exp": True,
                "verify_iat": True,
                "verify_nbf": True,
            },
        )

        logger.debug(f"📋 Token decoded - payload_keys={list(payload.keys())}")

        # Check issuer if configured
        if settings.API_SESSION_EXCHANGE_ALLOWED_ISS:
            token_iss = payload.get("iss")
            if token_iss != settings.API_SESSION_EXCHANGE_ALLOWED_ISS:
                logger.warning(f"⚠️ Issuer mismatch - expected={settings.API_SESSION_EXCHANGE_ALLOWED_ISS}, got={token_iss}")
                return None

        # Extract and normalize claims
        claims = {
            "email": payload.get("email"),
            "name": payload.get("name"),
            "picture": payload.get("picture"),
            "provider": payload.get("provider"),
            "google_sub": payload.get("google_sub"),
            "sub": payload.get("sub"),
            "iat": payload.get("iat"),
            "exp": payload.get("exp"),
            "iss": payload.get("iss"),
        }

        # Validate required fields
        if not claims["email"]:
            logger.warning(f"⚠️ Token decoded but missing required 'email' field")
            return None

        logger.info(f"✅ JWT token verified successfully - user={claims['email']}")
        return claims

    except jwt.ExpiredSignatureError:
        logger.warning(f"⚠️ Token has expired")
        return None
    except jwt.InvalidSignatureError:
        logger.error(f"❌ Token signature is invalid - NEXTAUTH_SECRET mismatch between frontend/backend")
        logger.error(f"⚠️ Ensure NEXTAUTH_SECRET in backend/.env matches ui/.env.local")
        return None
    except jwt.DecodeError as e:
        logger.error(f"❌ Token decode error: {e}")
        logger.error(f"⚠️ Token format may be incorrect or NEXTAUTH_SECRET is wrong")
        return None
    except jwt.InvalidTokenError as e:
        logger.error(f"❌ Invalid token error: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"❌ Unexpected error during token verification: {type(e).__name__}: {e}", exc_info=True)
        return None
