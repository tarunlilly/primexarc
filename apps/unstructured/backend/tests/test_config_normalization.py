"""
Test config pattern normalization for datasources API.
"""

import pytest
from uuid import uuid4


def test_normalize_inclusion_patterns_string():
    """Test that inclusion_patterns string is converted to include list."""
    from primedata.api.datasources import _normalize_config_patterns

    config = {
        "inclusion_patterns": "*.pdf,*.docx,*.txt",
        "s3_bucket_name": "bucket",
        "s3_region": "us-east-1"
    }

    normalized = _normalize_config_patterns(config)

    assert "inclusion_patterns" not in normalized
    assert normalized["include"] == ["*.pdf", "*.docx", "*.txt"]
    assert normalized["bucket_name"] == "bucket"
    assert normalized["region"] == "us-east-1"
    print("✅ inclusion_patterns string converted to include list")


def test_normalize_exclusion_patterns_string():
    """Test that exclusion_patterns string is converted to exclude list."""
    from primedata.api.datasources import _normalize_config_patterns

    config = {
        "exclusion_patterns": "*.tmp,*.log,*.bak",
        "bucket_name": "bucket"
    }

    normalized = _normalize_config_patterns(config)

    assert "exclusion_patterns" not in normalized
    assert normalized["exclude"] == ["*.tmp", "*.log", "*.bak"]
    print("✅ exclusion_patterns string converted to exclude list")


def test_normalize_with_spaces():
    """Test that patterns with spaces are trimmed."""
    from primedata.api.datasources import _normalize_config_patterns

    config = {
        "inclusion_patterns": "*.pdf , *.docx , *.txt",
    }

    normalized = _normalize_config_patterns(config)

    assert normalized["include"] == ["*.pdf", "*.docx", "*.txt"]
    print("✅ Spaces in patterns are trimmed")


def test_normalize_s3_field_names():
    """Test that S3 field names are normalized."""
    from primedata.api.datasources import _normalize_config_patterns

    config = {
        "s3_bucket_name": "primedata-dev",
        "s3_region": "us-east-2",
        "s3_prefix": "sample_test4/",
        "inclusion_patterns": "*.pdf"
    }

    normalized = _normalize_config_patterns(config)

    assert "s3_bucket_name" not in normalized
    assert "s3_region" not in normalized
    assert "s3_prefix" not in normalized
    assert normalized["bucket_name"] == "primedata-dev"
    assert normalized["region"] == "us-east-2"
    assert normalized["prefix"] == "sample_test4/"
    assert normalized["include"] == ["*.pdf"]
    print("✅ S3 field names normalized (s3_* → *)")


def test_normalize_removes_zone_type():
    """Test that zone_type is removed (not used by connectors)."""
    from primedata.api.datasources import _normalize_config_patterns

    config = {
        "zone_type": "refine_zone",
        "bucket_name": "bucket"
    }

    normalized = _normalize_config_patterns(config)

    assert "zone_type" not in normalized
    assert normalized["bucket_name"] == "bucket"
    print("✅ zone_type removed")


def test_normalize_empty_patterns():
    """Test that empty patterns are handled."""
    from primedata.api.datasources import _normalize_config_patterns

    config = {
        "inclusion_patterns": "",
        "exclusion_patterns": ""
    }

    normalized = _normalize_config_patterns(config)

    assert normalized["include"] == []
    assert normalized["exclude"] == []
    print("✅ Empty patterns handled correctly")


def test_normalize_all_fields():
    """Test complete normalization with all fields."""
    from primedata.api.datasources import _normalize_config_patterns

    config = {
        "workspace_id": "ws123",
        "zone_type": "refine_zone",
        "s3_bucket_name": "primedata-dev",
        "s3_region": "us-east-2",
        "s3_prefix": "sample_test4/",
        "inclusion_patterns": "*.pdf,*.docx",
        "exclusion_patterns": "*.tmp,*.log",
        "max_file_size": 104857600
    }

    normalized = _normalize_config_patterns(config)

    # Check removed fields
    assert "s3_bucket_name" not in normalized
    assert "s3_region" not in normalized
    assert "s3_prefix" not in normalized
    assert "zone_type" not in normalized
    assert "inclusion_patterns" not in normalized
    assert "exclusion_patterns" not in normalized

    # Check renamed fields
    assert normalized["bucket_name"] == "primedata-dev"
    assert normalized["region"] == "us-east-2"
    assert normalized["prefix"] == "sample_test4/"

    # Check converted patterns
    assert normalized["include"] == ["*.pdf", "*.docx"]
    assert normalized["exclude"] == ["*.tmp", "*.log"]

    # Check preserved fields
    assert normalized["workspace_id"] == "ws123"
    assert normalized["max_file_size"] == 104857600

    print("✅ Complete normalization successful")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
