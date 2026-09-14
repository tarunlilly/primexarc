"""Auth dependency tests.

Validates the four security properties of require_user():
1. Dev bypass is GATED — only active when client_id is empty.
2. Dev bypass is ACTIVE — returns fixture user when client_id is empty.
3. Expired tokens are rejected (401).
4. Wrong-audience tokens are rejected (401).

All tests use a generated RSA key pair and a monkeypatched JWKS so no
real Azure AD calls are made.
"""
from __future__ import annotations

import json
import time

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from jose import jwt

import dependencies as deps
from config import settings


# ── Shared key fixture ────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def rsa_key_pair():
    """Generate a throwaway RSA-2048 key pair for the entire module."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    return private_key, public_key


@pytest.fixture(scope="module")
def jwks(rsa_key_pair):
    """Build a minimal JWKS from the public key."""
    _, public_key = rsa_key_pair
    pub_numbers = public_key.public_key().public_numbers() if hasattr(public_key, "public_key") else public_key.public_numbers()

    import base64
    import math

    def int_to_base64url(n: int) -> str:
        byte_len = math.ceil(n.bit_length() / 8)
        b = n.to_bytes(byte_len, "big")
        return base64.urlsafe_b64encode(b).rstrip(b"=").decode()

    return {
        "keys": [
            {
                "kty": "RSA",
                "kid": "test-key-1",
                "use": "sig",
                "alg": "RS256",
                "n": int_to_base64url(pub_numbers.n),
                "e": int_to_base64url(pub_numbers.e),
            }
        ]
    }


def _make_token(private_key, *, audience: str, issuer: str, exp_offset: int = 3600) -> str:
    """Build a signed JWT for testing."""
    now = int(time.time())
    claims = {
        "oid": "test-user-oid",
        "preferred_username": "test@lilly.com",
        "aud": audience,
        "iss": issuer,
        "exp": now + exp_offset,
        "iat": now,
        "nbf": now,
    }
    pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    )
    return jwt.encode(claims, pem, algorithm="RS256", headers={"kid": "test-key-1"})


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dev_bypass_returns_401_when_client_id_set(monkeypatch):
    """When client_id is configured, a missing token must return 401."""
    monkeypatch.setattr(settings, "client_id", "real-client-id")

    with pytest.raises(HTTPException) as exc_info:
        await deps.require_user(credentials=None)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_dev_bypass_allowed_when_no_client_id(monkeypatch):
    """When client_id is empty (local dev), a missing token returns the fixture user."""
    monkeypatch.setattr(settings, "client_id", "")

    user = await deps.require_user(credentials=None)

    assert user.user_id == "dev_user"
    assert user.email == "dev@lilly.com"


@pytest.mark.asyncio
async def test_expired_token_returns_401(monkeypatch, rsa_key_pair, jwks):
    """A token with exp in the past must be rejected with 401."""
    private_key, _ = rsa_key_pair
    monkeypatch.setattr(settings, "client_id", "test-client-id")
    monkeypatch.setattr(settings, "tenant_id", "test-tenant-id")
    monkeypatch.setattr(deps, "_JWKS_CACHE", jwks)
    monkeypatch.setattr(deps, "_JWKS_FETCHED_AT", time.monotonic())

    expired_token = _make_token(
        private_key,
        audience="test-client-id",
        issuer="https://login.microsoftonline.com/test-tenant-id/v2.0",
        exp_offset=-3600,  # expired 1 hour ago
    )

    from fastapi.security import HTTPAuthorizationCredentials
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=expired_token)

    with pytest.raises(HTTPException) as exc_info:
        await deps.require_user(credentials=creds)

    assert exc_info.value.status_code == 401
    assert "expired" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_wrong_audience_returns_401(monkeypatch, rsa_key_pair, jwks):
    """A token with the wrong audience must be rejected with 401."""
    private_key, _ = rsa_key_pair
    monkeypatch.setattr(settings, "client_id", "correct-client-id")
    monkeypatch.setattr(settings, "tenant_id", "test-tenant-id")
    monkeypatch.setattr(deps, "_JWKS_CACHE", jwks)
    monkeypatch.setattr(deps, "_JWKS_FETCHED_AT", time.monotonic())

    wrong_aud_token = _make_token(
        private_key,
        audience="some-other-app-id",  # wrong audience
        issuer="https://login.microsoftonline.com/test-tenant-id/v2.0",
    )

    from fastapi.security import HTTPAuthorizationCredentials
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=wrong_aud_token)

    with pytest.raises(HTTPException) as exc_info:
        await deps.require_user(credentials=creds)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_valid_token_returns_user(monkeypatch, rsa_key_pair, jwks):
    """A well-formed, signed, unexpired token with correct aud/iss succeeds."""
    private_key, _ = rsa_key_pair
    monkeypatch.setattr(settings, "client_id", "test-client-id")
    monkeypatch.setattr(settings, "tenant_id", "test-tenant-id")
    monkeypatch.setattr(deps, "_JWKS_CACHE", jwks)
    monkeypatch.setattr(deps, "_JWKS_FETCHED_AT", time.monotonic())

    token = _make_token(
        private_key,
        audience="test-client-id",
        issuer="https://login.microsoftonline.com/test-tenant-id/v2.0",
    )

    from fastapi.security import HTTPAuthorizationCredentials
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    user = await deps.require_user(credentials=creds)

    assert user.user_id == "test-user-oid"
    assert user.email == "test@lilly.com"
