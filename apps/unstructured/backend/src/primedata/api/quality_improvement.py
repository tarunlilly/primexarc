"""
Quality Improvement API Endpoints

Provides endpoints for retrieving before/after quality improvements for products.
Demonstrates the value PrimeData delivers by showing measurable quality improvements.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..core.security import get_current_user
from ..db.database import get_db
from ..db.models import Product
from ..services.quality_improvement_calculator import QualityImprovementCalculator
from primedata.utils.log_utils import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Quality"])


class QualityMetrics(BaseModel):
    """Quality metrics for a dimension."""
    overall: float
    completeness: float
    noise: float
    structure: float


class QualityImprovementResponse(BaseModel):
    """Response model for quality improvement endpoint."""
    product_id: str
    product_name: str
    version: int
    before: QualityMetrics
    after: QualityMetrics
    improvement: QualityMetrics
    improvement_percentage: float
    has_improvement: bool
    files_processed: int
    chunks_created: int
    baseline_available: bool
    drill_down_available: bool
    low_quality_chunks: int = 0  # Chunks with quality_score < 70
    high_noise_chunks: int = 0  # Chunks with noise_free_score < 50
    mid_sentence_chunks: int = 0  # Chunks ending mid-sentence
    calculated_at: str


@router.get("/products/{product_id}/quality-improvement", response_model=QualityImprovementResponse)
async def get_quality_improvement(
    product_id: UUID,
    version: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> QualityImprovementResponse:
    """
    Get before/after quality comparison for a product.

    Shows the measurable quality improvement from raw data to AI-ready data.

    Args:
        product_id: Product UUID
        version: Optional product version (defaults to current_version)
        db: Database session
        current_user: Authenticated user

    Returns:
        Before/after metrics with improvement calculations

    Raises:
        404: Product not found
        500: Calculation error
    """
    logger.info(f"Getting quality improvement | product_id={product_id}, version={version}")

    try:
        # Verify product exists
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            logger.warning(f"Product not found: {product_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product not found: {product_id}"
            )

        # Calculate improvement
        calculator = QualityImprovementCalculator(db)
        result = calculator.calculate(product_id, version)

        logger.info(
            f"Quality improvement retrieved | product={product.name}, "
            f"improvement_pct={result['improvement_percentage']:.1f}%"
        )

        return QualityImprovementResponse(**result)

    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error calculating quality improvement: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to calculate quality improvement"
        )
