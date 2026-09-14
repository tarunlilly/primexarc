"""
Unit tests for config resolver precedence.

Tests the resolve_effective_config function with all precedence levels.
"""

import pytest

from primedata.config.models import ChunkingConfig, EffectiveConfig
from primedata.config.resolver import resolve_effective_config


class MockProduct:
    """Mock product row for testing."""

    def __init__(self, chunking_config=None, playbook_id=None, workspace_id=None):
        self.chunking_config = chunking_config or {}
        self.playbook_id = playbook_id
        self.workspace_id = workspace_id


def test_precedence_1_run_conf_overrides():
    """Test that run_conf overrides have highest priority."""
    product = MockProduct(
        chunking_config={
            "mode": "manual",
            "manual_settings": {
                "chunk_size": 500,
                "chunk_overlap": 100,
                "chunking_strategy": "semantic",
            },
        }
    )

    run_conf = {
        "chunking_config": {
            "chunk_size": 2000,
            "chunk_overlap": 400,
        }
    }

    result = resolve_effective_config(run_conf, product)

    assert result.chunking_config.chunk_size == 2000
    assert result.chunking_config.chunk_overlap == 400
    assert result.resolution_trace.chunk_size == "run_conf"
    assert result.resolution_trace.chunk_overlap == "run_conf"
    assert result.resolution_trace.chunking_strategy == "product_manual_settings"


def test_precedence_2_force_product_chunking_config():
    """Test that force_product_chunking_config takes precedence over manual settings."""
    product = MockProduct(
        chunking_config={
            "mode": "manual",
            "manual_settings": {
                "chunk_size": 500,
                "chunk_overlap": 100,
            },
        }
    )

    run_conf = {
        "force_product_chunking_config": True,
        "chunking_config": {
            "chunk_size": 800,
        },
    }

    result = resolve_effective_config(run_conf, product)

    # force_product_chunking_config should use product_chunking, but run_conf still overrides
    assert result.chunking_config.chunk_size == 800  # run_conf still wins
    assert result.resolution_trace.chunk_size == "run_conf"


def test_precedence_3_product_manual_settings():
    """Test that product manual settings take precedence over playbook defaults."""
    product = MockProduct(
        chunking_config={
            "mode": "manual",
            "manual_settings": {
                "chunk_size": 1200,
                "chunk_overlap": 300,
                "chunking_strategy": "semantic",
            },
        },
        playbook_id="TECH",
    )

    result = resolve_effective_config({}, product)

    assert result.chunking_config.chunk_size == 1200
    assert result.chunking_config.chunk_overlap == 300
    assert result.chunking_config.chunking_strategy == "semantic"
    assert result.resolution_trace.chunk_size == "product_manual_settings"
    assert result.resolution_trace.chunk_overlap == "product_manual_settings"
    assert result.resolution_trace.chunking_strategy == "product_manual_settings"


def test_precedence_4_playbook_defaults():
    """Test that playbook defaults are used when product settings are not provided."""
    product = MockProduct(playbook_id="TECH")

    result = resolve_effective_config({}, product)

    # Should use playbook defaults or global defaults
    assert result.chunking_config.chunk_size is not None
    assert result.chunking_config.chunk_overlap is not None
    assert result.playbook_id == "TECH"
    # Trace should show playbook_defaults or global_defaults
    assert result.resolution_trace.chunk_size in ["playbook_defaults", "global_default", "content_type_defaults"]


def test_precedence_5_global_defaults():
    """Test that content_type_defaults are used when nothing else is provided."""
    product = MockProduct()

    result = resolve_effective_config({}, product)

    # When no product settings exist, defaults from playbook (content_type_defaults) are used
    assert result.chunking_config.chunk_size is not None
    assert result.chunking_config.chunk_overlap is not None
    assert result.chunking_config.chunking_strategy is not None
    # Resolution trace should indicate content_type_defaults, not global_default
    assert result.resolution_trace.chunk_size == "content_type_defaults"
    assert result.resolution_trace.chunk_overlap == "content_type_defaults"
    assert result.resolution_trace.chunking_strategy == "content_type_defaults"


def test_playbook_id_precedence():
    """Test playbook ID resolution precedence."""
    # Test: run_conf > detected_playbook > product > global default
    product = MockProduct(playbook_id="HEALTHCARE")

    # Case 1: run_conf wins
    result = resolve_effective_config({"playbook_id": "TECH"}, product)
    assert result.playbook_id == "TECH"
    assert result.resolution_trace.playbook_id == "run_conf"

    # Case 2: detected_playbook wins when no run_conf
    result = resolve_effective_config({}, product, detected_playbook="FINANCIAL")
    assert result.playbook_id == "FINANCIAL"
    assert result.resolution_trace.playbook_id == "detected_playbook"

    # Case 3: product wins when no run_conf or detected
    result = resolve_effective_config({}, product)
    assert result.playbook_id == "HEALTHCARE"
    assert result.resolution_trace.playbook_id == "product"

    # Case 4: global default when nothing provided
    product_no_playbook = MockProduct()
    result = resolve_effective_config({}, product_no_playbook)
    assert result.playbook_id == "TECH"  # Global default
    assert result.resolution_trace.playbook_id == "global_default"


def test_resolution_trace_completeness():
    """Test that resolution trace tracks all fields."""
    product = MockProduct(
        chunking_config={
            "manual_settings": {
                "chunk_size": 800,
                "chunk_overlap": 200,
            },
        },
        playbook_id="REGULATORY",
    )

    result = resolve_effective_config({}, product)

    # All trace fields should be set
    assert result.resolution_trace.chunk_size != ""
    assert result.resolution_trace.chunk_overlap != ""
    assert result.resolution_trace.min_chunk_size != ""
    assert result.resolution_trace.max_chunk_size != ""
    assert result.resolution_trace.chunking_strategy != ""
    assert result.resolution_trace.content_type != ""
    assert result.resolution_trace.playbook_id != ""


def test_mixed_precedence_scenario():
    """Test a realistic scenario with mixed precedence levels."""
    product = MockProduct(
        chunking_config={
            "mode": "manual",
            "manual_settings": {
                "chunk_size": 1500,
                "chunk_overlap": 300,
            },
        },
        playbook_id="FINANCIAL",
    )

    run_conf = {
        "chunking_config": {
            "chunk_size": 2000,  # Override
        },
    }

    result = resolve_effective_config(run_conf, product, detected_playbook="LEGAL")

    # chunk_size: run_conf (highest)
    assert result.chunking_config.chunk_size == 2000
    assert result.resolution_trace.chunk_size == "run_conf"

    # chunk_overlap: product_manual_settings (no run_conf override)
    assert result.chunking_config.chunk_overlap == 300
    assert result.resolution_trace.chunk_overlap == "product_manual_settings"

    # playbook_id: run_conf (but we don't have it in run_conf, so detected_playbook)
    # Actually, run_conf doesn't have playbook_id, so detected_playbook wins
    assert result.playbook_id == "LEGAL"
    assert result.resolution_trace.playbook_id == "detected_playbook"


def test_empty_configurations():
    """Test behavior with empty/minimal configurations."""
    product = MockProduct()

    result = resolve_effective_config({}, product)

    # Should fall back to global defaults
    assert isinstance(result, EffectiveConfig)
    assert isinstance(result.chunking_config, ChunkingConfig)
    assert result.chunking_config.chunk_size == 1000
    assert result.chunking_config.chunk_overlap == 200


def test_none_values_handling():
    """Test that None values don't override valid values."""
    product = MockProduct(
        chunking_config={
            "manual_settings": {
                "chunk_size": 1200,
                "chunk_overlap": 250,
            },
        }
    )

    run_conf = {
        "chunking_config": {
            "chunk_size": None,  # None should not override
            "chunk_overlap": 400,
        },
    }

    result = resolve_effective_config(run_conf, product)

    # chunk_size should come from product_manual_settings (None ignored)
    assert result.chunking_config.chunk_size == 1200
    assert result.resolution_trace.chunk_size == "product_manual_settings"

    # chunk_overlap should come from run_conf
    assert result.chunking_config.chunk_overlap == 400
    assert result.resolution_trace.chunk_overlap == "run_conf"
