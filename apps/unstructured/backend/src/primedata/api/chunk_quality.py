"""
Chunk Quality Drill-Down API

Provides advanced chunk quality filtering and analysis capabilities.
Supports filtering by quality scores, metadata, and detecting boundary issues.
"""

from typing import Optional, List
from uuid import UUID
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from primedata.core.security import get_current_user
from primedata.db.database import get_db
from primedata.db.models import Product
from primedata.indexing.vector_search_client import get_vector_search_client
from primedata.services.quality_analysis import (
    detect_mid_sentence_boundaries,
    identify_quality_issues,
    calculate_text_similarity,
    calculate_cosine_similarity,
    calculate_euclidean_distance,
    matches_filters,
)
from primedata.utils.log_utils import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/chunk-quality", tags=["Chunk Quality"])


# ============================================================================
# ENUMS
# ============================================================================


class SortOrder(str, Enum):
    """Sort order enum."""

    ASC = "asc"
    DESC = "desc"


class SortField(str, Enum):
    """Sortable fields enum."""

    CONFIDENCE = "confidence_score"
    COHERENCE = "coherence_score"
    NOISE = "noise_score"
    CHUNK_ORDER = "chunk_order"
    PAGE_NUMBER = "page_number"
    SOURCE_FILE = "source_file"
    SCORE = "score"  # AI Trust Score


# ============================================================================
# FILTER MODELS
# ============================================================================


class QualityScoreFilter(BaseModel):
    """Quality score filter."""

    min_score: Optional[float] = Field(None, ge=0, le=100, description="Minimum score")
    max_score: Optional[float] = Field(None, ge=0, le=100, description="Maximum score")


class ChunkQualityFilters(BaseModel):
    """Filters for chunk quality queries."""

    confidence: Optional[QualityScoreFilter] = Field(None, description="Confidence score filter")
    coherence: Optional[QualityScoreFilter] = Field(None, description="Coherence score filter")
    noise: Optional[QualityScoreFilter] = Field(None, description="Noise score filter (inverted)")
    score: Optional[QualityScoreFilter] = Field(None, description="AI Trust Score filter")
    source_file: Optional[str] = Field(None, description="Source file filter")
    section: Optional[str] = Field(None, description="Section filter")
    page_number: Optional[int] = Field(None, ge=1, description="Page number filter")


# ============================================================================
# RESPONSE MODELS
# ============================================================================


class QualityChunkMetadata(BaseModel):
    """Extended metadata for quality analysis."""

    chunk_id: str
    chunk_text: str = Field(..., description="Chunk content")
    chunk_order: int
    source_file: Optional[str] = None
    section: Optional[str] = None
    page_number: Optional[int] = None
    confidence_score: float = Field(0.0, ge=0, le=100)
    noise_score: float = Field(0.0, ge=0, le=100)
    coherence_score: float = Field(0.0, ge=0, le=100)
    score: float = Field(0.0, description="AI Trust Score")
    mid_sentence_start: bool = Field(False, description="Chunk starts mid-sentence")
    mid_sentence_end: bool = Field(False, description="Chunk ends mid-sentence")
    raw_text: Optional[str] = Field(None, description="Original raw text before cleaning")
    has_raw_text: bool = Field(False, description="Whether raw text is available")


class QualityChunkPoint(BaseModel):
    """Quality-analyzed chunk point."""

    id: str
    metadata: QualityChunkMetadata
    quality_issues: List[str] = Field(default_factory=list, description="Quality issues found")


class ChunkQualityResponse(BaseModel):
    """Response for chunk quality drill-down."""

    product_id: str
    product_name: str
    version: int
    chunks: List[QualityChunkPoint]
    total_count: int
    returned_count: int
    offset: int
    limit: int
    has_more: bool
    quality_summary: Optional[dict] = Field(None, description="Summary statistics")


# ============================================================================
# API ENDPOINTS
# ============================================================================


@router.get(
    "/products/{product_id}/versions/{version}/chunks",
    response_model=ChunkQualityResponse,
)
async def get_chunk_quality(
    product_id: UUID,
    version: int,
    offset: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(100, ge=1, le=1000, description="Pagination limit"),
    sort_by: SortField = Query(SortField.CONFIDENCE, description="Sort field"),
    sort_order: SortOrder = Query(SortOrder.DESC, description="Sort order"),
    confidence_min: Optional[float] = Query(None, ge=0, le=100, description="Min confidence"),
    confidence_max: Optional[float] = Query(None, ge=0, le=100, description="Max confidence"),
    noise_max: Optional[float] = Query(None, ge=0, le=100, description="Max noise"),
    coherence_min: Optional[float] = Query(None, ge=0, le=100, description="Min coherence"),
    score_min: Optional[float] = Query(None, ge=0, description="Min AI Trust Score"),
    score_max: Optional[float] = Query(None, ge=0, description="Max AI Trust Score"),
    source_file: Optional[str] = Query(None, description="Filter by source file"),
    section: Optional[str] = Query(None, description="Filter by section"),
    page_number: Optional[int] = Query(None, ge=1, description="Filter by page number"),
    skip_mid_sentence: bool = Query(False, description="Skip mid-sentence chunks"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> ChunkQualityResponse:
    """
    Get chunks with quality analysis and filtering.

    Advanced filtering by quality scores, metadata, and boundary detection.
    """
    logger.info(
        f"ENTRY get_chunk_quality | product_id={product_id}, version={version}, "
        f"offset={offset}, limit={limit}, sort_by={sort_by}, sort_order={sort_order}"
    )
    logger.info(f"   Filters: confidence_min={confidence_min}, confidence_max={confidence_max}, noise_max={noise_max}, coherence_min={coherence_min}")

    try:
        # Step 1: Verify product exists
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            logger.warning(f"Product not found: {product_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product not found: {product_id}",
            )

        # Step 2: Build filters
        confidence_filter = None
        if confidence_min is not None and confidence_max is not None:
            confidence_filter = QualityScoreFilter(
                min_score=float(confidence_min) if confidence_min else None,
                max_score=float(confidence_max) if confidence_max else None
            )
        elif confidence_min is not None or confidence_max is not None:
            confidence_filter = QualityScoreFilter(
                min_score=float(confidence_min) if confidence_min is not None else None,
                max_score=float(confidence_max) if confidence_max is not None else None
            )

        coherence_filter = None
        if coherence_min is not None:
            coherence_filter = QualityScoreFilter(min_score=float(coherence_min))

        noise_filter = None
        if noise_max is not None:
            noise_filter = QualityScoreFilter(max_score=float(noise_max))

        score_filter = None
        if score_min is not None and score_max is not None:
            score_filter = QualityScoreFilter(
                min_score=float(score_min) if score_min else None,
                max_score=float(score_max) if score_max else None
            )
        elif score_min is not None or score_max is not None:
            score_filter = QualityScoreFilter(
                min_score=float(score_min) if score_min is not None else None,
                max_score=float(score_max) if score_max is not None else None
            )

        filters = ChunkQualityFilters(
            confidence=confidence_filter,
            coherence=coherence_filter,
            noise=noise_filter,
            score=score_filter,
            source_file=source_file,
            section=section,
            page_number=page_number,
        )

        # Step 3: Get vector search client
        vector_search_client = get_vector_search_client()

        # Step 4: Get collection name
        collection_name = vector_search_client.find_collection_name(
            product.workspace_id, product_id, version, product.name
        )
        if not collection_name:
            return ChunkQualityResponse(
                product_id=str(product_id),
                product_name=product.name,
                version=version,
                chunks=[],
                total_count=0,
                returned_count=0,
                offset=offset,
                limit=limit,
                has_more=False,
            )

        # Step 5: Retrieve and filter chunks
        chunks, quality_summary = _retrieve_and_filter_chunks(
            vector_search_client,
            collection_name,
            filters,
            sort_by,
            sort_order,
            offset,
            limit,
            skip_mid_sentence,
            product_id,
            version,
            db,
        )

        return ChunkQualityResponse(
            product_id=str(product_id),
            product_name=product.name,
            version=version,
            chunks=chunks,
            total_count=quality_summary.get("total_available", 0),
            returned_count=len(chunks),
            offset=offset,
            limit=limit,
            has_more=(offset + len(chunks)) < quality_summary.get("total_available", 0),
            quality_summary=quality_summary,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving chunk quality: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve chunk quality",
        )


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def _retrieve_and_filter_chunks(
    vector_search_client,
    collection_name: str,
    filters: ChunkQualityFilters,
    sort_by: SortField,
    sort_order: SortOrder,
    offset: int,
    limit: int,
    skip_mid_sentence: bool,
    product_id: UUID,
    version: int,
    db: Session,
) -> tuple:
    """
    Retrieve and apply quality filters to chunks using OpenSearch pagination.

    Uses search_with_filters for efficient server-side filtering and pagination.
    """
    try:
        logger.info(f"ENTRY _retrieve_and_filter_chunks | collection={collection_name}")

        # Build filter dict for OpenSearch
        os_filters = {}

        if filters.noise:
            os_filters["noise_score"] = {"max": filters.noise.max_score} if filters.noise.max_score is not None else {}

        if filters.confidence:
            os_filters["confidence_score"] = {}
            if filters.confidence.min_score is not None:
                os_filters["confidence_score"]["min"] = filters.confidence.min_score
            if filters.confidence.max_score is not None:
                os_filters["confidence_score"]["max"] = filters.confidence.max_score

        if filters.coherence:
            os_filters["coherence_score"] = {"min": filters.coherence.min_score} if filters.coherence.min_score is not None else {}

        if filters.score:
            os_filters["score"] = {}
            if filters.score.min_score is not None:
                os_filters["score"]["min"] = filters.score.min_score
            if filters.score.max_score is not None:
                os_filters["score"]["max"] = filters.score.max_score

        # Add metadata filters
        if filters.source_file:
            os_filters["source_file"] = filters.source_file

        if filters.section:
            os_filters["section"] = filters.section

        if filters.page_number:
            os_filters["page_number"] = filters.page_number

        # Query OpenSearch with filters and pagination
        chunks_raw, total_count = vector_search_client.search_with_filters(
            collection_name=collection_name,
            filters=os_filters,
            sort_by=sort_by.value if sort_by else None,
            sort_order=sort_order.value,
            offset=offset,
            limit=limit,
        )

        logger.info(f"OpenSearch query complete | returned={len(chunks_raw)}, total_available={total_count}")

        # Post-process: extract metadata, detect boundaries, identify issues
        all_chunks = []
        quality_stats = {
            "total_checked": len(chunks_raw),
            "filtered_out": 0,
            "mid_sentence_issues": 0,
            "errors": 0,
        }

        for point in chunks_raw:
            try:
                chunk_id = point.get("id", "?")
                payload = point.get("payload", {})

                if not payload:
                    quality_stats["errors"] += 1
                    continue

                # Extract metadata
                try:
                    chunk_metadata = _extract_quality_metadata(payload, str(product_id), version, db)
                except Exception as e:
                    logger.warning(f"Failed to extract metadata for chunk {chunk_id}: {e}")
                    quality_stats["errors"] += 1
                    continue

                # Check mid-sentence boundaries
                try:
                    mid_start, mid_end = detect_mid_sentence_boundaries(chunk_metadata.chunk_text)
                    chunk_metadata.mid_sentence_start = mid_start
                    chunk_metadata.mid_sentence_end = mid_end
                except Exception as e:
                    logger.warning(f"Failed to detect boundaries for chunk {chunk_id}: {e}")
                    mid_start, mid_end = False, False

                # Skip if mid-sentence
                if skip_mid_sentence and (mid_start or mid_end):
                    quality_stats["mid_sentence_issues"] += 1
                    quality_stats["filtered_out"] += 1
                    continue

                # Identify issues
                try:
                    issues = identify_quality_issues(chunk_metadata, mid_start, mid_end)
                except Exception as e:
                    logger.warning(f"Failed to identify issues for chunk {chunk_id}: {e}")
                    issues = []

                point_obj = QualityChunkPoint(
                    id=point.get("id", ""),
                    metadata=chunk_metadata,
                    quality_issues=issues,
                )
                all_chunks.append(point_obj)

            except Exception as e:
                logger.warning(f"Error processing point: {e}")
                quality_stats["errors"] += 1
                continue

        logger.info(f"Post-processing complete | retained={len(all_chunks)}, filtered={quality_stats['filtered_out']}, errors={quality_stats['errors']}")

        # Build summary
        quality_summary = {
            "total_checked": quality_stats["total_checked"],
            "total_retained": len(all_chunks),
            "filtered_out": quality_stats["filtered_out"],
            "mid_sentence_issues": quality_stats["mid_sentence_issues"],
            "errors": quality_stats["errors"],
            "total_available": total_count,
            "avg_confidence": (
                sum(c.metadata.confidence_score for c in all_chunks) / len(all_chunks)
                if all_chunks
                else 0
            ),
            "avg_noise": (
                sum(c.metadata.noise_score for c in all_chunks) / len(all_chunks)
                if all_chunks
                else 0
            ),
        }

        return all_chunks, quality_summary

    except Exception as e:
        logger.error(f"Fatal error in _retrieve_and_filter_chunks: {type(e).__name__}: {e}", exc_info=True)
        return [], {}


def _get_payload(point: dict) -> dict:
    """Extract payload from OpenSearch point.

    OpenSearch scroll_points returns: {"id": "...", "payload": {...}, "vector": [...]}
    """
    if not point:
        return {}

    payload = point.get("payload", {})
    return payload


def _extract_quality_metadata(payload: dict, product_id: str = None, version: int = None, db: Session = None) -> QualityChunkMetadata:
    """Extract enhanced metadata for quality analysis.

    Fetches raw_text from OpenSearch payload (stored during indexing).
    """
    # Note: chunks stored in OpenSearch use "text" field, not "chunk_text"
    chunk_text = payload.get("text") or payload.get("chunk_text", "")

    # Get raw_text from payload (stored during indexing from preprocessing stage)
    raw_text = payload.get("raw_text")
    has_raw_text = bool(raw_text)

    # Safely extract scores with fallback to 0.0
    try:
        confidence_score = float(payload.get("confidence_score") or 0)
    except (TypeError, ValueError):
        confidence_score = 0.0

    try:
        noise_score = float(payload.get("noise_score") or 0)
    except (TypeError, ValueError):
        noise_score = 0.0

    try:
        coherence_score = float(payload.get("coherence_score") or 0)
    except (TypeError, ValueError):
        coherence_score = 0.0

    return QualityChunkMetadata(
        chunk_id=payload.get("chunk_id", ""),
        chunk_text=chunk_text[:1000] if chunk_text else "",
        chunk_order=payload.get("chunk_order", 0),
        source_file=payload.get("source_file"),
        section=payload.get("section"),
        page_number=payload.get("page_number"),
        confidence_score=confidence_score,
        noise_score=noise_score,
        coherence_score=coherence_score,
        score=float(payload.get("score") or 0),
        raw_text=raw_text[:1000] if raw_text else None,
        has_raw_text=has_raw_text,
    )


@router.get(
    "/products/{product_id}/versions/{version}/inspect",
    tags=["Chunk Quality Debug"],
)
async def inspect_collection(
    product_id: UUID,
    version: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """
    DEBUG: Inspect a collection to see sample documents and field names.

    Useful for troubleshooting empty results or field mapping issues.
    """
    try:
        logger.info(f"Inspecting collection | product_id={product_id}, version={version}")

        # Get product
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

        # Get vector search client and collection name
        vector_search_client = get_vector_search_client()
        collection_name = vector_search_client.find_collection_name(
            product.workspace_id, product_id, version, product.name
        )

        if not collection_name:
            return {
                "status": "error",
                "message": f"No collection found for product {product_id} version {version}",
                "product_id": str(product_id),
                "version": version,
            }

        # Get sample document
        sample = vector_search_client.get_sample_document(collection_name)

        if not sample:
            return {
                "status": "empty",
                "message": f"Collection {collection_name} is empty or has no documents",
                "collection_name": collection_name,
                "product_id": str(product_id),
                "version": version,
            }

        # Count total documents
        try:
            query_body = {"size": 0, "query": {"match_all": {}}}
            response = vector_search_client.client.search(index=collection_name, body=query_body)
            total_count = response["hits"]["total"]["value"]
        except Exception as e:
            logger.warning(f"Could not get total count: {e}")
            total_count = None

        return {
            "status": "ok",
            "collection_name": collection_name,
            "total_documents": total_count,
            "sample_document": sample,
            "field_names": list(sample.keys()),
            "product_id": str(product_id),
            "version": version,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error inspecting collection: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to inspect collection: {str(e)}",
        )


# Register routes from the diff/summary sub-module
import primedata.api.chunk_quality_diff  # noqa: F401 - registers routes

# Backward-compatible aliases for tests that import private names
_matches_filters = matches_filters
_detect_mid_sentence_boundaries = detect_mid_sentence_boundaries
_identify_quality_issues = identify_quality_issues
_calculate_text_similarity = calculate_text_similarity
_calculate_cosine_similarity = calculate_cosine_similarity
_calculate_euclidean_distance = calculate_euclidean_distance


def _sort_chunks(
    chunks: List[QualityChunkPoint], sort_by: SortField, sort_order: SortOrder
) -> List[QualityChunkPoint]:
    """Deprecated: sorting is now done at OpenSearch level."""
    return chunks


# Re-export models from sub-module for backward compatibility
from primedata.api.chunk_quality_diff import ChunkDiffResponse, QualitySummaryResponse  # noqa: E402, F401
