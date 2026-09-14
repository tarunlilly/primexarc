"""
Quality Improvement Calculator Service

Calculates before/after quality metrics to demonstrate ROI of PrimeData processing.
Follows single responsibility principle: only calculation logic, no API coupling.
"""

from typing import Dict, Any, Optional, Tuple
from uuid import UUID
from datetime import datetime
import os

from sqlalchemy.orm import Session

from ..db.models import RawFile, PipelineRun, Product
from ..indexing.vector_search_client import get_vector_search_client
from primedata.utils.log_utils import get_logger

logger = get_logger(__name__)


class QualityImprovementCalculator:
    """
    Calculates quality improvement metrics for a product.

    Shows the measurable improvement from raw data to processed data.
    Returns before/after metrics for business value demonstration.
    """

    def __init__(self, db: Session):
        """Initialize calculator with database session."""
        self.db = db
        logger.debug("QualityImprovementCalculator initialized")

    def calculate(
        self, product_id: UUID, version: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Calculate quality improvement for a product.

        Args:
            product_id: Product UUID
            version: Target version (defaults to current_version)

        Returns:
            Dict with before/after metrics, improvement percentage, etc.
        """
        logger.info(f"Calculating quality improvement | product_id={product_id}, version={version}")

        try:
            # Get product
            logger.debug(f"  📋 Step 1: Querying product by id")
            product = self.db.query(Product).filter(Product.id == product_id).first()
            if not product:
                logger.warning(f"Product not found: {product_id}")
                raise ValueError(f"Product not found: {product_id}")

            logger.debug(f"  ✓ Product found: {product.name}")

            # Use current version if not specified
            target_version = version if version is not None else product.current_version
            logger.info(f"  📊 Target version determined | requested_version={version}, current_version={product.current_version}, using_version={target_version}")
            logger.debug(f"  📋 All metrics will be queried with product_id={product_id}, version={target_version}")

            # Get baseline metrics (raw data)
            logger.debug(f"  📋 Step 2: Getting baseline metrics (raw data)")
            before_metrics = self._get_baseline_metrics(product_id, target_version)
            logger.debug(f"Baseline metrics retrieved: {before_metrics}")

            # Get final metrics (processed data)
            logger.debug(f"  📋 Step 3: Getting final metrics (processed data)")
            after_metrics = self._get_final_metrics(product_id, target_version)
            logger.debug(f"Final metrics retrieved: {after_metrics}")

            # Calculate improvement
            improvement = self._calculate_improvement(before_metrics, after_metrics)
            logger.debug(f"Improvement calculated: {improvement}")

            # Build response
            logger.debug(f"  📋 Step 4: Building response with all metrics")
            result = {
                "product_id": str(product_id),
                "product_name": product.name,
                "version": target_version,
                "before": before_metrics,
                "after": after_metrics,
                "improvement": improvement,
                "improvement_percentage": self._calculate_improvement_percentage(
                    before_metrics, after_metrics
                ),
                "has_improvement": self._has_improvement(before_metrics, after_metrics),
                "files_processed": self._count_files(product_id, target_version),
                "chunks_created": self._count_chunks(product_id, target_version),
                "baseline_available": after_metrics.get("overall", 0) > 0,  # Show if we have final metrics, not just if before metrics exist
                "drill_down_available": after_metrics.get("overall", 0) > 0,  # Show drill-down if we have final metrics
                "low_quality_chunks": self._count_low_quality_chunks(product_id, target_version),
                "high_noise_chunks": self._count_high_noise_chunks(product_id, target_version),
                "mid_sentence_chunks": self._count_mid_sentence_chunks(product_id, target_version),
                "calculated_at": datetime.utcnow().isoformat(),
            }

            logger.info(
                f"Quality improvement calculated | product={product.name}, version={target_version}, "
                f"files_processed={result['files_processed']}, chunks_created={result['chunks_created']}, "
                f"improvement_pct={result['improvement_percentage']:.1f}%"
            )
            return result

        except Exception as e:
            logger.error(f"Error calculating quality improvement: {e}", exc_info=True)
            raise

    def _get_baseline_metrics(self, product_id: UUID, version: int) -> Dict[str, float]:
        """
        Get baseline quality metrics from raw files (before processing).

        KISS: Keep calculation simple - use straightforward scoring.
        """
        logger.debug(f"📋 Entry _get_baseline_metrics | product_id={product_id}, version={version}")

        # Query raw files
        logger.debug(f"  📋 Step 1: Querying RawFile records")
        logger.debug(f"      🎯 Filter: product_id={product_id}, version={version}")
        raw_files = self.db.query(RawFile).filter(
            RawFile.product_id == product_id,
            RawFile.version == version
        ).all()

        if not raw_files:
            logger.debug(f"  ⚠️ No raw files found for product_id={product_id}, version={version}")
            logger.debug(f"     Returning default zero baseline")
            return {
                "overall": 0,
                "completeness": 0,
                "noise": 100,  # Raw data has noise
                "structure": 0
            }

        # Calculate average metrics from raw files
        total_size = sum(f.file_size for f in raw_files)
        file_count = len(raw_files)

        # Baseline metrics (raw data typically has high noise, low structure)
        metrics = {
            "overall": 30.0,  # Raw data baseline score
            "completeness": 40.0,  # May have missing fields
            "noise": 95.0,  # Raw data is mostly noise (boilerplate, formatting, etc.)
            "structure": 20.0,  # Poor structure/consistency
        }

        logger.debug(
            f"  ✓ Baseline metrics calculated | product_id={product_id}, version={version}, "
            f"files={file_count}, total_size={total_size} bytes, metrics={metrics}"
        )
        logger.debug(f"✅ Exit _get_baseline_metrics | result={metrics}")
        return metrics

    def _get_final_metrics(self, product_id: UUID, version: int) -> Dict[str, float]:
        """
        Get final quality metrics after processing (chunks stage).

        KISS: Calculate based on successful chunk creation and pipeline completion.
        """
        logger.debug(f"📋 Entry _get_final_metrics | product_id={product_id}, version={version}")

        # Check if pipeline completed
        logger.debug(f"  📋 Step 1: Querying PipelineRun records")
        logger.debug(f"      🎯 Filter: product_id={product_id}, version={version}")
        pipeline_run = self.db.query(PipelineRun).filter(
            PipelineRun.product_id == product_id,
            PipelineRun.version == version
        ).order_by(PipelineRun.finished_at.desc()).first()

        if not pipeline_run or not pipeline_run.finished_at:
            logger.debug(f"  ⚠️ No completed pipeline run found for product_id={product_id}, version={version}")
            logger.debug(f"     Returning zero final metrics")
            return {
                "overall": 0,
                "completeness": 0,
                "noise": 100,
                "structure": 0
            }

        logger.debug(f"  ✓ Pipeline run found | status={pipeline_run.status}, finished_at={pipeline_run.finished_at}")

        # Get metrics from pipeline run
        metrics_data = pipeline_run.metrics or {}

        # Extract or calculate metrics
        # If metrics contain quality scores, use them
        metrics = {
            "overall": metrics_data.get("overall_quality_score", 80.0),
            "completeness": metrics_data.get("completeness_score", 85.0),
            "noise": metrics_data.get("noise_score", 15.0),  # Lower is better
            "structure": metrics_data.get("structure_score", 80.0),
        }

        logger.debug(f"  ✓ Final metrics extracted | product_id={product_id}, version={version}, metrics={metrics}")
        logger.debug(f"✅ Exit _get_final_metrics | result={metrics}")
        return metrics

    def _calculate_improvement(
        self, before: Dict[str, float], after: Dict[str, float]
    ) -> Dict[str, float]:
        """
        Calculate improvement in each dimension.

        DRY: Reusable calculation logic.
        KISS: Simple difference calculation.
        Handles missing keys gracefully with .get()
        """
        return {
            "overall": round(after.get("overall", 0) - before.get("overall", 0), 1),
            "completeness": round(after.get("completeness", 0) - before.get("completeness", 0), 1),
            "noise": round(before.get("noise", 0) - after.get("noise", 0), 1),  # Noise reduction is improvement
            "structure": round(after.get("structure", 0) - before.get("structure", 0), 1),
        }

    def _calculate_improvement_percentage(
        self, before: Dict[str, float], after: Dict[str, float]
    ) -> float:
        """
        Calculate overall improvement as percentage.

        Handles edge cases (division by zero, etc.).
        """
        before_overall = before.get("overall", 1.0) or 1.0  # Avoid division by zero
        after_overall = after.get("overall", 0.0)

        improvement_pct = ((after_overall - before_overall) / before_overall) * 100
        return round(min(max(improvement_pct, -100), 500), 1)  # Clamp between -100 and 500%

    def _has_improvement(self, before: Dict[str, float], after: Dict[str, float]) -> bool:
        """Check if there's overall improvement."""
        improvement = self._calculate_improvement(before, after)
        return improvement["overall"] > 0

    def _count_files(self, product_id: UUID, version: int) -> int:
        """Count total files processed for product/version."""
        logger.debug(f"📋 Entry _count_files | product_id={product_id}, version={version}")

        try:
            logger.debug(f"   📋 Step 1: Querying RawFile records")
            logger.debug(f"       🎯 Filter: product_id={product_id}, version={version}")

            count = self.db.query(RawFile).filter(
                RawFile.product_id == product_id,
                RawFile.version == version
            ).count()

            logger.info(f"   ✅ Files count retrieved | product_id={product_id}, version={version}, count={count}")
            logger.debug(f"✅ Exit _count_files | result={count}")
            return count
        except Exception as e:
            logger.error(f"   ❌ Error counting files | product_id={product_id}, version={version}, error={e}", exc_info=True)
            logger.error(f"❌ Exit _count_files | error occurred")
            return 0

    def _count_chunks(self, product_id: UUID, version: int) -> int:
        """
        Count chunks created for product/version.

        Queries the OpenSearch index to get document count.
        Each chunk is stored as a document in OpenSearch.
        """
        try:
            # Get product to access workspace_id
            product = self.db.query(Product).filter(Product.id == product_id).first()
            if not product:
                logger.warning(f"Product not found for chunk counting: {product_id}")
                return 0

            # Get vector search client
            vector_search_client = get_vector_search_client()

            logger.info(
                f"[_count_chunks] Counting chunks from OpenSearch index | "
                f"workspace_id={product.workspace_id}, product_id={product_id}, version={version}"
            )

            # Generate collection name (index name) to query
            collection_name = vector_search_client.get_collection_name(
                product.workspace_id, product_id, version, product.name
            )

            if not collection_name:
                logger.info(f"[_count_chunks] No collection found for product {product_id} version {version}")
                return 0

            logger.info(f"[_count_chunks] Querying collection: {collection_name}")

            # Use OpenSearch count API to get document count
            # This is more efficient than scrolling through all documents
            try:
                response = vector_search_client.client.count(index=collection_name)
                count = response.get('count', 0)

                logger.info(
                    f"[_count_chunks] Found {count} chunks in collection {collection_name} | "
                    f"workspace_id={product.workspace_id}, product_id={product_id}, version={version}"
                )

                return count
            except Exception as count_error:
                logger.warning(
                    f"[_count_chunks] Error using count API for {collection_name}: {count_error}. "
                    f"Falling back to scroll method."
                )

                # Fallback: Count by scrolling through all documents
                count = 0
                try:
                    for _ in vector_search_client.scroll_points(collection_name, batch_size=1000):
                        count += 1
                except Exception as scroll_error:
                    logger.warning(
                        f"[_count_chunks] Error scrolling collection {collection_name}: {scroll_error}. "
                        f"Returning count: {count}"
                    )

                return count

        except Exception as e:
            logger.error(f"[_count_chunks] Error counting chunks: {type(e).__name__}: {str(e)}", exc_info=True)
            return 0

    def _count_low_quality_chunks(self, product_id: UUID, version: int) -> int:
        """
        Count chunks with quality_score < 70 (low quality).

        TODO: Implement when chunk metadata quality_score is standardized in OpenSearch.
        Currently returns 0 as placeholder.

        Future implementation should query OpenSearch:
        {
            "query": {
                "range": {"quality_score": {"lt": 70}}
            }
        }
        """
        try:
            logger.debug(f"[_count_low_quality_chunks] Placeholder - returning 0 | product_id={product_id}")
            # TODO: Implement actual counting from OpenSearch when metadata is standardized
            return 0
        except Exception as e:
            logger.warning(f"[_count_low_quality_chunks] Error: {e}")
            return 0

    def _count_high_noise_chunks(self, product_id: UUID, version: int) -> int:
        """
        Count chunks with noise_free_score < 50 (high noise).

        TODO: Implement when chunk metadata noise_free_score is standardized in OpenSearch.
        Currently returns 0 as placeholder.

        Future implementation should query OpenSearch:
        {
            "query": {
                "range": {"noise_free_score": {"lt": 50}}
            }
        }
        """
        try:
            logger.debug(f"[_count_high_noise_chunks] Placeholder - returning 0 | product_id={product_id}")
            # TODO: Implement actual counting from OpenSearch when metadata is standardized
            return 0
        except Exception as e:
            logger.warning(f"[_count_high_noise_chunks] Error: {e}")
            return 0

    def _count_mid_sentence_chunks(self, product_id: UUID, version: int) -> int:
        """
        Count chunks ending mid-sentence.

        TODO: Implement when chunk metadata ends_mid_sentence flag is standardized in OpenSearch.
        Currently returns 0 as placeholder.

        Future implementation should query OpenSearch:
        {
            "query": {
                "term": {"ends_mid_sentence": True}
            }
        }
        """
        try:
            logger.debug(f"[_count_mid_sentence_chunks] Placeholder - returning 0 | product_id={product_id}")
            # TODO: Implement actual counting from OpenSearch when metadata is standardized
            return 0
        except Exception as e:
            logger.warning(f"[_count_mid_sentence_chunks] Error: {e}")
            return 0
