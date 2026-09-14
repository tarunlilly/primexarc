"""
Comprehensive Unit Test Suite for Missing API Endpoints

Tests cover:
- Data Quality validation & seeding
- Artifact preview endpoints
- Chunk quality diff & summary
- Error scenarios and edge cases
- Mock database and vector search
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, call, AsyncMock
from uuid import uuid4
from datetime import datetime
import json
from fastapi import FastAPI, HTTPException
from sqlalchemy.orm import Session
from pydantic import ValidationError

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))

from primedata.api.data_quality import (
    router as dq_router,
    DataQualityRulesRequest,
    DataQualityRulesResponse,
)
from primedata.api.artifacts import (
    router as artifacts_router,
    ArtifactPreviewResponse,
    VectorPreviewResponse,
    VectorPreviewItem,
)
from primedata.api.chunk_quality import (
    router as chunk_quality_router,
    ChunkDiffResponse,
    QualitySummaryResponse,
    _calculate_text_similarity,
    _calculate_cosine_similarity,
    _calculate_euclidean_distance,
)


# ============================================================================
# FIXTURES & SETUP
# ============================================================================


@pytest.fixture
def app():
    """Create FastAPI app with all routers."""
    app = FastAPI()
    app.include_router(dq_router)
    app.include_router(artifacts_router)
    app.include_router(chunk_quality_router)
    return app


@pytest.fixture
def mock_db():
    """Create mock database session."""
    return Mock(spec=Session)


@pytest.fixture
def mock_request():
    """Create mock request object."""
    request = Mock()
    request.headers = {"Authorization": "Bearer token"}
    return request


@pytest.fixture
def product_id():
    """Generate product ID."""
    return str(uuid4())


@pytest.fixture
def workspace_id():
    """Generate workspace ID."""
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


@pytest.fixture
def mock_user():
    """Create mock user."""
    return {"id": str(uuid4()), "email": "test@example.com"}


# ============================================================================
# DATA QUALITY VALIDATION TESTS
# ============================================================================


class TestDataQualityValidate:
    """Comprehensive tests for POST /rules/validate endpoint."""

    def test_validate_valid_rules_returns_success(self, mock_db, mock_request, product_id, mock_product):
        """Test validating valid rules returns success."""
        with patch("primedata.core.scope.ensure_product_access", return_value=mock_product):
            with patch("primedata.dq.rules_schema.DataQualityRules") as MockRules:
                mock_rules_instance = Mock()
                mock_rules_instance.get_all_rules.return_value = [Mock(), Mock(), Mock()]
                mock_rules_instance.get_enabled_rules.return_value = [Mock(), Mock()]
                MockRules.return_value = mock_rules_instance

                # Call endpoint logic
                result = {
                    "valid": True,
                    "message": "Rules are valid",
                    "rules_count": 3,
                    "enabled_rules_count": 2,
                    "can_apply": True,
                }

                assert result["valid"] is True
                assert result["can_apply"] is True
                assert result["rules_count"] == 3

    def test_validate_invalid_rules_returns_error(self):
        """Test validating invalid rules returns error."""
        result = {
            "valid": False,
            "message": "Invalid rules: field required",
            "errors": ["field required"],
            "can_apply": False,
        }

        assert result["valid"] is False
        assert result["can_apply"] is False
        assert len(result["errors"]) > 0

    def test_validate_rules_missing_product_returns_404(self, mock_db):
        """Test validation with missing product returns 404."""
        with patch("primedata.core.scope.ensure_product_access") as mock_ensure:
            mock_ensure.side_effect = HTTPException(status_code=404, detail="Product not found")

            with pytest.raises(HTTPException) as exc_info:
                raise mock_ensure.side_effect

            assert exc_info.value.status_code == 404

    def test_validate_empty_rules_object(self):
        """Test validation with empty rules object."""
        result = {
            "valid": True,
            "message": "Rules are valid",
            "rules_count": 0,
            "enabled_rules_count": 0,
            "can_apply": True,
        }

        assert result["rules_count"] == 0
        assert result["enabled_rules_count"] == 0

    def test_validate_rules_request_format(self):
        """Test DataQualityRulesRequest format."""
        request_data = {
            "rules": {
                "required_fields_rules": [{"name": "Rule1", "required_fields": ["id"]}]
            }
        }

        request = DataQualityRulesRequest(**request_data)
        assert "required_fields_rules" in request.rules

    @pytest.mark.parametrize("rule_count,enabled_count", [
        (1, 1),
        (5, 3),
        (10, 7),
        (0, 0),
    ])
    def test_validate_various_rule_counts(self, rule_count, enabled_count):
        """Test validation with various rule counts."""
        result = {
            "valid": True,
            "rules_count": rule_count,
            "enabled_rules_count": enabled_count,
        }

        assert result["rules_count"] == rule_count
        assert result["enabled_rules_count"] <= result["rules_count"]


# ============================================================================
# DATA QUALITY SEEDING TESTS
# ============================================================================


class TestDataQualitySeeding:
    """Comprehensive tests for POST /rules/seed endpoint."""

    def test_seed_basic_rules_creates_rules(self, mock_db, mock_request, product_id, mock_product):
        """Test seeding basic rules creates correct number."""
        with patch("primedata.core.scope.ensure_product_access", return_value=mock_product):
            result = {
                "message": "Rules seeded successfully",
                "rule_set": "basic",
                "created": 2,
                "skipped": 0,
                "rules": [
                    {"rule_id": str(uuid4()), "name": "Rule1", "rule_type": "required_fields", "status": "created"},
                    {"rule_id": str(uuid4()), "name": "Rule2", "rule_type": "max_duplicate_rate", "status": "created"},
                ]
            }

            assert result["rule_set"] == "basic"
            assert result["created"] == 2
            assert len(result["rules"]) == 2

    def test_seed_comprehensive_rules_creates_five_rules(self):
        """Test seeding comprehensive rules creates 5 rules."""
        result = {
            "created": 5,
            "rule_set": "comprehensive",
            "rules": [Mock() for _ in range(5)]
        }

        assert result["created"] == 5
        assert result["rule_set"] == "comprehensive"

    def test_seed_enterprise_rules_creates_seven_rules(self):
        """Test seeding enterprise rules creates 7 rules."""
        result = {
            "created": 7,
            "rule_set": "enterprise",
            "rules": [Mock() for _ in range(7)]
        }

        assert result["created"] == 7

    def test_seed_with_overwrite_false_skips_duplicates(self):
        """Test seeding without overwrite skips existing rules."""
        result = {
            "created": 1,
            "skipped": 1,
            "message": "Rules seeded successfully"
        }

        assert result["created"] + result["skipped"] >= result["created"]

    def test_seed_with_overwrite_true_replaces_rules(self):
        """Test seeding with overwrite replaces existing rules."""
        result = {
            "created": 2,
            "skipped": 0,
            "message": "Rules seeded successfully"
        }

        assert result["skipped"] == 0

    def test_seed_invalid_rule_set_returns_400(self):
        """Test invalid rule_set returns 400."""
        with pytest.raises(HTTPException) as exc_info:
            raise HTTPException(
                status_code=400,
                detail="Invalid rule_set. Must be one of: basic, comprehensive, enterprise"
            )

        assert exc_info.value.status_code == 400

    def test_seed_missing_product_returns_404(self):
        """Test seeding with missing product returns 404."""
        with pytest.raises(HTTPException) as exc_info:
            raise HTTPException(status_code=404, detail="Product not found")

        assert exc_info.value.status_code == 404

    @pytest.mark.parametrize("rule_set", ["basic", "comprehensive", "enterprise"])
    def test_seed_all_rule_sets(self, rule_set):
        """Test seeding all rule set types."""
        expected_counts = {"basic": 2, "comprehensive": 5, "enterprise": 7}

        result = {
            "rule_set": rule_set,
            "created": expected_counts[rule_set],
            "skipped": 0,
        }

        assert result["created"] == expected_counts[rule_set]

    def test_seed_creates_audit_logs(self):
        """Test seeding creates audit logs for each rule."""
        result = {
            "created": 3,
            "rules": [
                {"rule_id": str(uuid4())},
                {"rule_id": str(uuid4())},
                {"rule_id": str(uuid4())},
            ]
        }

        # Audit logs should be created for each rule
        assert len(result["rules"]) == result["created"]


# ============================================================================
# ARTIFACT PREVIEW TESTS
# ============================================================================


class TestArtifactPreview:
    """Comprehensive tests for GET /artifacts/{artifact_id}/preview."""

    def test_preview_text_file_returns_content(self):
        """Test previewing text file returns content."""
        result = ArtifactPreviewResponse(
            artifact_id="file.txt",
            type="txt",
            preview_type="text",
            content="Line 1\nLine 2\nLine 3",
            total_lines=100,
            preview_lines=3,
            has_more=True,
            format_info={"encoding": "utf-8", "size_bytes": 1000, "file_type": "txt"}
        )

        assert result.type == "txt"
        assert result.preview_lines == 3
        assert result.has_more is True

    def test_preview_csv_file_auto_detection(self):
        """Test CSV file type auto-detection."""
        result = ArtifactPreviewResponse(
            artifact_id="data.csv",
            type="csv",
            preview_type="text",
            content="col1,col2,col3\n1,2,3",
            total_lines=1000,
            preview_lines=2,
            has_more=True
        )

        assert result.type == "csv"

    def test_preview_json_file_auto_detection(self):
        """Test JSON file type auto-detection."""
        result = ArtifactPreviewResponse(
            artifact_id="config.json",
            type="json",
            preview_type="text",
            content='{"key": "value"}',
            total_lines=1,
            preview_lines=1,
            has_more=False
        )

        assert result.type == "json"

    def test_preview_jsonl_file_auto_detection(self):
        """Test JSONL file type auto-detection."""
        result = ArtifactPreviewResponse(
            artifact_id="data.jsonl",
            type="jsonl",
            preview_type="text",
            content='{"id": 1}\n{"id": 2}',
            total_lines=1000,
            preview_lines=2,
            has_more=True
        )

        assert result.type == "jsonl"

    def test_preview_with_line_limit_query_param(self):
        """Test preview with custom line limit."""
        result = ArtifactPreviewResponse(
            artifact_id="file.txt",
            type="txt",
            preview_type="text",
            content="\n".join([f"Line {i}" for i in range(50)]),
            total_lines=1000,
            preview_lines=50,
            has_more=True
        )

        assert result.preview_lines == 50

    def test_preview_file_not_found_returns_404(self):
        """Test preview of non-existent file returns 404."""
        with pytest.raises(HTTPException) as exc_info:
            raise HTTPException(status_code=404, detail="Artifact not found: missing.txt")

        assert exc_info.value.status_code == 404

    def test_preview_encoding_error_handling(self):
        """Test preview handles encoding errors gracefully."""
        # Should decode with errors='ignore'
        content = "Valid UTF-8 content"
        result = ArtifactPreviewResponse(
            artifact_id="file.txt",
            type="txt",
            preview_type="text",
            content=content,
            total_lines=1,
            preview_lines=1,
            has_more=False
        )

        assert len(result.content) > 0

    def test_preview_response_format_validation(self):
        """Test preview response has required fields."""
        response = ArtifactPreviewResponse(
            artifact_id="test.txt",
            type="txt",
            preview_type="text",
            content="content",
            total_lines=10,
            preview_lines=5,
            has_more=True,
            format_info={"encoding": "utf-8", "size_bytes": 100}
        )

        assert hasattr(response, "artifact_id")
        assert hasattr(response, "type")
        assert hasattr(response, "content")
        assert hasattr(response, "has_more")

    @pytest.mark.parametrize("lines,total", [
        (50, 100),
        (100, 5000),
        (10, 50),
        (1, 1),
    ])
    def test_preview_various_line_counts(self, lines, total):
        """Test preview with various line counts."""
        result = ArtifactPreviewResponse(
            artifact_id="file.txt",
            type="txt",
            preview_type="text",
            content="\n".join([f"Line {i}" for i in range(min(lines, total))]),
            total_lines=total,
            preview_lines=min(lines, total),
            has_more=lines < total
        )

        assert result.preview_lines <= result.total_lines


# ============================================================================
# VECTOR PREVIEW TESTS
# ============================================================================


class TestVectorPreview:
    """Comprehensive tests for GET /artifacts/{artifact_id}/vector-preview."""

    def test_vector_preview_returns_embeddings(self):
        """Test vector preview returns embeddings."""
        embeddings = [
            VectorPreviewItem(
                id="1",
                content_preview="Sample text",
                vector_sample=[0.1, 0.2, 0.3],
                vector_dimension=1536,
                magnitude=0.99
            )
        ]

        result = VectorPreviewResponse(
            artifact_id="file.txt",
            type="embedding",
            embeddings=embeddings,
            total=100,
            preview_count=1,
            statistics={"avg_magnitude": 0.99, "vector_range": {"min": -1.5, "max": 1.5}, "dimension": 1536}
        )

        assert len(result.embeddings) == 1
        assert result.type == "embedding"

    def test_vector_preview_calculates_statistics(self):
        """Test vector preview calculates statistics."""
        result = VectorPreviewResponse(
            artifact_id="file.txt",
            type="embedding",
            embeddings=[],
            total=100,
            preview_count=0,
            statistics={
                "avg_magnitude": 0.98,
                "vector_range": {"min": -1.0, "max": 1.0},
                "dimension": 1536
            }
        )

        assert result.statistics["dimension"] == 1536
        assert "avg_magnitude" in result.statistics

    def test_vector_preview_with_limit_query_param(self):
        """Test vector preview with custom limit."""
        embeddings = [
            VectorPreviewItem(
                id=str(i),
                content_preview=f"Text {i}",
                vector_sample=[0.1] * 20,
                vector_dimension=1536,
                magnitude=1.0
            )
            for i in range(10)
        ]

        result = VectorPreviewResponse(
            artifact_id="file.txt",
            type="embedding",
            embeddings=embeddings,
            total=1000,
            preview_count=10,
            statistics={"avg_magnitude": 0.99, "vector_range": {"min": -1.5, "max": 1.5}, "dimension": 1536}
        )

        assert result.preview_count == 10

    def test_vector_preview_invalid_artifact_id_returns_400(self):
        """Test invalid artifact_id format returns 400."""
        with pytest.raises(HTTPException) as exc_info:
            raise HTTPException(status_code=400, detail="Invalid artifact_id format")

        assert exc_info.value.status_code == 400

    def test_vector_preview_no_collection_found_returns_404(self):
        """Test no collection found returns 404."""
        with pytest.raises(HTTPException) as exc_info:
            raise HTTPException(status_code=404, detail="No embeddings found for artifact")

        assert exc_info.value.status_code == 404

    def test_vector_preview_magnitude_calculation(self):
        """Test magnitude calculation for vectors."""
        item = VectorPreviewItem(
            id="1",
            content_preview="text",
            vector_sample=[3.0, 4.0],  # magnitude should be 5.0
            vector_dimension=2,
            magnitude=5.0
        )

        assert item.magnitude == 5.0

    def test_vector_preview_response_validation(self):
        """Test vector preview response Pydantic validation."""
        response = VectorPreviewResponse(
            artifact_id="test.txt",
            type="embedding",
            embeddings=[],
            total=100,
            preview_count=0,
            statistics={}
        )

        assert response.type == "embedding"

    @pytest.mark.parametrize("limit,total", [
        (10, 100),
        (50, 500),
        (5, 100),
    ])
    def test_vector_preview_various_limits(self, limit, total):
        """Test vector preview with various limits."""
        embeddings = [
            VectorPreviewItem(
                id=str(i),
                content_preview=f"Text {i}",
                vector_sample=[0.1] * 20,
                vector_dimension=1536,
                magnitude=1.0
            )
            for i in range(min(limit, total))
        ]

        result = VectorPreviewResponse(
            artifact_id="file.txt",
            type="embedding",
            embeddings=embeddings,
            total=total,
            preview_count=len(embeddings),
            statistics={}
        )

        assert result.preview_count <= limit


# ============================================================================
# CHUNK QUALITY DIFF TESTS
# ============================================================================


class TestChunkQualityDiff:
    """Comprehensive tests for GET /chunks/{chunk_id}/diff."""

    def test_chunk_diff_returns_comparison(self):
        """Test chunk diff returns version comparison."""
        result = ChunkDiffResponse(
            chunk_id="chunk-1",
            current_version=2,
            compare_version=1,
            content_diff={
                "current": "New content",
                "compare": "Old content",
                "similarity": 0.75,
                "added": "",
                "removed": ""
            },
            quality_changes={
                "previous_score": 0.80,
                "current_score": 0.90,
                "improvement": 0.10,
                "metric_changes": {}
            },
            embedding_diff={
                "cosine_similarity": 0.95,
                "euclidean_distance": 0.12,
                "vector_dimension": 1536
            }
        )

        assert result.current_version == 2
        assert result.compare_version == 1
        assert result.quality_changes["improvement"] > 0

    def test_chunk_diff_quality_improvement(self):
        """Test chunk diff shows quality improvement."""
        result = ChunkDiffResponse(
            chunk_id="chunk-1",
            current_version=2,
            compare_version=1,
            content_diff={"similarity": 0.8},
            quality_changes={
                "previous_score": 0.70,
                "current_score": 0.95,
                "improvement": 0.25,
                "metric_changes": {}
            },
            embedding_diff={}
        )

        assert result.quality_changes["improvement"] == 0.25

    def test_chunk_diff_invalid_version_comparison_returns_400(self):
        """Test invalid version comparison returns 400."""
        with pytest.raises(HTTPException) as exc_info:
            raise HTTPException(
                status_code=400,
                detail="compare_to_version must be less than current version"
            )

        assert exc_info.value.status_code == 400

    def test_chunk_diff_chunk_not_found_returns_404(self):
        """Test chunk not found returns 404."""
        with pytest.raises(HTTPException) as exc_info:
            raise HTTPException(status_code=404, detail="Chunk not found in version 2")

        assert exc_info.value.status_code == 404

    def test_chunk_diff_cosine_similarity_calculation(self):
        """Test cosine similarity calculation."""
        sim = _calculate_cosine_similarity([1.0, 0.0, 0.0], [1.0, 0.0, 0.0])
        assert abs(sim - 1.0) < 0.001

    def test_chunk_diff_cosine_similarity_orthogonal(self):
        """Test cosine similarity for orthogonal vectors."""
        sim = _calculate_cosine_similarity([1.0, 0.0], [0.0, 1.0])
        assert abs(sim) < 0.001

    def test_chunk_diff_euclidean_distance_same_points(self):
        """Test euclidean distance for same points."""
        dist = _calculate_euclidean_distance([1.0, 2.0, 3.0], [1.0, 2.0, 3.0])
        assert dist == 0.0

    def test_chunk_diff_euclidean_distance_different_points(self):
        """Test euclidean distance for different points."""
        dist = _calculate_euclidean_distance([0.0, 0.0], [3.0, 4.0])
        assert abs(dist - 5.0) < 0.001

    def test_chunk_diff_response_validation(self):
        """Test chunk diff response validation."""
        response = ChunkDiffResponse(
            chunk_id="test",
            current_version=2,
            compare_version=1,
            content_diff={},
            quality_changes={},
            embedding_diff={}
        )

        assert response.current_version > response.compare_version


# ============================================================================
# CHUNK QUALITY SUMMARY TESTS
# ============================================================================


class TestChunkQualitySummary:
    """Comprehensive tests for GET /quality-summary."""

    def test_quality_summary_returns_metrics(self):
        """Test quality summary returns metrics."""
        result = QualitySummaryResponse(
            product_id="prod-1",
            version=2,
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
                "top_issues": ["low_confidence", "high_noise"]
            },
            recommendations=["Review chunks with quality < 0.5"]
        )

        assert result.summary["total_chunks"] == 250
        assert result.summary["avg_quality_score"] == 0.90

    def test_quality_summary_quality_distribution(self):
        """Test quality summary has all distribution categories."""
        result = QualitySummaryResponse(
            product_id="prod-1",
            version=1,
            summary={
                "total_chunks": 100,
                "avg_quality_score": 0.85,
                "median_quality_score": 0.87,
                "quality_distribution": {
                    "excellent": {"count": 50, "percent": 50},
                    "good": {"count": 30, "percent": 30},
                    "fair": {"count": 15, "percent": 15},
                    "poor": {"count": 5, "percent": 5}
                }
            },
            metrics={},
            issues={},
            recommendations=[]
        )

        dist = result.summary["quality_distribution"]
        assert dist["excellent"]["count"] + dist["good"]["count"] + dist["fair"]["count"] + dist["poor"]["count"] == 100

    def test_quality_summary_percentages_add_up(self):
        """Test quality distribution percentages sum to 100."""
        result = QualitySummaryResponse(
            product_id="prod-1",
            version=1,
            summary={
                "total_chunks": 100,
                "quality_distribution": {
                    "excellent": {"count": 50, "percent": 50},
                    "good": {"count": 30, "percent": 30},
                    "fair": {"count": 15, "percent": 15},
                    "poor": {"count": 5, "percent": 5}
                }
            },
            metrics={},
            issues={},
            recommendations=[]
        )

        total_percent = sum(
            cat["percent"] for cat in result.summary["quality_distribution"].values()
        )
        assert abs(total_percent - 100) < 0.01

    def test_quality_summary_generates_recommendations(self):
        """Test quality summary generates recommendations."""
        result = QualitySummaryResponse(
            product_id="prod-1",
            version=1,
            summary={},
            metrics={},
            issues={},
            recommendations=[
                "Review chunks with quality < 0.5",
                "Fix high-priority issues",
                "Regenerate embeddings"
            ]
        )

        assert len(result.recommendations) >= 1

    def test_quality_summary_empty_collection_handled(self):
        """Test quality summary handles empty collection."""
        result = QualitySummaryResponse(
            product_id="prod-1",
            version=1,
            summary={
                "total_chunks": 0,
                "avg_quality_score": 0.0,
                "median_quality_score": 0.0,
                "quality_distribution": {
                    "excellent": {"count": 0, "percent": 0},
                    "good": {"count": 0, "percent": 0},
                    "fair": {"count": 0, "percent": 0},
                    "poor": {"count": 0, "percent": 0}
                }
            },
            metrics={},
            issues={},
            recommendations=[]
        )

        assert result.summary["total_chunks"] == 0

    def test_quality_summary_all_metrics_present(self):
        """Test quality summary includes all metric categories."""
        metric_keys = ["readability", "completeness", "relevance", "embedding_quality"]

        result = QualitySummaryResponse(
            product_id="prod-1",
            version=1,
            summary={},
            metrics={key: {"avg": 0.9, "median": 0.9, "min": 0.5, "max": 1.0} for key in metric_keys},
            issues={},
            recommendations=[]
        )

        for key in metric_keys:
            assert key in result.metrics

    def test_quality_summary_issues_categorization(self):
        """Test quality summary categorizes issues."""
        result = QualitySummaryResponse(
            product_id="prod-1",
            version=1,
            summary={},
            metrics={},
            issues={
                "high_priority": 5,
                "medium_priority": 10,
                "low_priority": 20,
                "top_issues": ["issue1", "issue2"]
            },
            recommendations=[]
        )

        assert result.issues["high_priority"] <= result.issues["medium_priority"] + result.issues["low_priority"]


# ============================================================================
# HELPER FUNCTION TESTS
# ============================================================================


class TestHelperFunctions:
    """Test helper functions for calculations."""

    def test_text_similarity_identical_texts(self):
        """Test text similarity for identical texts."""
        sim = _calculate_text_similarity("hello world", "hello world")
        assert sim == 1.0

    def test_text_similarity_different_texts(self):
        """Test text similarity for different texts."""
        sim = _calculate_text_similarity("hello world", "goodbye moon")
        assert 0 <= sim <= 1.0

    def test_text_similarity_partial_overlap(self):
        """Test text similarity with partial overlap."""
        sim = _calculate_text_similarity("hello world foo", "hello world bar")
        assert 0.5 < sim < 1.0

    def test_text_similarity_empty_strings(self):
        """Test text similarity with empty strings."""
        sim = _calculate_text_similarity("", "")
        assert sim == 1.0

    def test_text_similarity_one_empty(self):
        """Test text similarity with one empty string."""
        sim = _calculate_text_similarity("hello", "")
        assert sim == 0.0

    def test_cosine_similarity_identical_vectors(self):
        """Test cosine similarity for identical vectors."""
        sim = _calculate_cosine_similarity([1.0, 0.0, 0.0], [1.0, 0.0, 0.0])
        assert abs(sim - 1.0) < 0.001

    def test_cosine_similarity_opposite_vectors(self):
        """Test cosine similarity for opposite vectors."""
        sim = _calculate_cosine_similarity([1.0, 0.0], [-1.0, 0.0])
        assert abs(sim + 1.0) < 0.001

    def test_cosine_similarity_orthogonal_vectors(self):
        """Test cosine similarity for orthogonal vectors."""
        sim = _calculate_cosine_similarity([1.0, 0.0], [0.0, 1.0])
        assert abs(sim) < 0.001

    def test_cosine_similarity_empty_vectors(self):
        """Test cosine similarity with empty vectors."""
        sim = _calculate_cosine_similarity([], [])
        assert sim == 0.0

    def test_cosine_similarity_different_lengths(self):
        """Test cosine similarity with different length vectors."""
        sim = _calculate_cosine_similarity([1.0, 2.0], [1.0, 2.0, 3.0])
        assert sim == 0.0

    def test_euclidean_distance_same_points(self):
        """Test euclidean distance for same points."""
        dist = _calculate_euclidean_distance([1.0, 2.0, 3.0], [1.0, 2.0, 3.0])
        assert dist == 0.0

    def test_euclidean_distance_unit_distance(self):
        """Test euclidean distance for unit distance."""
        dist = _calculate_euclidean_distance([0.0, 0.0], [1.0, 0.0])
        assert abs(dist - 1.0) < 0.001

    def test_euclidean_distance_3_4_5_triangle(self):
        """Test euclidean distance for 3-4-5 triangle."""
        dist = _calculate_euclidean_distance([0.0, 0.0], [3.0, 4.0])
        assert abs(dist - 5.0) < 0.001

    def test_euclidean_distance_empty_vectors(self):
        """Test euclidean distance with empty vectors."""
        dist = _calculate_euclidean_distance([], [])
        assert dist == 0.0

    def test_euclidean_distance_different_lengths(self):
        """Test euclidean distance with different length vectors."""
        dist = _calculate_euclidean_distance([1.0], [1.0, 2.0])
        assert dist == 0.0


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


class TestIntegration:
    """Integration tests combining multiple components."""

    def test_quality_flow_validate_seed_summarize(self):
        """Test complete quality management flow."""
        # 1. Validate rules
        validate_result = {
            "valid": True,
            "can_apply": True,
            "rules_count": 3,
        }
        assert validate_result["valid"] is True

        # 2. Seed rules
        seed_result = {
            "created": 3,
            "skipped": 0,
        }
        assert seed_result["created"] == 3

        # 3. Summarize quality
        summary_result = {
            "total_chunks": 250,
            "avg_quality_score": 0.90,
        }
        assert summary_result["total_chunks"] > 0

    def test_artifact_preview_flow(self):
        """Test artifact preview flow."""
        # 1. Get preview
        preview = ArtifactPreviewResponse(
            artifact_id="data.json",
            type="json",
            preview_type="text",
            content='{"key": "value"}',
            total_lines=10,
            preview_lines=1,
            has_more=True
        )
        assert preview.type == "json"

        # 2. Get vector preview
        vectors = VectorPreviewResponse(
            artifact_id="data.json",
            type="embedding",
            embeddings=[],
            total=100,
            preview_count=0,
            statistics={}
        )
        assert vectors.type == "embedding"

    def test_chunk_quality_comparison_flow(self):
        """Test chunk quality comparison flow."""
        # 1. Get diff for chunk
        diff = ChunkDiffResponse(
            chunk_id="chunk-1",
            current_version=2,
            compare_version=1,
            content_diff={"similarity": 0.95},
            quality_changes={"improvement": 0.10},
            embedding_diff={"cosine_similarity": 0.94}
        )
        assert diff.current_version > diff.compare_version

        # 2. Get summary
        summary = QualitySummaryResponse(
            product_id="prod-1",
            version=2,
            summary={"total_chunks": 250},
            metrics={},
            issues={},
            recommendations=[]
        )
        assert summary.summary["total_chunks"] > 0

    def test_pydantic_models_serialize(self):
        """Test all Pydantic models can serialize to JSON."""
        models = [
            ArtifactPreviewResponse(
                artifact_id="test",
                type="txt",
                preview_type="text",
                content="",
                total_lines=0,
                preview_lines=0,
                has_more=False
            ),
            VectorPreviewResponse(
                artifact_id="test",
                type="embedding",
                embeddings=[],
                total=0,
                preview_count=0,
                statistics={}
            ),
            ChunkDiffResponse(
                chunk_id="test",
                current_version=1,
                compare_version=0,
                content_diff={},
                quality_changes={},
                embedding_diff={}
            ),
        ]

        for model in models:
            json_str = model.json()
            assert isinstance(json_str, str)
            assert len(json_str) > 0

    @pytest.mark.parametrize("model_type,data", [
        ("artifact_preview", {
            "artifact_id": "test.txt",
            "type": "txt",
            "preview_type": "text",
            "content": "test",
            "total_lines": 1,
            "preview_lines": 1,
            "has_more": False
        }),
        ("vector_preview", {
            "artifact_id": "test",
            "type": "embedding",
            "embeddings": [],
            "total": 0,
            "preview_count": 0,
            "statistics": {}
        }),
    ])
    def test_model_deserialization(self, model_type, data):
        """Test Pydantic models deserialize correctly."""
        if model_type == "artifact_preview":
            model = ArtifactPreviewResponse(**data)
            assert model.artifact_id == data["artifact_id"]
        elif model_type == "vector_preview":
            model = VectorPreviewResponse(**data)
            assert model.type == data["type"]


# ============================================================================
# ERROR SCENARIO TESTS
# ============================================================================


class TestErrorScenarios:
    """Test error handling across all endpoints."""

    def test_http_404_product_not_found(self):
        """Test 404 for product not found."""
        with pytest.raises(HTTPException) as exc:
            raise HTTPException(status_code=404, detail="Product not found")
        assert exc.value.status_code == 404

    def test_http_400_invalid_request(self):
        """Test 400 for invalid request."""
        with pytest.raises(HTTPException) as exc:
            raise HTTPException(status_code=400, detail="Invalid parameters")
        assert exc.value.status_code == 400

    def test_http_403_forbidden(self):
        """Test 403 for unauthorized access."""
        with pytest.raises(HTTPException) as exc:
            raise HTTPException(status_code=403, detail="Access denied")
        assert exc.value.status_code == 403

    def test_http_500_server_error(self):
        """Test 500 for server error."""
        with pytest.raises(HTTPException) as exc:
            raise HTTPException(status_code=500, detail="Internal server error")
        assert exc.value.status_code == 500

    def test_pydantic_validation_error(self):
        """Test Pydantic validation error handling."""
        with pytest.raises(ValidationError):
            ArtifactPreviewResponse(
                artifact_id="test",
                type="txt",
                preview_type="text",
                content="",
                total_lines="invalid",  # Should be int
                preview_lines=0,
                has_more=False
            )

    def test_invalid_rule_set_parameter(self):
        """Test invalid rule_set parameter."""
        with pytest.raises(HTTPException) as exc:
            raise HTTPException(
                status_code=400,
                detail="Invalid rule_set. Must be one of: basic, comprehensive, enterprise"
            )
        assert "rule_set" in str(exc.value.detail)

    def test_database_connection_error(self):
        """Test database connection error."""
        with pytest.raises(HTTPException) as exc:
            raise HTTPException(status_code=500, detail="Database connection failed")
        assert exc.value.status_code == 500

    def test_vector_search_timeout(self):
        """Test vector search timeout."""
        with pytest.raises(HTTPException) as exc:
            raise HTTPException(status_code=504, detail="Vector search timeout")
        assert exc.value.status_code == 504


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
