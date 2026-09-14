"""
Products API - Analytics endpoints.

Handles trust metrics, insights, embedding diagnostics, and chunk metadata.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from uuid import uuid4 as uuid_uuid4

import numpy as np
from fastapi import Depends, HTTPException, Query, Request, status
from primedata.api.products import (
    ProductInsightsResponse,
    TrustMetricsResponse,
    _enrich_fingerprint_with_vector_metrics,
    router,
)
from primedata.core.scope import ensure_product_access
from primedata.core.settings import get_settings
from primedata.db.database import get_db
from primedata.db.models import Product, Workspace
from primedata.utils.logger import get_logger
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

logger = get_logger(__name__)


class ChunkMetadataResponse(BaseModel):
    """Chunk metadata response (M4)."""

    model_config = ConfigDict(from_attributes=True)  # Pydantic v2 syntax

    id: UUID
    chunk_id: str
    score: Optional[float]
    source_file: Optional[str]
    page_number: Optional[int]
    section: Optional[str]
    field_name: Optional[str]
    extra_tags: Optional[Dict[str, Any]]
    created_at: datetime


@router.get("/{product_id}/trust-metrics", response_model=TrustMetricsResponse)
def get_trust_metrics(
    product_id: UUID, request: Request, db: Session = Depends(get_db)
):
    """
    Get aggregated trust metrics for a product (M2).
    """
    logger.info(f"GET /api/v1/products/{product_id}/trust-metrics: Fetching trust metrics")

    try:
        from primedata.core.scope import ensure_product_access
        from primedata.ingestion_pipeline.aird_stages.storage import AirdStorageAdapter

        logger.debug(f"   Validating product access")
        product = ensure_product_access(db, request, product_id)
        logger.debug(f"   Access granted")

        # Try to get from product model first (lazy load from S3 if needed)
        from primedata.services.lazy_json_loader import load_product_json_field

        logger.debug(f"   Loading fingerprint data from product")
        fingerprint_data = load_product_json_field(product, "readiness_fingerprint")

        if fingerprint_data:
            logger.debug(f"   Fingerprint data found in product")

            # Handle both old format (nested in metrics) and new format (direct fingerprint)
            if isinstance(fingerprint_data, dict):
                # Check if it's the old format with nested fingerprint
                if "fingerprint" in fingerprint_data and isinstance(fingerprint_data["fingerprint"], dict):
                    logger.debug(f"      Using legacy format (nested fingerprint)")
                    fingerprint = fingerprint_data["fingerprint"]
                    trust_score = fingerprint.get(
                        "AI_Trust_Score", fingerprint_data.get("trust_score", product.trust_score or 0.0)
                    )
                else:
                    # New format: fingerprint is directly the metrics dict
                    logger.debug(f"      Using current format (direct fingerprint)")
                    fingerprint = fingerprint_data
                    trust_score = fingerprint.get("AI_Trust_Score", product.trust_score or 0.0)
            else:
                logger.warning(f"Fingerprint data is not a dict, using fallback")
                fingerprint = {}
                trust_score = product.trust_score or 0.0

            logger.info(f"GET /api/v1/products/{product_id}/trust-metrics: SUCCESS | trust_score={trust_score}")
            return TrustMetricsResponse(
                ai_trust_score=float(trust_score) if trust_score is not None else 0.0,
                metrics=fingerprint,
                chunk_count=0,  # Could be calculated from chunk_metrics if available
            )

        # Fallback: try to load from storage
        logger.debug(f"   No fingerprint in product, trying storage fallback")
        try:
            storage = AirdStorageAdapter(
                workspace_id=product.workspace_id,
                product_id=product.id,
                version=product.current_version,
            )

            logger.debug(f"   Loading metrics from storage")
            metrics = storage.get_metrics_json()
            if metrics:
                logger.debug(f"   Metrics loaded from storage | count={len(metrics)}")
                from primedata.services.fingerprint import generate_fingerprint

                fingerprint = generate_fingerprint(metrics)
                trust_score = fingerprint.get("AI_Trust_Score", 0.0)
                logger.debug(f"      Generated fingerprint | trust_score={trust_score}")

                logger.info(f"GET /api/v1/products/{product_id}/trust-metrics: SUCCESS (from storage) | trust_score={trust_score}")
                return TrustMetricsResponse(
                    ai_trust_score=trust_score,
                    metrics=fingerprint,
                    chunk_count=len(metrics),
                )
            else:
                logger.debug(f"   No metrics found in storage")
        except Exception as e:
            logger.warning(f"Failed to load metrics from storage: {e}")

        # Return empty if no metrics found
        logger.warning(f"get_trust_metrics: NO_METRICS - No metrics available for product {product_id}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trust metrics not available for this product")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"get_trust_metrics: FAILED - {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve trust metrics")


@router.get("/{product_id}/insights", response_model=ProductInsightsResponse)
def get_product_insights(
    product_id: UUID, request: Request, db: Session = Depends(get_db)
):
    """
    Get product insights including fingerprint, policy, and optimizer (M2).
    """
    logger.info(f"GET /api/v1/products/{product_id}/insights: Fetching product insights")

    try:
        from primedata.core.scope import ensure_product_access
        from primedata.ingestion_pipeline.aird_stages.config import get_aird_config
        from primedata.ingestion_pipeline.aird_stages.storage import AirdStorageAdapter
        from primedata.services.policy_engine import evaluate_policy

        logger.debug(f"   Validating product access")
        product = ensure_product_access(db, request, product_id)
        logger.debug(f"   Access granted")

        # Get fingerprint (lazy load from S3 if needed)
        from primedata.services.lazy_json_loader import load_product_json_field

        logger.debug(f"   Loading fingerprint data")
        fingerprint_data = load_product_json_field(product, "readiness_fingerprint")
        fingerprint = None

        if fingerprint_data:
            logger.debug(f"   Fingerprint data found")
            # Handle both old format (nested in metrics) and new format (direct fingerprint)
            if isinstance(fingerprint_data, dict):
                # Check if it's the old format with nested fingerprint
                if "fingerprint" in fingerprint_data and isinstance(fingerprint_data["fingerprint"], dict):
                    logger.debug(f"      Using legacy format")
                    fingerprint = fingerprint_data["fingerprint"]
                else:
                    # New format: fingerprint is directly the metrics dict
                    logger.debug(f"      Using current format")
                    fingerprint = fingerprint_data

        if not fingerprint:
            logger.debug(f"   No fingerprint in product, trying storage fallback")
            # Try to load from storage
            try:
                storage = AirdStorageAdapter(
                    workspace_id=product.workspace_id,
                    product_id=product.id,
                    version=product.current_version,
                )

                logger.debug(f"   Loading metrics from storage")
                metrics = storage.get_metrics_json()
                if metrics:
                    logger.debug(f"   Metrics loaded | count={len(metrics)}")
                    from primedata.services.fingerprint import generate_fingerprint

                    fingerprint = generate_fingerprint(metrics)
                    logger.debug(f"      Generated fingerprint")
            except Exception as e:
                logger.warning(f"Failed to load fingerprint from storage: {e}")

        if not fingerprint:
            logger.error(f"get_product_insights: NO_FINGERPRINT - No fingerprint available")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fingerprint not available for this product")

        logger.debug(f"   Enriching fingerprint with vector metrics")
        fingerprint = _enrich_fingerprint_with_vector_metrics(fingerprint=fingerprint, product=product)
        logger.debug(f"   Fingerprint enriched")

        # Evaluate policy
        logger.debug(f"   Evaluating policy")
        config = get_aird_config()
        thresholds = {
            "min_trust_score": config.policy_min_trust_score,
            "min_secure": config.policy_min_secure,
            "min_metadata_presence": config.policy_min_metadata_presence,
            "min_kb_ready": config.policy_min_kb_ready,
        }
        logger.debug(f"      Thresholds: {thresholds}")

        policy_result = evaluate_policy(fingerprint, thresholds)
        logger.debug(f"   Policy evaluated | status={policy_result.get('status', 'unknown')}")

        # Optimizer suggestions (M5)
        logger.debug(f"   Generating optimizer suggestions")
        from primedata.services.optimizer import suggest_next_config

        optimizer = suggest_next_config(
            fingerprint=fingerprint,
            policy=policy_result,
            current_playbook=product.playbook_id,
        )
        logger.debug(f"   Optimizer suggestions generated")

        logger.info(f"GET /api/v1/products/{product_id}/insights: SUCCESS | policy_status={policy_result.get('status', 'unknown')}")
        return ProductInsightsResponse(
            fingerprint=fingerprint,
            policy=policy_result,
            optimizer=optimizer,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"get_product_insights: FAILED - {str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve product insights")


@router.get("/{product_id}/embedding-diagnostics")
def get_embedding_diagnostics(
    product_id: UUID, request: Request, db: Session = Depends(get_db)
):
    """
    Diagnostic endpoint to check embedding model configuration and status.

    Returns information about:
    - Embedding model configured for the product
    - API key status (configured/not configured)
    - Model availability and status
    - Whether hash-based fallback is being used
    """
    # Ensure user has access to the product
    ensure_product_access(db, request, product_id)

    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    # Get embedding configuration
    embedding_config = product.embedding_config or {}
    model_name = embedding_config.get("embedder_name")
    dimension = embedding_config.get("embedding_dimension")
    deployment_name = embedding_config.get("deployment_name")

    if not model_name or not dimension:
        raise ValueError("Product does not have valid embedding_config with embedder_name and embedding_dimension")

    # Check workspace settings for API key
    workspace = db.query(Workspace).filter(Workspace.id == product.workspace_id).first()
    workspace_has_key = False
    if workspace and workspace.settings:
        workspace_has_key = bool(workspace.settings.get("openai_api_key"))

    # Check environment variable
    settings = get_settings()
    env_has_key = bool(settings.OPENAI_API_KEY)

    # Try to initialize embedding generator to check status
    from primedata.indexing.embeddings import EmbeddingGenerator

    try:
        embedder = EmbeddingGenerator(model_name=model_name, dimension=dimension, workspace_id=product.workspace_id, db=db, deployment_name=deployment_name)
        model_info = embedder.get_model_info()
        actual_dimension = embedder.get_dimension()

        is_loaded = model_info.get("is_loaded", False)
        is_openai = model_info.get("is_openai", False)
        fallback_mode = model_info.get("fallback_mode", False)
        model_type = model_info.get("model_type", "unknown")
        model_loaded = model_info.get("model_loaded", False)

        # Test embedding generation to verify actual status
        test_text = "This is a test sentence for embedding generation."
        try:
            test_embedding = embedder.embed(test_text)
            embedding_works = True
            embedding_error = None

            # Verify it's actually OpenAI if configured as such
            # Check if openai_client is set (most reliable indicator)
            if model_name.startswith("openai"):
                if hasattr(embedder, "openai_client") and embedder.openai_client is not None:
                    is_openai = True
                    fallback_mode = False
                    model_type = "openai"
                elif len(test_embedding) == dimension and dimension >= 1536:
                    # High dimension suggests OpenAI (hash-based would be different)
                    # But verify by checking if it's consistent (OpenAI embeddings are deterministic)
                    test_embedding2 = embedder.embed(test_text)
                    if np.allclose(test_embedding, test_embedding2, atol=1e-6):
                        # Consistent embeddings suggest OpenAI
                        is_openai = True
                        fallback_mode = False
                        model_type = "openai"
        except Exception as e:
            embedding_works = False
            embedding_error = str(e)
    except Exception as e:
        is_loaded = False
        is_openai = False
        fallback_mode = True
        model_type = "unknown"
        actual_dimension = dimension
        embedding_works = False
        embedding_error = str(e)

    # Get model configuration details
    from primedata.core.embedding_config import get_embedding_model_config

    model_config = get_embedding_model_config(model_name)
    model_config_details = None
    if model_config:
        model_config_details = {
            "name": model_config.name,
            "model_type": model_config.model_type.value,
            "dimension": model_config.dimension,
            "requires_api_key": model_config.requires_api_key,
            "is_available": model_config.is_available,
            "model_path": model_config.model_path if hasattr(model_config, "model_path") else None,
        }

    return {
        "product_id": str(product_id),
        "product_name": product.name,
        "embedding_config": {
            "model_name": model_name,
            "configured_dimension": dimension,
            "actual_dimension": actual_dimension,
        },
        "api_key_status": {
            "workspace_configured": workspace_has_key,
            "environment_configured": env_has_key,
            "has_api_key": workspace_has_key or env_has_key,
            "note": "OpenAI models require API key. Check workspace settings or OPENAI_API_KEY environment variable.",
        },
        "model_status": {
            "is_loaded": is_loaded,
            "is_openai": is_openai,
            "model_type": model_type,
            "using_fallback": fallback_mode,
            "embedding_works": embedding_works,
            "embedding_error": embedding_error,
        },
        "model_config": model_config_details,
        "recommendations": _get_embedding_recommendations(
            model_name, fallback_mode, workspace_has_key, env_has_key, embedding_works
        ),
    }


def _get_embedding_recommendations(
    model_name: str, fallback_mode: bool, workspace_has_key: bool, env_has_key: bool, embedding_works: bool
) -> List[str]:
    """Generate recommendations based on diagnostic results."""
    recommendations = []

    if fallback_mode:
        recommendations.append(
            "CRITICAL: Using hash-based fallback embeddings. Semantic search will NOT work correctly. "
            "Results will be random and irrelevant."
        )

    if "openai" in model_name.lower():
        if not workspace_has_key and not env_has_key:
            recommendations.append(
                "OpenAI API key not configured. Configure it in workspace settings or set OPENAI_API_KEY environment variable."
            )
        elif not embedding_works:
            recommendations.append("OpenAI API key is configured but embedding generation failed. Check API key validity.")
        else:
            recommendations.append("OpenAI API key is configured and working correctly.")

    if not embedding_works and not fallback_mode:
        recommendations.append("Embedding generation failed. Check model installation and configuration.")

    if not fallback_mode and embedding_works:
        recommendations.append("Embedding model is working correctly. Semantic search should function properly.")

    return recommendations


@router.get("/{product_id}/chunk-metadata", response_model=List[ChunkMetadataResponse])
def list_chunk_metadata(
    product_id: UUID,
    request: Request,
    version: Optional[int] = Query(None, description="Filter by version"),
    section: Optional[str] = Query(None, description="Filter by section"),
    field_name: Optional[str] = Query(None, description="Filter by field name"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: Session = Depends(get_db)
):
    """
    List chunk metadata for a product (M4).
    """
    from primedata.core.scope import ensure_product_access
    from primedata.services.vector_metadata import get_chunk_metadata

    product = ensure_product_access(db, request, product_id)

    # Use version from product if not specified
    if version is None:
        version = product.current_version

    metadata = get_chunk_metadata(
        db=db,
        product_id=product_id,
        version=version,
        section=section,
        field_name=field_name,
        limit=limit,
        offset=offset,
    )

    # Metadata is now returned as dicts from Qdrant, not ORM objects
    # Map dict keys to ChunkMetadataResponse fields
    result = []
    for m in metadata:
        # Map Qdrant payload fields to response model
        result.append(
            ChunkMetadataResponse(
                id=uuid_uuid4(),  # Generate new UUID for response (not stored in Qdrant)
                chunk_id=m.get("chunk_id", ""),
                score=m.get("score"),
                source_file=m.get("source_file"),
                page_number=m.get("page_number"),
                section=m.get("section"),
                field_name=m.get("field_name"),
                extra_tags=m.get("extra_tags"),
                created_at=(
                    datetime.fromisoformat(m.get("created_at", datetime.utcnow().isoformat()))
                    if isinstance(m.get("created_at"), str)
                    else m.get("created_at", datetime.utcnow())
                ),
            )
        )
    return result
