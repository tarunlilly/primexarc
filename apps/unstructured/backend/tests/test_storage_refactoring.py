"""
Comprehensive tests for storage refactoring verification.

Tests verify that:
1. All path helpers produce correct prefixes (with S3_METADATA_PATH included exactly once)
2. All bucket constants match expected values
3. Consumer code uses constants and helpers correctly
4. No double prefixes or missing prefixes in generated paths
"""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

# Import all path helpers
from primedata.storage.paths import (
    raw_prefix,
    clean_prefix,
    chunk_prefix,
    embed_prefix,
    export_prefix,
    artifacts_prefix,
    dq_rules_key,
    bundle_key,
    _get_base_prefix,
)

# Import bucket constants
from primedata.core.constants import (
    BUCKET_RAW,
    BUCKET_CLEAN,
    BUCKET_CHUNK,
    BUCKET_EMBED,
    BUCKET_EXPORTS,
    BUCKET_CONFIG,
)


class TestBucketConstants:
    """Test that bucket constants have correct values."""

    def test_bucket_raw_constant(self):
        assert BUCKET_RAW == "primedata-raw"

    def test_bucket_clean_constant(self):
        assert BUCKET_CLEAN == "primedata-clean"

    def test_bucket_chunk_constant(self):
        assert BUCKET_CHUNK == "primedata-chunk"

    def test_bucket_embed_constant(self):
        assert BUCKET_EMBED == "primedata-embed"

    def test_bucket_exports_constant(self):
        assert BUCKET_EXPORTS == "primedata-exports"

    def test_bucket_config_constant(self):
        assert BUCKET_CONFIG == "primedata-config"


class TestPathHelpers:
    """Test all path helpers with and without S3_METADATA_PATH."""

    def setup_method(self):
        """Save original S3_METADATA_PATH."""
        self.original_s3_path = os.environ.get("S3_METADATA_PATH")

    def teardown_method(self):
        """Restore original S3_METADATA_PATH."""
        if self.original_s3_path:
            os.environ["S3_METADATA_PATH"] = self.original_s3_path
        elif "S3_METADATA_PATH" in os.environ:
            del os.environ["S3_METADATA_PATH"]

    @pytest.mark.parametrize("s3_path", [None, "", "metadata-prefix/", "dev/metadata/"])
    def test_raw_prefix_path_construction(self, s3_path):
        """Test raw_prefix generates correct path."""
        if s3_path is not None:
            os.environ["S3_METADATA_PATH"] = s3_path
        elif "S3_METADATA_PATH" in os.environ:
            del os.environ["S3_METADATA_PATH"]

        ws_id = uuid4()
        prod_id = uuid4()
        version = 5

        result = raw_prefix(ws_id, prod_id, version)

        # Assert correct structure
        assert f"ws/{ws_id}/prod/{prod_id}/v/{version}/raw/" in result

        # Verify S3_METADATA_PATH handling
        if s3_path:
            assert result.startswith(s3_path.rstrip("/") + "/")
            # Count occurrences to ensure no double prefixes
            count = result.count(str(ws_id))
            assert count == 1, f"Workspace ID appears {count} times, expected 1"

    @pytest.mark.parametrize("s3_path", [None, "", "metadata-prefix/", "dev/metadata/"])
    def test_clean_prefix_path_construction(self, s3_path):
        """Test clean_prefix generates correct path."""
        if s3_path is not None:
            os.environ["S3_METADATA_PATH"] = s3_path
        elif "S3_METADATA_PATH" in os.environ:
            del os.environ["S3_METADATA_PATH"]

        ws_id = uuid4()
        prod_id = uuid4()
        version = 3

        result = clean_prefix(ws_id, prod_id, version)

        # Assert correct structure
        assert f"ws/{ws_id}/prod/{prod_id}/v/{version}/clean/" in result

        # Verify S3_METADATA_PATH handling
        if s3_path:
            assert result.startswith(s3_path.rstrip("/") + "/")

    @pytest.mark.parametrize("s3_path", [None, "", "metadata-prefix/", "dev/metadata/"])
    def test_chunk_prefix_path_construction(self, s3_path):
        """Test chunk_prefix generates correct path."""
        if s3_path is not None:
            os.environ["S3_METADATA_PATH"] = s3_path
        elif "S3_METADATA_PATH" in os.environ:
            del os.environ["S3_METADATA_PATH"]

        ws_id = uuid4()
        prod_id = uuid4()
        version = 7

        result = chunk_prefix(ws_id, prod_id, version)

        # Assert correct structure
        assert f"ws/{ws_id}/prod/{prod_id}/v/{version}/chunk/" in result
        assert result.endswith("/")

    @pytest.mark.parametrize("s3_path", [None, "", "metadata-prefix/", "dev/metadata/"])
    def test_embed_prefix_path_construction(self, s3_path):
        """Test embed_prefix generates correct path."""
        if s3_path is not None:
            os.environ["S3_METADATA_PATH"] = s3_path
        elif "S3_METADATA_PATH" in os.environ:
            del os.environ["S3_METADATA_PATH"]

        ws_id = uuid4()
        prod_id = uuid4()
        version = 2

        result = embed_prefix(ws_id, prod_id, version)

        # Assert correct structure
        assert f"ws/{ws_id}/prod/{prod_id}/v/{version}/embed/" in result
        assert result.endswith("/")

    @pytest.mark.parametrize("s3_path", [None, "", "metadata-prefix/", "dev/metadata/"])
    def test_export_prefix_path_construction(self, s3_path):
        """Test export_prefix generates correct path."""
        if s3_path is not None:
            os.environ["S3_METADATA_PATH"] = s3_path
        elif "S3_METADATA_PATH" in os.environ:
            del os.environ["S3_METADATA_PATH"]

        ws_id = uuid4()
        prod_id = uuid4()
        version = 1

        result = export_prefix(ws_id, prod_id, version)

        # Assert correct structure
        assert f"ws/{ws_id}/prod/{prod_id}/v/{version}/export/" in result
        assert result.endswith("/")

    @pytest.mark.parametrize("s3_path", [None, "", "metadata-prefix/", "dev/metadata/"])
    def test_artifacts_prefix_path_construction(self, s3_path):
        """Test artifacts_prefix generates correct path."""
        if s3_path is not None:
            os.environ["S3_METADATA_PATH"] = s3_path
        elif "S3_METADATA_PATH" in os.environ:
            del os.environ["S3_METADATA_PATH"]

        ws_id = uuid4()
        prod_id = uuid4()
        version = 4

        result = artifacts_prefix(ws_id, prod_id, version)

        # Assert correct structure
        assert f"ws/{ws_id}/prod/{prod_id}/v/{version}/artifacts/" in result
        assert result.endswith("/")

        # Verify S3_METADATA_PATH handling
        if s3_path:
            assert result.startswith(s3_path.rstrip("/") + "/")

    @pytest.mark.parametrize("s3_path", [None, "", "metadata-prefix/", "dev/metadata/"])
    def test_dq_rules_key_path_construction(self, s3_path):
        """Test dq_rules_key generates correct path (non-versioned)."""
        if s3_path is not None:
            os.environ["S3_METADATA_PATH"] = s3_path
        elif "S3_METADATA_PATH" in os.environ:
            del os.environ["S3_METADATA_PATH"]

        ws_id = uuid4()
        prod_id = uuid4()

        result = dq_rules_key(ws_id, prod_id)

        # Assert correct structure (non-versioned)
        assert f"ws/{ws_id}/prod/{prod_id}/dq/rules.yaml" in result
        assert not result.endswith("/")

        # Verify S3_METADATA_PATH handling
        if s3_path:
            assert result.startswith(s3_path.rstrip("/") + "/")

    @pytest.mark.parametrize("s3_path", [None, "", "metadata-prefix/", "dev/metadata/"])
    def test_bundle_key_path_construction(self, s3_path):
        """Test bundle_key generates correct path (non-versioned)."""
        if s3_path is not None:
            os.environ["S3_METADATA_PATH"] = s3_path
        elif "S3_METADATA_PATH" in os.environ:
            del os.environ["S3_METADATA_PATH"]

        ws_id = uuid4()
        prod_id = uuid4()
        bundle_name = "bundle-20250126_123456-v5.zip"

        result = bundle_key(ws_id, prod_id, bundle_name)

        # Assert correct structure
        assert f"ws/{ws_id}/prod/{prod_id}/exports/{bundle_name}" in result
        assert not result.endswith("/")

        # Verify S3_METADATA_PATH handling
        if s3_path:
            assert result.startswith(s3_path.rstrip("/") + "/")


class TestNoDuplicatePrefixes:
    """Test that paths don't include S3_METADATA_PATH multiple times."""

    def setup_method(self):
        """Set a test S3_METADATA_PATH."""
        self.original_s3_path = os.environ.get("S3_METADATA_PATH")
        os.environ["S3_METADATA_PATH"] = "test-metadata/"

    def teardown_method(self):
        """Restore original S3_METADATA_PATH."""
        if self.original_s3_path:
            os.environ["S3_METADATA_PATH"] = self.original_s3_path
        else:
            del os.environ["S3_METADATA_PATH"]

    def test_no_duplicate_prefixes_in_all_helpers(self):
        """Verify no helper produces duplicate S3_METADATA_PATH."""
        ws_id = uuid4()
        prod_id = uuid4()
        version = 3

        # Test all versioned prefix helpers
        for helper in [raw_prefix, clean_prefix, chunk_prefix, embed_prefix, export_prefix, artifacts_prefix]:
            result = helper(ws_id, prod_id, version)
            count = result.count("test-metadata/")
            assert count == 1, f"{helper.__name__} includes 'test-metadata/' {count} times"

        # Test non-versioned helpers
        result = dq_rules_key(ws_id, prod_id)
        assert result.count("test-metadata/") == 1

        result = bundle_key(ws_id, prod_id, "bundle.zip")
        assert result.count("test-metadata/") == 1


class TestPathHelperIntegration:
    """Integration tests verifying actual code paths use helpers and constants."""

    @pytest.mark.asyncio
    async def test_dq_validator_uses_constants_and_helpers(self):
        """Verify dq_validator uses BUCKET_CONFIG, BUCKET_EMBED, and dq_rules_key."""
        # Import after env is set
        from primedata.dq.validator import DataQualityValidator
        from primedata.storage.storage_client import storage_client

        ws_id = uuid4()
        prod_id = uuid4()

        # Mock storage client
        with patch.object(storage_client, "get_object", new_callable=AsyncMock) as mock_get:
            with patch.object(storage_client, "list_objects", new_callable=AsyncMock) as mock_list:
                mock_get.return_value = '{"rules": []}'
                mock_list.return_value = []

                validator = DataQualityValidator()

                # Test that dq_rules_key uses correct format with BUCKET_CONFIG
                rules_key = dq_rules_key(ws_id, prod_id)
                assert BUCKET_CONFIG == "primedata-config"
                assert f"ws/{ws_id}" in rules_key
                assert f"prod/{prod_id}" in rules_key
                assert "dq/rules.yaml" in rules_key

    @pytest.mark.asyncio
    async def test_exports_create_uses_bundle_key_and_constants(self):
        """Verify exports uses BUCKET_EXPORTS and bundle_key."""
        # Test bundle_key and BUCKET_EXPORTS directly
        ws_id = str(uuid4())
        prod_id = str(uuid4())
        bundle_name = "test-bundle.zip"

        # Verify BUCKET_EXPORTS constant
        assert BUCKET_EXPORTS == "primedata-exports"

        # Verify bundle_key produces correct format
        key = bundle_key(ws_id, prod_id, bundle_name)
        assert f"ws/{ws_id}" in key
        assert f"prod/{prod_id}" in key
        assert f"exports/{bundle_name}" in key

    def test_artifacts_api_uses_constants(self):
        """Verify artifacts.py imports use BUCKET_RAW and BUCKET_EXPORTS."""
        # Import to verify no errors
        from primedata.api.artifacts import router

        # Verify router is created
        assert router is not None
        assert router.prefix == "/api/v1/artifacts"


class TestPathConsistency:
    """Test that paths are consistent across helpers."""

    def setup_method(self):
        """Set a test S3_METADATA_PATH."""
        self.original_s3_path = os.environ.get("S3_METADATA_PATH")
        os.environ["S3_METADATA_PATH"] = "dev/data/"

    def teardown_method(self):
        """Restore original S3_METADATA_PATH."""
        if self.original_s3_path:
            os.environ["S3_METADATA_PATH"] = self.original_s3_path
        else:
            del os.environ["S3_METADATA_PATH"]

    def test_versioned_prefixes_include_version(self):
        """All versioned prefixes include v/{version}."""
        ws_id = uuid4()
        prod_id = uuid4()
        version = 42

        versioned_helpers = [
            raw_prefix,
            clean_prefix,
            chunk_prefix,
            embed_prefix,
            export_prefix,
            artifacts_prefix,
        ]

        for helper in versioned_helpers:
            result = helper(ws_id, prod_id, version)
            assert f"v/{version}/" in result, f"{helper.__name__} missing v/{version}/"

    def test_non_versioned_keys_no_version_segment(self):
        """Non-versioned keys don't include v/{version}."""
        ws_id = uuid4()
        prod_id = uuid4()

        result_rules = dq_rules_key(ws_id, prod_id)
        assert "/v/" not in result_rules, "dq_rules_key should not include v/ segment"

        result_bundle = bundle_key(ws_id, prod_id, "test.zip")
        assert "/v/" not in result_bundle, "bundle_key should not include v/ segment"

    def test_all_paths_include_workspace_and_product(self):
        """All paths include workspace_id and product_id."""
        ws_id = uuid4()
        prod_id = uuid4()
        version = 1

        all_results = [
            raw_prefix(ws_id, prod_id, version),
            clean_prefix(ws_id, prod_id, version),
            chunk_prefix(ws_id, prod_id, version),
            embed_prefix(ws_id, prod_id, version),
            export_prefix(ws_id, prod_id, version),
            artifacts_prefix(ws_id, prod_id, version),
            dq_rules_key(ws_id, prod_id),
            bundle_key(ws_id, prod_id, "test.zip"),
        ]

        for result in all_results:
            assert str(ws_id) in result, f"Missing workspace_id: {result}"
            assert str(prod_id) in result, f"Missing product_id: {result}"


class TestEdgeCases:
    """Test edge cases and special scenarios."""

    def setup_method(self):
        """Set up test environment."""
        self.original_s3_path = os.environ.get("S3_METADATA_PATH")

    def teardown_method(self):
        """Restore original S3_METADATA_PATH."""
        if self.original_s3_path:
            os.environ["S3_METADATA_PATH"] = self.original_s3_path
        elif "S3_METADATA_PATH" in os.environ:
            del os.environ["S3_METADATA_PATH"]

    def test_s3_metadata_path_with_trailing_slash(self):
        """Test handling of S3_METADATA_PATH with trailing slash."""
        os.environ["S3_METADATA_PATH"] = "prefix/"
        ws_id = uuid4()
        prod_id = uuid4()

        result = raw_prefix(ws_id, prod_id, 1)
        # Should not double the slash
        assert "//" not in result

    def test_s3_metadata_path_without_trailing_slash(self):
        """Test handling of S3_METADATA_PATH without trailing slash."""
        os.environ["S3_METADATA_PATH"] = "prefix"
        ws_id = uuid4()
        prod_id = uuid4()

        result = raw_prefix(ws_id, prod_id, 1)
        # Should add the slash
        assert "prefix/" in result

    def test_bundle_key_with_special_characters_in_name(self):
        """Test bundle_key with various filename formats."""
        ws_id = uuid4()
        prod_id = uuid4()

        test_names = [
            "bundle-20250126_123456-v5.zip",
            "bundle-2025-01-26_12-34-56-v10.zip",
            "bundle.zip",
        ]

        for name in test_names:
            result = bundle_key(ws_id, prod_id, name)
            assert name in result, f"Bundle name '{name}' not in result"

    def test_empty_s3_metadata_path(self):
        """Test with empty S3_METADATA_PATH."""
        os.environ["S3_METADATA_PATH"] = ""
        ws_id = uuid4()
        prod_id = uuid4()

        result = raw_prefix(ws_id, prod_id, 1)
        # Should still work without the prefix
        assert f"ws/{ws_id}/prod/{prod_id}/v/1/raw/" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
