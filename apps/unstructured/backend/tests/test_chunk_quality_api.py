"""
Unit Tests for Chunk Quality Drill-Down API

Tests cover:
- Quality filtering (confidence, coherence, noise)
- Metadata filtering (source file, section, page)
- Mid-sentence boundary detection
- Sorting capabilities
- Pagination
- Quality issue identification
- Edge cases
"""

import pytest
from uuid import uuid4, UUID
from unittest.mock import Mock, patch

from sqlalchemy.orm import Session
from fastapi import HTTPException

from primedata.api.chunk_quality import (
    get_chunk_quality,
    QualityChunkMetadata,
    QualityChunkPoint,
    ChunkQualityFilters,
    QualityScoreFilter,
    SortField,
    SortOrder,
    _extract_quality_metadata,
    _matches_filters,
    _detect_mid_sentence_boundaries,
    _identify_quality_issues,
    _sort_chunks,
    _retrieve_and_filter_chunks,
)
from primedata.db.models import Product


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_db():
    """Create mock database session."""
    return Mock(spec=Session)


@pytest.fixture
def test_product_id():
    """Test product ID."""
    return uuid4()


@pytest.fixture
def test_product(test_product_id):
    """Create test product."""
    product = Mock(spec=Product)
    product.id = test_product_id
    product.name = "Test Product"
    product.workspace_id = uuid4()
    product.current_version = 1
    return product


@pytest.fixture
def mock_current_user():
    """Create mock current user."""
    return {"id": "user-123", "email": "test@example.com"}


@pytest.fixture
def high_quality_chunk():
    """Create high-quality chunk."""
    return {
        "chunk_id": "hq-1",
        "chunk_text": "This is a high-quality chunk with complete sentences.",
        "confidence_score": 95,
        "noise_score": 5,
        "coherence_score": 92,
        "source_file": "document.pdf",
        "section": "Introduction",
        "page_number": 1,
        "chunk_order": 0,
    }


@pytest.fixture
def low_quality_chunk():
    """Create low-quality chunk."""
    return {
        "chunk_id": "lq-1",
        "chunk_text": "fragment partial",
        "confidence_score": 30,
        "noise_score": 80,
        "coherence_score": 20,
        "source_file": "document.pdf",
        "section": "Methods",
        "page_number": 5,
        "chunk_order": 10,
    }


# ============================================================================
# MODEL TESTS
# ============================================================================


class TestQualityChunkMetadata:
    """Test QualityChunkMetadata model."""

    def test_metadata_creation(self, high_quality_chunk):
        """Test creating quality metadata."""
        metadata = QualityChunkMetadata(**high_quality_chunk)

        assert metadata.chunk_id == "hq-1"
        assert metadata.confidence_score == 95
        assert metadata.noise_score == 5
        assert metadata.mid_sentence_start is False
        assert metadata.mid_sentence_end is False

    def test_metadata_defaults(self):
        """Test metadata with minimal fields."""
        metadata = QualityChunkMetadata(
            chunk_id="c1",
            chunk_text="text",
            chunk_order=0,
        )

        assert metadata.confidence_score == 0.0
        assert metadata.noise_score == 0.0
        assert metadata.coherence_score == 0.0


class TestChunkQualityFilters:
    """Test filter models."""

    def test_quality_score_filter(self):
        """Test score filter."""
        f = QualityScoreFilter(min_score=50, max_score=90)

        assert f.min_score == 50
        assert f.max_score == 90

    def test_chunk_quality_filters(self):
        """Test composite filters."""
        filters = ChunkQualityFilters(
            confidence=QualityScoreFilter(min_score=70),
            source_file="doc.pdf",
        )

        assert filters.confidence.min_score == 70
        assert filters.source_file == "doc.pdf"


# ============================================================================
# HELPER FUNCTION TESTS
# ============================================================================


class TestExtractQualityMetadata:
    """Test metadata extraction."""

    def test_extract_full_metadata(self, high_quality_chunk):
        """Test extracting full metadata."""
        metadata = _extract_quality_metadata(high_quality_chunk)

        assert metadata.chunk_id == "hq-1"
        assert metadata.confidence_score == 95
        assert metadata.source_file == "document.pdf"
        assert metadata.page_number == 1

    def test_extract_with_defaults(self):
        """Test extraction with missing fields."""
        payload = {"chunk_id": "c1", "chunk_text": "text"}
        metadata = _extract_quality_metadata(payload)

        assert metadata.confidence_score == 0.0
        assert metadata.source_file is None
        assert metadata.page_number is None

    def test_extract_truncates_long_text(self):
        """Test text truncation."""
        payload = {
            "chunk_id": "c1",
            "chunk_text": "x" * 2000,
        }
        metadata = _extract_quality_metadata(payload)

        assert len(metadata.chunk_text) == 1000


class TestMidSentenceBoundaryDetection:
    """Test mid-sentence detection."""

    def test_complete_sentence_both_boundaries(self):
        """Test complete sentence detection."""
        text = "This is a complete sentence."
        starts_mid, ends_mid = _detect_mid_sentence_boundaries(text)

        assert starts_mid is False
        assert ends_mid is False

    def test_starts_mid_sentence(self):
        """Test detection of mid-sentence start."""
        text = "and then something happened."
        starts_mid, ends_mid = _detect_mid_sentence_boundaries(text)

        assert starts_mid is True
        assert ends_mid is False

    def test_ends_mid_sentence(self):
        """Test detection of mid-sentence end."""
        text = "This is the first part"
        starts_mid, ends_mid = _detect_mid_sentence_boundaries(text)

        assert starts_mid is False
        assert ends_mid is True

    def test_both_mid_sentence(self):
        """Test detection of both boundaries mid-sentence."""
        text = "continuation of previous thought"
        starts_mid, ends_mid = _detect_mid_sentence_boundaries(text)

        assert starts_mid is True
        assert ends_mid is True

    def test_starts_with_quote(self):
        """Test quoted text detection."""
        text = '"quoted text".'
        starts_mid, ends_mid = _detect_mid_sentence_boundaries(text)

        assert starts_mid is False

    def test_question_and_exclamation(self):
        """Test question and exclamation marks."""
        text1 = "Is this a question?"
        _, ends1 = _detect_mid_sentence_boundaries(text1)
        assert ends1 is False

        text2 = "This is exciting!"
        _, ends2 = _detect_mid_sentence_boundaries(text2)
        assert ends2 is False

    def test_empty_text(self):
        """Test empty text handling."""
        starts_mid, ends_mid = _detect_mid_sentence_boundaries("")
        assert starts_mid is False
        assert ends_mid is False


class TestQualityIssueIdentification:
    """Test quality issue identification."""

    def test_mid_sentence_issues(self, high_quality_chunk):
        """Test mid-sentence issue detection."""
        metadata = QualityChunkMetadata(**high_quality_chunk)
        issues = _identify_quality_issues(metadata, mid_start=True, mid_end=False)

        assert "starts_mid_sentence" in issues

    def test_low_confidence_issue(self, low_quality_chunk):
        """Test low confidence detection."""
        metadata = QualityChunkMetadata(**low_quality_chunk)
        issues = _identify_quality_issues(metadata, False, False)

        assert "low_confidence" in issues

    def test_high_noise_issue(self, low_quality_chunk):
        """Test high noise detection."""
        metadata = QualityChunkMetadata(**low_quality_chunk)
        issues = _identify_quality_issues(metadata, False, False)

        assert "high_noise" in issues

    def test_low_coherence_issue(self, low_quality_chunk):
        """Test low coherence detection."""
        metadata = QualityChunkMetadata(**low_quality_chunk)
        issues = _identify_quality_issues(metadata, False, False)

        assert "low_coherence" in issues

    def test_no_issues_high_quality(self, high_quality_chunk):
        """Test high quality chunk has no issues."""
        metadata = QualityChunkMetadata(**high_quality_chunk)
        issues = _identify_quality_issues(metadata, False, False)

        assert len(issues) == 0


class TestFilterMatching:
    """Test filter matching logic."""

    def test_confidence_filter_min(self, high_quality_chunk):
        """Test minimum confidence filtering."""
        metadata = QualityChunkMetadata(**high_quality_chunk)
        filters = ChunkQualityFilters(
            confidence=QualityScoreFilter(min_score=0.9)
        )

        result = _matches_filters(metadata, filters)
        assert result is True

    def test_confidence_filter_exceeds_min(self):
        """Test confidence below minimum."""
        metadata = QualityChunkMetadata(
            chunk_id="c1",
            chunk_text="text",
            chunk_order=0,
            confidence_score=0.3,
        )
        filters = ChunkQualityFilters(
            confidence=QualityScoreFilter(min_score=0.7)
        )

        result = _matches_filters(metadata, filters)
        assert result is False

    def test_noise_filter_max(self, low_quality_chunk):
        """Test maximum noise filtering."""
        metadata = QualityChunkMetadata(**low_quality_chunk)
        filters = ChunkQualityFilters(
            noise=QualityScoreFilter(max_score=90)
        )

        result = _matches_filters(metadata, filters)
        assert result is True

    def test_noise_exceeds_max(self):
        """Test noise exceeds maximum."""
        metadata = QualityChunkMetadata(
            chunk_id="c1",
            chunk_text="text",
            chunk_order=0,
            noise_score=0.95,
        )
        filters = ChunkQualityFilters(
            noise=QualityScoreFilter(max_score=0.5)
        )

        result = _matches_filters(metadata, filters)
        assert result is False

    def test_source_file_filter(self, high_quality_chunk):
        """Test source file filtering."""
        metadata = QualityChunkMetadata(**high_quality_chunk)
        filters = ChunkQualityFilters(source_file="document.pdf")

        result = _matches_filters(metadata, filters)
        assert result is True

    def test_source_file_mismatch(self):
        """Test source file mismatch."""
        metadata = QualityChunkMetadata(
            chunk_id="c1",
            chunk_text="text",
            chunk_order=0,
            source_file="other.pdf",
        )
        filters = ChunkQualityFilters(source_file="document.pdf")

        result = _matches_filters(metadata, filters)
        assert result is False

    def test_multiple_filters_all_match(self, high_quality_chunk):
        """Test multiple filters all matching."""
        metadata = QualityChunkMetadata(**high_quality_chunk)
        filters = ChunkQualityFilters(
            confidence=QualityScoreFilter(min_score=0.9),
            source_file="document.pdf",
            page_number=1,
        )

        result = _matches_filters(metadata, filters)
        assert result is True

    def test_multiple_filters_one_fails(self, high_quality_chunk):
        """Test multiple filters with one failure."""
        metadata = QualityChunkMetadata(**high_quality_chunk)
        filters = ChunkQualityFilters(
            confidence=QualityScoreFilter(min_score=0.9),
            source_file="other.pdf",  # Mismatch
        )

        result = _matches_filters(metadata, filters)
        assert result is False


class TestChunkSorting:
    """Test chunk sorting."""

    def test_sort_by_confidence_descending(self):
        """Test sorting by confidence descending."""
        chunks = [
            QualityChunkPoint(
                id="p1",
                metadata=QualityChunkMetadata(
                    chunk_id="c1", chunk_text="t1", chunk_order=0, confidence_score=70
                ),
            ),
            QualityChunkPoint(
                id="p2",
                metadata=QualityChunkMetadata(
                    chunk_id="c2", chunk_text="t2", chunk_order=1, confidence_score=90
                ),
            ),
        ]

        sorted_chunks = _sort_chunks(chunks, SortField.CONFIDENCE, SortOrder.DESC)

        assert sorted_chunks[0].metadata.confidence_score == 90
        assert sorted_chunks[1].metadata.confidence_score == 70

    def test_sort_by_confidence_ascending(self):
        """Test sorting by confidence ascending."""
        chunks = [
            QualityChunkPoint(
                id="p1",
                metadata=QualityChunkMetadata(
                    chunk_id="c1", chunk_text="t1", chunk_order=0, confidence_score=70
                ),
            ),
            QualityChunkPoint(
                id="p2",
                metadata=QualityChunkMetadata(
                    chunk_id="c2", chunk_text="t2", chunk_order=1, confidence_score=90
                ),
            ),
        ]

        sorted_chunks = _sort_chunks(chunks, SortField.CONFIDENCE, SortOrder.ASC)

        assert sorted_chunks[0].metadata.confidence_score == 70
        assert sorted_chunks[1].metadata.confidence_score == 90

    def test_sort_by_chunk_order(self):
        """Test sorting by chunk order."""
        chunks = [
            QualityChunkPoint(
                id="p1",
                metadata=QualityChunkMetadata(
                    chunk_id="c1", chunk_text="t1", chunk_order=5
                ),
            ),
            QualityChunkPoint(
                id="p2",
                metadata=QualityChunkMetadata(
                    chunk_id="c2", chunk_text="t2", chunk_order=2
                ),
            ),
        ]

        sorted_chunks = _sort_chunks(chunks, SortField.CHUNK_ORDER, SortOrder.ASC)

        assert sorted_chunks[0].metadata.chunk_order == 2
        assert sorted_chunks[1].metadata.chunk_order == 5

    def test_sort_by_page_number_handles_none(self):
        """Test sorting by page number with None values."""
        chunks = [
            QualityChunkPoint(
                id="p1",
                metadata=QualityChunkMetadata(
                    chunk_id="c1", chunk_text="t1", chunk_order=0, page_number=5
                ),
            ),
            QualityChunkPoint(
                id="p2",
                metadata=QualityChunkMetadata(
                    chunk_id="c2", chunk_text="t2", chunk_order=1, page_number=None
                ),
            ),
        ]

        sorted_chunks = _sort_chunks(chunks, SortField.PAGE_NUMBER, SortOrder.ASC)

        # None should sort first (treated as 0)
        assert sorted_chunks[0].metadata.page_number is None
        assert sorted_chunks[1].metadata.page_number == 5


# ============================================================================
# ENDPOINT TESTS
# ============================================================================


class TestGetChunkQualityEndpoint:
    """Test get_chunk_quality API endpoint."""

    @pytest.mark.asyncio
    async def test_get_chunk_quality_success(
        self, mock_db, test_product, test_product_id, mock_current_user
    ):
        """Test successful chunk quality retrieval."""
        mock_db.query.return_value.filter.return_value.first.return_value = test_product

        mock_client = Mock()
        mock_client.get_collection_name.return_value = "collection_v1"
        mock_client.scroll_points.return_value = iter([])

        with patch(
            "primedata.api.chunk_quality.get_vector_search_client",
            return_value=mock_client,
        ):
            response = await get_chunk_quality(
                product_id=test_product_id,
                version=1,
                offset=0,
                limit=100,
                sort_by=SortField.CONFIDENCE,
                sort_order=SortOrder.DESC,
                confidence_min=None,
                confidence_max=None,
                noise_max=None,
                coherence_min=None,
                source_file=None,
                section=None,
                page_number=None,
                skip_mid_sentence=False,
                db=mock_db,
                current_user=mock_current_user,
            )

        assert response.product_id == str(test_product_id)
        assert response.version == 1

    @pytest.mark.asyncio
    async def test_get_chunk_quality_product_not_found(
        self, mock_db, test_product_id, mock_current_user
    ):
        """Test chunk quality with product not found."""
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await get_chunk_quality(
                product_id=test_product_id,
                version=1,
                offset=0,
                limit=100,
                db=mock_db,
                current_user=mock_current_user,
            )

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_chunk_quality_with_filters(
        self, mock_db, test_product, test_product_id, mock_current_user
    ):
        """Test chunk quality with quality filters."""
        mock_db.query.return_value.filter.return_value.first.return_value = test_product

        mock_client = Mock()
        mock_client.get_collection_name.return_value = "collection_v1"
        mock_client.scroll_points.return_value = iter([])

        with patch(
            "primedata.api.chunk_quality.get_vector_search_client",
            return_value=mock_client,
        ):
            response = await get_chunk_quality(
                product_id=test_product_id,
                version=1,
                offset=0,
                limit=100,
                sort_by=SortField.CONFIDENCE,
                sort_order=SortOrder.DESC,
                confidence_min=0.7,
                confidence_max=1.0,
                noise_max=0.3,
                coherence_min=None,
                source_file="doc.pdf",
                section=None,
                page_number=None,
                skip_mid_sentence=False,
                db=mock_db,
                current_user=mock_current_user,
            )

        assert response.product_id == str(test_product_id)


# ============================================================================
# EDGE CASE TESTS
# ============================================================================


class TestChunkQualityEdgeCases:
    """Test edge cases."""

    def test_empty_chunks_list_sorting(self):
        """Test sorting empty list."""
        result = _sort_chunks([], SortField.CONFIDENCE, SortOrder.DESC)
        assert len(result) == 0

    def test_single_chunk_sorting(self):
        """Test sorting single chunk."""
        chunk = QualityChunkPoint(
            id="p1",
            metadata=QualityChunkMetadata(
                chunk_id="c1", chunk_text="t1", chunk_order=0
            ),
        )
        result = _sort_chunks([chunk], SortField.CONFIDENCE, SortOrder.DESC)

        assert len(result) == 1
        assert result[0].id == "p1"

    def test_all_chunks_filtered_out(self):
        """Test filtering that removes all chunks."""
        metadata = QualityChunkMetadata(
            chunk_id="c1",
            chunk_text="text",
            chunk_order=0,
            confidence_score=0.3,
        )
        filters = ChunkQualityFilters(
            confidence=QualityScoreFilter(min_score=0.9)
        )

        # Simulate filtering loop
        result = _matches_filters(metadata, filters)
        assert result is False

    def test_numeric_score_boundaries(self):
        """Test boundary conditions for scores."""
        # Test score of exactly 0
        metadata = QualityChunkMetadata(
            chunk_id="c1",
            chunk_text="text",
            chunk_order=0,
            confidence_score=0.0,
        )
        filters = ChunkQualityFilters(
            confidence=QualityScoreFilter(min_score=0.0)
        )
        assert _matches_filters(metadata, filters) is True

        # Test score of exactly 100
        metadata2 = QualityChunkMetadata(
            chunk_id="c2",
            chunk_text="text",
            chunk_order=0,
            confidence_score=100.0,
        )
        filters2 = ChunkQualityFilters(
            confidence=QualityScoreFilter(max_score=100.0)
        )
        assert _matches_filters(metadata2, filters2) is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
