"""ARC LLM layer — Cortex-backed synthesizer.

Public surface:
- `advise(...)` — single integration seam used by `api/assess.py`. The
  ONLY callable outside this package.
- `LLMUnavailable` — raised by the client when Cortex credentials are
  missing or the call fails. Caller's fallback handles it; the run still
  completes.

Hard contract (CLAUDE.md + EXECUTION_PLAN A2):
- The LLM never computes a number, metric, or score. It enriches the
  deterministic Report additively with narrative/strengths/recommendations.
- Every recommendation links back to a finding_id in the Report — prose
  stays evidence-anchored.
- SECURITY_GUARDRAILS prefix and `wrap_untrusted()` fencing apply on every
  call. Data-derived text (table names, column descriptions, sample
  values) is NEVER treated as instructions.
"""
from llm.advisor import advise
from llm.exceptions import LLMUnavailable, LLMSchemaError

__all__ = ["advise", "LLMUnavailable", "LLMSchemaError"]
