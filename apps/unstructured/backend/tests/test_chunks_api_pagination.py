"""
Test for new OpenSearch from/size pagination in chunks API.

Tests the efficient offset-based pagination using OpenSearch's native from/size.
"""

import pytest
from uuid import uuid4, UUID
from unittest.mock import Mock, patch

from primedata.api.chunks import (
    _retrieve_chunks_paginated,
    _extract_chunk_metadata,
    ChunkPoint,
    ChunkMetadata,
)


class TestChunksPaginationWithSearchFilters:
    """Test pagination using search_with_filters with from/size."""

    def test_retrieve_chunks_pagination_first_page(self):
        """Test retrieving first page of chunks."""
        # Mock data: flat structure at top level
        mock_chunks_raw = [
            {
                "id": "chunk-1",
                "vector": [0.1, 0.2, 0.3],
                "payload": {
                    "chunk_id": "chunk-1",
                    "text": "First chunk content",
                    "chunk_order": 0,
                    "source_file": "doc1.pdf",
                    "section": "intro",
                    "page_number": 1,
                    "confidence_score": 0.95,
                    "noise_score": 0.05,
                    "coherence_score": 0.88,
                },
            },
            {
                "id": "chunk-2",
                "vector": [0.4, 0.5, 0.6],
                "payload": {
                    "chunk_id": "chunk-2",
                    "text": "Second chunk content",
                    "chunk_order": 1,
                    "source_file": "doc1.pdf",
                    "section": "body",
                    "page_number": 2,
                    "confidence_score": 0.92,
                    "noise_score": 0.08,
                    "coherence_score": 0.85,
                },
            },
        ]

        mock_client = Mock()
        mock_client.search_with_filters.return_value = (mock_chunks_raw, 100)

        # Call with offset=0, limit=2
        chunks = _retrieve_chunks_paginated(mock_client, "test_collection", offset=0, limit=2)

        # Verify search_with_filters was called with correct parameters
        mock_client.search_with_filters.assert_called_once_with(
            collection_name="test_collection",
            filters=None,
            sort_by=None,
            sort_order="desc",
            offset=0,
            limit=2,
        )

        # Verify chunks returned
        assert len(chunks) == 2
        assert chunks[0].id == "chunk-1"
        assert chunks[1].id == "chunk-2"
        assert chunks[0].metadata.chunk_id == "chunk-1"
        assert chunks[0].metadata.source_file == "doc1.pdf"
        assert chunks[1].metadata.section == "body"

    def test_retrieve_chunks_pagination_second_page(self):
        """Test retrieving second page with offset."""
        mock_chunks_raw = [
            {
                "id": "chunk-3",
                "vector": [0.7, 0.8, 0.9],
                "payload": {
                    "chunk_id": "chunk-3",
                    "text": "Third chunk",
                    "chunk_order": 2,
                    "source_file": "doc1.pdf",
                    "section": "conclusion",
                    "page_number": 3,
                    "confidence_score": 0.91,
                    "noise_score": 0.09,
                    "coherence_score": 0.87,
                },
            },
        ]

        mock_client = Mock()
        mock_client.search_with_filters.return_value = (mock_chunks_raw, 100)

        # Call with offset=2, limit=2 (get items 2-4)
        chunks = _retrieve_chunks_paginated(mock_client, "test_collection", offset=2, limit=2)

        # Verify search_with_filters was called with offset=2
        mock_client.search_with_filters.assert_called_once_with(
            collection_name="test_collection",
            filters=None,
            sort_by=None,
            sort_order="desc",
            offset=2,
            limit=2,
        )

        assert len(chunks) == 1
        assert chunks[0].id == "chunk-3"

    def test_metadata_extraction_from_flat_structure(self):
        """Test metadata extraction from flat top-level structure."""
        # Flat structure as stored in OpenSearch
        flat_payload = {
            "chunk_id": "test-chunk",
            "text": "Test chunk content here",
            "chunk_order": 5,
            "source_file": "document.pdf",
            "section": "methodology",
            "page_number": 15,
            "confidence_score": 0.96,
            "noise_score": 0.02,
            "coherence_score": 0.94,
            "vector": [0.1, 0.2, 0.3],
        }

        metadata = _extract_chunk_metadata(flat_payload)

        assert isinstance(metadata, ChunkMetadata)
        assert metadata.chunk_id == "test-chunk"
        assert metadata.chunk_text == "Test chunk content here"
        assert metadata.chunk_order == 5
        assert metadata.source_file == "document.pdf"
        assert metadata.section == "methodology"
        assert metadata.page_number == 15
        assert metadata.confidence_score == 0.96
        assert metadata.noise_score == 0.02
        assert metadata.coherence_score == 0.94

    def test_metadata_extraction_missing_optional_fields(self):
        """Test metadata extraction with missing optional fields."""
        partial_payload = {
            "chunk_id": "minimal-chunk",
            "text": "Minimal content",
            "chunk_order": 0,
        }

        metadata = _extract_chunk_metadata(partial_payload)

        assert metadata.chunk_id == "minimal-chunk"
        assert metadata.chunk_text == "Minimal content"
        assert metadata.source_file is None
        assert metadata.section is None
        assert metadata.page_number is None
        assert metadata.confidence_score is None

    def test_empty_result_set(self):
        """Test handling of empty result set."""
        mock_client = Mock()
        mock_client.search_with_filters.return_value = ([], 0)

        chunks = _retrieve_chunks_paginated(mock_client, "test_collection", offset=0, limit=10)

        assert len(chunks) == 0
        mock_client.search_with_filters.assert_called_once()

    def test_skip_chunks_with_missing_payload(self):
        """Test that chunks without payload are skipped."""
        mock_chunks_raw = [
            {
                "id": "chunk-1",
                "vector": [0.1, 0.2, 0.3],
                "payload": {
                    "chunk_id": "chunk-1",
                    "text": "Valid chunk",
                },
            },
            {
                "id": "chunk-2",
                "vector": [0.4, 0.5, 0.6],
                "payload": {},  # Empty payload - should be skipped
            },
            {
                "id": "chunk-3",
                "vector": [0.7, 0.8, 0.9],
                "payload": {
                    "chunk_id": "chunk-3",
                    "text": "Another valid chunk",
                },
            },
        ]

        mock_client = Mock()
        mock_client.search_with_filters.return_value = (mock_chunks_raw, 3)

        chunks = _retrieve_chunks_paginated(mock_client, "test_collection", offset=0, limit=10)

        # Should only return 2 valid chunks (chunk-1 and chunk-3)
        assert len(chunks) == 2
        assert chunks[0].id == "chunk-1"
        assert chunks[1].id == "chunk-3"

    def test_vector_size_calculation(self):
        """Test that vector_size is calculated correctly."""
        mock_chunks_raw = [
            {
                "id": "chunk-1",
                "vector": [0.1] * 3072,  # 3072-dimensional vector
                "payload": {
                    "chunk_id": "chunk-1",
                    "text": "Content",
                },
            },
            {
                "id": "chunk-2",
                "vector": None,  # Missing vector
                "payload": {
                    "chunk_id": "chunk-2",
                    "text": "Content",
                },
            },
        ]

        mock_client = Mock()
        mock_client.search_with_filters.return_value = (mock_chunks_raw, 2)

        chunks = _retrieve_chunks_paginated(mock_client, "test_collection", offset=0, limit=10)

        assert len(chunks) == 2
        assert chunks[0].vector_size == 3072
        assert chunks[1].vector_size is None

    def test_large_pagination_offset(self):
        """Test pagination with large offset."""
        mock_chunks_raw = [
            {
                "id": "chunk-1001",
                "vector": [0.1, 0.2, 0.3],
                "payload": {
                    "chunk_id": "chunk-1001",
                    "text": "Content at offset 1000",
                },
            },
        ]

        mock_client = Mock()
        mock_client.search_with_filters.return_value = (mock_chunks_raw, 5000)

        chunks = _retrieve_chunks_paginated(mock_client, "test_collection", offset=1000, limit=10)

        # Verify that offset was passed directly to search_with_filters
        mock_client.search_with_filters.assert_called_once_with(
            collection_name="test_collection",
            filters=None,
            sort_by=None,
            sort_order="desc",
            offset=1000,
            limit=10,
        )

        assert len(chunks) == 1
        assert chunks[0].id == "chunk-1001"

    def test_text_field_fallback(self):
        """Test that 'text' field is used over 'chunk_text'."""
        # OpenSearch stores as 'text', not 'chunk_text'
        payload_with_text = {
            "chunk_id": "chunk-1",
            "text": "This is the text field",
            "chunk_text": "This should not be used",  # Fallback only
        }

        metadata = _extract_chunk_metadata(payload_with_text)
        assert metadata.chunk_text == "This is the text field"

        # Test fallback when 'text' is not present
        payload_with_chunk_text = {
            "chunk_id": "chunk-2",
            "chunk_text": "This is chunk_text",
        }

        metadata = _extract_chunk_metadata(payload_with_chunk_text)
        assert metadata.chunk_text == "This is chunk_text"

    def test_chunk_text_truncation(self):
        """Test that chunk_text is truncated to 1000 chars."""
        long_text = "a" * 2000

        payload = {
            "chunk_id": "chunk-1",
            "text": long_text,
        }

        metadata = _extract_chunk_metadata(payload)
        assert len(metadata.chunk_text) == 1000
        assert metadata.chunk_text == "a" * 1000

    def test_exception_handling(self):
        """Test exception handling in pagination."""
        mock_client = Mock()
        mock_client.search_with_filters.side_effect = Exception("Connection error")

        chunks = _retrieve_chunks_paginated(mock_client, "test_collection", offset=0, limit=10)

        # Should return empty list on error
        assert len(chunks) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
