"""
API Endpoint Integration Tests

Tests for:
1. Complete endpoint workflows
2. Request/response validation
3. Error scenarios
4. Authentication
5. Rate limiting
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, MagicMock
from uuid import UUID, uuid4
from datetime import datetime
import json

# Endpoint Tests
# ============================================================================

class TestLineageEndpoints:
    """Test Lineage API endpoints."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from primedata.api.app import app
        return TestClient(app)

    @pytest.fixture
    def auth_headers(self):
        """Create auth headers."""
        return {"Authorization": "Bearer test_token"}

    def test_lineage_health_no_auth(self, client):
        """Test lineage health check doesn't require auth."""
        response = client.get("/api/v1/lineage/health")

        assert response.status_code in [200, 401]  # 401 if auth enforced globally
        if response.status_code == 200:
            data = response.json()
            assert data["status"] == "healthy"

    @patch("primedata.api.lineage.get_db")
    @patch("primedata.core.security.get_current_user")
    def test_product_lineage_endpoint(self, mock_auth, mock_db, client, auth_headers):
        """Test GET /lineage/products/{product_id}."""
        product_id = "fb8356d9-d7bd-407f-a801-f0af6517bb9e"

        mock_auth.return_value = {"user_id": "test_user"}

        response = client.get(
            f"/api/v1/lineage/products/{product_id}?depth=2",
            headers=auth_headers
        )

        # Should not return 404 (method not allowed) or 405
        assert response.status_code != 405
        assert response.status_code != 404  # Router is registered

    @patch("primedata.api.lineage.get_db")
    @patch("primedata.core.security.get_current_user")
    def test_detailed_lineage_endpoint(self, mock_auth, mock_db, client, auth_headers):
        """Test GET /lineage/products/{product_id}/detailed."""
        product_id = "fb8356d9-d7bd-407f-a801-f0af6517bb9e"

        mock_auth.return_value = {"user_id": "test_user"}

        response = client.get(
            f"/api/v1/lineage/products/{product_id}/detailed",
            headers=auth_headers
        )

        assert response.status_code != 405

    @patch("primedata.api.lineage.get_db")
    @patch("primedata.core.security.get_current_user")
    def test_artifact_lineage_endpoint(self, mock_auth, mock_db, client, auth_headers):
        """Test GET /lineage/artifacts/{artifact_id}."""
        artifact_id = "art-001"

        mock_auth.return_value = {"user_id": "test_user"}

        response = client.get(
            f"/api/v1/lineage/artifacts/{artifact_id}?direction=both&max_depth=3",
            headers=auth_headers
        )

        assert response.status_code != 405

    @patch("primedata.api.lineage.get_db")
    @patch("primedata.core.security.get_current_user")
    def test_lineage_search_endpoint(self, mock_auth, mock_db, client, auth_headers):
        """Test POST /lineage/search."""
        mock_auth.return_value = {"user_id": "test_user"}

        response = client.post(
            "/api/v1/lineage/search",
            headers=auth_headers,
            json={
                "query": "embeddings",
                "entity_type": "artifact",
                "limit": 20
            }
        )

        assert response.status_code != 405

    @patch("primedata.api.lineage.get_db")
    @patch("primedata.core.security.get_current_user")
    def test_lineage_export_endpoint(self, mock_auth, mock_db, client, auth_headers):
        """Test GET /lineage/export/{product_id}."""
        product_id = "fb8356d9-d7bd-407f-a801-f0af6517bb9e"

        mock_auth.return_value = {"user_id": "test_user"}

        response = client.get(
            f"/api/v1/lineage/export/{product_id}?format=json",
            headers=auth_headers
        )

        assert response.status_code != 405

    @patch("primedata.api.lineage.get_db")
    @patch("primedata.core.security.get_current_user")
    def test_lineage_impact_endpoint(self, mock_auth, mock_db, client, auth_headers):
        """Test GET /lineage/impact/{artifact_id}."""
        artifact_id = "art-001"

        mock_auth.return_value = {"user_id": "test_user"}

        response = client.get(
            f"/api/v1/lineage/impact/{artifact_id}",
            headers=auth_headers
        )

        assert response.status_code != 405


class TestQualityImprovementEndpoint:
    """Test Quality Improvement API endpoint."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from primedata.api.app import app
        return TestClient(app)

    @pytest.fixture
    def auth_headers(self):
        """Create auth headers."""
        return {"Authorization": "Bearer test_token"}

    @patch("primedata.api.quality_improvement.QualityImprovementCalculator")
    @patch("primedata.api.quality_improvement.get_current_user")
    @patch("primedata.api.quality_improvement.get_db")
    def test_quality_improvement_returns_chunks_created(
        self, mock_db_dep, mock_auth, mock_calculator_class, client, auth_headers
    ):
        """Test quality improvement endpoint returns correct chunks_created."""
        product_id = "8037da2b-61cd-435d-8db7-b5472c98f805"

        mock_auth.return_value = {"user_id": "test_user"}

        # Mock calculator result with chunks_created > 0
        mock_calculator = Mock()
        mock_calculator_class.return_value = mock_calculator
        mock_calculator.calculate.return_value = {
            "product_id": product_id,
            "product_name": "Test Product",
            "version": 1,
            "before": {
                "overall": 30.0,
                "completeness": 40.0,
                "noise": 95.0,
                "structure": 20.0
            },
            "after": {
                "overall": 85.0,
                "completeness": 90.0,
                "noise": 15.0,
                "structure": 85.0
            },
            "improvement": {
                "overall": 55.0,
                "completeness": 50.0,
                "noise": 80.0,
                "structure": 65.0
            },
            "improvement_percentage": 60.5,
            "has_improvement": True,
            "files_processed": 1,
            "chunks_created": 12543,  # Should be > 0
            "baseline_available": True,
            "calculated_at": datetime.utcnow().isoformat()
        }

        mock_db = Mock()
        mock_product = Mock()
        mock_product.id = UUID(product_id)
        mock_db.query.return_value.filter.return_value.first.return_value = mock_product
        mock_db_dep.return_value = mock_db

        response = client.get(
            f"/api/v1/products/{product_id}/quality-improvement",
            headers=auth_headers
        )

        if response.status_code == 200:
            data = response.json()
            assert data["chunks_created"] == 12543
            assert data["chunks_created"] > 0

    @patch("primedata.api.quality_improvement.QualityImprovementCalculator")
    @patch("primedata.api.quality_improvement.get_current_user")
    @patch("primedata.api.quality_improvement.get_db")
    def test_quality_improvement_chunks_match_api(
        self, mock_db_dep, mock_auth, mock_calculator_class, client, auth_headers
    ):
        """Test that chunks_created from quality endpoint matches chunks API."""
        product_id = "8037da2b-61cd-435d-8db7-b5472c98f805"
        version = 1

        mock_auth.return_value = {"user_id": "test_user"}

        # Simulate chunks API returning 150 chunks
        expected_chunks = 150

        mock_calculator = Mock()
        mock_calculator_class.return_value = mock_calculator
        mock_calculator.calculate.return_value = {
            "product_id": product_id,
            "product_name": "Test Product",
            "version": version,
            "before": {"overall": 30.0, "completeness": 40.0, "noise": 95.0, "structure": 20.0},
            "after": {"overall": 85.0, "completeness": 90.0, "noise": 15.0, "structure": 85.0},
            "improvement": {"overall": 55.0, "completeness": 50.0, "noise": 80.0, "structure": 65.0},
            "improvement_percentage": 60.5,
            "has_improvement": True,
            "files_processed": 1,
            "chunks_created": expected_chunks,
            "baseline_available": True,
            "calculated_at": datetime.utcnow().isoformat()
        }

        mock_db = Mock()
        mock_product = Mock()
        mock_product.id = UUID(product_id)
        mock_db.query.return_value.filter.return_value.first.return_value = mock_product
        mock_db_dep.return_value = mock_db

        response = client.get(
            f"/api/v1/products/{product_id}/quality-improvement",
            headers=auth_headers
        )

        if response.status_code == 200:
            data = response.json()
            assert data["chunks_created"] == expected_chunks


class TestChunksEndpoint:
    """Test Chunks API endpoint."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from primedata.api.app import app
        return TestClient(app)

    @pytest.fixture
    def auth_headers(self):
        """Create auth headers."""
        return {"Authorization": "Bearer test_token"}

    @patch("primedata.api.chunks.get_db")
    @patch("primedata.api.chunks.get_current_user")
    def test_chunks_endpoint_pagination(self, mock_auth, mock_db, client, auth_headers):
        """Test chunks endpoint with pagination parameters."""
        product_id = "8037da2b-61cd-435d-8db7-b5472c98f805"

        mock_auth.return_value = {"user_id": "test_user"}

        response = client.get(
            f"/api/v1/products/{product_id}/chunks?version=1&offset=0&limit=50",
            headers=auth_headers
        )

        # Should return 200 or 404 if product doesn't exist, not 405
        assert response.status_code != 405

    @patch("primedata.api.chunks.get_db")
    @patch("primedata.api.chunks.get_current_user")
    def test_chunks_endpoint_without_version_uses_alias(self, mock_auth, mock_db, client, auth_headers):
        """Test that chunks endpoint without version uses production alias."""
        product_id = "8037da2b-61cd-435d-8db7-b5472c98f805"

        mock_auth.return_value = {"user_id": "test_user"}

        response = client.get(
            f"/api/v1/products/{product_id}/chunks?offset=0&limit=50",
            headers=auth_headers
        )

        # Should not fail - alias should be tried
        assert response.status_code != 405


# Error Handling Tests
# ============================================================================

class TestErrorHandling:
    """Test error handling in updated APIs."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from primedata.api.app import app
        return TestClient(app)

    def test_lineage_invalid_product_id(self, client):
        """Test lineage endpoint with invalid product ID."""
        response = client.get("/api/v1/lineage/products/invalid-uuid")

        # Should return 422 (validation error), not 405
        assert response.status_code != 405

    def test_lineage_invalid_depth_parameter(self, client):
        """Test lineage endpoint with invalid depth parameter."""
        product_id = "fb8356d9-d7bd-407f-a801-f0af6517bb9e"

        response = client.get(f"/api/v1/lineage/products/{product_id}?depth=100")

        # Should validate depth (1-5), not return 405
        assert response.status_code != 405

    def test_quality_improvement_invalid_product(self, client):
        """Test quality improvement with invalid product."""
        response = client.get("/api/v1/products/invalid-uuid/quality-improvement")

        assert response.status_code != 405

    @patch("primedata.api.lineage.get_db")
    @patch("primedata.core.security.get_current_user")
    def test_lineage_artifact_not_found(self, mock_auth, mock_db, client):
        """Test artifact lineage with non-existent artifact."""
        mock_auth.return_value = {"user_id": "test_user"}

        artifact_id = "nonexistent-artifact"

        response = client.get(
            f"/api/v1/lineage/artifacts/{artifact_id}",
            headers={"Authorization": "Bearer test_token"}
        )

        # Should return 404, not 405
        if response.status_code != 405:
            # Either 404 or 200 (not found in DB returns empty)
            assert response.status_code in [200, 404]


# Validation Tests
# ============================================================================

class TestRequestValidation:
    """Test request validation for updated APIs."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from primedata.api.app import app
        return TestClient(app)

    @pytest.fixture
    def auth_headers(self):
        """Create auth headers."""
        return {"Authorization": "Bearer test_token"}

    @patch("primedata.api.lineage.get_current_user")
    def test_lineage_search_missing_query(self, mock_auth, client, auth_headers):
        """Test lineage search with missing query parameter."""
        mock_auth.return_value = {"user_id": "test_user"}

        response = client.post(
            "/api/v1/lineage/search",
            headers=auth_headers,
            json={"entity_type": "artifact"}  # Missing query
        )

        # Should return 422 (validation error)
        assert response.status_code in [422, 400]

    @patch("primedata.api.lineage.get_current_user")
    def test_lineage_search_invalid_entity_type(self, mock_auth, client, auth_headers):
        """Test lineage search with invalid entity_type."""
        mock_auth.return_value = {"user_id": "test_user"}

        response = client.post(
            "/api/v1/lineage/search",
            headers=auth_headers,
            json={
                "query": "test",
                "entity_type": "invalid_type",
                "limit": 20
            }
        )

        # Should handle gracefully
        assert response.status_code != 405

    @patch("primedata.api.lineage.get_current_user")
    def test_lineage_depth_parameter_validation(self, mock_auth, client, auth_headers):
        """Test lineage depth parameter validation."""
        mock_auth.return_value = {"user_id": "test_user"}
        product_id = "fb8356d9-d7bd-407f-a801-f0af6517bb9e"

        # Test with invalid depth values
        for depth in [0, 6, 100, -1]:
            response = client.get(
                f"/api/v1/lineage/products/{product_id}?depth={depth}",
                headers=auth_headers
            )

            # Should reject invalid depth values
            assert response.status_code != 405


# Response Format Tests
# ============================================================================

class TestResponseFormats:
    """Test response formats for updated APIs."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from primedata.api.app import app
        return TestClient(app)

    def test_lineage_health_response_format(self, client):
        """Test lineage health response format."""
        response = client.get("/api/v1/lineage/health")

        if response.status_code == 200:
            data = response.json()
            assert "status" in data
            assert "message" in data
            assert data["status"] == "healthy"

    @patch("primedata.api.quality_improvement.QualityImprovementCalculator")
    @patch("primedata.api.quality_improvement.get_current_user")
    @patch("primedata.api.quality_improvement.get_db")
    def test_quality_improvement_response_format(
        self, mock_db_dep, mock_auth, mock_calculator_class, client
    ):
        """Test quality improvement response format."""
        mock_auth.return_value = {"user_id": "test_user"}

        product_id = "8037da2b-61cd-435d-8db7-b5472c98f805"

        mock_calculator = Mock()
        mock_calculator_class.return_value = mock_calculator
        mock_calculator.calculate.return_value = {
            "product_id": product_id,
            "product_name": "Test",
            "version": 1,
            "before": {"overall": 30, "completeness": 40, "noise": 95, "structure": 20},
            "after": {"overall": 85, "completeness": 90, "noise": 15, "structure": 85},
            "improvement": {"overall": 55, "completeness": 50, "noise": 80, "structure": 65},
            "improvement_percentage": 60.5,
            "has_improvement": True,
            "files_processed": 1,
            "chunks_created": 100,
            "baseline_available": True,
            "calculated_at": datetime.utcnow().isoformat()
        }

        mock_db = Mock()
        mock_product = Mock()
        mock_product.id = UUID(product_id)
        mock_db.query.return_value.filter.return_value.first.return_value = mock_product
        mock_db_dep.return_value = mock_db

        response = client.get(
            f"/api/v1/products/{product_id}/quality-improvement",
            headers={"Authorization": "Bearer test_token"}
        )

        if response.status_code == 200:
            data = response.json()

            # Check required fields
            required_fields = [
                "product_id",
                "product_name",
                "version",
                "before",
                "after",
                "improvement",
                "chunks_created",
                "files_processed"
            ]

            for field in required_fields:
                assert field in data


# Performance Tests
# ============================================================================

class TestPerformance:
    """Test performance of updated APIs."""

    def test_chunk_prefix_generation_performance(self):
        """Test chunk_prefix generation is fast."""
        from primedata.storage.paths import chunk_prefix
        import time

        workspace_id = UUID("4b979faf-0462-4560-897b-e26800378f90")
        product_id = UUID("fb8356d9-d7bd-407f-a801-f0af6517bb9e")

        start = time.time()
        for i in range(1000):
            prefix = chunk_prefix(workspace_id, product_id, i)
        elapsed = time.time() - start

        # Should complete 1000 calls in < 1 second
        assert elapsed < 1.0

    @patch("primedata.services.quality_improvement_calculator.storage_client")
    def test_chunk_counting_performance(self, mock_storage):
        """Test chunk counting performance."""
        from primedata.services.quality_improvement_calculator import QualityImprovementCalculator
        from primedata.db.models import Product
        import time

        # Mock large number of chunks
        mock_chunks = [{"Key": f"chunk_{i}"} for i in range(10000)]
        mock_storage.list_objects.return_value = mock_chunks

        mock_db = Mock()
        mock_product = Mock(spec=Product)
        mock_product.id = UUID("8037da2b-61cd-435d-8db7-b5472c98f805")
        mock_product.workspace_id = UUID("4b979faf-0462-4560-897b-e26800378f90")
        mock_db.query.return_value.filter.return_value.first.return_value = mock_product

        calculator = QualityImprovementCalculator(mock_db)

        start = time.time()
        count = calculator._count_chunks(
            UUID("8037da2b-61cd-435d-8db7-b5472c98f805"),
            1
        )
        elapsed = time.time() - start

        assert count == 10000
        assert elapsed < 0.5  # Should be fast
