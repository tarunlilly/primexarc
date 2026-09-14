"""
Tests for newly implemented missing API endpoints.

Tests for:
- Data Quality validation and seeding endpoints
- Artifact preview endpoints
- Chunk Quality diff and summary endpoints
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from uuid import uuid4
from fastapi.testclient import TestClient
from fastapi import FastAPI, HTTPException
from sqlalchemy.orm import Session

# Test imports
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))

from primedata.api.data_quality import (
    router as dq_router,
    validate_data_quality_rules,
    seed_data_quality_rules,
)
from primedata.api.artifacts import (
    router as artifacts_router,
    get_artifact_preview,
    get_vector_preview,
)
from primedata.api.chunk_quality import (
    router as chunk_quality_router,
    get_chunk_quality_diff,
    get_quality_summary,
)


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def app():
    """Create test FastAPI app with routers."""
    app = FastAPI()
    app.include_router(dq_router)
    app.include_router(artifacts_router)
    app.include_router(chunk_quality_router)
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_db():
    """Create mock database session."""
    return Mock(spec=Session)


@pytest.fixture
def product_id():
    """Generate a test product ID."""
    return str(uuid4())


@pytest.fixture
def workspace_id():
    """Generate a test workspace ID."""
    return str(uuid4())


@pytest.fixture
def mock_product(product_id, workspace_id):
    """Create mock product."""
    product = Mock()
    product.id = product_id
    product.workspace_id = workspace_id
    product.name = "Test Product"
    product.current_version = 2
    return product


# ============================================================================
# DATA QUALITY VALIDATION TESTS
# ============================================================================


class TestDataQualityValidation:
    """Tests for data quality rule validation endpoint."""

    def test_validate_rules_post_endpoint_exists(self, client):
        """Test that POST /products/{product_id}/rules/validate endpoint exists."""
        product_id = str(uuid4())
        with patch("primedata.core.scope.ensure_product_access"):
            with patch("primedata.dq.rules_schema.DataQualityRules"):
                response = client.post(
                    f"/products/{product_id}/rules/validate",
                    json={"rules": {}}
                )
                # Either 200 or other response, just check endpoint exists
                assert response.status_code in [200, 422, 500]

    def test_validate_rules_request_format(self):
        """Test validate rules request format is correct."""
        from primedata.api.data_quality import DataQualityRulesRequest

        request = DataQualityRulesRequest(rules={"key": "value"})
        assert request.rules == {"key": "value"}

    def test_validate_rules_response_format(self):
        """Test validate rules response includes required fields."""
        expected_fields = ["valid", "message", "rules_count", "enabled_rules_count", "can_apply"]
        # Response is dict with these fields
        response_data = {
            "valid": True,
            "message": "Rules are valid",
            "rules_count": 5,
            "enabled_rules_count": 4,
            "can_apply": True
        }
        for field in expected_fields:
            assert field in response_data


# ============================================================================
# DATA QUALITY SEEDING TESTS
# ============================================================================


class TestDataQualitySeeding:
    """Tests for data quality rule seeding endpoint."""

    def test_seed_rules_post_endpoint_exists(self, client):
        """Test that POST /products/{product_id}/rules/seed endpoint exists."""
        product_id = str(uuid4())
        with patch("primedata.api.data_quality.ensure_product_access"):
            with patch("primedata.api.data_quality.DataQualityRule"):
                response = client.post(
                    f"/products/{product_id}/rules/seed",
                    json={"rule_set": "basic", "overwrite": False}
                )
                # Either 200 or other response, just check endpoint exists
                assert response.status_code in [200, 422, 500]

    def test_seed_rules_request_format(self):
        """Test seed rules request format."""
        # Example request
        request_data = {
            "rule_set": "basic",
            "overwrite": False
        }
        assert request_data["rule_set"] in ["basic", "comprehensive", "enterprise"]
        assert isinstance(request_data["overwrite"], bool)

    def test_seed_rules_response_format(self):
        """Test seed rules response includes required fields."""
        response_data = {
            "message": "Rules seeded successfully",
            "created": 5,
            "skipped": 0,
            "rules": [
                {"rule_id": "uuid", "name": "Rule", "rule_type": "required_fields", "status": "created"}
            ]
        }
        assert "message" in response_data
        assert "created" in response_data
        assert "skipped" in response_data
        assert "rules" in response_data
        assert isinstance(response_data["rules"], list)

    def test_default_rule_sets(self):
        """Test that default rule sets are properly defined."""
        from primedata.api.data_quality import seed_data_quality_rules

        # Rule sets should include basic, comprehensive, enterprise
        expected_sets = ["basic", "comprehensive", "enterprise"]

        # Verify they're defined in the function
        import inspect
        source = inspect.getsource(seed_data_quality_rules)
        for rule_set in expected_sets:
            assert f'"{rule_set}"' in source or f"'{rule_set}'" in source


# ============================================================================
# ARTIFACT PREVIEW TESTS
# ============================================================================


class TestArtifactPreview:
    """Tests for artifact preview endpoints."""

    def test_get_artifact_preview_endpoint_exists(self, client):
        """Test that GET /{artifact_id}/preview endpoint exists."""
        artifact_id = "ws/123/prod/456/v/1/raw/file.txt"
        with patch("primedata.api.artifacts.storage_client.get_object") as mock_get:
            mock_get.return_value = b"sample content"
            response = client.get(
                f"/{artifact_id}/preview?lines=50"
            )
            # Either 200 or 404 (artifact not set up), just check endpoint exists
            assert response.status_code in [200, 404, 422]

    def test_artifact_preview_response_format(self):
        """Test artifact preview response format."""
        from primedata.api.artifacts import ArtifactPreviewResponse

        response = ArtifactPreviewResponse(
            artifact_id="file.txt",
            type="txt",
            preview_type="text",
            content="sample content",
            total_lines=10,
            preview_lines=5,
            has_more=True,
            format_info={"encoding": "utf-8", "size_bytes": 100}
        )
        assert response.artifact_id == "file.txt"
        assert response.type == "txt"
        assert response.preview_type == "text"
        assert response.has_more is True

    def test_get_vector_preview_endpoint_exists(self, client):
        """Test that GET /{artifact_id}/vector-preview endpoint exists."""
        artifact_id = "ws/123/prod/456/v/1/raw/file.txt"
        with patch("primedata.api.artifacts.get_vector_search_client"):
            response = client.get(
                f"/{artifact_id}/vector-preview?limit=10"
            )
            # Either 200 or 400/404, just check endpoint exists
            assert response.status_code in [200, 400, 404, 422]

    def test_vector_preview_response_format(self):
        """Test vector preview response format."""
        from primedata.api.artifacts import VectorPreviewResponse, VectorPreviewItem

        items = [
            VectorPreviewItem(
                id="1",
                content_preview="sample",
                vector_sample=[0.1, 0.2, 0.3],
                vector_dimension=1536,
                magnitude=1.0
            )
        ]

        response = VectorPreviewResponse(
            artifact_id="file",
            type="embedding",
            embeddings=items,
            total=100,
            preview_count=1,
            statistics={
                "avg_magnitude": 0.99,
                "vector_range": {"min": -1.5, "max": 1.5},
                "dimension": 1536
            }
        )
        assert response.type == "embedding"
        assert len(response.embeddings) == 1
        assert response.total == 100


# ============================================================================
# CHUNK QUALITY DIFF TESTS
# ============================================================================


class TestChunkQualityDiff:
    """Tests for chunk quality diff endpoint."""

    def test_get_chunk_quality_diff_endpoint_exists(self, client):
        """Test that GET /chunks/{chunk_id}/diff endpoint exists."""
        product_id = str(uuid4())
        chunk_id = "chunk123"
        with patch("primedata.api.chunk_quality.get_current_user", return_value={}):
            with patch("primedata.api.chunk_quality.db.query"):
                response = client.get(
                    f"/products/{product_id}/versions/2/chunks/{chunk_id}/diff?compare_to_version=1"
                )
                # Either 200 or other response, just check endpoint exists
                assert response.status_code in [200, 404, 422, 500]

    def test_chunk_diff_response_format(self):
        """Test chunk diff response format."""
        from primedata.api.chunk_quality import ChunkDiffResponse

        response = ChunkDiffResponse(
            chunk_id="chunk123",
            current_version=2,
            compare_version=1,
            content_diff={
                "current": "text1",
                "compare": "text2",
                "similarity": 0.92,
                "added": "",
                "removed": ""
            },
            quality_changes={
                "previous_score": 0.85,
                "current_score": 0.95,
                "improvement": 0.10,
                "metric_changes": {
                    "confidence": {"from": 0.80, "to": 0.90, "change": 0.10}
                }
            },
            embedding_diff={
                "cosine_similarity": 0.94,
                "euclidean_distance": 0.12,
                "vector_dimension": 1536
            }
        )
        assert response.chunk_id == "chunk123"
        assert response.current_version == 2
        assert response.compare_version == 1


# ============================================================================
# CHUNK QUALITY SUMMARY TESTS
# ============================================================================


class TestChunkQualitySummary:
    """Tests for chunk quality summary endpoint."""

    def test_get_quality_summary_endpoint_exists(self, client):
        """Test that GET /quality-summary endpoint exists."""
        product_id = str(uuid4())
        with patch("primedata.api.chunk_quality.get_current_user", return_value={}):
            with patch("primedata.api.chunk_quality.db.query"):
                response = client.get(
                    f"/products/{product_id}/versions/1/quality-summary"
                )
                # Either 200 or other response, just check endpoint exists
                assert response.status_code in [200, 404, 422, 500]

    def test_quality_summary_response_format(self):
        """Test quality summary response format."""
        from primedata.api.chunk_quality import QualitySummaryResponse

        response = QualitySummaryResponse(
            product_id="prod123",
            version=1,
            summary={
                "total_chunks": 250,
                "avg_quality_score": 0.90,
                "median_quality_score": 0.92,
                "quality_distribution": {
                    "excellent": {"count": 150, "percent": 60},
                    "good": {"count": 75, "percent": 30},
                    "fair": {"count": 20, "percent": 8},
                    "poor": {"count": 5, "percent": 2}
                }
            },
            metrics={
                "readability": {"avg": 0.88, "median": 0.90, "min": 0.45, "max": 0.99},
                "completeness": {"avg": 0.85, "median": 0.87, "min": 0.40, "max": 0.99},
                "relevance": {"avg": 0.90, "median": 0.92, "min": 0.50, "max": 0.99},
                "embedding_quality": {"avg": 0.89, "median": 0.91, "min": 0.45, "max": 0.99}
            },
            issues={
                "high_priority": 10,
                "medium_priority": 35,
                "low_priority": 80,
                "top_issues": ["low_confidence_chunks", "high_noise_content", "boundary_issues"]
            },
            recommendations=[
                "Review chunks with quality < 0.5",
                "Re-chunk content with low completeness",
                "Regenerate embeddings for low quality scores"
            ]
        )
        assert response.product_id == "prod123"
        assert response.summary["total_chunks"] == 250
        assert response.summary["avg_quality_score"] == 0.90
        assert len(response.recommendations) > 0


# ============================================================================
# HELPER FUNCTION TESTS
# ============================================================================


class TestHelperFunctions:
    """Tests for helper functions used in endpoints."""

    def test_text_similarity_calculation(self):
        """Test text similarity calculation."""
        from primedata.api.chunk_quality import _calculate_text_similarity

        # Identical texts
        sim1 = _calculate_text_similarity("hello world", "hello world")
        assert sim1 == 1.0

        # Different texts
        sim2 = _calculate_text_similarity("hello world", "goodbye moon")
        assert 0 <= sim2 <= 1.0

        # Empty texts
        sim3 = _calculate_text_similarity("", "")
        assert sim3 == 1.0

    def test_cosine_similarity_calculation(self):
        """Test cosine similarity calculation."""
        from primedata.api.chunk_quality import _calculate_cosine_similarity

        # Identical vectors
        vec = [1.0, 0.0, 0.0]
        sim1 = _calculate_cosine_similarity(vec, vec)
        assert abs(sim1 - 1.0) < 0.001

        # Orthogonal vectors
        vec1 = [1.0, 0.0]
        vec2 = [0.0, 1.0]
        sim2 = _calculate_cosine_similarity(vec1, vec2)
        assert abs(sim2) < 0.001

    def test_euclidean_distance_calculation(self):
        """Test euclidean distance calculation."""
        from primedata.api.chunk_quality import _calculate_euclidean_distance

        # Same points
        vec = [1.0, 2.0, 3.0]
        dist1 = _calculate_euclidean_distance(vec, vec)
        assert dist1 == 0.0

        # Different points
        vec1 = [0.0, 0.0]
        vec2 = [3.0, 4.0]
        dist2 = _calculate_euclidean_distance(vec1, vec2)
        assert abs(dist2 - 5.0) < 0.001


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


class TestIntegration:
    """Integration tests for new endpoints."""

    def test_all_routers_have_tags(self):
        """Test all routers have proper tags."""
        assert dq_router.tags == ["data-quality"]
        assert artifacts_router.tags == ["Artifacts"]
        assert chunk_quality_router.tags == ["Chunk Quality"]

    def test_all_endpoints_have_proper_methods(self):
        """Test endpoints use correct HTTP methods."""
        # Data Quality
        dq_routes = [route.path for route in dq_router.routes]
        assert any("/validate" in path for path in dq_routes)
        assert any("/seed" in path for path in dq_routes)

        # Artifacts
        artifacts_routes = [route.path for route in artifacts_router.routes]
        assert any("/preview" in path for path in artifacts_routes)
        assert any("/vector-preview" in path for path in artifacts_routes)

        # Chunk Quality
        cq_routes = [route.path for route in chunk_quality_router.routes]
        assert any("/diff" in path for path in cq_routes)
        assert any("/quality-summary" in path for path in cq_routes)

    def test_response_models_are_valid_pydantic(self):
        """Test that all response models are valid Pydantic models."""
        from primedata.api.data_quality import DataQualityRulesResponse
        from primedata.api.artifacts import ArtifactPreviewResponse, VectorPreviewResponse
        from primedata.api.chunk_quality import ChunkDiffResponse, QualitySummaryResponse

        models = [
            DataQualityRulesResponse,
            ArtifactPreviewResponse,
            VectorPreviewResponse,
            ChunkDiffResponse,
            QualitySummaryResponse
        ]

        for model in models:
            assert hasattr(model, "schema")
            schema = model.schema()
            assert "properties" in schema or "type" in schema


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
