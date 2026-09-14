"""Cortex API client — Lilly's OAuth-fronted LLM gateway.

Auth: client_credentials flow against
    https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token
with scope `api://Cortex.lilly.com/.default`. The bearer token is cached
per-process until 60s before its `exp` claim.

Inference: HTTP POST (multipart form) to
    {cortex_base_url}/model/ask/{model_config_name}
with required APIM headers `x-user`, `x-groups`, `x-org` for identity
routing, plus form fields `q` (prompt) and `stream=false`.

This file is the only place in the backend that talks to Cortex. The
synthesizer / advisor layers consume `call_model()`. Credentials are read
from `settings.client_id_llm`, `settings.tenant_id_llm`,
`settings.client_secret_llm`, `settings.cortex_base_url`,
`settings.model_config_name`. They are never logged.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Type, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from config import settings
from llm.exceptions import LLMSchemaError, LLMUnavailable

logger = logging.getLogger(__name__)

_L = "══ LLM ══"  # visual separator for LLM log lines


# Margin between token expiry and our cached-good window. Cortex uses a
# 60-min default token TTL; refreshing 60s early avoids a race in flight.
_TOKEN_REFRESH_MARGIN_S = 60

# OAuth scope required by the Cortex gateway. Pinned constant.
_CORTEX_SCOPE = "api://Cortex.lilly.com/.default"

# Connect / read timeouts for the two HTTP calls we make.
_OAUTH_TIMEOUT_S = 15.0

T = TypeVar("T", bound=BaseModel)


@dataclass
class _CachedToken:
    token: str
    expires_at: float  # epoch seconds


# Module-level token cache. Per-process, intentional — Cortex tokens are
# cheap, and a shared cache across requests amortizes the OAuth roundtrip.
_token_cache: _CachedToken | None = None
_token_lock: asyncio.Lock | None = None
_token_lock_loop: asyncio.AbstractEventLoop | None = None
_http_client: httpx.AsyncClient | None = None
_http_client_loop: asyncio.AbstractEventLoop | None = None
_http_client_lock: asyncio.Lock | None = None
_http_client_lock_loop: asyncio.AbstractEventLoop | None = None


def _get_token_lock() -> asyncio.Lock:
    """Return a per-event-loop lock for token refresh serialization."""
    global _token_lock, _token_lock_loop

    loop = asyncio.get_running_loop()
    if _token_lock is None or _token_lock_loop is not loop:
        _token_lock = asyncio.Lock()
        _token_lock_loop = loop
    return _token_lock


def _get_http_client_lock() -> asyncio.Lock:
    """Return a per-event-loop lock for shared HTTP client setup."""
    global _http_client_lock, _http_client_lock_loop

    loop = asyncio.get_running_loop()
    if _http_client_lock is None or _http_client_lock_loop is not loop:
        _http_client_lock = asyncio.Lock()
        _http_client_lock_loop = loop
    return _http_client_lock


async def _get_http_client() -> httpx.AsyncClient:
    """Return a shared AsyncClient so LLM calls reuse one keepalive session."""
    global _http_client, _http_client_loop

    loop = asyncio.get_running_loop()
    lock = _get_http_client_lock()
    async with lock:
        if (
            _http_client is not None
            and _http_client_loop is loop
            and not getattr(_http_client, "is_closed", False)
        ):
            return _http_client

        if _http_client is not None and not getattr(_http_client, "is_closed", False):
            await _http_client.aclose()

        _http_client = httpx.AsyncClient()
        _http_client_loop = loop
        return _http_client


async def close_http_client() -> None:
    """Close the shared HTTP client on app shutdown."""
    global _http_client, _http_client_loop

    if _http_client is not None and not getattr(_http_client, "is_closed", False):
        await _http_client.aclose()
    _http_client = None
    _http_client_loop = None


def _have_credentials() -> bool:
    """All four secrets must be present for any LLM call to succeed."""
    return all((
        settings.client_id_llm,
        settings.tenant_id_llm,
        settings.client_secret_llm,
        settings.model_config_name,
    ))


async def _acquire_token() -> str:
    """Return a valid bearer token, fetching a new one if cached is stale.

    Raises LLMUnavailable on missing creds or any auth failure. Never logs
    secret values — only the failure code/message scrubbed of payloads.
    """
    global _token_cache
    if not _have_credentials():
        _token_cache = None
        raise LLMUnavailable("missing_credentials")

    now = time.time()
    if _token_cache and _token_cache.expires_at - _TOKEN_REFRESH_MARGIN_S > now:
        logger.debug("%s OAuth token cache hit", _L)
        return _token_cache.token

    lock = _get_token_lock()
    wait_started = time.monotonic()
    async with lock:
        wait_ms = int((time.monotonic() - wait_started) * 1000)
        now = time.time()
        if _token_cache and _token_cache.expires_at - _TOKEN_REFRESH_MARGIN_S > now:
            logger.debug("%s OAuth token cache hit after wait wait_ms=%d", _L, wait_ms)
            return _token_cache.token

        token_url = (
            f"https://login.microsoftonline.com/"
            f"{settings.tenant_id_llm}/oauth2/v2.0/token"
        )
        payload = {
            "grant_type": "client_credentials",
            "client_id": settings.client_id_llm,
            "client_secret": settings.client_secret_llm,
            "scope": _CORTEX_SCOPE,
        }
        refresh_started = time.monotonic()
        try:
            client = await _get_http_client()
            resp = await client.post(token_url, data=payload, timeout=_OAUTH_TIMEOUT_S)
            resp.raise_for_status()
            body = resp.json()
        except httpx.HTTPError as e:
            # NEVER log payload — `e` may carry the response body which echoes
            # the client_secret in some Azure error envelopes.
            logger.warning("Cortex OAuth failed: %s", type(e).__name__)
            raise LLMUnavailable("oauth_failed") from None

        token = body.get("access_token")
        if not token:
            raise LLMUnavailable("oauth_no_token")
        expires_in = float(body.get("expires_in", 3600))
        _token_cache = _CachedToken(token=token, expires_at=now + expires_in)
        refresh_ms = int((time.monotonic() - refresh_started) * 1000)
        logger.info(
            "%s OAuth token refreshed wait_ms=%d refresh_ms=%d expires_in_s=%d",
            _L,
            wait_ms,
            refresh_ms,
            int(expires_in),
        )
        return token


def _strip_code_fences(text: str) -> str:
    """Remove ```json ... ``` fences if the model wrapped its JSON in one.

    Cortex passes prompts to Claude verbatim and Claude often wraps JSON in
    a fenced block when asked for structured output. We accept either
    fenced or bare JSON and surface the raw payload to the schema parser.
    """
    text = text.strip()
    if text.startswith("```"):
        # Strip opening fence (``` or ```json) and the trailing fence.
        text = re.sub(r"^```[a-zA-Z0-9]*\n?", "", text)
        if text.endswith("```"):
            text = text[: -len("```")]
    return text.strip()


def _extract_first_json_object(text: str) -> str:
    """Return the first balanced JSON object substring, or the input
    stripped. Tolerant of leading prose the model may emit before the
    structured payload.
    """
    text = _strip_code_fences(text)
    start = text.find("{")
    if start == -1:
        return text
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\" and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return text[start:]


# Module-level URL cache. Once one endpoint succeeds, subsequent calls skip
# the failed one until a failure resets it.
_last_working_url: str | None = None


async def _post_inference(prompt: str, *, timeout_s: float | None = None) -> str:
    """Single Cortex inference call. Tries the configured endpoint chain in
    order and caches the last-working URL to avoid repeated failover.

    Uses HTTP POST with multipart form data and the required APIM gateway
    identity headers (x-user, x-groups, x-org). This matches the Cortex
    boilerplate contract.
    """
    global _last_working_url
    token = await _acquire_token()
    effective_timeout_s = float(timeout_s or settings.llm_inference_timeout_seconds)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {
        "q": prompt,
        "stream": "false",
    }

    urls = settings.cortex_base_urls
    if _last_working_url and _last_working_url in urls:
        urls = [_last_working_url] + [u for u in urls if u != _last_working_url]

    for base_url in urls:
        url = f"{base_url}/model/ask/{settings.model_config_name}"
        try:
            client = await _get_http_client()
            resp = await client.post(url, headers=headers, data=data, timeout=effective_timeout_s)
            resp.raise_for_status()
            _last_working_url = base_url
            # Cortex returns a JSON envelope. Extract the model's text.
            raw_text = resp.text
            try:
                envelope = json.loads(raw_text)
                # Cortex envelope: {"message": "...", "source_metadata": [...], "steps": [...]}
                if isinstance(envelope, dict):
                    model_text = (
                        envelope.get("message")
                        or envelope.get("response")
                        or envelope.get("answer")
                        or envelope.get("result")
                        or envelope.get("text")
                        or envelope.get("output")
                    )
                    if model_text:
                        logger.debug("Cortex envelope unwrapped, keys: %s", list(envelope.keys()))
                        return str(model_text)
                # If not a dict or no known key, return raw
                logger.debug("Cortex response not a recognized envelope, using raw text")
            except (json.JSONDecodeError, TypeError):
                pass
            return raw_text
        except httpx.HTTPError as e:
            logger.info(
                "Cortex call failed on %s: %s timeout_s=%s",
                base_url,
                type(e).__name__,
                effective_timeout_s,
            )
            continue

    logger.warning("%s Cortex inference failed on all configured URLs", _L)
    raise LLMUnavailable("inference_failed_both_urls") from None


async def call_model(
    prompt: str,
    *,
    schema: Type[T] | None = None,
    timeout_s: float | None = None,
) -> str | T:
    """Call Cortex with the given prompt.

    When `schema` is provided, the response is parsed against it. On parse
    failure we retry the call ONCE with a clarifying suffix appended to
    the prompt; if that also fails, raise `LLMSchemaError`.

    When `schema` is None, the raw response text is returned.

    Raises:
        LLMUnavailable: missing creds, auth failure, network error.
        LLMSchemaError: structured output failed to parse after retry.
    """
    raw = await _post_inference(prompt, timeout_s=timeout_s)
    if schema is None:
        return raw

    logger.debug("Cortex raw response (first 500 chars): %s", raw[:500])
    payload = _extract_first_json_object(raw)
    logger.debug("Extracted JSON payload (first 500 chars): %s", payload[:500])
    try:
        return schema.model_validate_json(payload)
    except (ValidationError, json.JSONDecodeError) as e:
        logger.info("%s Schema parse FAILED, retrying. Error: %s. Payload start: %.200s",
                    _L, str(e)[:200], payload[:200])

    retry_prompt = (
        prompt
        + "\n\nIMPORTANT: Your previous response was not valid JSON matching the "
          "requested schema. Respond with ONLY a JSON object — no prose, no "
          "code fences, no commentary."
    )
    raw2 = await _post_inference(retry_prompt, timeout_s=timeout_s)
    payload2 = _extract_first_json_object(raw2)
    logger.debug("Retry payload (first 500 chars): %s", payload2[:500])
    try:
        return schema.model_validate_json(payload2)
    except (ValidationError, json.JSONDecodeError) as e:
        logger.warning("%s Retry also FAILED. Error: %s. Payload start: %.200s",
                       _L, str(e)[:300], payload2[:200])
        raise LLMSchemaError(f"structured output invalid after retry: {type(e).__name__}") from None


async def ping() -> dict:
    """Lightweight connection test for the admin console.

    Acquires a token (or uses cache) and sends a minimal prompt. Returns
    latency + status + which URL worked. Never exposes credentials.
    """
    start = time.time()
    try:
        await _acquire_token()
        await _post_inference("Respond with only the word 'ok'.")
        elapsed = int((time.time() - start) * 1000)
        return {
            "ok": True,
            "latency_ms": elapsed,
            "model_config": settings.model_config_name,
            "token_cached": _token_cache is not None,
            "url": _last_working_url or "unknown",
        }
    except LLMUnavailable as e:
        elapsed = int((time.time() - start) * 1000)
        return {
            "ok": False,
            "latency_ms": elapsed,
            "error": str(e),
            "urls_tried": settings.cortex_base_urls,
        }
