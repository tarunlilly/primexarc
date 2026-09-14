"""
Tests for the length-guard that protects chunks from degenerate LLM output.

A model that returns "OK" or "." instead of cleaned text would otherwise
overwrite real chunk content. These tests exercise the rejection path at
both Layer A (LLMOptimizationService.enhance_text) and Layer B
(HybridOptimizer.optimize).
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from primedata.services.llm_optimization import (
    LLM_OUTPUT_MIN_CHARS,
    LLM_OUTPUT_MIN_RATIO,
    LLMOptimizationService,
)


def _mock_openai_response(content: str, prompt_tokens: int = 100, completion_tokens: int = 5):
    """Build a fake OpenAI ChatCompletion response."""
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
    )


@pytest.fixture
def llm_service():
    with patch.object(LLMOptimizationService, "__init__", lambda self, **kw: None):
        svc = LLMOptimizationService()
    svc.api_key = "test-key"
    svc.model = "gpt-4o-mini"
    svc.client = MagicMock()
    svc.pricing = LLMOptimizationService.MODEL_PRICING["gpt-4o-mini"]
    return svc


class TestEnhanceTextLengthGuard:
    """Layer A: enhance_text must reject suspiciously short LLM output."""

    def test_two_char_response_rejected_for_long_input(self, llm_service):
        long_text = "This is a long passage of text that should be cleaned. " * 20  # ~1100 chars
        llm_service.client.chat.completions.create.return_value = _mock_openai_response("OK")

        result = llm_service.enhance_text(long_text)

        assert result["enhanced_text"] == long_text, "original text must be preserved"
        assert "error" in result and "too short" in result["error"]
        assert result["cost_estimate"] > 0, "cost is recorded even when output is rejected"

    def test_below_floor_rejected_even_for_short_input(self, llm_service):
        short_text = "x" * 40
        llm_service.client.chat.completions.create.return_value = _mock_openai_response(".")

        result = llm_service.enhance_text(short_text)

        assert result["enhanced_text"] == short_text
        assert "error" in result

    def test_below_ratio_rejected(self, llm_service):
        text = "x" * 100
        # 40 chars is above the 10-char floor but below the 50% ratio
        llm_service.client.chat.completions.create.return_value = _mock_openai_response("y" * 40)

        result = llm_service.enhance_text(text)

        assert result["enhanced_text"] == text
        assert "error" in result

    def test_aggressive_but_acceptable_cleaning_passes(self, llm_service):
        text = "x" * 100 + "  garbage  noise  " * 5  # ~190 chars
        cleaned = "x" * 100  # ~52% of input — acceptable
        llm_service.client.chat.completions.create.return_value = _mock_openai_response(cleaned)

        result = llm_service.enhance_text(text)

        assert result["enhanced_text"] == cleaned
        assert "error" not in result

    def test_normal_response_unaffected(self, llm_service):
        text = "Some text with errors that need fixing." * 5
        cleaned = text.replace("errors", "issues")
        llm_service.client.chat.completions.create.return_value = _mock_openai_response(cleaned)

        result = llm_service.enhance_text(text)

        assert result["enhanced_text"] == cleaned
        assert "error" not in result

    def test_empty_input_returns_early_without_calling_llm(self, llm_service):
        result = llm_service.enhance_text("")

        assert result["enhanced_text"] == ""
        assert llm_service.client.chat.completions.create.call_count == 0


class TestLengthGuardConstants:
    """The guard constants are the public contract for callers."""

    def test_floor_is_at_least_a_few_chars(self):
        assert LLM_OUTPUT_MIN_CHARS >= 5

    def test_ratio_is_strict_enough_to_catch_99_percent_truncation(self):
        # 2 chars out of 1000 = 0.002 ratio. Guard must catch this.
        assert LLM_OUTPUT_MIN_RATIO > 0.002
        # But lenient enough to allow real cleaning (typically drops <50% of content).
        assert LLM_OUTPUT_MIN_RATIO <= 0.6


class TestHybridOptimizerLengthGuard:
    """Layer B: HybridOptimizer must reject short enhanced_text from any LLM service."""

    def test_short_enhanced_text_does_not_overwrite_pattern_result(self):
        from primedata.ingestion_pipeline.aird_stages.optimization.hybrid import HybridOptimizer

        text = "Some moderately long input text that should be cleaned. " * 10

        # Mock LLMOptimizationService at the import path used inside HybridOptimizer.
        fake_service = MagicMock()
        fake_service.model = "gpt-4o-mini"
        fake_service.enhance_text.return_value = {
            "enhanced_text": "OK",  # degenerate — must be rejected
            "changes_made": [],
            "cost_estimate": 0.0001,
            "tokens_used": 5,
            "input_tokens": 100,
            "output_tokens": 5,
            # NB: no "error" key — simulates a buggy service that returns short text without flagging it
        }

        with patch(
            "primedata.services.llm_optimization.LLMOptimizationService",
            return_value=fake_service,
        ):
            optimizer = HybridOptimizer()
            result = optimizer.optimize(
                text=text,
                mode="hybrid",
                pattern_flags={},
                llm_config={"api_key": "test", "model": "gpt-4o-mini"},
                quality_threshold=75,
            )

        # The 2-char "OK" must not be adopted as the optimized text.
        assert result["optimized_text"] != "OK"
        assert len(result["optimized_text"]) >= LLM_OUTPUT_MIN_CHARS
