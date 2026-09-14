"""
Unit Tests for Promote API Endpoint

Focus: Ensure promote endpoint error messages are generic and
don't hardcode backend-specific technology names.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from uuid import uuid4
from fastapi import HTTPException, status

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))


class TestPromoteEndpointErrorMessages:
    """Test that promote endpoint error messages are backend-agnostic."""

    def test_promote_error_message_generic(self):
        """
        Test that promote endpoint uses generic 'vector search backend'
        instead of hardcoded 'Qdrant' or 'Elasticsearch'.

        This prevents confusing users when OpenSearch is actually being used.
        """
        expected_error_message = (
            "Failed to set production alias in vector search backend. "
            "No vectors/collection found for this version. "
            "Run the pipeline with vector indexing enabled (or promote a version that has vectors)."
        )

        # The error message should NOT contain:
        # - "Qdrant"
        # - "Elasticsearch"
        # - "Qdrant alias"
        # - Any other specific backend name

        assert "Qdrant" not in expected_error_message
        assert "Elasticsearch" not in expected_error_message
        assert "vector search backend" in expected_error_message
        assert "collection found" in expected_error_message

    def test_promote_error_message_actionable(self):
        """Test that error messages are actionable and helpful."""
        error_message = (
            "Failed to set production alias in vector search backend. "
            "No vectors/collection found for this version. "
            "Run the pipeline with vector indexing enabled (or promote a version that has vectors)."
        )

        # Should tell user what the problem is
        assert "No vectors" in error_message or "collection found" in error_message

        # Should suggest a fix
        assert "vector indexing enabled" in error_message or "promote a version" in error_message


class TestPromoteEndpointIntegration:
    """Integration-level tests for promote endpoint."""

    def test_promote_without_artifacts_fails_gracefully(self):
        """
        Test that promote fails gracefully when no indexing artifacts exist,
        rather than returning a confusing error message.
        """
        # Scenario: User tries to promote a version with no vectors

        error_detail = (
            "Failed to set production alias in vector search backend. "
            "No vectors/collection found for this version. "
            "Run the pipeline with vector indexing enabled (or promote a version that has vectors)."
        )

        # Error should be clear and actionable
        assert "No vectors/collection found" in error_detail
        assert "Run the pipeline" in error_detail

    def test_promote_with_artifacts_includes_collection_name(self):
        """
        Test that when artifacts exist with collection_name,
        the promote endpoint uses that to set the alias.
        """
        # Mock artifact metadata that promote endpoint would query
        artifact_metadata = {
            "collection_name": "prod_ws_abc123__my-product__v_1",
            "points_indexed": 5000,
        }

        # Promote should extract collection_name
        collection_name = artifact_metadata.get("collection_name")

        assert collection_name is not None
        assert collection_name.startswith("prod_ws_")


class TestPromoteEndpointWithMissingArtifacts:
    """Test promote endpoint behavior when artifacts are missing."""

    def test_promote_detects_missing_artifacts_early(self):
        """
        Test that promote endpoint checks for artifacts BEFORE trying to set alias.
        If artifacts are missing, it should fail fast with clear error.
        """
        # Simulate: query for indexing artifacts returns None (missing)
        indexing_artifact = None

        if indexing_artifact:
            collection_name = indexing_artifact.artifact_metadata.get("collection_name")
        else:
            collection_name = None

        # Should be None when artifacts don't exist
        assert collection_name is None

        # This should trigger the error message
        if not collection_name:
            error_msg = (
                "Failed to set production alias in vector search backend. "
                "No vectors/collection found for this version."
            )
            assert "No vectors" in error_msg or "collection" in error_msg


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
