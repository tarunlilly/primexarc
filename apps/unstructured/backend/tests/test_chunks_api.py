"""
Unit Tests for Chunks Retrieval API

Tests cover:
- Chunks API endpoint functionality
- Pagination logic
- Metadata extraction
- Version targeting
- Error handling
- Edge cases
"""

import pytest
from uuid import uuid4, UUID
from unittest.mock import Mock, patch, MagicMock

from sqlalchemy.orm import Session
from fastapi import HTTPException

from primedata.api.chunks import (
    get_chunks,
    ChunkMetadata,
    ChunkPoint,
    ChunksResponse,
    _retrieve_chunks_paginated,
    _extract_chunk_metadata,
)
from primedata.db.models import Product, Workspace


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_db():
    """Create mock database session."""
    return Mock(spec=Session)


@pytest.fixture
def test_workspace_id():
    """Test workspace ID."""
    return uuid4()


@pytest.fixture
def test_product_id():
    """Test product ID."""
    return uuid4()


@pytest.fixture
def test_workspace(test_workspace_id):
    """Create test workspace."""
    workspace = Mock(spec=Workspace)
    workspace.id = test_workspace_id
    workspace.name = "Test Workspace"
    return workspace


@pytest.fixture
def test_product(test_product_id, test_workspace_id):
    """Create test product."""
    product = Mock(spec=Product)
    product.id = test_product_id
    product.name = "Test Product"
    product.workspace_id = test_workspace_id
    product.current_version = 1
    return product


@pytest.fixture
def mock_vector_client():
    """Create mock vector search client."""
    client = Mock()
    client.is_connected.return_value = True
    client.get_collection_name.return_value = "collection_v1"
    client.scroll_points.return_value = iter([])
    return client


@pytest.fixture
def mock_current_user():
    """Create mock current user."""
    return {"id": "user-123", "email": "test@example.com"}


@pytest.fixture
def test_chunk_point():
    """Create test chunk point."""
    return {
        "id": "chunk-1",
        "vector": [0.1, 0.2, 0.3],
        "payload": {
            "chunk_id": "chunk-1",
            "chunk_text": "This is test chunk content",
            "chunk_order": 0,
            "source_file": "document.pdf",
            "section": "Introduction",
            "page_number": 1,
            "confidence_score": 0.95,
            "noise_score": 0.05,
            "coherence_score": 0.92,
        },
    }


# ============================================================================
# MODEL TESTS
# ============================================================================


class TestChunkMetadata:
    """Test ChunkMetadata model."""

    def test_chunk_metadata_creation(self):
        """Test creating chunk metadata."""
        metadata = ChunkMetadata(
            chunk_id="chunk-1",
            chunk_text="test content",
            chunk_order=0,
            source_file="doc.pdf",
            section="Intro",
            page_number=1,
            confidence_score=0.95,
        )

        assert metadata.chunk_id == "chunk-1"
        assert metadata.chunk_text == "test content"
        assert metadata.chunk_order == 0
        assert metadata.source_file == "doc.pdf"
        assert metadata.section == "Intro"
        assert metadata.page_number == 1
        assert metadata.confidence_score == 0.95

    def test_chunk_metadata_with_defaults(self):
        """Test chunk metadata with default values."""
        metadata = ChunkMetadata(
            chunk_id="chunk-1",
            chunk_text="content",
        )

        assert metadata.chunk_id == "chunk-1"
        assert metadata.chunk_text == "content"
        assert metadata.chunk_order == 0
        assert metadata.source_file is None
        assert metadata.page_number is None


class TestChunkPoint:
    """Test ChunkPoint model."""

    def test_chunk_point_creation(self):
        """Test creating chunk point."""
        metadata = ChunkMetadata(chunk_id="c1", chunk_text="text")
        point = ChunkPoint(id="p1", vector_size=384, metadata=metadata)

        assert point.id == "p1"
        assert point.vector_size == 384
        assert point.metadata.chunk_id == "c1"

    def test_chunk_point_allows_extra_fields(self):
        """Test that chunk point allows extra fields."""
        metadata = ChunkMetadata(chunk_id="c1", chunk_text="text")
        point = ChunkPoint(
            id="p1",
            vector_size=384,
            metadata=metadata,
            extra_field="extra_value",
        )

        assert point.id == "p1"
        assert point.extra_field == "extra_value"


class TestChunksResponse:
    """Test ChunksResponse model."""

    def test_chunks_response_creation(self):
        """Test creating chunks response."""
        metadata = ChunkMetadata(chunk_id="c1", chunk_text="text")
        point = ChunkPoint(id="p1", vector_size=384, metadata=metadata)

        response = ChunksResponse(
            product_id="prod-1",
            product_name="Product",
            version=1,
            chunks=[point],
            total_count=10,
            returned_count=1,
            offset=0,
            limit=100,
            has_more=True,
        )

        assert response.product_id == "prod-1"
        assert response.product_name == "Product"
        assert response.version == 1
        assert len(response.chunks) == 1
        assert response.total_count == 10
        assert response.returned_count == 1
        assert response.has_more is True

    def test_chunks_response_empty(self):
        """Test empty chunks response."""
        response = ChunksResponse(
            product_id="prod-1",
            product_name="Product",
            version=1,
        )

        assert response.product_id == "prod-1"
        assert len(response.chunks) == 0
        assert response.total_count == 0
        assert response.returned_count == 0
        assert response.has_more is False


# ============================================================================
# HELPER FUNCTION TESTS
# ============================================================================


class TestExtractChunkMetadata:
    """Test metadata extraction helper."""

    def test_extract_metadata_full(self):
        """Test extracting full metadata from payload."""
        payload = {
            "chunk_id": "chunk-1",
            "chunk_text": "test content",
            "chunk_order": 2,
            "source_file": "doc.pdf",
            "section": "Methods",
            "page_number": 5,
            "confidence_score": 0.98,
            "noise_score": 0.02,
            "coherence_score": 0.95,
        }

        metadata = _extract_chunk_metadata(payload)

        assert metadata.chunk_id == "chunk-1"
        assert metadata.chunk_text == "test content"
        assert metadata.chunk_order == 2
        assert metadata.source_file == "doc.pdf"
        assert metadata.page_number == 5
        assert metadata.confidence_score == 0.98

    def test_extract_metadata_partial(self):
        """Test extracting partial metadata with defaults."""
        payload = {
            "chunk_id": "chunk-2",
            "chunk_text": "minimal content",
        }

        metadata = _extract_chunk_metadata(payload)

        assert metadata.chunk_id == "chunk-2"
        assert metadata.chunk_text == "minimal content"
        assert metadata.chunk_order == 0
        assert metadata.source_file is None
        assert metadata.page_number is None

    def test_extract_metadata_empty_payload(self):
        """Test extracting metadata from empty payload."""
        metadata = _extract_chunk_metadata({})

        assert metadata.chunk_id == ""
        assert metadata.chunk_text == ""
        assert metadata.chunk_order == 0

    def test_extract_metadata_truncates_long_text(self):
        """Test that long chunk text is truncated."""
        long_text = "x" * 2000
        payload = {
            "chunk_id": "chunk-3",
            "chunk_text": long_text,
        }

        metadata = _extract_chunk_metadata(payload)

        assert len(metadata.chunk_text) == 1000
        assert metadata.chunk_text == "x" * 1000


class TestRetrieveChunksPaginated:
    """Test paginated chunk retrieval."""

    def test_retrieve_chunks_single_batch(self):
        """Test retrieving chunks from single batch."""
        mock_client = Mock()
        test_points = [
            {
                "id": "p1",
                "vector": [0.1] * 384,
                "payload": {
                    "chunk_id": "c1",
                    "chunk_text": "text1",
                    "chunk_order": 0,
                },
            },
            {
                "id": "p2",
                "vector": [0.2] * 384,
                "payload": {
                    "chunk_id": "c2",
                    "chunk_text": "text2",
                    "chunk_order": 1,
                },
            },
        ]
        mock_client.scroll_points.return_value = iter(test_points)

        chunks = _retrieve_chunks_paginated(mock_client, "coll1", offset=0, limit=100)

        assert len(chunks) == 2
        assert chunks[0].id == "p1"
        assert chunks[0].metadata.chunk_text == "text1"
        assert chunks[1].id == "p2"
        assert chunks[1].metadata.chunk_text == "text2"

    def test_retrieve_chunks_with_offset(self):
        """Test retrieving chunks with offset pagination."""
        mock_client = Mock()
        test_points = [
            {
                "id": "p1",
                "payload": {"chunk_id": "c1", "chunk_text": "text1"},
            },
            {
                "id": "p2",
                "payload": {"chunk_id": "c2", "chunk_text": "text2"},
            },
            {
                "id": "p3",
                "payload": {"chunk_id": "c3", "chunk_text": "text3"},
            },
        ]
        mock_client.scroll_points.return_value = iter(test_points)

        chunks = _retrieve_chunks_paginated(mock_client, "coll1", offset=1, limit=2)

        # Should skip first item and return next 2
        assert len(chunks) == 2
        assert chunks[0].id == "p2"
        assert chunks[1].id == "p3"

    def test_retrieve_chunks_with_limit(self):
        """Test retrieving chunks respects limit."""
        mock_client = Mock()
        test_points = [
            {"id": f"p{i}", "payload": {"chunk_id": f"c{i}", "chunk_text": f"text{i}"}}
            for i in range(10)
        ]
        mock_client.scroll_points.return_value = iter(test_points)

        chunks = _retrieve_chunks_paginated(mock_client, "coll1", offset=0, limit=3)

        assert len(chunks) == 3
        assert chunks[0].id == "p0"
        assert chunks[2].id == "p2"

    def test_retrieve_chunks_error_handling(self):
        """Test error handling in pagination."""
        mock_client = Mock()
        mock_client.scroll_points.side_effect = Exception("Connection error")

        chunks = _retrieve_chunks_paginated(mock_client, "coll1", offset=0, limit=100)

        assert len(chunks) == 0

    def test_retrieve_chunks_empty_result(self):
        """Test retrieving chunks from empty collection."""
        mock_client = Mock()
        mock_client.scroll_points.return_value = iter([])

        chunks = _retrieve_chunks_paginated(mock_client, "coll1", offset=0, limit=100)

        assert len(chunks) == 0


# ============================================================================
# API ENDPOINT TESTS
# ============================================================================


class TestGetChunksEndpoint:
    """Test get_chunks API endpoint."""

    @pytest.mark.asyncio
    async def test_get_chunks_success(self, mock_db, test_product, test_product_id, mock_current_user):
        """Test successful chunks retrieval."""
        # Setup mocks
        mock_db.query.return_value.filter.return_value.first.return_value = test_product

        mock_client = Mock()
        mock_client.get_collection_name.return_value = "collection_v1"
        mock_client.scroll_points.return_value = iter(
            [
                {
                    "id": "p1",
                    "payload": {
                        "chunk_id": "c1",
                        "chunk_text": "content1",
                    },
                },
            ]
        )

        with patch(
            "primedata.api.chunks.get_vector_search_client", return_value=mock_client
        ):
            response = await get_chunks(
                product_id=test_product_id,
                version=1,
                offset=0,
                limit=100,
                db=mock_db,
                current_user=mock_current_user,
            )

        assert response.product_id == str(test_product_id)
        assert response.product_name == "Test Product"
        assert response.version == 1
        assert response.returned_count == 1

    @pytest.mark.asyncio
    async def test_get_chunks_product_not_found(self, mock_db, test_product_id, mock_current_user):
        """Test chunks retrieval with product not found."""
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await get_chunks(
                product_id=test_product_id,
                version=1,
                offset=0,
                limit=100,
                db=mock_db,
                current_user=mock_current_user,
            )

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_get_chunks_uses_current_version(
        self, mock_db, test_product, test_product_id, mock_current_user
    ):
        """Test that current version is used when not specified."""
        test_product.current_version = 5
        mock_db.query.return_value.filter.return_value.first.return_value = test_product

        mock_client = Mock()
        mock_client.get_collection_name.return_value = "collection_v5"
        mock_client.scroll_points.return_value = iter([])

        with patch(
            "primedata.api.chunks.get_vector_search_client", return_value=mock_client
        ):
            response = await get_chunks(
                product_id=test_product_id,
                version=None,  # No version specified
                offset=0,
                limit=100,
                db=mock_db,
                current_user=mock_current_user,
            )

        assert response.version == 5
        mock_client.get_collection_name.assert_called_with(
            test_product.workspace_id, test_product_id, 5
        )

    @pytest.mark.asyncio
    async def test_get_chunks_no_collection(
        self, mock_db, test_product, test_product_id, mock_current_user
    ):
        """Test chunks retrieval when no collection exists."""
        mock_db.query.return_value.filter.return_value.first.return_value = test_product

        mock_client = Mock()
        mock_client.get_collection_name.return_value = None

        with patch(
            "primedata.api.chunks.get_vector_search_client", return_value=mock_client
        ):
            response = await get_chunks(
                product_id=test_product_id,
                version=1,
                offset=0,
                limit=100,
                db=mock_db,
                current_user=mock_current_user,
            )

        assert response.total_count == 0
        assert response.returned_count == 0
        assert len(response.chunks) == 0
        assert response.has_more is False

    @pytest.mark.asyncio
    async def test_get_chunks_pagination_has_more(
        self, mock_db, test_product, test_product_id, mock_current_user
    ):
        """Test pagination has_more flag when limit matches returned count."""
        mock_db.query.return_value.filter.return_value.first.return_value = test_product

        mock_client = Mock()
        mock_client.get_collection_name.return_value = "collection_v1"
        # Return exactly limit items
        mock_client.scroll_points.return_value = iter(
            [
                {
                    "id": f"p{i}",
                    "payload": {"chunk_id": f"c{i}", "chunk_text": f"text{i}"},
                }
                for i in range(10)
            ]
        )

        with patch(
            "primedata.api.chunks.get_vector_search_client", return_value=mock_client
        ):
            response = await get_chunks(
                product_id=test_product_id,
                version=1,
                offset=0,
                limit=10,
                db=mock_db,
                current_user=mock_current_user,
            )

        assert response.returned_count == 10
        assert response.limit == 10
        assert response.has_more is True

    @pytest.mark.asyncio
    async def test_get_chunks_pagination_no_more(
        self, mock_db, test_product, test_product_id, mock_current_user
    ):
        """Test pagination has_more is false when fewer items than limit."""
        mock_db.query.return_value.filter.return_value.first.return_value = test_product

        mock_client = Mock()
        mock_client.get_collection_name.return_value = "collection_v1"
        # Return fewer items than limit
        mock_client.scroll_points.return_value = iter(
            [
                {
                    "id": f"p{i}",
                    "payload": {"chunk_id": f"c{i}", "chunk_text": f"text{i}"},
                }
                for i in range(5)
            ]
        )

        with patch(
            "primedata.api.chunks.get_vector_search_client", return_value=mock_client
        ):
            response = await get_chunks(
                product_id=test_product_id,
                version=1,
                offset=0,
                limit=10,
                db=mock_db,
                current_user=mock_current_user,
            )

        assert response.returned_count == 5
        assert response.limit == 10
        assert response.has_more is False

    @pytest.mark.asyncio
    async def test_get_chunks_error_handling(
        self, mock_db, test_product, test_product_id, mock_current_user
    ):
        """Test error handling during chunk retrieval returns empty chunks gracefully."""
        mock_db.query.return_value.filter.return_value.first.return_value = test_product

        mock_client = Mock()
        mock_client.get_collection_name.return_value = "collection_v1"
        mock_client.scroll_points.side_effect = Exception("Vector DB error")

        with patch(
            "primedata.api.chunks.get_vector_search_client", return_value=mock_client
        ):
            # Should not raise, but return empty chunks gracefully
            response = await get_chunks(
                product_id=test_product_id,
                version=1,
                offset=0,
                limit=100,
                db=mock_db,
                current_user=mock_current_user,
            )

        # Should return successful response with empty chunks
        assert response.product_id == str(test_product_id)
        assert response.returned_count == 0
        assert len(response.chunks) == 0


# ============================================================================
# EDGE CASE TESTS
# ============================================================================


class TestChunksEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_pagination_offset_zero(self):
        """Test pagination with offset=0."""
        mock_client = Mock()
        mock_client.scroll_points.return_value = iter([{"id": "p1", "payload": {}}])

        chunks = _retrieve_chunks_paginated(mock_client, "coll", offset=0, limit=10)

        assert len(chunks) == 1

    def test_pagination_limit_max(self):
        """Test pagination with max limit."""
        mock_client = Mock()
        mock_client.scroll_points.return_value = iter(
            [{"id": f"p{i}", "payload": {}} for i in range(1000)]
        )

        chunks = _retrieve_chunks_paginated(mock_client, "coll", offset=0, limit=1000)

        assert len(chunks) == 1000

    def test_pagination_offset_beyond_available(self):
        """Test pagination with offset beyond available items."""
        mock_client = Mock()
        mock_client.scroll_points.return_value = iter(
            [{"id": "p1", "payload": {}}]
        )

        chunks = _retrieve_chunks_paginated(mock_client, "coll", offset=100, limit=10)

        assert len(chunks) == 0

    def test_chunk_with_missing_payload(self):
        """Test chunk without payload field."""
        mock_client = Mock()
        mock_client.scroll_points.return_value = iter([{"id": "p1"}])

        chunks = _retrieve_chunks_paginated(mock_client, "coll", offset=0, limit=10)

        assert len(chunks) == 1
        assert chunks[0].metadata.chunk_id == ""

    def test_chunk_with_special_characters_in_text(self):
        """Test chunk with special characters."""
        payload = {
            "chunk_id": "c1",
            "chunk_text": "Special chars: @#$%^&*()_+-=[]{}|;:',.<>?",
        }

        metadata = _extract_chunk_metadata(payload)

        assert metadata.chunk_text == "Special chars: @#$%^&*()_+-=[]{}|;:',.<>?"

    def test_chunk_with_unicode_text(self):
        """Test chunk with unicode characters."""
        payload = {
            "chunk_id": "c1",
            "chunk_text": "Unicode: 中文, العربية, Русский, 日本語",
        }

        metadata = _extract_chunk_metadata(payload)

        assert "中文" in metadata.chunk_text
        assert "العربية" in metadata.chunk_text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
