"""
Analytics API endpoints for dashboard metrics and insights.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import and_, desc, func
from sqlalchemy.orm import Session

from ..core.security import get_current_user
from ..db.database import get_db
from ..db.models import DataSource, DqViolation, PipelineArtifact, PipelineRun, PipelineRunStatus, Product, RawFile, User, Workspace

from primedata.utils.logger import get_logger
logger = get_logger(__name__)

router = APIRouter()


def _enrich_fingerprint_with_vector_metrics(*, fingerprint: Dict[str, Any], product) -> Dict[str, Any]:
    """
    Add vector-health metrics to the readiness fingerprint so the UI can render them.
    Uses OpenSearch/Elasticsearch index metadata (dimension + counts). Safe no-op on any failure.
    """
    try:
        from ..indexing.vector_search_client import vector_search_client

        if not vector_search_client.is_connected():
            return fingerprint

        collection_name = vector_search_client.find_collection_name(
            workspace_id=str(product.workspace_id),
            product_id=str(product.id),
            version=product.current_version,
            product_name=product.name,
        )
        if not collection_name:
            return fingerprint

        info = vector_search_client.get_collection_info(collection_name) or {}

        # Elasticsearch returns slightly different shapes depending on client/version
        actual_dim = (
            info.get("config", {}).get("params", {}).get("vectors", {}).get("size")
            or info.get("config", {}).get("vector_size")
            or info.get("vector_size")
            or 0
        )
        points_count = int(info.get("points_count") or info.get("vectors_count") or 0)
        indexed_count = int(info.get("indexed_vectors_count") or points_count)

        expected_dim = int(((product.embedding_config or {}) or {}).get("embedding_dimension") or 0)

        dim_consistency = 100.0 if (expected_dim and actual_dim and expected_dim == actual_dim) else 0.0
        success_rate = 0.0 if points_count <= 0 else round((indexed_count / max(points_count, 1)) * 100.0, 2)

        # Lightweight computed placeholders (no vector sampling)
        vector_quality = round((dim_consistency * 0.5) + (success_rate * 0.5), 2)
        model_health = 100.0 if dim_consistency > 0 else 0.0
        semantic_readiness = round((dim_consistency + success_rate + vector_quality + model_health) / 4.0, 2)

        # Always override if None, "Not Evaluated", or 0 (don't use setdefault)
        # This ensures enrichment works even if pipeline set incorrect values
        # We recalculate from Qdrant because it's the source of truth for vector metrics
        if fingerprint.get("Embedding_Dimension_Consistency") in (None, "Not Evaluated", 0, 0.0):
            fingerprint["Embedding_Dimension_Consistency"] = dim_consistency

        if fingerprint.get("Embedding_Success_Rate") in (None, "Not Evaluated", 0, 0.0):
            fingerprint["Embedding_Success_Rate"] = success_rate

        if fingerprint.get("Vector_Quality_Score") in (None, "Not Evaluated", 0, 0.0):
            fingerprint["Vector_Quality_Score"] = vector_quality

        if fingerprint.get("Embedding_Model_Health") in (None, "Not Evaluated", 0, 0.0):
            fingerprint["Embedding_Model_Health"] = model_health

        # Semantic readiness should ALWAYS be recalculated since it depends on the above metrics
        fingerprint["Semantic_Search_Readiness"] = semantic_readiness

        return fingerprint
    except Exception:
        return fingerprint


def _filter_redundant_metrics(fingerprint: Dict[str, Any]) -> Dict[str, Any]:
    """
    Filter out redundant per-chunk metrics from the fingerprint before returning to UI.

    Removes:
    - Per-chunk metrics that have aggregated equivalents (Chunk_Coherence, Noise_Free_Score)
    - Placeholder metrics that are always 0% (vector_metrics_details, rag_metrics_details)
    - Metrics removed from trust score calculation (Timeliness, Token_Count, Audience_*, Diversity)

    Returns:
        Filtered fingerprint dictionary
    """
    if not isinstance(fingerprint, dict):
        return fingerprint

    # Create a copy to avoid mutating the original
    filtered = dict(fingerprint)

    # Remove per-chunk metrics (keep only aggregated versions)
    # Also remove deprecated metrics that no longer contribute to trust score
    metrics_to_remove = [
        # Per-chunk metrics (keep aggregated versions)
        "Chunk_Coherence",  # Keep only Avg_Chunk_Coherence
        "Noise_Free_Score",  # Keep only Avg_Noise_Free_Score

        # Placeholder metrics (always 0%)
        "vector_metrics_details",
        "rag_metrics_details",
        # Deprecated metrics (removed from trust score calculation)
        "Timeliness",
        "Token_Count",
        "GPT_Confidence",
        "Audience_Intentionality",
        "Diversity",
        "Audience_Accessibility",
    ]

    for metric in metrics_to_remove:
        filtered.pop(metric, None)

    return filtered


class ProductInsightsResponse(BaseModel):
    """Product insights response (M2)."""

    fingerprint: Optional[Dict[str, Any]] = None  # Readiness fingerprint (can contain nested structures)
    policy: Optional[Dict[str, Any]] = None  # Policy evaluation result
    optimizer: Optional[Dict[str, Any]] = None  # Optimizer suggestions (M3)
    status: str = "available"  # "available", "draft", "no_data"
    message: Optional[str] = None  # Optional message explaining the status


class AnalyticsMetrics(BaseModel):
    """Analytics metrics response model."""

    total_products: int
    total_data_sources: int
    total_pipeline_runs: int
    success_rate: float
    avg_processing_time: float
    data_quality_score: float
    recent_activity: List[Dict[str, Any]]
    monthly_stats: List[Dict[str, Any]]


@router.get("/metrics", response_model=AnalyticsMetrics)
async def get_analytics_metrics(
    request: Request,
    workspace_id: str = Query(..., description="Workspace ID"),
    db: Session = Depends(get_db)
):
    """
    Get analytics metrics for the workspace.
    """
    logger.info(f"📊 Fetching analytics metrics | workspace_id={workspace_id}")

    try:
        from uuid import UUID

        from ..core.scope import ensure_workspace_access

        # Ensure user has access to the workspace
        workspace_uuid = UUID(workspace_id)
        workspace = ensure_workspace_access(db, request, workspace_uuid)

        logger.info(f"📋 Querying products and data sources | workspace_id={workspace_id}")
        # Basic counts - filter by workspace_id (already verified access above)
        total_products = db.query(Product).filter(Product.workspace_id == workspace_uuid).count()
        total_data_sources = db.query(DataSource).filter(DataSource.workspace_id == workspace_uuid).count()
        logger.info(f"💾 Results | products={total_products}, sources={total_data_sources}")

        # Pipeline runs metrics - filter by workspace_id (already verified access above)
        pipeline_runs = db.query(PipelineRun).filter(PipelineRun.workspace_id == workspace_uuid)
        total_pipeline_runs = pipeline_runs.count()
        logger.info(f"💾 Pipeline runs | total={total_pipeline_runs}")

        # Success rate calculation
        successful_runs = pipeline_runs.filter(PipelineRun.status == PipelineRunStatus.SUCCEEDED).count()
        success_rate = (successful_runs / max(total_pipeline_runs, 1)) * 100
        logger.info(f"📊 Success rate calculated | successful={successful_runs}, rate={success_rate}%")

        # Average processing time (in minutes)
        completed_runs = pipeline_runs.filter(
            and_(
                PipelineRun.status == PipelineRunStatus.SUCCEEDED,
                PipelineRun.started_at.isnot(None),
                PipelineRun.finished_at.isnot(None),
            )
        ).all()

        avg_processing_time = 0
        if completed_runs:
            total_time = sum(
                [
                    (run.finished_at - run.started_at).total_seconds()
                    for run in completed_runs
                    if run.finished_at and run.started_at
                ]
            )
            avg_processing_time = (total_time / len(completed_runs)) / 60  # Convert to minutes
            logger.info(f"📊 Avg processing time | minutes={avg_processing_time}")

        # Data quality score (based on violations)
        logger.info(f"📋 Calculating data quality score")
        # Use single aggregation query instead of subquery + separate count
        total_violations = (
            db.query(func.count(DqViolation.id))
            .join(Product, DqViolation.product_id == Product.id)
            .filter(Product.workspace_id == workspace_uuid)
            .scalar()
        ) or 0
        # Simple quality score: higher is better, based on violation rate
        data_quality_score = max(0, 100 - (total_violations * 2))  # Each violation reduces score by 2%
        logger.info(f"✔️ Quality score | violations={total_violations}, score={data_quality_score}")

        # Recent activity (last 10 pipeline runs)
        logger.info(f"📋 Fetching recent activity")
        # Pre-compute workspace_products for reuse below
        workspace_products = db.query(Product.id).filter(Product.workspace_id == workspace_uuid).subquery()
        recent_runs = pipeline_runs.order_by(desc(PipelineRun.started_at)).limit(10).all()
        recent_activity = []

        for run in recent_runs:
            status_icon = (
                "success"
                if run.status == PipelineRunStatus.SUCCEEDED
                else "error" if run.status == PipelineRunStatus.FAILED else "warning"
            )
            activity_type = "pipeline"

            if run.status == PipelineRunStatus.SUCCEEDED:
                message = f"Product pipeline completed successfully"
            elif run.status == PipelineRunStatus.FAILED:
                message = f"Product pipeline failed"
            else:
                message = f"Product pipeline {run.status.value}"

            recent_activity.append(
                {
                    "id": str(run.id),
                    "type": activity_type,
                    "message": message,
                    "timestamp": run.started_at.isoformat() if run.started_at else datetime.now(timezone.utc).isoformat(),
                    "status": status_icon,
                }
            )

        logger.info(f"✅ Recent activity retrieved | count={len(recent_activity)}")

        # Monthly stats - show recent 6 months:
        # - If user joined < 6 months ago: show all months from join date to current
        # - If user joined >= 6 months ago: show only last 6 months (current + previous 5)
        # Get the earliest date: workspace creation or user creation
        # Ensure timezone-aware datetime
        now_utc = datetime.now(timezone.utc)
        workspace_created = workspace.created_at if workspace.created_at else now_utc
        # If workspace_created is timezone-naive, make it timezone-aware (UTC)
        if workspace_created.tzinfo is None:
            workspace_created = workspace_created.replace(tzinfo=timezone.utc)

        user_created = None
        # Extract user ID from request headers
        user_id = request.headers.get("X-USER-ID")
        if user_id:
            try:
                user = db.query(User).filter(User.id == user_id).first()
                if user and user.created_at:
                    user_created = user.created_at
                    # If user_created is timezone-naive, make it timezone-aware (UTC)
                    if user_created.tzinfo is None:
                        user_created = user_created.replace(tzinfo=timezone.utc)
            except Exception as e:
                logger.warning(f"Failed to get user creation date: {e}")
        
        # Determine the earliest date - prioritize user creation date to show months from when user joined
        if user_created:
            earliest_date = user_created
        else:
            earliest_date = workspace_created
        
        # Calculate how many months to show (up to 6 months)
        # Ensure timezone-aware datetime
        current_month_start = now_utc.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        # Ensure earliest_date is timezone-aware before using replace
        if earliest_date.tzinfo is None:
            earliest_date = earliest_date.replace(tzinfo=timezone.utc)
        earliest_month_start = earliest_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        # Calculate months difference (number of months from join to current, inclusive)
        months_diff = (current_month_start.year - earliest_month_start.year) * 12 + (current_month_start.month - earliest_month_start.month)
        total_months = months_diff + 1  # +1 to include current month
        
        # Determine start month for display
        # If user joined less than 6 months ago: start from join month
        # If user joined 6+ months ago: start from 5 months before current (to show last 6 months)
        MAX_MONTHS_TO_SHOW = 6
        if total_months <= MAX_MONTHS_TO_SHOW:
            # Show all months from join to current
            display_start_month = earliest_month_start
        else:
            # Show only last 6 months: go back 5 months from current
            display_start_month = current_month_start
            for _ in range(MAX_MONTHS_TO_SHOW - 1):
                if display_start_month.month == 1:
                    display_start_month = display_start_month.replace(year=display_start_month.year - 1, month=12, day=1)
                else:
                    display_start_month = display_start_month.replace(month=display_start_month.month - 1, day=1)
        
        # Debug logging
        logger.debug(f"Analytics monthly stats calculation: current_month_start={current_month_start}, earliest_month_start={earliest_month_start}, months_diff={months_diff}, total_months={total_months}, display_start_month={display_start_month}")
        
        monthly_stats = []
        
        # Build list of months from display_start_month to current (inclusive), then reverse to get current first
        months_to_process = []
        temp_month = display_start_month
        
        # Ensure display_start_month is timezone-aware
        if temp_month.tzinfo is None:
            temp_month = temp_month.replace(tzinfo=timezone.utc)
        
        # Build the list - iterate until we include current_month_start
        while len(months_to_process) < MAX_MONTHS_TO_SHOW:
            # Ensure temp_month is timezone-aware
            if temp_month.tzinfo is None:
                temp_month = temp_month.replace(tzinfo=timezone.utc)
            
            months_to_process.append(temp_month)
            
            # Stop if we've reached or passed current month
            if temp_month >= current_month_start:
                break
            
            # Move to next month (replace preserves timezone if present)
            if temp_month.month == 12:
                temp_month = temp_month.replace(year=temp_month.year + 1, month=1, day=1)
            else:
                temp_month = temp_month.replace(month=temp_month.month + 1, day=1)
        
        # Reverse to show current month first
        months_to_process.reverse()
        
        # Process each month
        for month_start in months_to_process:
            # Ensure month_start is timezone-aware
            if month_start.tzinfo is None:
                month_start = month_start.replace(tzinfo=timezone.utc)
            
            # Calculate month end (first day of next month)
            if month_start.month == 12:
                month_end = month_start.replace(year=month_start.year + 1, month=1, day=1)
            else:
                month_end = month_start.replace(month=month_start.month + 1, day=1)
            
            # Ensure month_end is timezone-aware
            if month_end.tzinfo is None:
                month_end = month_end.replace(tzinfo=timezone.utc)

            # Pipeline runs for this month
            month_runs = pipeline_runs.filter(
                and_(PipelineRun.started_at >= month_start, PipelineRun.started_at < month_end)
            ).count()

            # Products created in this month
            month_products = db.query(Product).filter(
                and_(
                    Product.workspace_id == workspace_uuid,
                    Product.created_at >= month_start,
                    Product.created_at < month_end
                )
            ).count()

            # Data sources created in this month
            month_data_sources = db.query(DataSource).filter(
                and_(
                    DataSource.workspace_id == workspace_uuid,
                    DataSource.created_at >= month_start,
                    DataSource.created_at < month_end
                )
            ).count()

            # Calculate data size from pipeline artifacts for this month
            # Get pipeline runs for this month
            month_pipeline_runs = pipeline_runs.filter(
                and_(PipelineRun.started_at >= month_start, PipelineRun.started_at < month_end)
            ).all()

            month_run_ids = [run.id for run in month_pipeline_runs]
            data_size_bytes = 0
            if month_run_ids:
                # Sum up artifact sizes for runs in this month
                artifacts = db.query(PipelineArtifact).filter(
                    PipelineArtifact.pipeline_run_id.in_(month_run_ids)
                ).all()
                data_size_bytes = sum(artifact.file_size for artifact in artifacts)

            # If no artifacts, try to get from raw files processed in this month
            if data_size_bytes == 0:
                raw_files = db.query(RawFile).filter(
                    and_(
                        RawFile.product_id.in_(workspace_products),
                        RawFile.processed_at >= month_start,
                        RawFile.processed_at < month_end
                    )
                ).all()
                data_size_bytes = sum(raw_file.file_size for raw_file in raw_files)
            
            # Convert to TB
            data_processed_tb = data_size_bytes / (1024 ** 4)  # Convert bytes to TB

            # Calculate success rate for this month (percentage of successful pipeline runs)
            month_success_rate = 0.0
            if month_runs > 0:
                month_successful_runs = pipeline_runs.filter(
                    and_(
                        PipelineRun.started_at >= month_start,
                        PipelineRun.started_at < month_end,
                        PipelineRun.status == PipelineRunStatus.SUCCEEDED
                    )
                ).count()
                month_success_rate = (month_successful_runs / month_runs) * 100

            monthly_stats.append(
                {
                    "month": month_start.strftime("%b %Y"),
                    "pipeline_runs": month_runs,
                    "products": month_products,
                    "data_sources": month_data_sources,
                    "data_processed": round(data_processed_tb, 2),
                    "success_rate": round(month_success_rate, 1),
                }
            )
        
        # List is already in correct order: current month first, then previous months

        logger.info(f"✅ Analytics metrics assembled | products={total_products}, sources={total_data_sources}, runs={total_pipeline_runs}")
        return AnalyticsMetrics(
            total_products=total_products,
            total_data_sources=total_data_sources,
            total_pipeline_runs=total_pipeline_runs,
            success_rate=round(success_rate, 1),
            avg_processing_time=round(avg_processing_time, 1),
            data_quality_score=round(data_quality_score, 1),
            recent_activity=recent_activity,
            monthly_stats=monthly_stats,
        )

    except Exception as e:
        logger.error(f"❌ Failed to get analytics metrics | workspace_id={workspace_id}, error={str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get analytics metrics: {str(e)}"
        )


@router.get("/products/{product_id}/insights", response_model=ProductInsightsResponse)
async def get_product_insights(
    product_id: UUID, request: Request, db: Session = Depends(get_db)
):
    """
    Get product insights including fingerprint, policy, and optimizer (M2).
    This endpoint is available under /api/v1/analytics/products/{product_id}/insights
    """
    logger.info(f"📊 Fetching product insights | product_id={product_id}")

    from ..core.scope import ensure_product_access
    from ..ingestion_pipeline.aird_stages.config import get_aird_config
    from ..ingestion_pipeline.aird_stages.storage import AirdStorageAdapter
    from ..services.policy_engine import evaluate_policy

    product = ensure_product_access(db, request, product_id)

    # Get fingerprint (lazy load from S3 if needed)
    from primedata.services.lazy_json_loader import load_product_json_field

    logger.info(f"📋 Loading fingerprint from S3")
    fingerprint_data = load_product_json_field(product, "readiness_fingerprint")
    fingerprint = None

    if fingerprint_data:
        logger.info(f"📋 Processing fingerprint data")
        # Handle both old format (nested in metrics) and new format (direct fingerprint)
        if isinstance(fingerprint_data, dict):
            # Check if it's the old format with nested fingerprint
            if "fingerprint" in fingerprint_data and isinstance(fingerprint_data["fingerprint"], dict):
                fingerprint = fingerprint_data["fingerprint"]
                logger.info(f"✅ Old format fingerprint detected")
            else:
                # New format: fingerprint is directly the metrics dict
                fingerprint = fingerprint_data
                logger.info(f"✅ New format fingerprint detected")

    if not fingerprint:
        logger.info(f"📋 Loading fingerprint from storage")
        # Try to load from storage
        try:
            storage = AirdStorageAdapter(
                workspace_id=product.workspace_id,
                product_id=product.id,
                version=product.current_version,
            )

            metrics = storage.get_metrics_json()
            if metrics:
                from ..services.fingerprint import generate_fingerprint

                fingerprint = generate_fingerprint(metrics)
                logger.info(f"✅ Fingerprint generated from storage metrics")
        except Exception as e:
            logger.warning(f"⚠️ Failed to load fingerprint from storage | error={str(e)}")

    # If no fingerprint, return a response indicating the product needs a pipeline run
    if not fingerprint:
        # Check if product is in draft state or has no pipeline runs
        from ..db.models import ProductStatus

        if product.status == ProductStatus.DRAFT or product.current_version <= 0:
            logger.info(f"📊 Product in draft state | product_id={product_id}")
            return ProductInsightsResponse(
                fingerprint=None,
                policy=None,
                optimizer=None,
                status="draft",
                message="Product is in draft state. Run a pipeline to generate insights.",
            )
        else:
            logger.info(f"📊 No fingerprint data available | product_id={product_id}")
            return ProductInsightsResponse(
                fingerprint=None,
                policy=None,
                optimizer=None,
                status="no_data",
                message="No fingerprint data available. Run a pipeline to generate insights.",
            )

    logger.info(f"📋 Enriching fingerprint with vector metrics")
    fingerprint = _enrich_fingerprint_with_vector_metrics(fingerprint=fingerprint, product=product)

    # Filter out redundant per-chunk metrics before returning to UI
    fingerprint = _filter_redundant_metrics(fingerprint)

    # Evaluate policy
    logger.info(f"📋 Evaluating policy")
    config = get_aird_config()
    thresholds = {
        "min_trust_score": config.policy_min_trust_score,
        "min_secure": config.policy_min_secure,
        "min_metadata_presence": config.policy_min_metadata_presence,
        "min_kb_ready": config.policy_min_kb_ready,
    }

    policy_result = evaluate_policy(fingerprint, thresholds)
    logger.info(f"✅ Policy evaluated")

    # Optimizer suggestions (M5)
    logger.info(f"📋 Generating optimizer suggestions")
    from ..services.optimizer import suggest_next_config

    optimizer = suggest_next_config(
        fingerprint=fingerprint,
        policy=policy_result,
        current_playbook=product.playbook_id,
    )
    logger.info(f"✅ Optimizer suggestions generated")

    logger.info(f"✅ Product insights complete | product_id={product_id}")
    return ProductInsightsResponse(
        fingerprint=fingerprint,
        policy=policy_result,
        optimizer=optimizer,
        status="available",
        message=None,
    )
