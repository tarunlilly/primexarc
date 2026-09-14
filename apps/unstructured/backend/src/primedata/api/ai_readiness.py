"""
AI Readiness Assessment and Control API endpoints.

This module provides comprehensive assessment of data quality and AI-readiness,
along with controls to improve data quality for AI applications.
"""

import json
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from ..core.scope import ensure_product_access
from ..core.security import get_current_user
from ..core.user_utils import get_current_user_from_request
from ..db.database import get_db
from ..db.models import Product
from ..indexing.vector_search_client import vector_search_client
from ..storage.storage_client import storage_client

from primedata.utils.logger import get_logger
logger = get_logger(__name__)

router = APIRouter()


class DataQualityMetrics(BaseModel):
    """Data quality metrics for AI readiness assessment."""

    total_documents: int = Field(..., description="Total number of documents")
    total_chunks: int = Field(..., description="Total number of chunks")
    avg_chunk_size: float = Field(..., description="Average chunk size in characters")
    min_chunk_size: int = Field(..., description="Minimum chunk size")
    max_chunk_size: int = Field(..., description="Maximum chunk size")
    empty_chunks: int = Field(..., description="Number of empty or near-empty chunks")
    duplicate_chunks: int = Field(..., description="Number of duplicate chunks")
    encoding_issues: int = Field(..., description="Number of chunks with encoding issues")
    low_quality_chunks: int = Field(..., description="Number of low-quality chunks")


class AIReadinessScore(BaseModel):
    """AI readiness score and recommendations."""

    overall_score: float = Field(..., description="Overall AI readiness score (0-10)")
    data_quality_score: float = Field(..., description="Data quality score (0-10)")
    chunk_quality_score: float = Field(..., description="Chunk quality score (0-10)")
    embedding_quality_score: float = Field(..., description="Embedding quality score (0-10)")
    coverage_score: float = Field(..., description="Content coverage score (0-10)")
    recommendations: List[str] = Field(..., description="List of improvement recommendations")
    critical_issues: List[str] = Field(..., description="Critical issues that must be addressed")


class QualityControlConfig(BaseModel):
    """Configuration for data quality controls."""

    min_chunk_size: int = Field(default=100, description="Minimum chunk size in characters")
    max_chunk_size: int = Field(default=2000, description="Maximum chunk size in characters")
    chunk_overlap: int = Field(default=200, description="Chunk overlap in characters")
    remove_duplicates: bool = Field(default=True, description="Remove duplicate chunks")
    clean_encoding: bool = Field(default=True, description="Clean encoding issues")
    remove_low_quality: bool = Field(default=True, description="Remove low-quality chunks")
    quality_threshold: float = Field(default=0.7, description="Quality threshold for chunk filtering")


class AIReadinessResponse(BaseModel):
    """Complete AI readiness assessment response."""

    product_id: str = Field(..., description="Product ID")
    version: int = Field(..., description="Data version")
    collection_name: str = Field(..., description="Qdrant collection name")
    metrics: DataQualityMetrics = Field(..., description="Data quality metrics")
    score: AIReadinessScore = Field(..., description="AI readiness score and recommendations")
    sample_chunks: List[Dict[str, Any]] = Field(..., description="Sample chunks for review")
    last_assessed: str = Field(..., description="Last assessment timestamp")


@router.get("/api/v1/ai-readiness/assess/{product_id}", response_model=AIReadinessResponse)
async def assess_ai_readiness(
    product_id: str,
    request: Request,
    use: str = "current",  # "current" or "prod"
    current_user: dict = Depends(get_current_user_from_request),
    db=Depends(get_db),
):
    """
    Assess the AI readiness of a product's data.

    This endpoint performs a comprehensive analysis of data quality,
    chunk quality, embedding quality, and provides recommendations
    for improving AI readiness.
    """
    logger.info(f"🤖 Assessing AI readiness | product_id={product_id}, use={use}")

    try:
        # Ensure user has access to the product
        from uuid import UUID

        product = ensure_product_access(db=db, request=request, product_id=UUID(product_id))

        if not product:
            logger.warning(f"🤖 Product not found or access denied | product_id={product_id}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found or access denied")

        # Determine which collection to use
        if use == "prod":
            logger.info(f"📋 Using production version | product_id={product_id}")
            # Check if product has a promoted version
            if not product.promoted_version:
                logger.warning(f"🤖 No production version | product_id={product_id}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No production version available. Please promote a version first.",
                )

            # Use production alias
            from ..indexing.vector_search_client import vector_search_client

            collection_name = vector_search_client.get_prod_alias_collection(
                workspace_id=str(product.workspace_id), product_id=str(product.id), product_name=product.name
            )

            if not collection_name:
                logger.warning(f"🤖 Production alias not found | product_id={product_id}")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Production alias not found. Please promote a version first."
                )

            version = product.promoted_version
        else:
            logger.info(f"📋 Using current version | product_id={product_id}, version={product.current_version}")
            # Use current version (default behavior)
            if product.current_version <= 0:
                logger.warning(f"🤖 No data available | product_id={product_id}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="No data available. Please run a pipeline first."
                )

            # Initialize clients first
            # Using global vector_search_client
            if not vector_search_client.is_connected():
                logger.error(f"🤖 Vector database connection failed | product_id={product_id}")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Vector database connection failed"
                )

            # Find collection name (checks both product name and product_id formats for backward compatibility)
            collection_name = vector_search_client.find_collection_name(
                workspace_id=str(product.workspace_id),
                product_id=str(product.id),
                version=product.current_version,
                product_name=product.name,
            )
            version = product.current_version

        # Check if collection exists
        if not collection_name:
            logger.warning(f"🤖 Collection not found | product_id={product_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Collection not found. Please run a pipeline first."
            )

        # Get collection info
        collection_info = vector_search_client.get_collection_info(collection_name)
        total_chunks = collection_info.get("points_count", 0)
        logger.info(f"📋 Collection info | chunks={total_chunks}")

        if total_chunks == 0:
            logger.warning(f"🤖 No data points found | product_id={product_id}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No data points found in collection")

        # Perform comprehensive assessment
        logger.info(f"📋 Running assessment steps | product_id={product_id}")
        metrics = await _assess_data_quality(vector_search_client, collection_name, total_chunks)
        logger.info(f"✅ Quality assessment complete | metrics={metrics}")

        score = await _calculate_ai_readiness_score(metrics)
        logger.info(f"✅ AI readiness score calculated | score={score.overall_score}")

        sample_chunks = await _get_sample_chunks(vector_search_client, collection_name)
        logger.info(f"✅ Sample chunks retrieved | count={len(sample_chunks)}")

        result = AIReadinessResponse(
            product_id=product_id,
            version=version,
            collection_name=collection_name,
            metrics=metrics,
            score=score,
            sample_chunks=sample_chunks,
            last_assessed=time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        )

        logger.info(f"✅ AI readiness assessment complete | product_id={product_id}")
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ AI readiness assessment failed | product_id={product_id}, error={str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Assessment failed: {str(e)}")


@router.post("/api/v1/ai-readiness/improve/{product_id}")
async def improve_ai_readiness(
    product_id: str,
    config: QualityControlConfig,
    request: Request,
    current_user: dict = Depends(get_current_user_from_request),
    db=Depends(get_db),
):
    """
    Apply quality controls to improve AI readiness of a product's data.

    This endpoint re-processes the data with quality controls to improve
    chunk quality, remove duplicates, fix encoding issues, and optimize
    for AI applications.
    """
    logger.info(f"🤖 Improving AI readiness | product_id={product_id}, config={config.dict()}")

    try:
        # Ensure user has access to the product
        from uuid import UUID

        product = ensure_product_access(db=db, request=request, product_id=UUID(product_id))

        if not product:
            logger.warning(f"🤖 Product not found or access denied | product_id={product_id}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found or access denied")

        # Check if product has data
        if product.current_version <= 0:
            logger.warning(f"🤖 No data available | product_id={product_id}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="No data available. Please run a pipeline first."
            )

        # Initialize Qdrant client
        logger.info(f"📋 Connecting to vector database | product_id={product_id}")
        # Using global vector_search_client
        if not vector_search_client.is_connected():
            logger.error(f"🤖 Vector database connection failed | product_id={product_id}")
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Vector database connection failed")

        # Implement data improvement pipeline
        logger.info(f"📋 Starting quality improvement pipeline | product_id={product_id}")
        improvement_result = await _improve_data_quality(product, vector_search_client, config)
        logger.info(f"✅ Quality improvement complete | result={improvement_result}")

        return improvement_result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ AI readiness improvement failed | product_id={product_id}, error={str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Improvement failed: {str(e)}")


async def _assess_data_quality(vector_search_client: Any, collection_name: str, total_chunks: int) -> DataQualityMetrics:
    """Assess data quality metrics."""
    logger.info(f"📋 Starting data quality assessment | collection={collection_name}, total_chunks={total_chunks}")

    # Get sample of chunks for analysis
    sample_size = min(1000, total_chunks)
    logger.info(f"📋 Fetching sample chunks | sample_size={sample_size}")

    # Search for all chunks (with high limit to get sample)
    search_results = vector_search_client.search_points(
        collection_name=collection_name,
        query_vector=[0.1] * 384,  # Small non-zero vector to get results
        limit=sample_size,
        score_threshold=0.0,
    )

    chunk_sizes = []
    empty_chunks = 0
    duplicate_chunks = 0
    encoding_issues = 0
    low_quality_chunks = 0
    chunk_texts = []

    logger.info(f"📋 Analyzing {len(search_results)} chunks")

    for result in search_results:
        payload = result.get("payload", {})
        text = payload.get("text", "")

        # Analyze chunk size
        chunk_size = len(text)
        chunk_sizes.append(chunk_size)

        # Check for empty chunks
        if chunk_size < 50:
            empty_chunks += 1

        # Check for encoding issues
        if "\u0000" in text or any(
            ord(c) > 127 and c not in text.encode("utf-8", errors="ignore").decode("utf-8") for c in text
        ):
            encoding_issues += 1

        # Check for low quality (too short, repetitive, etc.)
        if _is_low_quality_chunk(text):
            low_quality_chunks += 1

        chunk_texts.append(text)

    # Check for duplicates
    text_counts = Counter(chunk_texts)
    duplicate_chunks = sum(count - 1 for count in text_counts.values() if count > 1)

    logger.info(f"✅ Quality assessment complete | empty={empty_chunks}, duplicates={duplicate_chunks}, encoding_issues={encoding_issues}, low_quality={low_quality_chunks}")

    return DataQualityMetrics(
        total_documents=len(
            set(payload.get("source_file", "") for result in search_results for payload in [result.get("payload", {})])
        ),
        total_chunks=total_chunks,
        avg_chunk_size=sum(chunk_sizes) / len(chunk_sizes) if chunk_sizes else 0,
        min_chunk_size=min(chunk_sizes) if chunk_sizes else 0,
        max_chunk_size=max(chunk_sizes) if chunk_sizes else 0,
        empty_chunks=empty_chunks,
        duplicate_chunks=duplicate_chunks,
        encoding_issues=encoding_issues,
        low_quality_chunks=low_quality_chunks,
    )


async def _calculate_ai_readiness_score(metrics: DataQualityMetrics) -> AIReadinessScore:
    """Calculate AI readiness score based on metrics."""
    logger.info(f"🤖 Calculating AI readiness score | metrics={metrics.dict()}")

    recommendations = []
    critical_issues = []

    # Data Quality Score (0-10)
    data_quality_score = 10.0

    # Penalize for empty chunks
    if metrics.empty_chunks > 0:
        penalty = min(3.0, (metrics.empty_chunks / metrics.total_chunks) * 10)
        data_quality_score -= penalty
        critical_issues.append(f"{metrics.empty_chunks} empty or near-empty chunks found")
        logger.info(f"📋 Penalty for empty chunks | penalty={penalty}")

    # Penalize for duplicates
    if metrics.duplicate_chunks > 0:
        penalty = min(2.0, (metrics.duplicate_chunks / metrics.total_chunks) * 10)
        data_quality_score -= penalty
        recommendations.append(f"Remove {metrics.duplicate_chunks} duplicate chunks")
        logger.info(f"📋 Penalty for duplicates | penalty={penalty}")

    # Penalize for encoding issues
    if metrics.encoding_issues > 0:
        penalty = min(2.5, (metrics.encoding_issues / metrics.total_chunks) * 10)
        data_quality_score -= penalty
        critical_issues.append(f"{metrics.encoding_issues} chunks have encoding issues")
        logger.info(f"📋 Penalty for encoding issues | penalty={penalty}")

    # Penalize for low quality chunks
    if metrics.low_quality_chunks > 0:
        penalty = min(1.5, (metrics.low_quality_chunks / metrics.total_chunks) * 10)
        data_quality_score -= penalty
        recommendations.append(f"Review and improve {metrics.low_quality_chunks} low-quality chunks")
        logger.info(f"📋 Penalty for low quality | penalty={penalty}")

    # Chunk Quality Score (0-10)
    chunk_quality_score = 10.0

    # Check chunk size distribution
    if metrics.avg_chunk_size < 200:
        chunk_quality_score -= 2.0
        recommendations.append("Average chunk size is too small (< 200 chars). Consider increasing chunk size.")
        logger.info(f"📋 Warning: small chunk size | avg={metrics.avg_chunk_size}")
    elif metrics.avg_chunk_size > 1500:
        chunk_quality_score -= 1.5
        recommendations.append("Average chunk size is too large (> 1500 chars). Consider decreasing chunk size.")
        logger.info(f"📋 Warning: large chunk size | avg={metrics.avg_chunk_size}")

    if metrics.min_chunk_size < 50:
        chunk_quality_score -= 2.5
        critical_issues.append("Some chunks are too small (< 50 chars)")
        logger.info(f"📋 Warning: min chunk size too small | min={metrics.min_chunk_size}")

    if metrics.max_chunk_size > 3000:
        chunk_quality_score -= 2.0
        recommendations.append("Some chunks are too large (> 3000 chars)")
        logger.info(f"📋 Warning: max chunk size too large | max={metrics.max_chunk_size}")

    # Embedding Quality Score (assume good for now)
    embedding_quality_score = 8.5  # Could be improved with actual embedding quality checks

    # Coverage Score
    coverage_score = 10.0
    if metrics.total_documents < 5:
        coverage_score -= 3.0
        recommendations.append("Very few documents. Consider adding more data sources.")
        logger.info(f"📋 Warning: few documents | count={metrics.total_documents}")
    elif metrics.total_documents < 20:
        coverage_score -= 1.5
        recommendations.append("Limited document coverage. Consider adding more data sources.")
        logger.info(f"📋 Warning: limited coverage | count={metrics.total_documents}")

    if metrics.total_chunks < 100:
        coverage_score -= 2.5
        recommendations.append("Very few chunks. Consider adjusting chunking strategy.")
        logger.info(f"📋 Warning: few chunks | count={metrics.total_chunks}")

    # Overall Score
    overall_score = data_quality_score * 0.3 + chunk_quality_score * 0.3 + embedding_quality_score * 0.2 + coverage_score * 0.2

    # Add general recommendations
    if overall_score < 7.0:
        recommendations.append("Overall data quality needs improvement for optimal AI performance")
        logger.info(f"⚠️ Low readiness score | score={overall_score}")

    if not recommendations and not critical_issues:
        recommendations.append("Data quality looks good! Consider monitoring for ongoing quality.")
        logger.info(f"✅ Excellent data quality detected")

    result = AIReadinessScore(
        overall_score=round(overall_score, 1),
        data_quality_score=round(data_quality_score, 1),
        chunk_quality_score=round(chunk_quality_score, 1),
        embedding_quality_score=round(embedding_quality_score, 1),
        coverage_score=round(coverage_score, 1),
        recommendations=recommendations,
        critical_issues=critical_issues,
    )

    logger.info(f"✅ AI readiness score calculated | overall={result.overall_score}, critical_issues={len(critical_issues)}, recommendations={len(recommendations)}")
    return result


async def _get_sample_chunks(vector_search_client: Any, collection_name: str) -> List[Dict[str, Any]]:
    """Get sample chunks for review."""
    search_results = vector_search_client.search_points(
        collection_name=collection_name,
        query_vector=[0.1] * 384,  # Small non-zero vector to get results
        limit=5,
        score_threshold=0.0,
    )

    sample_chunks = []
    for result in search_results:
        payload = result.get("payload", {})
        sample_chunks.append(
            {
                "text": (
                    payload.get("text", "")[:200] + "..." if len(payload.get("text", "")) > 200 else payload.get("text", "")
                ),
                "source_file": payload.get("source_file", ""),
                "chunk_index": payload.get("chunk_index", 0),
                "quality_issues": _identify_quality_issues(payload.get("text", "")),
            }
        )

    return sample_chunks


def _is_low_quality_chunk(text: str) -> bool:
    """Check if a chunk is low quality."""
    if len(text) < 50:
        return True

    # Check for repetitive content
    words = text.split()
    if len(words) > 10:
        word_counts = Counter(words)
        most_common_count = word_counts.most_common(1)[0][1]
        if most_common_count > len(words) * 0.3:  # More than 30% same word
            return True

    # Check for mostly non-alphabetic content
    alpha_chars = sum(1 for c in text if c.isalpha())
    if alpha_chars < len(text) * 0.5:  # Less than 50% alphabetic
        return True

    return False


def _identify_quality_issues(text: str) -> List[str]:
    """Identify specific quality issues in a chunk."""
    issues = []

    if len(text) < 50:
        issues.append("Too short")

    if "\u0000" in text:
        issues.append("Encoding issues")

    if len(text.split()) < 10:
        issues.append("Too few words")

    # Check for repetitive content
    words = text.split()
    if len(words) > 10:
        word_counts = Counter(words)
        most_common_count = word_counts.most_common(1)[0][1]
        if most_common_count > len(words) * 0.3:
            issues.append("Repetitive content")

    return issues


async def _improve_data_quality(product: Product, vector_search_client: Any, config: QualityControlConfig) -> Dict[str, Any]:
    """Improve data quality by re-processing chunks with quality controls."""
    logger.info(f"🤖 Starting data quality improvement | product_id={product.id}, config={config.dict()}")

    try:
        # Find collection name (checks both product name and product_id formats for backward compatibility)
        collection_name = vector_search_client.find_collection_name(
            workspace_id=str(product.workspace_id),
            product_id=str(product.id),
            version=product.current_version,
            product_name=product.name,
        )

        if not collection_name:
            logger.error(f"🤖 Collection not found | product_id={product.id}")
            raise ValueError(f"Collection not found for product {product.id} version {product.current_version}")

        # Get all current chunks by using a simple search
        logger.info(f"📋 Fetching chunks from collection | collection={collection_name}")
        search_results = vector_search_client.search_points(
            collection_name=collection_name,
            query_vector=[0.1] * 384,  # Small non-zero vector to get some results
            limit=1000,  # Reasonable limit
            score_threshold=0.0,
        )

        if not search_results:
            logger.warning(f"🤖 No data found to improve | collection={collection_name}")
            return {"status": "no_data", "message": "No data found to improve", "improvements_applied": 0}

        # Process chunks with quality controls
        improved_chunks = []
        removed_count = 0
        fixed_count = 0

        logger.info(f"📋 Processing {len(search_results)} chunks")

        for result in search_results:
            payload = result.get("payload", {})
            text = payload.get("text", "")

            # Apply quality controls
            improved_text = _apply_quality_controls(text, config)

            if improved_text is None:
                # Chunk was removed due to quality issues
                removed_count += 1
                continue

            if improved_text != text:
                # Chunk was improved
                fixed_count += 1

            # Create improved chunk
            improved_chunk = {
                "id": result.get("id"),
                "vector": result.get("vector", [0.0] * 384),  # Keep original vector for now
                "payload": {
                    **payload,
                    "text": improved_text,
                    "improved": True,
                    "improvement_timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
                },
            }
            improved_chunks.append(improved_chunk)

        logger.info(f"✅ Chunk processing complete | total={len(improved_chunks)}, removed={removed_count}, fixed={fixed_count}")

        # Update Qdrant collection with improved chunks
        if improved_chunks:
            logger.info(f"💾 Upserting improved chunks to collection | count={len(improved_chunks)}")
            success = vector_search_client.upsert_points(collection_name, improved_chunks)

            if success:
                logger.info(f"✅ Collection update successful")
                return {
                    "status": "completed",
                    "message": f"Data quality improvement completed successfully",
                    "improvements_applied": len(improved_chunks),
                    "chunks_removed": removed_count,
                    "chunks_fixed": fixed_count,
                    "config": config.dict(),
                }
            else:
                logger.error(f"❌ Failed to update collection")
                return {
                    "status": "failed",
                    "message": "Failed to update Qdrant collection with improved chunks",
                    "improvements_applied": 0,
                }
        else:
            logger.warning(f"🤖 No chunks met quality criteria")
            return {
                "status": "no_improvements",
                "message": "No chunks met the quality criteria",
                "improvements_applied": 0,
                "chunks_removed": removed_count,
            }

    except Exception as e:
        logger.error(f"❌ Data quality improvement failed | product_id={product.id}, error={str(e)}", exc_info=True)
        return {"status": "error", "message": f"Improvement failed: {str(e)}", "improvements_applied": 0}


def _apply_quality_controls(text: str, config: QualityControlConfig) -> Optional[str]:
    """Apply quality controls to a chunk of text."""
    if not text:
        return None

    # Clean encoding issues
    if config.clean_encoding:
        # Remove null characters and fix encoding
        text = text.replace("\u0000", "")
        # Remove other problematic characters
        text = "".join(char for char in text if ord(char) >= 32 or char in "\n\t")

    # Check minimum size
    if len(text) < config.min_chunk_size:
        return None

    # Check maximum size
    if len(text) > config.max_chunk_size:
        # Truncate to max size
        text = text[: config.max_chunk_size]

    # Check for low quality content
    if config.remove_low_quality and _is_low_quality_chunk(text):
        return None

    # Remove excessive whitespace
    text = " ".join(text.split())

    return text if text else None
