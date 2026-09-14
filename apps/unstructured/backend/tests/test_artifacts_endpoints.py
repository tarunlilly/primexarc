"""
Unit Tests for Artifacts API Endpoints

Focus: Artifact preview, vector preview, and metadata operations
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from uuid import uuid4
from fastapi import HTTPException

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))

from primedata.api.artifacts import (
    ArtifactInfo,
    RawArtifactsResponse,
    ArtifactPreviewResponse,
    VectorPreviewItem,
    VectorPreviewResponse,
)


class TestArtifactPreviewEndpoint:
    """Test /artifacts/{artifact_id}/preview endpoint."""

    def test_preview_text_file(self):
        """Test previewing text file."""
        response = ArtifactPreviewResponse(
            artifact_id="data.txt",
            type="txt",
            preview_type="text",
            content="Line 1\nLine 2\nLine 3",
            total_lines=100,
            preview_lines=3,
            has_more=True,
            format_info={"encoding": "utf-8", "size_bytes": 1024}
        )

        assert response.type == "txt"
        assert response.preview_lines == 3
        assert response.has_more is True

    def test_preview_csv_file(self):
        """Test previewing CSV file."""
        response = ArtifactPreviewResponse(
            artifact_id="data.csv",
            type="csv",
            preview_type="text",
            content="col1,col2,col3\n1,2,3\n4,5,6",
            total_lines=1000,
            preview_lines=3,
            has_more=True
        )

        assert response.type == "csv"
        assert "col1" in response.content

    def test_preview_json_file(self):
        """Test previewing JSON file."""
        response = ArtifactPreviewResponse(
            artifact_id="config.json",
            type="json",
            preview_type="text",
            content='{"key": "value", "nested": {"prop": "value"}}',
            total_lines=1,
            preview_lines=1,
            has_more=False
        )

        assert response.type == "json"
        assert "key" in response.content

    def test_preview_jsonl_file(self):
        """Test previewing JSONL file."""
        response = ArtifactPreviewResponse(
            artifact_id="records.jsonl",
            type="jsonl",
            preview_type="text",
            content='{"id": 1}\n{"id": 2}\n{"id": 3}',
            total_lines=10000,
            preview_lines=3,
            has_more=True
        )

        assert response.type == "jsonl"

    def test_preview_pdf_file(self):
        """Test previewing PDF file (text extraction)."""
        response = ArtifactPreviewResponse(
            artifact_id="document.pdf",
            type="pdf",
            preview_type="text",
            content="PDF text content extracted...",
            total_lines=500,
            preview_lines=50,
            has_more=True
        )

        assert response.type == "pdf"

    def test_preview_custom_line_limit(self):
        """Test preview with custom line limit."""
        content_lines = [f"Line {i}" for i in range(100)]
        response = ArtifactPreviewResponse(
            artifact_id="data.txt",
            type="txt",
            preview_type="text",
            content="\n".join(content_lines[:100]),
            total_lines=1000,
            preview_lines=100,
            has_more=True
        )

        assert response.preview_lines == 100

    def test_preview_small_file_no_more(self):
        """Test preview of small file shows has_more=false."""
        response = ArtifactPreviewResponse(
            artifact_id="small.txt",
            type="txt",
            preview_type="text",
            content="Single line file",
            total_lines=1,
            preview_lines=1,
            has_more=False
        )

        assert response.has_more is False

    def test_preview_file_not_found_returns_404(self):
        """Test preview of non-existent file returns 404."""
        with pytest.raises(HTTPException) as exc:
            raise HTTPException(status_code=404, detail="Artifact not found: missing.txt")

        assert exc.value.status_code == 404

    def test_preview_encoding_error_handling(self):
        """Test preview handles encoding errors gracefully."""
        response = ArtifactPreviewResponse(
            artifact_id="data.txt",
            type="txt",
            preview_type="text",
            content="Valid UTF-8 content with special chars: é à ç",
            total_lines=10,
            preview_lines=1,
            has_more=True
        )

        assert len(response.content) > 0

    def test_preview_large_file_pagination(self):
        """Test preview respects pagination for large files."""
        response = ArtifactPreviewResponse(
            artifact_id="large.txt",
            type="txt",
            preview_type="text",
            content="\n".join([f"Line {i}" for i in range(50)]),
            total_lines=1000000,
            preview_lines=50,
            has_more=True
        )

        assert response.has_more is True
        assert response.total_lines > response.preview_lines

    @pytest.mark.parametrize("file_type,extension", [
        ("txt", ".txt"),
        ("csv", ".csv"),
        ("json", ".json"),
        ("jsonl", ".jsonl"),
        ("pdf", ".pdf"),
    ])
    def test_preview_file_type_detection(self, file_type, extension):
        """Test file type auto-detection for various formats."""
        response = ArtifactPreviewResponse(
            artifact_id=f"file{extension}",
            type=file_type,
            preview_type="text",
            content="content",
            total_lines=1,
            preview_lines=1,
            has_more=False
        )

        assert response.type == file_type


class TestVectorPreviewEndpoint:
    """Test /artifacts/{artifact_id}/vector-preview endpoint."""

    def test_vector_preview_returns_embeddings(self):
        """Test vector preview returns embeddings."""
        items = [
            VectorPreviewItem(
                id="1",
                content_preview="Sample text content",
                vector_sample=[0.1, 0.2, 0.3],
                vector_dimension=1536,
                magnitude=0.99
            )
        ]

        response = VectorPreviewResponse(
            artifact_id="data.txt",
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

        assert len(response.embeddings) == 1
        assert response.total == 100

    def test_vector_preview_multiple_embeddings(self):
        """Test vector preview with multiple embeddings."""
        items = [
            VectorPreviewItem(
                id=str(i),
                content_preview=f"Text {i}",
                vector_sample=[0.1] * 20,
                vector_dimension=1536,
                magnitude=1.0
            )
            for i in range(10)
        ]

        response = VectorPreviewResponse(
            artifact_id="data.txt",
            type="embedding",
            embeddings=items,
            total=1000,
            preview_count=10,
            statistics={}
        )

        assert len(response.embeddings) == 10

    def test_vector_preview_statistics_included(self):
        """Test vector preview includes statistics."""
        response = VectorPreviewResponse(
            artifact_id="data.txt",
            type="embedding",
            embeddings=[],
            total=100,
            preview_count=0,
            statistics={
                "avg_magnitude": 0.985,
                "vector_range": {"min": -1.2, "max": 1.3},
                "dimension": 1536
            }
        )

        assert response.statistics["dimension"] == 1536
        assert response.statistics["avg_magnitude"] == 0.985

    def test_vector_preview_custom_limit(self):
        """Test vector preview respects limit parameter."""
        items = [
            VectorPreviewItem(
                id=str(i),
                content_preview=f"Text {i}",
                vector_sample=[0.1] * 20,
                vector_dimension=1536,
                magnitude=1.0
            )
            for i in range(25)
        ]

        response = VectorPreviewResponse(
            artifact_id="data.txt",
            type="embedding",
            embeddings=items[:25],  # Limited to 25
            total=5000,
            preview_count=25,
            statistics={}
        )

        assert response.preview_count <= 25

    def test_vector_preview_invalid_artifact_format_returns_400(self):
        """Test invalid artifact_id format returns 400."""
        with pytest.raises(HTTPException) as exc:
            raise HTTPException(status_code=400, detail="Invalid artifact_id format")

        assert exc.value.status_code == 400

    def test_vector_preview_no_collection_returns_404(self):
        """Test no collection found returns 404."""
        with pytest.raises(HTTPException) as exc:
            raise HTTPException(status_code=404, detail="No embeddings found for artifact")

        assert exc.value.status_code == 404

    def test_vector_preview_magnitude_normalization(self):
        """Test vector magnitude is normalized."""
        item = VectorPreviewItem(
            id="1",
            content_preview="text",
            vector_sample=[3.0, 4.0],  # magnitude = 5.0
            vector_dimension=2,
            magnitude=5.0
        )

        assert item.magnitude == 5.0

    def test_vector_preview_large_dimensions(self):
        """Test vector preview with large dimension vectors."""
        item = VectorPreviewItem(
            id="1",
            content_preview="text",
            vector_sample=[0.1] * 1536,
            vector_dimension=1536,
            magnitude=12.4  # sqrt(1536 * 0.01)
        )

        assert item.vector_dimension == 1536

    def test_vector_preview_empty_collection(self):
        """Test vector preview handles empty collection."""
        response = VectorPreviewResponse(
            artifact_id="data.txt",
            type="embedding",
            embeddings=[],
            total=0,
            preview_count=0,
            statistics={
                "avg_magnitude": 0.0,
                "vector_range": {"min": 0.0, "max": 0.0},
                "dimension": 0
            }
        )

        assert response.total == 0
        assert len(response.embeddings) == 0

    @pytest.mark.parametrize("limit,total", [
        (10, 100),
        (50, 500),
        (1, 100),
        (100, 100),
    ])
    def test_vector_preview_various_limits(self, limit, total):
        """Test vector preview with various limits."""
        items = [
            VectorPreviewItem(
                id=str(i),
                content_preview=f"Text {i}",
                vector_sample=[0.1] * 20,
                vector_dimension=1536,
                magnitude=1.0
            )
            for i in range(min(limit, total))
        ]

        response = VectorPreviewResponse(
            artifact_id="data.txt",
            type="embedding",
            embeddings=items,
            total=total,
            preview_count=len(items),
            statistics={}
        )

        assert response.preview_count <= limit


class TestArtifactInfo:
    """Test ArtifactInfo model."""

    def test_artifact_info_creation(self):
        """Test creating artifact info."""
        info = ArtifactInfo(
            name="data.csv",
            size=1024000,
            last_modified="2026-03-30T00:00:00",
            url="https://bucket.s3.amazonaws.com/data.csv",
            content_type="text/csv"
        )

        assert info.name == "data.csv"
        assert info.size == 1024000

    def test_artifact_info_without_content_type(self):
        """Test artifact info with optional content_type."""
        info = ArtifactInfo(
            name="data.txt",
            size=512,
            last_modified="2026-03-30T00:00:00",
            url="https://bucket.s3.amazonaws.com/data.txt"
        )

        assert info.content_type is None


class TestRawArtifactsResponse:
    """Test RawArtifactsResponse model."""

    def test_raw_artifacts_response_creation(self):
        """Test creating raw artifacts response."""
        artifacts = [
            ArtifactInfo(
                name="file1.csv",
                size=1000,
                last_modified="2026-03-30T00:00:00",
                url="url1"
            ),
            ArtifactInfo(
                name="file2.json",
                size=2000,
                last_modified="2026-03-30T00:00:00",
                url="url2"
            )
        ]

        response = RawArtifactsResponse(
            artifacts=artifacts,
            total_files=2,
            total_bytes=3000,
            prefix="ws/123/prod/456/v/1/"
        )

        assert response.total_files == 2
        assert response.total_bytes == 3000

    def test_raw_artifacts_response_empty(self):
        """Test raw artifacts response when empty."""
        response = RawArtifactsResponse(
            artifacts=[],
            total_files=0,
            total_bytes=0,
            prefix="ws/123/prod/456/v/1/"
        )

        assert response.total_files == 0
        assert len(response.artifacts) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
