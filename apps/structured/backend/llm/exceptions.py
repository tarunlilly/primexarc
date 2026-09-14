"""Exceptions raised by the LLM layer."""
from __future__ import annotations


class LLMUnavailable(Exception):
    """Raised when the LLM cannot be called — missing credentials, network
    failure, auth failure, etc. Callers MUST catch this and fall back to
    rule-based output so the assessment still completes."""


class LLMSchemaError(Exception):
    """Raised when the model returns output that cannot be parsed against
    the expected pydantic schema after the configured retry budget."""
