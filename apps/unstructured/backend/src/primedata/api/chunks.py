"""
Chunks Retrieval API Endpoints

Provides endpoints for retrieving processed chunks from the vector database.
Supports pagination, filtering, and version targeting.
"""

from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from primedata.core.security import get_current_user
from primedata.db.database import get_db
from primedata.db.models import Product
from primedata.indexing.vector_search_client import get_vector_search_client
from primedata.utils.log_utils import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Chunks"])


# ============================================================================
# RESPONSE MODELS
# ============================================================================


class ChunkMetadata(BaseModel):
    """Metadata for a chunk."""

    chunk_id: str = Field(..., description="Unique chunk identifier")
    chunk_text: str = Field(..., description="Chunk content text")
    chunk_order: int = Field(default=0, description="Order of chunk in document")
    source_file: Optional[str] = Field(None, description="Source file name")
    section: Optional[str] = Field(None, description="Document section")
    page_number: Optional[int] = Field(None, description="Page number (if applicable)")
    confidence_score: Optional[float] = Field(None, description="Quality confidence score")
    noise_score: Optional[float] = Field(None, description="Noise level score")
    coherence_score: Optional[float] = Field(None, description="Coherence score")


class ChunkPoint(BaseModel):
    """Chunk point from vector database."""

    id: str = Field(..., description="Point ID in vector database")
    vector_size: Optional[int] = Field(None, description="Vector embedding dimension")
    metadata: ChunkMetadata = Field(..., description="Chunk metadata")

    class Config:
        extra = "allow"  # Allow additional fields from payload


class ChunksResponse(BaseModel):
    """Response model for chunks listing."""

    product_id: str
    product_name: str
    version: int
    chunks: List[ChunkPoint] = Field(default_factory=list, description="List of chunks")
    total_count: int = Field(0, description="Total number of chunks available")
    returned_count: int = Field(0, description="Number of chunks returned in this response")
    offset: int = Field(0, description="Pagination offset used")
    limit: int = Field(100, description="Pagination limit used")
    has_more: bool = Field(False, description="Whether more chunks are available")


# ============================================================================
# API ENDPOINTS
# ============================================================================


@router.get("/products/{product_id}/chunks", response_model=ChunksResponse)
async def get_chunks(
    product_id: UUID,
    version: Optional[int] = Query(None, description="Product version (defaults to current)"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(100, ge=1, le=1000, description="Pagination limit"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> ChunksResponse:
    """
    Get chunks for a product.

    Retrieves processed chunks from the vector database with pagination support.

    Args:
        product_id: Product UUID
        version: Optional product version (defaults to current_version)
        offset: Pagination offset (default 0)
        limit: Pagination limit (default 100, max 1000)
        db: Database session
        current_user: Authenticated user

    Returns:
        Chunks with metadata and pagination info

    Raises:
        404: Product not found
        500: Retrieval error
    """
    logger.info(
        f"Getting chunks | product_id={product_id}, version={version}, "
        f"offset={offset}, limit={limit}"
    )

    try:
        # Verify product exists
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            logger.warning(f"Product not found: {product_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product not found: {product_id}",
            )

        # Get vector search client
        vector_search_client = get_vector_search_client()

        # Determine collection name to query
        collection_name = None

        if version is None:
            # No specific version requested: use production alias (points to promoted version)
            logger.info(f"📊 [CHUNKS] Version not specified, using production alias")
            collection_name = vector_search_client.get_prod_alias_collection(
                workspace_id=str(product.workspace_id),
                product_id=str(product_id),
                product_name=product.name
            )
            if collection_name:
                logger.info(f"✅ [CHUNKS] Got collection from prod alias: {collection_name}")
                target_version = "promoted"
            else:
                # Fallback to current_version if no alias exists
                logger.warning(f"⚠️ [CHUNKS] No production alias found, falling back to current_version")
                target_version = product.current_version
        else:
            # Specific version requested: generate index name for that version
            logger.info(f"📊 [CHUNKS] Version {version} specified, generating index name")
            target_version = version

        # If collection_name not set yet, generate it
        if not collection_name:
            logger.debug(f"🔎 [CHUNKS] Generating collection name for workspace={product.workspace_id}, product={product_id}, version={target_version}, product_name={product.name}")
            collection_name = vector_search_client.get_collection_name(
                product.workspace_id, product_id, target_version, product.name
            )
            logger.debug(f"📝 [CHUNKS] Generated collection name: {collection_name}")

        # Check if collection exists
        if not collection_name:
            logger.info(f"⚠️ [CHUNKS] No chunks found for product {product_id} version {target_version}")
            return ChunksResponse(
                product_id=str(product_id),
                product_name=product.name,
                version=target_version if isinstance(target_version, int) else product.current_version,
                chunks=[],
                total_count=0,
                returned_count=0,
                offset=offset,
                limit=limit,
                has_more=False,
            )

        logger.info(f"🔍 [CHUNKS] Querying collection: {collection_name}")

        # Retrieve chunks from vector database with pagination
        chunks = _retrieve_chunks_paginated(
            vector_search_client, collection_name, offset, limit
        )

        logger.info(
            f"✅ [CHUNKS] Chunks retrieved | product={product.name}, collection={collection_name}, "
            f"count={len(chunks)}, offset={offset}, limit={limit}"
        )

        return ChunksResponse(
            product_id=str(product_id),
            product_name=product.name,
            version=target_version if isinstance(target_version, int) else product.current_version,
            chunks=chunks,
            total_count=len(chunks) + offset,  # Approximate total
            returned_count=len(chunks),
            offset=offset,
            limit=limit,
            has_more=len(chunks) == limit,  # Has more if we got exactly limit items
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving chunks: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve chunks",
        )


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def _retrieve_chunks_paginated(
    vector_search_client, collection_name: str, offset: int, limit: int
) -> List[ChunkPoint]:
    """
    Retrieve chunks with offset-based pagination using OpenSearch from/size.

    Uses OpenSearch's native from/size parameters for efficient pagination.

    Args:
        vector_search_client: Vector search client instance
        collection_name: Name of collection to query
        offset: Starting position (from parameter)
        limit: Maximum number of items to return (size parameter)

    Returns:
        List of ChunkPoint objects
    """
    try:
        # Use search_with_filters with no filters to get all documents
        # This leverages OpenSearch's from/size for efficient pagination
        chunks_raw, total_count = vector_search_client.search_with_filters(
            collection_name=collection_name,
            filters=None,  # No filters - get all documents
            sort_by=None,  # No specific sort
            sort_order="desc",
            offset=offset,
            limit=limit,
        )

        # Extract metadata from each chunk
        chunks = []
        for point in chunks_raw:
            payload = point.get("payload", {})
            if not payload:
                logger.warning(f"⚠️ Point {point.get('id')} has no payload")
                continue

            metadata = _extract_chunk_metadata(payload)
            chunk = ChunkPoint(
                id=point.get("id", ""),
                vector_size=len(point.get("vector", [])) if point.get("vector") else None,
                metadata=metadata,
            )
            chunks.append(chunk)

        logger.debug(f"Retrieved {len(chunks)} chunks with offset={offset}, limit={limit}")
        return chunks

    except Exception as e:
        logger.error(f"Error retrieving paginated chunks: {e}", exc_info=True)
        return []


def _extract_chunk_metadata(payload: dict) -> ChunkMetadata:
    """
    Extract chunk metadata from vector database payload.

    OpenSearch stores data flat at top level (not nested under payload).

    Args:
        payload: Full _source from OpenSearch document

    Returns:
        ChunkMetadata object
    """
    # Note: chunks stored in OpenSearch use "text" field, not "chunk_text"
    chunk_text = payload.get("text") or payload.get("chunk_text", "")
    return ChunkMetadata(
        chunk_id=payload.get("chunk_id", ""),
        chunk_text=chunk_text[:1000],  # Limit to 1000 chars
        chunk_order=payload.get("chunk_order", 0),
        source_file=payload.get("source_file"),
        section=payload.get("section"),
        page_number=payload.get("page_number"),
        confidence_score=payload.get("confidence_score"),
        noise_score=payload.get("noise_score"),
        coherence_score=payload.get("coherence_score"),
    )
