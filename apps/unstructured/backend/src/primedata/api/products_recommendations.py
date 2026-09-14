"""
Products API - Recommendation endpoints.

Handles applying optimizer recommendations and downloading reports.
"""

from typing import Any, Dict, List
from uuid import UUID

from fastapi import Depends, HTTPException, Request, Response, status
from primedata.api.products import router
from primedata.core.scope import ensure_product_access
from primedata.db.database import get_db
from primedata.db.models import Product
from primedata.utils.logger import get_logger
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

logger = get_logger(__name__)


class ApplyRecommendationRequest(BaseModel):
    """Request model for applying an optimizer recommendation."""

    action: str = Field(
        ...,
        description="Action to apply: 'increase_chunk_overlap', 'switch_playbook', 'enhance_normalization', 'extract_metadata'",
    )
    recommendation_config: Dict[str, Any] = Field(
        default_factory=dict, description="Configuration for the recommendation action"
    )


class ApplyRecommendationResponse(BaseModel):
    """Response model for applying an optimizer recommendation."""

    success: bool
    message: str
    applied_changes: Dict[str, Any]
    requires_pipeline_rerun: bool = Field(default=True, description="Whether a pipeline rerun is required to see the changes")


def _apply_increase_chunk_overlap(product, recommendation_config: Dict[str, Any]) -> tuple:
    """Apply chunk overlap increase recommendation to a product.

    :param product: Product ORM instance to modify.
    :param recommendation_config: Config dict with 'increase_by_percent' and 'min_overlap'.
    :return: Tuple of (applied_changes dict, message string).
    """
    from sqlalchemy.orm.attributes import flag_modified

    current_config = product.chunking_config or {}
    manual_settings = current_config.get("manual_settings", {})

    current_overlap = manual_settings.get("chunk_overlap", 200)
    chunk_size = manual_settings.get("chunk_size", 1000)

    increase_percent = recommendation_config.get("increase_by_percent", 20)
    min_overlap = recommendation_config.get("min_overlap", 200)

    new_overlap = max(min_overlap, int(current_overlap * (1 + increase_percent / 100)))
    max_overlap = int(chunk_size * 0.9)
    new_overlap = min(new_overlap, max_overlap)

    if current_config.get("mode") != "manual":
        current_config["mode"] = "manual"
        if "auto_settings" not in current_config or not current_config.get("auto_settings"):
            current_config["auto_settings"] = {
                "content_type": "general",
                "model_optimized": True,
                "confidence_threshold": 0.7,
            }

    if "manual_settings" not in current_config:
        current_config["manual_settings"] = {}

    current_config["manual_settings"]["chunk_overlap"] = new_overlap
    if "chunk_size" not in current_config["manual_settings"]:
        current_config["manual_settings"]["chunk_size"] = chunk_size
    if "chunking_strategy" not in current_config["manual_settings"]:
        current_config["manual_settings"]["chunking_strategy"] = manual_settings.get("chunking_strategy", "semantic")

    product.chunking_config = current_config
    flag_modified(product, "chunking_config")

    applied_changes = {"chunk_overlap": {"old": current_overlap, "new": new_overlap}}
    message = f"Chunk overlap increased from {current_overlap} to {new_overlap} tokens."
    return applied_changes, message


def _apply_switch_playbook(product, recommendation_config: Dict[str, Any]) -> tuple:
    """Apply playbook switch recommendation to a product.

    :param product: Product ORM instance to modify.
    :param recommendation_config: Config dict with 'playbook_id'.
    :return: Tuple of (applied_changes dict, message string).
    :raises HTTPException: If playbook_id is missing from config.
    """
    new_playbook_id = recommendation_config.get("playbook_id")
    if not new_playbook_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="playbook_id is required for switch_playbook action"
        )

    old_playbook_id = product.playbook_id
    product.playbook_id = new_playbook_id

    applied_changes = {"playbook_id": {"old": old_playbook_id, "new": new_playbook_id}}
    message = f"Playbook switched from {old_playbook_id} to {new_playbook_id}."
    return applied_changes, message


def _apply_preprocessing_flags(product, recommendation_config: Dict[str, Any], flags: Dict[str, Any]) -> tuple:
    """Apply preprocessing flag changes to a product's chunking config.

    :param product: Product ORM instance to modify.
    :param recommendation_config: Config dict with optional overrides.
    :param flags: Dict of preprocessing flag names to their values.
    :return: Tuple of (applied_changes dict, message string).
    """
    from sqlalchemy.orm.attributes import flag_modified

    current_config = product.chunking_config or {}
    existing_optimization_mode = current_config.get("optimization_mode", "pattern")
    if "preprocessing_flags" not in current_config:
        current_config["preprocessing_flags"] = {}

    for flag_name, flag_value in flags.items():
        current_config["preprocessing_flags"][flag_name] = flag_value

    current_config["optimization_mode"] = existing_optimization_mode
    product.chunking_config = current_config
    flag_modified(product, "chunking_config")

    return dict(flags), ""


def _apply_all_quality_improvements(product, recommendation_config: Dict[str, Any]) -> tuple:
    """Apply all quality improvement flags and optionally increase overlap.

    :param product: Product ORM instance to modify.
    :param recommendation_config: Config dict with optional 'increase_overlap' flag.
    :return: Tuple of (applied_changes dict, message string).
    """
    from sqlalchemy.orm.attributes import flag_modified

    current_config = product.chunking_config or {}
    existing_optimization_mode = current_config.get("optimization_mode", "pattern")
    if "preprocessing_flags" not in current_config:
        current_config["preprocessing_flags"] = {}

    current_config["preprocessing_flags"]["enhanced_normalization"] = True
    current_config["preprocessing_flags"]["error_correction"] = True
    current_config["preprocessing_flags"]["extract_metadata"] = True
    current_config["optimization_mode"] = existing_optimization_mode

    if recommendation_config.get("increase_overlap", False):
        if "manual_settings" not in current_config:
            current_config["manual_settings"] = {}
        current_overlap = current_config["manual_settings"].get("chunk_overlap", 200)
        new_overlap = min(int(current_overlap * 1.25), 400)
        current_config["manual_settings"]["chunk_overlap"] = new_overlap
        applied_changes = {
            "enhanced_normalization": True,
            "error_correction": True,
            "extract_metadata": True,
            "chunk_overlap": {"old": current_overlap, "new": new_overlap},
        }
    else:
        applied_changes = {"enhanced_normalization": True, "error_correction": True, "extract_metadata": True}

    product.chunking_config = current_config
    flag_modified(product, "chunking_config")

    message = "All quality improvements enabled (enhanced normalization, error correction, metadata extraction). This will maximize AI readiness scores on the next pipeline run."
    return applied_changes, message


@router.post("/{product_id}/apply-recommendation", response_model=ApplyRecommendationResponse)
def apply_recommendation(
    product_id: UUID,
    request_body: ApplyRecommendationRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Apply an optimizer recommendation to improve AI readiness.

    This endpoint allows users to apply specific recommendations from the optimizer
    service, such as increasing chunk overlap, switching playbooks, or enhancing
    text normalization.
    """
    from primedata.core.scope import ensure_product_access
    from primedata.ingestion_pipeline.aird_stages.config import get_aird_config
    from primedata.services.optimizer import suggest_next_config
    from primedata.services.policy_engine import evaluate_policy

    logger.info(f"POST /api/v1/products/{product_id}/apply-recommendation - Action: {request_body.action}")

    try:
        product = ensure_product_access(db, request, product_id)

        # Get current optimizer recommendations to validate the action
        fingerprint_data = product.readiness_fingerprint
        fingerprint = None

        if fingerprint_data:
            if isinstance(fingerprint_data, dict):
                if "fingerprint" in fingerprint_data and isinstance(fingerprint_data["fingerprint"], dict):
                    fingerprint = fingerprint_data["fingerprint"]
                else:
                    fingerprint = fingerprint_data

        if not fingerprint:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No fingerprint data available. Run a pipeline first to generate metrics.",
            )

        # Evaluate policy and get optimizer recommendations
        config = get_aird_config()
        thresholds = {
            "min_trust_score": config.policy_min_trust_score,
            "min_secure": config.policy_min_secure,
            "min_metadata_presence": config.policy_min_metadata_presence,
            "min_kb_ready": config.policy_min_kb_ready,
        }

        policy_result = evaluate_policy(fingerprint, thresholds)
        optimizer = suggest_next_config(
            fingerprint=fingerprint,
            policy=policy_result,
            current_playbook=product.playbook_id,
        )

        applied_changes = {}
        requires_rerun = True

        # Apply the requested action
        if request_body.action == "increase_chunk_overlap":
            applied_changes, message = _apply_increase_chunk_overlap(product, request_body.recommendation_config)

        elif request_body.action == "switch_playbook":
            applied_changes, message = _apply_switch_playbook(product, request_body.recommendation_config)

        elif request_body.action == "enhance_normalization":
            flags = {
                "enhanced_normalization": True,
                "error_correction": request_body.recommendation_config.get("error_correction", True),
            }
            applied_changes, _ = _apply_preprocessing_flags(product, request_body.recommendation_config, flags)
            message = "Enhanced text normalization and error correction enabled. This will be applied on the next pipeline run."

        elif request_body.action == "extract_metadata":
            flags = {
                "extract_metadata": True,
                "force_metadata_extraction": request_body.recommendation_config.get("force_extraction", True),
                "additional_metadata_fields": request_body.recommendation_config.get("additional_fields", True),
            }
            applied_changes, _ = _apply_preprocessing_flags(product, request_body.recommendation_config, flags)
            message = "Enhanced metadata extraction enabled. This will be applied on the next pipeline run."
            requires_rerun = True

        elif request_body.action == "error_correction":
            flags = {"error_correction": True}
            applied_changes, _ = _apply_preprocessing_flags(product, request_body.recommendation_config, flags)
            message = "Error correction enabled. This will fix OCR mistakes and typos on the next pipeline run."
            requires_rerun = True

        elif request_body.action == "apply_all_quality_improvements":
            applied_changes, message = _apply_all_quality_improvements(product, request_body.recommendation_config)
            requires_rerun = True

        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown action: {request_body.action}. Supported actions: increase_chunk_overlap, switch_playbook, enhance_normalization, error_correction, extract_metadata, apply_all_quality_improvements"
)

        # Commit changes
        db.commit()
        db.refresh(product)

        # Log optimization_mode being used
        saved_config = product.chunking_config or {}
        optimization_mode = saved_config.get("optimization_mode", "pattern")
        logger.info(
            f"Successfully applied recommendation {request_body.action} for product {product_id}: {applied_changes}. "
            f"Optimization mode: {optimization_mode} (this will be used during next pipeline run)"
        )

        return ApplyRecommendationResponse(
            success=True, message=message, applied_changes=applied_changes, requires_pipeline_rerun=requires_rerun
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to apply recommendation for product {product_id}: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to apply recommendation: {str(e)}"
        )


@router.get("/{product_id}/validation-summary")
def download_validation_summary(
    product_id: UUID, request: Request, db: Session = Depends(get_db)
):
    """
    Download validation summary CSV for a product (M3).
    """
    from primedata.core.scope import ensure_product_access
    from primedata.ingestion_pipeline.aird_stages.storage import AirdStorageAdapter

    product = ensure_product_access(db, request, product_id)

    # Try to get from product model first
    if product.validation_summary_path:
        try:
            from primedata.storage.storage_client import storage_client

            # Extract bucket and key from path
            # Path format: "ws/{ws}/prod/{prod}/v/{version}/artifacts/ai_validation_summary.csv"
            # Or full S3/GCS path
            if product.validation_summary_path.startswith("primedata-exports/"):
                key = product.validation_summary_path.replace("primedata-exports/", "")
                bucket = "primedata-exports"
            else:
                # Assume it's a key in primedata-exports bucket
                bucket = "primedata-exports"
                key = product.validation_summary_path

            csv_data = storage_client.get_bytes(bucket, key)
            if csv_data:
                return Response(
                    content=csv_data,
                    media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="validation_summary_{product_id}.csv"'},
                )
        except Exception as e:
            logger.warning(f"Failed to load validation summary from path: {e}")

    # Fallback: try to generate on-the-fly from storage
    try:
        storage = AirdStorageAdapter(
            workspace_id=product.workspace_id,
            product_id=product.id,
            version=product.current_version,
        )

        metrics = storage.get_metrics_json()
        if metrics:
            from primedata.ingestion_pipeline.aird_stages.config import get_aird_config
            from primedata.services.reporting import generate_validation_summary

            config = get_aird_config()
            csv_content = generate_validation_summary(metrics, config.default_scoring_threshold)

            return Response(
                content=csv_content.encode("utf-8"),
                media_type="text/csv",
                headers={"Content-Disposition": f'attachment; filename="validation_summary_{product_id}.csv"'},
            )
    except Exception as e:
        logger.warning(f"Failed to generate validation summary: {e}")

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Validation summary not available for this product")


@router.get("/{product_id}/trust-report")
def download_trust_report(
    product_id: UUID, request: Request, db: Session = Depends(get_db)
):
    """
    Download trust report PDF for a product (M3).
    """
    from primedata.core.scope import ensure_product_access
    from primedata.ingestion_pipeline.aird_stages.storage import AirdStorageAdapter

    product = ensure_product_access(db, request, product_id)

    # Try to get from product model first
    if product.trust_report_path:
        try:
            from primedata.storage.storage_client import storage_client

            # Extract bucket and key from path
            if product.trust_report_path.startswith("primedata-exports/"):
                key = product.trust_report_path.replace("primedata-exports/", "")
                bucket = "primedata-exports"
            else:
                bucket = "primedata-exports"
                key = product.trust_report_path

            pdf_data = storage_client.get_bytes(bucket, key)
            if pdf_data:
                return Response(
                    content=pdf_data,
                    media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="trust_report_{product_id}.pdf"'},
                )
        except Exception as e:
            logger.warning(f"Failed to load trust report from path: {e}")

    # Fallback: try to generate on-the-fly from storage
    try:
        storage = AirdStorageAdapter(
            workspace_id=product.workspace_id,
            product_id=product.id,
            version=product.current_version,
        )

        metrics = storage.get_metrics_json()
        if metrics:
            from primedata.ingestion_pipeline.aird_stages.config import get_aird_config
            from primedata.services.reporting import generate_trust_report

            config = get_aird_config()
            pdf_bytes = generate_trust_report(metrics, config.default_scoring_threshold)

            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={"Content-Disposition": f'attachment; filename="trust_report_{product_id}.pdf"'},
            )
    except Exception as e:
        logger.warning(f"Failed to generate trust report: {e}")

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trust report not available for this product")
