"""
JWT key management for PrimeData API.
"""

import base64
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict

import jwt
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from primedata.core.settings import get_settings
from primedata.utils.log_utils import get_logger

logger = get_logger(__name__)


def get_keys_dir() -> Path:
    """Get the keys directory, creating it if it doesn't exist."""
    logger.debug(f"🗝️ get_keys_dir() - retrieving keys directory")
    keys_dir = Path(__file__).parent.parent.parent.parent / "keys"
    if not keys_dir.exists():
        logger.info(f"🗝️ ✅ Creating keys directory: {keys_dir}")
        keys_dir.mkdir(exist_ok=True)
    else:
        logger.debug(f"📋 Keys directory already exists: {keys_dir}")
    return keys_dir


def generate_keypair() -> tuple[str, str]:
    """Generate RSA keypair and return as PEM strings."""
    logger.info(f"🔑 ✅ Generating RSA keypair (2048-bit)")
    logger.debug(f"📋 Starting RSA key generation...")

    # Generate private key
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    logger.debug(f"📋 Private key generated")

    # Get public key
    public_key = private_key.public_key()
    logger.debug(f"📋 Public key derived from private key")

    # Serialize private key
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    logger.debug(f"📋 Private key serialized to PEM")

    # Serialize public key
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode("utf-8")
    logger.debug(f"📋 Public key serialized to PEM")

    logger.info(f"🔑 ✅ Keypair generation complete")
    return private_pem, public_pem


def get_or_create_keypair() -> tuple[str, str]:
    """Get existing keypair or create new one."""
    logger.debug(f"🗝️ get_or_create_keypair() - checking for existing keys")
    keys_dir = get_keys_dir()
    private_key_path = keys_dir / "private_key.pem"
    public_key_path = keys_dir / "public_key.pem"

    if private_key_path.exists() and public_key_path.exists():
        # Load existing keys
        logger.info(f"🗝️ ✅ Loading existing keypair from disk")
        logger.debug(f"📋 Private key path: {private_key_path}")
        logger.debug(f"📋 Public key path: {public_key_path}")
        with open(private_key_path, "r") as f:
            private_pem = f.read()
        with open(public_key_path, "r") as f:
            public_pem = f.read()
        logger.info(f"🗝️ ✅ Keypair loaded successfully")
        return private_pem, public_pem
    else:
        # Generate new keys
        logger.info(f"🗝️ No existing keypair found, generating new keys")
        logger.debug(f"📋 Looking for: {private_key_path}, {public_key_path}")
        private_pem, public_pem = generate_keypair()

        # Save keys
        logger.debug(f"📋 Saving private key to: {private_key_path}")
        with open(private_key_path, "w") as f:
            f.write(private_pem)
        logger.debug(f"✓ Private key saved")

        logger.debug(f"📋 Saving public key to: {public_key_path}")
        with open(public_key_path, "w") as f:
            f.write(public_pem)
        logger.debug(f"✓ Public key saved")

        logger.info(f"🗝️ ✅ New keypair generated and saved to {keys_dir}")
        return private_pem, public_pem


def sign_jwt(payload: Dict[str, Any], exp_s: int = 3600) -> str:
    """
    Sign JWT with RS256 algorithm.

    Args:
        payload: Data to encode in the token
        exp_s: Expiration time in seconds

    Returns:
        Encoded JWT token
    """
    logger.debug(f"🗝️ sign_jwt() - payload_keys={list(payload.keys())}, exp_s={exp_s}")
    logger.info(f"🗝️ ✅ Signing JWT token (exp_s={exp_s}s)")

    settings = get_settings()
    private_pem, _ = get_or_create_keypair()
    logger.debug(f"📋 Loaded private key for signing")

    private_key = serialization.load_pem_private_key(private_pem.encode("utf-8"), password=None)
    logger.debug(f"📋 Private key deserialized")

    now = datetime.utcnow()
    to_encode = payload.copy()
    to_encode.update(
        {
            "exp": now + timedelta(seconds=exp_s),
            "iat": now,
            "nbf": now,
            "iss": settings.JWT_ISSUER,
            "aud": settings.JWT_AUDIENCE,
        }
    )
    logger.debug(f"📋 JWT claims prepared - iss={settings.JWT_ISSUER}, aud={settings.JWT_AUDIENCE}")

    encoded_jwt = jwt.encode(to_encode, private_key, algorithm="RS256", headers={"kid": "primedata-key-1"})
    logger.info(f"🗝️ ✅ JWT signed successfully (algorithm=RS256)")
    logger.debug(f"📋 Token length: {len(encoded_jwt)} characters")
    return encoded_jwt


def get_jwks() -> Dict[str, Any]:
    """Get JWKS (JSON Web Key Set) for token verification."""
    logger.debug(f"🗝️ get_jwks() - retrieving JWKS")
    try:
        _, public_pem = get_or_create_keypair()
        logger.debug(f"📋 Public key loaded")

        # Load public key
        public_key = serialization.load_pem_public_key(public_pem.encode("utf-8"))
        logger.debug(f"📋 Public key deserialized")

        # Get key components
        public_numbers = public_key.public_numbers()
        logger.debug(f"📋 Public key components extracted")

        # Convert to JWK format
        n = base64.urlsafe_b64encode(public_numbers.n.to_bytes(256, "big")).decode("utf-8").rstrip("=")
        logger.debug(f"📋 Modulus (n) encoded")

        e = base64.urlsafe_b64encode(public_numbers.e.to_bytes(3, "big")).decode("utf-8").rstrip("=")
        logger.debug(f"📋 Exponent (e) encoded")

        # Create JWK
        jwk = {"kty": "RSA", "use": "sig", "kid": "primedata-key-1", "n": n, "e": e, "alg": "RS256"}
        logger.info(f"🗝️ ✅ JWKS generated successfully")
        logger.debug(f"📋 JWK: kid=primedata-key-1, alg=RS256")

        return {"keys": [jwk]}

    except Exception as e:
        # Return empty JWKS on error
        logger.error(f"❌ Failed to generate JWKS: {e}", exc_info=True)
        logger.warning(f"⚠️ Returning empty JWKS due to error")
        return {"keys": []}


def get_public_jwks() -> dict:
    """Get public JWKS for JWT key discovery."""
    logger.debug(f"🗝️ get_public_jwks() - retrieving public JWKS")
    jwks = get_jwks()
    logger.info(f"🗝️ ✅ Public JWKS retrieved ({len(jwks.get('keys', []))} keys)")
    return jwks
