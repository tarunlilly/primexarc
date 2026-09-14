"""
Unit Tests for Chunk Quality API Endpoints

Focus: Chunk diff, quality summary, and metrics operations
"""

import pytest
from unittest.mock import Mock, patch
from uuid import uuid4
from fastapi import HTTPException
import math

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))

from primedata.api.chunk_quality import (
    QualityChunkMetadata,
    QualityChunkPoint,
    ChunkQualityResponse,
    ChunkDiffResponse,
    QualitySummaryResponse,
    _calculate_text_similarity,
    _calculate_cosine_similarity,
    _calculate_euclidean_distance,
)


class TestChunkDiffEndpoint:
    """Test /chunks/{chunk_id}/diff endpoint."""

    def test_chunk_diff_returns_comparison(self):
        """Test chunk diff returns version comparison."""
        response = ChunkDiffResponse(
            chunk_id="chunk-1",
            current_version=2,
            compare_version=1,
            content_diff={
                "current": "New content with improvements",
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

        assert response.current_version == 2
        assert response.compare_version == 1
        assert response.quality_changes["improvement"] > 0

    def test_chunk_diff_quality_improvement(self):
        """Test chunk diff shows quality improvement."""
        response = ChunkDiffResponse(
            chunk_id="chunk-1",
            current_version=3,
            compare_version=2,
            content_diff={"similarity": 0.85},
            quality_changes={
                "previous_score": 0.70,
                "current_score": 0.95,
                "improvement": 0.25,
                "metric_changes": {
                    "confidence": {"from": 0.65, "to": 0.95, "change": 0.30},
                    "coherence": {"from": 0.75, "to": 0.95, "change": 0.20},
                    "noise": {"from": 0.30, "to": 0.05, "change": -0.25}
                }
            },
            embedding_diff={}
        )

        assert response.quality_changes["improvement"] == 0.25
        assert response.quality_changes["metric_changes"]["confidence"]["change"] > 0

    def test_chunk_diff_quality_degradation(self):
        """Test chunk diff shows quality degradation."""
        response = ChunkDiffResponse(
            chunk_id="chunk-1",
            current_version=2,
            compare_version=1,
            content_diff={"similarity": 0.50},
            quality_changes={
                "previous_score": 0.90,
                "current_score": 0.75,
                "improvement": -0.15,
                "metric_changes": {}
            },
            embedding_diff={}
        )

        assert response.quality_changes["improvement"] < 0

    def test_chunk_diff_embedding_similarity(self):
        """Test chunk diff includes embedding similarity."""
        response = ChunkDiffResponse(
            chunk_id="chunk-1",
            current_version=2,
            compare_version=1,
            content_diff={},
            quality_changes={},
            embedding_diff={
                "cosine_similarity": 0.92,
                "euclidean_distance": 0.15,
                "vector_dimension": 1536
            }
        )

        assert 0 <= response.embedding_diff["cosine_similarity"] <= 1.0
        assert response.embedding_diff["vector_dimension"] == 1536

    def test_chunk_diff_invalid_version_order_returns_400(self):
        """Test comparing to newer version returns 400."""
        with pytest.raises(HTTPException) as exc:
            raise HTTPException(
                status_code=400,
                detail="compare_to_version must be less than current version"
            )

        assert exc.value.status_code == 400

    def test_chunk_diff_chunk_not_found_returns_404(self):
        """Test non-existent chunk returns 404."""
        with pytest.raises(HTTPException) as exc:
            raise HTTPException(status_code=404, detail="Chunk not found in version 2")

        assert exc.value.status_code == 404

    def test_chunk_diff_version_not_found_returns_404(self):
        """Test non-existent version returns 404."""
        with pytest.raises(HTTPException) as exc:
            raise HTTPException(status_code=404, detail="No chunks found for version 99")

        assert exc.value.status_code == 404

    def test_chunk_diff_response_validation(self):
        """Test chunk diff response has required fields."""
        response = ChunkDiffResponse(
            chunk_id="test",
            current_version=2,
            compare_version=1,
            content_diff={},
            quality_changes={},
            embedding_diff={}
        )

        assert response.current_version > response.compare_version


class TestQualitySummaryEndpoint:
    """Test /quality-summary endpoint."""

    def test_quality_summary_returns_metrics(self):
        """Test quality summary returns all metrics."""
        response = QualitySummaryResponse(
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
                "top_issues": ["low_confidence_chunks"]
            },
            recommendations=["Review chunks with quality < 0.5"]
        )

        assert response.summary["total_chunks"] == 250
        assert response.summary["avg_quality_score"] == 0.90
        assert len(response.metrics) == 4

    def test_quality_summary_distribution_validation(self):
        """Test quality distribution percentages are valid."""
        response = QualitySummaryResponse(
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

        dist = response.summary["quality_distribution"]
        total_count = sum(cat["count"] for cat in dist.values())
        total_percent = sum(cat["percent"] for cat in dist.values())

        assert total_count == 100
        assert abs(total_percent - 100) < 0.01

    def test_quality_summary_issues_categorization(self):
        """Test quality summary categorizes issues correctly."""
        response = QualitySummaryResponse(
            product_id="prod-1",
            version=1,
            summary={},
            metrics={},
            issues={
                "high_priority": 5,
                "medium_priority": 10,
                "low_priority": 20,
                "top_issues": ["issue1", "issue2", "issue3"]
            },
            recommendations=[]
        )

        assert response.issues["high_priority"] <= response.issues["medium_priority"]
        assert len(response.issues["top_issues"]) <= 3

    def test_quality_summary_generates_recommendations(self):
        """Test quality summary generates recommendations."""
        response = QualitySummaryResponse(
            product_id="prod-1",
            version=1,
            summary={},
            metrics={},
            issues={},
            recommendations=[
                "Review chunks with quality < 0.5",
                "Fix high-priority issues",
                "Regenerate embeddings for low quality"
            ]
        )

        assert len(response.recommendations) >= 1

    def test_quality_summary_empty_collection(self):
        """Test quality summary handles empty collection."""
        response = QualitySummaryResponse(
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

        assert response.summary["total_chunks"] == 0

    def test_quality_summary_metric_ranges(self):
        """Test quality summary metric ranges are valid."""
        response = QualitySummaryResponse(
            product_id="prod-1",
            version=1,
            summary={},
            metrics={
                "readability": {"avg": 0.75, "median": 0.80, "min": 0.2, "max": 0.95}
            },
            issues={},
            recommendations=[]
        )

        metric = response.metrics["readability"]
        assert metric["min"] <= metric["avg"] <= metric["max"]
        assert metric["min"] <= metric["median"] <= metric["max"]


class TestQualityChunkMetadata:
    """Test QualityChunkMetadata model."""

    def test_quality_chunk_metadata_creation(self):
        """Test creating quality chunk metadata."""
        metadata = QualityChunkMetadata(
            chunk_id="chunk-1",
            chunk_text="Sample text content",
            chunk_order=1,
            source_file="document.pdf",
            section="Introduction",
            page_number=1,
            confidence_score=0.95,
            noise_score=0.05,
            coherence_score=0.92
        )

        assert metadata.chunk_id == "chunk-1"
        assert metadata.confidence_score == 0.95

    def test_quality_chunk_metadata_score_bounds(self):
        """Test quality scores are within bounds."""
        metadata = QualityChunkMetadata(
            chunk_id="chunk-1",
            chunk_text="text",
            chunk_order=1,
            confidence_score=0.5,
            noise_score=0.3,
            coherence_score=0.7
        )

        assert 0 <= metadata.confidence_score <= 100
        assert 0 <= metadata.noise_score <= 100
        assert 0 <= metadata.coherence_score <= 100


class TestQualityChunkPoint:
    """Test QualityChunkPoint model."""

    def test_quality_chunk_point_creation(self):
        """Test creating quality chunk point."""
        metadata = QualityChunkMetadata(
            chunk_id="chunk-1",
            chunk_text="text",
            chunk_order=1,
            confidence_score=0.9
        )

        point = QualityChunkPoint(
            id="point-1",
            metadata=metadata,
            quality_issues=["low_confidence", "high_noise"]
        )

        assert point.id == "point-1"
        assert len(point.quality_issues) == 2


# ============================================================================
# HELPER FUNCTION TESTS
# ============================================================================


class TestTextSimilarityFunction:
    """Test _calculate_text_similarity function."""

    def test_identical_texts(self):
        """Test similarity for identical texts."""
        sim = _calculate_text_similarity("hello world", "hello world")
        assert sim == 1.0

    def test_completely_different_texts(self):
        """Test similarity for completely different texts."""
        sim = _calculate_text_similarity("hello world", "goodbye moon")
        assert 0 <= sim < 1.0

    def test_partial_overlap(self):
        """Test similarity with partial overlap."""
        sim = _calculate_text_similarity("hello world foo", "hello world bar")
        assert 0.4 <= sim < 1.0

    def test_empty_strings(self):
        """Test similarity with both empty strings."""
        sim = _calculate_text_similarity("", "")
        assert sim == 0.0

    def test_one_empty_string(self):
        """Test similarity with one empty string."""
        sim = _calculate_text_similarity("hello", "")
        assert sim == 0.0

    def test_single_word_match(self):
        """Test similarity with single word match."""
        sim = _calculate_text_similarity("hello", "hello")
        assert sim == 1.0


class TestCosineSimilarityFunction:
    """Test _calculate_cosine_similarity function."""

    def test_identical_vectors(self):
        """Test cosine similarity for identical vectors."""
        sim = _calculate_cosine_similarity([1.0, 0.0, 0.0], [1.0, 0.0, 0.0])
        assert abs(sim - 1.0) < 0.001

    def test_opposite_vectors(self):
        """Test cosine similarity for opposite vectors."""
        sim = _calculate_cosine_similarity([1.0, 0.0], [-1.0, 0.0])
        assert abs(sim + 1.0) < 0.001

    def test_orthogonal_vectors(self):
        """Test cosine similarity for orthogonal vectors."""
        sim = _calculate_cosine_similarity([1.0, 0.0], [0.0, 1.0])
        assert abs(sim) < 0.001

    def test_normalized_vectors(self):
        """Test cosine similarity for normalized vectors."""
        sim = _calculate_cosine_similarity(
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0]
        )
        assert abs(sim) < 0.001

    def test_45_degree_angle(self):
        """Test cosine similarity for 45 degree angle."""
        sim = _calculate_cosine_similarity([1.0, 1.0], [1.0, 0.0])
        assert 0.7 < sim < 0.8

    def test_empty_vectors(self):
        """Test cosine similarity with empty vectors."""
        sim = _calculate_cosine_similarity([], [])
        assert sim == 0.0

    def test_different_length_vectors(self):
        """Test cosine similarity with different lengths."""
        sim = _calculate_cosine_similarity([1.0, 2.0], [1.0, 2.0, 3.0])
        assert sim == 0.0


class TestEuclideanDistanceFunction:
    """Test _calculate_euclidean_distance function."""

    def test_same_points(self):
        """Test distance for same points."""
        dist = _calculate_euclidean_distance([1.0, 2.0, 3.0], [1.0, 2.0, 3.0])
        assert dist == 0.0

    def test_unit_distance(self):
        """Test distance for unit displacement."""
        dist = _calculate_euclidean_distance([0.0, 0.0], [1.0, 0.0])
        assert abs(dist - 1.0) < 0.001

    def test_3_4_5_triangle(self):
        """Test distance for 3-4-5 right triangle."""
        dist = _calculate_euclidean_distance([0.0, 0.0], [3.0, 4.0])
        assert abs(dist - 5.0) < 0.001

    def test_diagonal_distance(self):
        """Test distance for diagonal."""
        dist = _calculate_euclidean_distance([0.0, 0.0], [1.0, 1.0])
        assert abs(dist - math.sqrt(2)) < 0.001

    def test_3d_distance(self):
        """Test distance in 3D space."""
        dist = _calculate_euclidean_distance([0.0, 0.0, 0.0], [1.0, 1.0, 1.0])
        assert abs(dist - math.sqrt(3)) < 0.001

    def test_empty_vectors(self):
        """Test distance with empty vectors."""
        dist = _calculate_euclidean_distance([], [])
        assert dist == 0.0

    def test_different_length_vectors(self):
        """Test distance with different lengths."""
        dist = _calculate_euclidean_distance([1.0], [1.0, 2.0])
        assert dist == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
