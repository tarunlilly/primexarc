"""Output schemas for the LLM layer.

The synthesizer's output is structured and validated. Anti-hallucination
contract: every Recommendation MUST link to a `finding_id` that exists in
the input Report. The validator rejects output that names a finding the
deterministic engine never produced.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SynthesizerRecommendation(BaseModel):
    """One LLM-prioritized recommendation linked to a finding."""
    finding_id: str = Field(min_length=1)
    priority: Literal["high", "medium", "low"]
    title: str = Field(min_length=1, max_length=200)
    detail: str = Field(min_length=1, max_length=800)
    technical_note: str = Field(default="", max_length=400)


class SynthesizerOutput(BaseModel):
    """Structured output of one synthesizer call. Inputs to a synthesizer
    call are findings + score + dimension scores ONLY; the output is the
    only place where prose lives."""
    narrative: str = Field(min_length=1, max_length=1200)
    strengths: list[str] = Field(default_factory=list, max_length=10)
    recommendations: list[SynthesizerRecommendation] = Field(
        default_factory=list, max_length=10,
    )
