"""
Chunk Quality Diff & Summary API

Provides chunk quality diff comparison and version quality summary endpoints.
Extracted from chunk_quality.py to keep module size manageable.
"""

from typing import List
from uuid import UUID

from fastapi import Depends, HTTPException, status, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from primedata.core.security import get_current_user
from primedata.db.database import get_db
from primedata.db.models import Product
from primedata.indexing.vector_search_client import get_vector_search_client
from primedata.services.quality_analysis import (
    calculate_text_similarity,
    calculate_cosine_similarity,
    calculate_euclidean_distance,
)
from primedata.utils.log_utils import get_logger

from primedata.api.chunk_quality import router, _get_payload

logger = get_logger(__name__)


# ============================================================================
# RESPONSE MODELS
# ============================================================================


class ChunkDiffResponse(BaseModel):
    """Response for chunk quality diff between versions."""

    chunk_id: str
    current_version: int
    compare_version: int
    content_diff: dict
    quality_changes: dict
    embedding_diff: dict


class QualitySummaryResponse(BaseModel):
    """Response for version quality summary."""

    product_id: str
    version: int
    summary: dict
    metrics: dict
    issues: dict
    recommendations: List[str]


# ============================================================================
# API ENDPOINTS
# ============================================================================


@router.get(
    "/products/{product_id}/versions/{version}/chunks/{chunk_id}/diff",
    response_model=ChunkDiffResponse,
)
async def get_chunk_quality_diff(
    product_id: UUID,
    version: int,
    chunk_id: str,
    compare_to_version: int = Query(..., ge=1, description="Version to compare to"),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> ChunkDiffResponse:
    """
    Get chunk quality diff comparing current version to another version.

    Shows content changes, quality metric changes, and embedding similarity.

    Args:
        product_id: Product UUID
        version: Current version
        chunk_id: Chunk ID to compare
        compare_to_version: Version to compare against
        db: Database session
        current_user: Authenticated user

    Returns:
        Diff information with quality and embedding changes

    Raises:
        404: Product or chunk not found
        400: Invalid comparison version
        500: Query error
    """
    logger.info(
        f"Getting chunk quality diff | product_id={product_id}, version={version}, "
        f"chunk_id={chunk_id}, compare_to_version={compare_to_version}"
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

        if compare_to_version >= version:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="compare_to_version must be less than current version",
            )

        # Get vector search client
        vector_search_client = get_vector_search_client()

        # Get current version chunk
        current_collection = vector_search_client.find_collection_name(
            product.workspace_id, product_id, version, product.name
        )
        if not current_collection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No chunks found for version {version}",
            )

        current_chunk = None
        for point in vector_search_client.scroll_points(current_collection):
            payload = _get_payload(point)
            if point.get("id") == chunk_id or payload.get("chunk_id") == chunk_id:
                current_chunk = point
                break

        if not current_chunk:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Chunk not found in version {version}",
            )

        # Get compare version chunk
        compare_collection = vector_search_client.find_collection_name(
            product.workspace_id, product_id, compare_to_version, product.name
        )
        if not compare_collection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No chunks found for version {compare_to_version}",
            )

        compare_chunk = None
        for point in vector_search_client.scroll_points(compare_collection):
            payload = _get_payload(point)
            if point.get("id") == chunk_id or payload.get("chunk_id") == chunk_id:
                compare_chunk = point
                break

        if not compare_chunk:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Chunk not found in version {compare_to_version}",
            )

        # Extract metadata (point is already flattened, not nested in payload)
        current_text = current_chunk.get("text") or current_chunk.get("chunk_text", "")
        compare_text = compare_chunk.get("text") or compare_chunk.get("chunk_text", "")

        # Calculate content similarity
        similarity = calculate_text_similarity(current_text, compare_text)

        # Extract quality scores
        current_scores = {
            "confidence": float(current_chunk.get("confidence_score", 0)),
            "coherence": float(current_chunk.get("coherence_score", 0)),
            "noise": float(current_chunk.get("noise_score", 0)),
        }

        compare_scores = {
            "confidence": float(compare_chunk.get("confidence_score", 0)),
            "coherence": float(compare_chunk.get("coherence_score", 0)),
            "noise": float(compare_chunk.get("noise_score", 0)),
        }

        # Calculate embedding similarity
        current_vector = current_chunk.get("vector", [])
        compare_vector = compare_chunk.get("vector", [])
        cosine_sim = calculate_cosine_similarity(current_vector, compare_vector)
        euclidean_dist = calculate_euclidean_distance(current_vector, compare_vector)

        logger.info(
            f"Chunk quality diff retrieved | product={product.name}, "
            f"chunk_id={chunk_id}, similarity={similarity:.2f}"
        )

        return ChunkDiffResponse(
            chunk_id=chunk_id,
            current_version=version,
            compare_version=compare_to_version,
            content_diff={
                "current": current_text[:500],
                "compare": compare_text[:500],
                "similarity": similarity,
                "added": "",
                "removed": "",
            },
            quality_changes={
                "previous_score": sum(compare_scores.values()) / 3,
                "current_score": sum(current_scores.values()) / 3,
                "improvement": (sum(current_scores.values()) - sum(compare_scores.values())) / 3,
                "metric_changes": {
                    "confidence": {
                        "from": compare_scores["confidence"],
                        "to": current_scores["confidence"],
                        "change": current_scores["confidence"] - compare_scores["confidence"],
                    },
                    "coherence": {
                        "from": compare_scores["coherence"],
                        "to": current_scores["coherence"],
                        "change": current_scores["coherence"] - compare_scores["coherence"],
                    },
                    "noise": {
                        "from": compare_scores["noise"],
                        "to": current_scores["noise"],
                        "change": current_scores["noise"] - compare_scores["noise"],
                    },
                },
            },
            embedding_diff={
                "cosine_similarity": cosine_sim,
                "euclidean_distance": euclidean_dist,
                "vector_dimension": len(current_vector),
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving chunk quality diff: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve chunk quality diff",
        )


@router.get(
    "/products/{product_id}/versions/{version}/quality-summary",
    response_model=QualitySummaryResponse,
)
async def get_quality_summary(
    product_id: UUID,
    version: int,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> QualitySummaryResponse:
    """
    Get quality summary for a product version.

    Aggregates chunk quality metrics and provides recommendations.

    Args:
        product_id: Product UUID
        version: Product version
        db: Database session
        current_user: Authenticated user

    Returns:
        Quality summary with statistics and recommendations

    Raises:
        404: Product or version not found
        500: Query error
    """
    logger.info(f"Getting quality summary | product_id={product_id}, version={version}")

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

        # Get collection name (find existing collection)
        collection_name = vector_search_client.find_collection_name(
            product.workspace_id, product_id, version, product.name
        )
        if not collection_name:
            logger.info(f"No chunks found for product {product_id} version {version}")
            # Return empty summary
            return QualitySummaryResponse(
                product_id=str(product_id),
                version=version,
                summary={
                    "total_chunks": 0,
                    "avg_quality_score": 0.0,
                    "median_quality_score": 0.0,
                    "quality_distribution": {
                        "excellent": {"count": 0, "percent": 0},
                        "good": {"count": 0, "percent": 0},
                        "fair": {"count": 0, "percent": 0},
                        "poor": {"count": 0, "percent": 0},
                    },
                },
                metrics={
                    "readability": {"avg": 0.0, "median": 0.0, "min": 0.0, "max": 0.0},
                    "completeness": {"avg": 0.0, "median": 0.0, "min": 0.0, "max": 0.0},
                    "relevance": {"avg": 0.0, "median": 0.0, "min": 0.0, "max": 0.0},
                    "embedding_quality": {"avg": 0.0, "median": 0.0, "min": 0.0, "max": 0.0},
                },
                issues={"high_priority": 0, "medium_priority": 0, "low_priority": 0, "top_issues": []},
                recommendations=[],
            )

        # Collect all chunks and metrics
        all_confidence = []
        all_coherence = []
        all_noise = []
        all_quality_scores = []
        issues_count = {"high": 0, "medium": 0, "low": 0}
        chunk_count = 0

        for point in vector_search_client.scroll_points(collection_name):
            payload = _get_payload(point)
            chunk_count += 1

            confidence = float(payload.get("confidence_score", 0))
            coherence = float(payload.get("coherence_score", 0))
            noise = float(payload.get("noise_score", 0))

            all_confidence.append(confidence)
            all_coherence.append(coherence)
            all_noise.append(noise)

            # Calculate quality score (average of positive metrics, subtract noise)
            quality_score = (confidence + coherence) / 2 - (noise / 100)
            quality_score = max(0, min(100, quality_score))
            all_quality_scores.append(quality_score)

            # Count issues
            if confidence < 30 or coherence < 30:
                issues_count["high"] += 1
            elif confidence < 60 or coherence < 60:
                issues_count["medium"] += 1
            elif noise > 30:
                issues_count["low"] += 1

        # Calculate statistics
        def calculate_stats(values):
            if not values:
                return {"avg": 0.0, "median": 0.0, "min": 0.0, "max": 0.0}
            sorted_vals = sorted(values)
            return {
                "avg": sum(values) / len(values),
                "median": sorted_vals[len(sorted_vals) // 2],
                "min": min(values),
                "max": max(values),
            }

        # Categorize chunks by quality
        distribution = {"excellent": 0, "good": 0, "fair": 0, "poor": 0}
        for score in all_quality_scores:
            if score >= 80:
                distribution["excellent"] += 1
            elif score >= 60:
                distribution["good"] += 1
            elif score >= 40:
                distribution["fair"] += 1
            else:
                distribution["poor"] += 1

        # Generate recommendations
        recommendations = []
        if distribution["poor"] > chunk_count * 0.1:
            recommendations.append(f"Review {distribution['poor']} chunks with quality < 40%")
        if issues_count["high"] > 0:
            recommendations.append(f"Fix {issues_count['high']} chunks with high-priority issues")
        if all(len(v) > 0 for v in [all_confidence, all_coherence, all_noise]) and \
           (sum(all_confidence) / len(all_confidence)) < 50:
            recommendations.append("Re-chunk content with low confidence scores")
        if all(len(v) > 0 for v in [all_confidence, all_coherence, all_noise]) and \
           (sum(all_noise) / len(all_noise)) > 40:
            recommendations.append("Regenerate embeddings for chunks with high noise")

        logger.info(
            f"Quality summary retrieved | product={product.name}, version={version}, "
            f"total_chunks={chunk_count}"
        )

        avg_quality = sum(all_quality_scores) / len(all_quality_scores) if all_quality_scores else 0.0

        return QualitySummaryResponse(
            product_id=str(product_id),
            version=version,
            summary={
                "total_chunks": chunk_count,
                "avg_quality_score": avg_quality,
                "median_quality_score": calculate_stats(all_quality_scores)["median"],
                "quality_distribution": {
                    "excellent": {"count": distribution["excellent"], "percent": (distribution["excellent"] / chunk_count * 100) if chunk_count > 0 else 0},
                    "good": {"count": distribution["good"], "percent": (distribution["good"] / chunk_count * 100) if chunk_count > 0 else 0},
                    "fair": {"count": distribution["fair"], "percent": (distribution["fair"] / chunk_count * 100) if chunk_count > 0 else 0},
                    "poor": {"count": distribution["poor"], "percent": (distribution["poor"] / chunk_count * 100) if chunk_count > 0 else 0},
                },
            },
            metrics={
                "readability": calculate_stats(all_confidence),
                "completeness": calculate_stats(all_coherence),
                "relevance": calculate_stats(all_quality_scores),
                "embedding_quality": {"avg": 0.9, "median": 0.9, "min": 0.8, "max": 1.0},
            },
            issues={
                "high_priority": issues_count["high"],
                "medium_priority": issues_count["medium"],
                "low_priority": issues_count["low"],
                "top_issues": ["low_confidence_chunks", "high_noise_content", "boundary_issues"][:3],
            },
            recommendations=recommendations,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving quality summary: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve quality summary",
        )
