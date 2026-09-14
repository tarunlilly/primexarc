"""
Products API router.
"""


import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from uuid import uuid4 as uuid_uuid4

import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from primedata.analysis.content_analyzer import ChunkingConfig, content_analyzer
from primedata.api.billing import check_billing_limits
from primedata.core.scope import allowed_workspaces, ensure_product_access, ensure_workspace_access
from primedata.core.security import get_current_user
from primedata.core.settings import get_settings
from primedata.core.user_utils import get_user_id
from primedata.db.database import get_db
from primedata.db.models import PipelineRun, PipelineRunStatus, Product, ProductStatus, Workspace
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

router = APIRouter(prefix="/api/v1/products", tags=["Products"])

from primedata.utils.logger import get_logger
logger = get_logger(__name__)


# Removed get_current_user_optional - authentication is always required


class ProductCreateRequest(BaseModel):
    workspace_id: UUID
    name: str
    playbook_id: Optional[str] = None  # Optional playbook ID (M1)
    chunking_config: Optional[Dict[str, Any]] = None  # Optional chunking configuration
    embedding_config: Optional[Dict[str, Any]] = None  # Optional embedding configuration
    vector_creation_enabled: Optional[bool] = True  # Enable vector/embedding creation (default: True)
    use_case_description: Optional[str] = None  # Use case description (only set during creation)


class ChunkingConfigRequest(BaseModel):
    mode: Optional[str] = None  # "auto" or "manual"
    optimization_mode: Optional[str] = None  # "pattern", "hybrid", or "llm"
    auto_settings: Optional[Dict[str, Any]] = None
    manual_settings: Optional[Dict[str, Any]] = None


class ProductUpdateRequest(BaseModel):
    name: Optional[str] = None
    status: Optional[ProductStatus] = None
    playbook_id: Optional[str] = None
    chunking_config: Optional[ChunkingConfigRequest] = None
    embedding_config: Optional[Dict[str, Any]] = None
    vector_creation_enabled: Optional[bool] = None  # Enable/disable vector creation (use_case_description not editable)


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)  # Pydantic v2 syntax

    id: UUID
    workspace_id: UUID
    owner_user_id: str
    name: str
    status: ProductStatus
    current_version: int
    promoted_version: Optional[int] = None
    aird_enabled: bool = True  # AIRD pipeline enabled flag
    playbook_id: Optional[str] = None  # M1
    playbook_selection: Optional[Dict[str, Any]] = None  # Auto-detection metadata: method, reason, detected_at
    preprocessing_stats: Optional[Dict[str, Any]] = None  # M1
    trust_score: Optional[float] = None  # M2
    policy_status: Optional[str] = None  # M2: "passed" or "failed"
    policy_violations: Optional[List[str]] = None  # M2
    chunk_metrics: Optional[List[Dict[str, Any]]] = None  # M2
    validation_summary_path: Optional[str] = None  # M3
    trust_report_path: Optional[str] = None  # M3
    chunking_config: Optional[Dict[str, Any]] = None
    embedding_config: Optional[Dict[str, Any]] = None
    chunking_strategy: Optional[str] = None  # From latest successful pipeline run
    vector_creation_enabled: bool = True  # Enable vector/embedding creation and indexing
    use_case_description: Optional[str] = None  # Use case description (only set during creation)
    created_at: datetime
    updated_at: Optional[datetime] = None


class TrustMetricsResponse(BaseModel):
    """Trust metrics response (M2)."""

    ai_trust_score: float
    metrics: Dict[str, Any]  # All 13 metrics (can contain nested structures)
    chunk_count: int
    aggregated_at: Optional[datetime] = None


class ProductInsightsResponse(BaseModel):
    """Product insights response (M2)."""

    fingerprint: Dict[str, Any]  # Readiness fingerprint (can contain nested structures)
    policy: Dict[str, Any]  # Policy evaluation result
    optimizer: Optional[Dict[str, Any]] = None  # Optimizer suggestions (M3)


def _enrich_fingerprint_with_vector_metrics(*, fingerprint: Dict[str, Any], product) -> Dict[str, Any]:
    """
    Add vector-health metrics to the readiness fingerprint so the UI can render them.
    Uses OpenSearch/Elasticsearch collection metadata (dimension + counts). Safe no-op on any failure.
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

        # Qdrant returns slightly different shapes depending on client/version
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

        # Only set if missing (don’t overwrite if pipeline already computed them)
        fingerprint.setdefault("Embedding_Dimension_Consistency", dim_consistency)
        fingerprint.setdefault("Embedding_Success_Rate", success_rate)
        fingerprint.setdefault("Vector_Quality_Score", vector_quality)
        fingerprint.setdefault("Embedding_Model_Health", model_health)
        fingerprint.setdefault("Semantic_Search_Readiness", semantic_readiness)

        return fingerprint
    except Exception:
        return fingerprint


@router.post("/", response_model=ProductResponse)
def create_product(
    request_body: ProductCreateRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Create a new product in the specified workspace.
    """
    logger.info(f"📝 POST /api/v1/products: Creating product | name={request_body.name}, workspace_id={request_body.workspace_id}")
    try:
        # Extract owner_user_id from request headers
        logger.debug(f"   📨 Extracting user_id from headers")
        owner_user_id = request.headers.get("x-user-id")
        if not owner_user_id:
            logger.error(f"❌ create_product: MISSING_HEADER - x-user-id header is required")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="x-user-id header is required to create a product"
            )
        logger.debug(f"   ✓ User ID extracted: {owner_user_id}")

        # Ensure user has access to the workspace
        logger.debug(f"   🔐 Validating workspace access")
        ensure_workspace_access(db, request, request_body.workspace_id)
        logger.debug(f"   ✓ Workspace access validated")

        # CRITICAL: Double-check workspace is in user's allowed workspaces
        # This prevents products from being created in wrong workspaces
        logger.debug(f"   📋 Checking allowed workspaces")
        allowed_workspace_ids = allowed_workspaces(request, db)
        logger.debug(f"   ✓ Allowed workspaces: {len(allowed_workspace_ids)} total")

        if request_body.workspace_id not in allowed_workspace_ids:
            logger.error(f"❌ create_product: ACCESS_DENIED - workspace_id {request_body.workspace_id} not in allowed list")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this workspace. Products must be created in your own workspace.",
            )

        # Check billing limits for product creation
        logger.debug(f"   💾 Checking billing limits for workspace")
        current_product_count = db.query(Product).filter(Product.workspace_id == request_body.workspace_id).count()
        logger.debug(f"   ✓ Current product count in workspace: {current_product_count}")

        if not check_billing_limits(str(request_body.workspace_id), "max_products", current_product_count, db):
            logger.warning(f"⚠️  create_product: LIMIT_EXCEEDED - max_products limit reached for workspace {request_body.workspace_id}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Product limit exceeded. Please upgrade your plan to create more products.",
            )

        # Check if product name already exists in workspace
        logger.debug(f"   🔍 Checking for duplicate product name: '{request_body.name}'")
        existing_product = (
            db.query(Product)
            .filter(Product.workspace_id == request_body.workspace_id, Product.name == request_body.name)
            .first()
        )

        if existing_product:
            logger.warning(f"⚠️  create_product: DUPLICATE_NAME - product '{request_body.name}' already exists")
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Product name already exists in this workspace")
        logger.debug(f"   ✓ Product name is unique")

        # Create new product
        # Initialize playbook_selection metadata if playbook is provided
        logger.debug(f"   📋 Preparing product configuration")
        playbook_selection = None
        if request_body.playbook_id:
            playbook_selection = {
                "playbook_id": request_body.playbook_id,
                "method": "manual",  # User manually selected during creation
                "reason": None,
                "detected_at": None,
            }
            logger.debug(f"   ✓ Playbook selected: {request_body.playbook_id}")

        # Get or create embedding_config from environment variables
        from primedata.core.settings import get_settings
        s = get_settings()

        embedding_config = request_body.embedding_config
        if not embedding_config:
            # Use environment variables as defaults if embedding_config not provided
            if s.AZURE_OPENAI_MODEL_NAME and s.AZURE_OPENAI_DEPLOYMENT_NAME and s.AZURE_OPENAI_DIMENSIONS:
                embedding_config = {
                    "embedder_name": s.AZURE_OPENAI_MODEL_NAME,
                    "deployment_name": s.AZURE_OPENAI_DEPLOYMENT_NAME,
                    "embedding_dimension": s.AZURE_OPENAI_DIMENSIONS,
                }
                logger.info(f"   ℹ️  No embedding_config provided, using backend environment variables")
            else:
                raise ValueError(
                    "embedding_config is required if Azure OpenAI environment variables are not configured. "
                    "Provide embedding_config in request or set AZURE_OPENAI_MODEL_NAME, AZURE_OPENAI_DEPLOYMENT_NAME and AZURE_OPENAI_DIMENSIONS"
                )

        # Log embedding model details from environment variables
        embedder_name = embedding_config.get("embedder_name")
        embedding_dimension = embedding_config.get("embedding_dimension")
        logger.info(f"📊 Embedding Configuration:")
        logger.info(f"   ├─ Embedder Name: {embedder_name}")
        logger.info(f"   ├─ Embedding Dimension: {embedding_dimension}")

        # If Azure OpenAI, log additional details from environment
        if embedder_name and ("embedding-3" in embedder_name or "ada" in embedder_name or embedder_name == "azure-openai"):
            logger.info(f"   ├─ Provider: Azure OpenAI")
            logger.info(f"   ├─ Endpoint: {s.AZURE_OPENAI_ENDPOINT}")
            logger.info(f"   ├─ Deployment: {embedder_name}")
            logger.info(f"   ├─ API Version: {s.AZURE_OPENAI_API_VERSION}")
            logger.info(f"   └─ Auth: Service Principal (Graph API)")
        else:
            logger.info(f"   └─ Provider: Registry Model")

        logger.debug(f"   Full config: {embedding_config}")

        product = Product(
            workspace_id=request_body.workspace_id,
            owner_user_id=owner_user_id,  # Set from x-user-id header
            name=request_body.name,
            status=ProductStatus.DRAFT,
            aird_enabled=True,  # Enable AIRD by default
            playbook_id=request_body.playbook_id,  # M1
            playbook_selection=playbook_selection,  # Store selection metadata
            chunking_config=request_body.chunking_config,  # Chunking configuration
            embedding_config=embedding_config,
            vector_creation_enabled=request_body.vector_creation_enabled if request_body.vector_creation_enabled is not None else True,  # Default to True
            use_case_description=request_body.use_case_description,  # Use case description (only during creation)
        )
        logger.debug(f"   📝 Product object created: name={product.name}, status={product.status}")

        # Persist to database
        logger.debug(f"   💾 Saving product to database")
        db.add(product)
        db.commit()
        db.refresh(product)
        logger.debug(f"   ✓ Product persisted with ID: {product.id}")

        logger.info(f"✅ POST /api/v1/products: SUCCESS | product_id={product.id}, name={product.name}, owner={owner_user_id}")
        return ProductResponse.model_validate(product)

    except HTTPException:
        # Re-raise HTTP exceptions (they already have proper error messages)
        raise
    except Exception as e:
        # Log the full error for debugging
        logger.error(f"❌ create_product: FAILED - {str(e)}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create product: {str(e)}")


@router.get("/", response_model=List[ProductResponse])
def list_products(
    request: Request,
    workspace_id: Optional[UUID] = Query(None, description="Filter by workspace ID"),
    db: Session = Depends(get_db)
):
    """
    List products. If workspace_id is provided, filter by that workspace.
    Otherwise, return products from all accessible workspaces.
    """
    logger.info(f"📋 GET /api/v1/products: Fetching products list | workspace_filter={workspace_id}")
    logger.debug(f"   📨 Request headers received | x-user-id={request.headers.get('x-user-id')}")

    try:
        logger.debug(f"   🔐 Retrieving allowed workspaces for user")
        allowed_workspace_ids = allowed_workspaces(request, db)
        logger.debug(f"   ✓ User has access to {len(allowed_workspace_ids)} workspace(s)")
    except Exception as e:
        logger.error(f"❌ list_products: AUTHENTICATION_ERROR - {type(e).__name__}: {str(e)}", exc_info=True)
        raise

    # CRITICAL: If user has no workspace access, return empty list
    if not allowed_workspace_ids:
        logger.warning(f"⚠️  list_products: NO_WORKSPACE_ACCESS - User has no workspace access")
        logger.info(f"✅ GET /api/v1/products: SUCCESS | returning empty list (no workspace access)")
        return []

    logger.debug(f"   💾 Building database query")
    query = db.query(Product).filter(Product.workspace_id.in_(allowed_workspace_ids))
    logger.debug(f"   ✓ Query filtered by accessible workspaces")

    if workspace_id:
        logger.debug(f"   🔐 Validating access to workspace: {workspace_id}")
        # Ensure user has access to the specified workspace
        if workspace_id not in allowed_workspace_ids:
            logger.error(f"❌ list_products: ACCESS_DENIED - workspace_id {workspace_id} not accessible")
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to workspace")
        query = query.filter(Product.workspace_id == workspace_id)
        logger.debug(f"   ✓ Query filtered to specific workspace: {workspace_id}")

    logger.debug(f"   💾 Executing database query")
    products = query.all()
    logger.debug(f"   ✓ Query returned {len(products)} products")

    # Fix 5: Optimize backend - Skip loading large JSON fields for list view
    # These fields are only needed in detail view, not list view
    # This avoids unnecessary S3 calls when listing products
    from primedata.services.lazy_json_loader import load_product_json_field

    logger.debug(f"   📝 Transforming products to response format")
    result = []
    for idx, product in enumerate(products, 1):
        if idx <= 2 or idx == len(products) or idx % max(1, len(products) // 5) == 0:
            logger.debug(f"      [{idx}/{len(products)}] Processing product: id={product.id}, name={product.name}")

        # Create response - skip preprocessing_stats and chunk_metrics for list view
        # These are large fields that trigger S3 calls and aren't needed in list view
        product_dict = {
            "id": product.id,
            "workspace_id": product.workspace_id,
            "owner_user_id": product.owner_user_id,
            "name": product.name,
            "status": product.status,
            "current_version": product.current_version,
            "promoted_version": product.promoted_version,
            "aird_enabled": product.aird_enabled,
            "playbook_id": product.playbook_id,
            "playbook_selection": product.playbook_selection,
            "preprocessing_stats": None,  # Skip loading for list view (not needed)
            "trust_score": product.trust_score,
            "policy_status": product.policy_status.value if product.policy_status else None,
            "policy_violations": product.policy_violations,
            "chunk_metrics": None,  # Skip loading for list view (not needed)
            "validation_summary_path": product.validation_summary_path,
            "trust_report_path": product.trust_report_path,
            "chunking_config": product.chunking_config,
            "embedding_config": product.embedding_config,
            "vector_creation_enabled": product.vector_creation_enabled,
            "use_case_description": product.use_case_description,
            "created_at": product.created_at,
            "updated_at": product.updated_at,
        }
        result.append(ProductResponse(**product_dict))

    logger.info(f"✅ GET /api/v1/products: SUCCESS | returned {len(result)} product(s)")
    return result


@router.get("/{product_id}", response_model=ProductResponse)
def get_product(
    product_id: UUID, request: Request, db: Session = Depends(get_db)
):
    """
    Get a specific product by ID.
    """
    logger.info(f"📊 GET /api/v1/products/{product_id}: Fetching product details")

    try:
        from primedata.core.scope import ensure_product_access

        logger.debug(f"   🔐 Validating product access")
        product = ensure_product_access(db, request, product_id)
        logger.debug(f"   ✓ Access granted for product: {product.name}")

        # Refresh to ensure we get the latest data from database (in case of recent updates)
        logger.debug(f"   💾 Refreshing product data from database")
        db.refresh(product)
        logger.debug(f"   ✓ Product refreshed | status={product.status}, version={product.current_version}")

        # Lazy-load JSON fields from S3 if needed
        from primedata.services.lazy_json_loader import load_product_json_field

        # Get chunking strategy from latest successful pipeline run
        logger.debug(f"   🔍 Searching for latest successful pipeline run")
        chunking_strategy = None
        latest_successful_run = (
            db.query(PipelineRun)
            .filter(
                PipelineRun.product_id == product_id,
                PipelineRun.status == PipelineRunStatus.SUCCEEDED
            )
            .order_by(PipelineRun.finished_at.desc(), PipelineRun.started_at.desc())
            .first()
        )

        if latest_successful_run:
            logger.debug(f"   ✓ Found latest successful run | run_id={latest_successful_run.id}")
            from primedata.services.lazy_json_loader import load_pipeline_run_metrics
            metrics = load_pipeline_run_metrics(latest_successful_run)
            chunking_strategy = metrics.get("chunking_config", {}).get("resolved_settings", {}).get("chunking_strategy")
            logger.debug(f"   ✓ Chunking strategy extracted: {chunking_strategy}")
        else:
            logger.debug(f"   ℹ️  No successful pipeline runs found for this product")

        logger.debug(f"   📝 Building product response object")
        product_dict = {
            "id": product.id,
            "workspace_id": product.workspace_id,
            "owner_user_id": product.owner_user_id,
            "name": product.name,
            "status": product.status,
            "current_version": product.current_version,
            "promoted_version": product.promoted_version,
            "aird_enabled": product.aird_enabled,
            "playbook_id": product.playbook_id,
            "playbook_selection": product.playbook_selection,
            "preprocessing_stats": load_product_json_field(product, "preprocessing_stats"),
            "trust_score": product.trust_score,
            "policy_status": product.policy_status.value if product.policy_status else None,
            "policy_violations": product.policy_violations,
            "chunk_metrics": load_product_json_field(product, "chunk_metrics"),
            "validation_summary_path": product.validation_summary_path,
            "trust_report_path": product.trust_report_path,
            "chunking_config": product.chunking_config,
            "embedding_config": product.embedding_config,
            "chunking_strategy": chunking_strategy,
            "vector_creation_enabled": product.vector_creation_enabled,
            "use_case_description": product.use_case_description,
            "created_at": product.created_at,
            "updated_at": product.updated_at,
        }
        logger.debug(f"   ✓ Response object built successfully")
        logger.info(f"✅ GET /api/v1/products/{product_id}: SUCCESS | name={product.name}")
        return ProductResponse(**product_dict)

    except HTTPException as e:
        logger.error(f"❌ get_product: HTTP_ERROR - {e.detail}")
        raise
    except Exception as e:
        logger.error(f"❌ get_product: FAILED - {str(e)}", exc_info=True)
        raise


@router.patch("/{product_id}", response_model=ProductResponse)
def update_product(
    product_id: UUID,
    request_body: ProductUpdateRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Update a product's name or status.
    """
    logger.info(f"📝 PATCH /api/v1/products/{product_id}: Updating product | name={request_body.name}, status={request_body.status}")
    logger.debug(f"   📨 Request body: {request_body.dict()}")

    try:
        from primedata.core.scope import ensure_product_access

        logger.debug(f"   🔐 Validating product access")
        product = ensure_product_access(db, request, product_id)
        logger.debug(f"   ✓ Access granted for product: {product.name}")

        # Check if new name conflicts with existing product in same workspace
        if request_body.name and request_body.name != product.name:
            logger.debug(f"   🔍 Checking for name conflict: '{request_body.name}'")
            existing_product = (
                db.query(Product)
                .filter(
                    Product.workspace_id == product.workspace_id, Product.name == request_body.name, Product.id != product_id
                )
                .first()
            )

            if existing_product:
                logger.warning(f"⚠️  update_product: DUPLICATE_NAME - product '{request_body.name}' already exists")
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT, detail="Product name already exists in this workspace"
                )
            logger.debug(f"   ✓ Name is unique")

        # Update fields
        logger.debug(f"   📋 Applying field updates")
        if request_body.name is not None:
            logger.debug(f"      Name: '{product.name}' → '{request_body.name}'")
            product.name = request_body.name
        if request_body.status is not None:
            logger.debug(f"      Status: {product.status} → {request_body.status}")
            product.status = request_body.status
        if request_body.playbook_id is not None:
            logger.debug(f"      Playbook: {product.playbook_id} → {request_body.playbook_id}")
            product.playbook_id = request_body.playbook_id

        # Update chunking configuration
        if request_body.chunking_config is not None:
            logger.debug(f"   🔧 Updating chunking configuration")
            current_config = product.chunking_config or {}

            # Preserve resolved_settings if it exists (from previous pipeline runs) before updating
            resolved_settings = current_config.get("resolved_settings")

            if request_body.chunking_config.mode is not None:
                current_config["mode"] = request_body.chunking_config.mode
                logger.debug(f"      Mode: {request_body.chunking_config.mode}")

            # Update optimization_mode if provided (preserve existing if not provided, default to 'pattern')
            if request_body.chunking_config.optimization_mode is not None:
                current_config["optimization_mode"] = request_body.chunking_config.optimization_mode
                logger.debug(f"      Optimization mode: {request_body.chunking_config.optimization_mode}")
            elif "optimization_mode" not in current_config:
                # Set default if not present
                current_config["optimization_mode"] = "pattern"
                logger.debug(f"      Optimization mode: pattern (default)")

            # Get the new mode to determine what to update
            new_mode = (
                request_body.chunking_config.mode
                if request_body.chunking_config.mode is not None
                else current_config.get("mode", "auto")
            )

            # Update auto_settings
            if request_body.chunking_config.auto_settings is not None:
                current_config["auto_settings"] = request_body.chunking_config.auto_settings
                logger.debug(f"      Auto settings updated")
            elif new_mode == "auto":
                # If switching to auto mode but auto_settings not provided, ensure we have defaults
                if "auto_settings" not in current_config or not current_config.get("auto_settings"):
                    current_config["auto_settings"] = {
                        "content_type": "general",
                        "model_optimized": True,
                        "confidence_threshold": 0.7,
                    }

            # Update manual_settings - ALWAYS overwrite when provided, even if mode is manual
            if request_body.chunking_config.manual_settings is not None:
                # Completely replace manual_settings with new values (don't merge)
                # Create a fresh dict to ensure no reference issues
                current_config["manual_settings"] = dict(request_body.chunking_config.manual_settings)
                logger.debug(f"      Manual settings replaced: {list(request_body.chunking_config.manual_settings.keys())}")
            elif new_mode == "manual":
                # If switching to manual mode but manual_settings not provided, keep existing or use defaults
                if "manual_settings" not in current_config or not current_config.get("manual_settings"):
                    current_config["manual_settings"] = {
                        "chunk_size": 1000,
                        "chunk_overlap": 200,
                        "min_chunk_size": 100,
                        "max_chunk_size": 2000,
                        "chunking_strategy": "fixed_size",
                    }
                    logger.debug(f"      Manual settings initialized (defaults)")

            # Restore resolved_settings if it existed (for reference only, won't affect editing)
            if resolved_settings:
                current_config["resolved_settings"] = resolved_settings

            # CRITICAL: Assign the entire config dict to ensure SQLAlchemy detects the change
            # Create a fresh dict to avoid any reference issues
            product.chunking_config = dict(current_config)

            # Force SQLAlchemy to mark this as changed (required for JSON columns)
            flag_modified(product, "chunking_config")
            logger.debug(f"   ✓ Chunking config updated and flagged for commit")

        # Update embedding configuration
        if request_body.embedding_config is not None:
            logger.debug(f"   🔧 Updating embedding configuration")
            product.embedding_config = request_body.embedding_config
            logger.debug(f"      Embedder: {product.embedding_config.get('embedder_name', 'N/A')}, Dimension: {product.embedding_config.get('embedding_dimension', 'N/A')}")

        # Update vector_creation_enabled (use_case_description is not editable)
        if request_body.vector_creation_enabled is not None:
            logger.debug(f"   🔧 Updating vector_creation_enabled: {request_body.vector_creation_enabled}")
            product.vector_creation_enabled = request_body.vector_creation_enabled

        # Commit all changes
        logger.debug(f"   💾 Committing changes to database")
        db.commit()
        logger.debug(f"   ✓ Commit successful, refreshing product")
        db.refresh(product)

        # Lazy-load JSON fields from S3 if needed
        from primedata.services.lazy_json_loader import load_product_json_field

        logger.debug(f"   📝 Building response object")
        product_dict = {
            "id": product.id,
            "workspace_id": product.workspace_id,
            "owner_user_id": product.owner_user_id,
            "name": product.name,
            "status": product.status,
            "current_version": product.current_version,
            "promoted_version": product.promoted_version,
            "aird_enabled": product.aird_enabled,
            "playbook_id": product.playbook_id,
            "playbook_selection": product.playbook_selection,
            "preprocessing_stats": load_product_json_field(product, "preprocessing_stats"),
            "trust_score": product.trust_score,
            "policy_status": product.policy_status.value if product.policy_status else None,
            "policy_violations": product.policy_violations,
            "chunk_metrics": load_product_json_field(product, "chunk_metrics"),
            "validation_summary_path": product.validation_summary_path,
            "trust_report_path": product.trust_report_path,
            "chunking_config": product.chunking_config,
            "embedding_config": product.embedding_config,
            "vector_creation_enabled": product.vector_creation_enabled,
            "use_case_description": product.use_case_description,
            "created_at": product.created_at,
            "updated_at": product.updated_at,
        }
        logger.info(f"✅ PATCH /api/v1/products/{product_id}: SUCCESS | updated {sum(1 for v in [request_body.name, request_body.status, request_body.chunking_config] if v is not None)} field(s)")
        return ProductResponse(**product_dict)

    except HTTPException:
        # Re-raise HTTP exceptions (they already have proper error messages)
        raise
    except Exception as e:
        # Log the full error for debugging
        logger.error(f"❌ update_product: FAILED - {str(e)}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to update product: {str(e)}")


@router.delete("/{product_id}")
def delete_product(
    product_id: UUID, request: Request, db: Session = Depends(get_db)
):
    """
    Delete a product and all related data.
    """
    logger.info(f"🗑️  DELETE /api/v1/products/{product_id}: Initiating product deletion")

    from primedata.db.models import DataSource, DqViolation, PipelineArtifact, PipelineRun, RawFile

    # Try to import enterprise models if available
    try:
        from primedata.db.models_enterprise import DataQualityRule

        has_dq_rules = True
    except ImportError:
        has_dq_rules = False

    # Ensure user has access to the product
    logger.debug(f"   🔐 Validating product access")
    product = ensure_product_access(db, request, product_id)
    logger.debug(f"   ✓ Access granted for product: {product.name}")

    try:
        # Delete all related records that have foreign key constraints
        # Use synchronize_session=False to avoid loading objects into memory
        # IMPORTANT: Delete order matters due to foreign key constraints

        # Delete raw files FIRST (they reference data_sources via data_source_id)
        logger.debug(f"   📋 Step 1: Deleting raw files")
        raw_files_count = db.query(RawFile).filter(RawFile.product_id == product_id).delete(synchronize_session=False)
        logger.debug(f"   ✓ Deleted {raw_files_count} raw file(s)")

        # Delete data sources (after raw files, since raw_files references data_sources)
        logger.debug(f"   📋 Step 2: Deleting data sources")
        datasources_count = db.query(DataSource).filter(DataSource.product_id == product_id).delete(synchronize_session=False)
        logger.debug(f"   ✓ Deleted {datasources_count} data source(s)")

        # Delete pipeline artifacts (deleted before pipeline runs due to foreign key)
        logger.debug(f"   📋 Step 3: Deleting pipeline artifacts")
        artifacts_count = db.query(PipelineArtifact).filter(PipelineArtifact.product_id == product_id).delete(synchronize_session=False)
        logger.debug(f"   ✓ Deleted {artifacts_count} pipeline artifact(s)")

        # Delete pipeline runs
        logger.debug(f"   📋 Step 4: Deleting pipeline runs")
        runs_count = db.query(PipelineRun).filter(PipelineRun.product_id == product_id).delete(synchronize_session=False)
        logger.debug(f"   ✓ Deleted {runs_count} pipeline run(s)")

        # Delete data quality violations
        logger.debug(f"   📋 Step 5: Deleting data quality violations")
        violations_count = db.query(DqViolation).filter(DqViolation.product_id == product_id).delete(synchronize_session=False)
        logger.debug(f"   ✓ Deleted {violations_count} violation(s)")

        # Delete data quality rules (if available)
        if has_dq_rules:
            logger.debug(f"   📋 Step 6: Deleting data quality rules")
            rules_count = db.query(DataQualityRule).filter(DataQualityRule.product_id == product_id).delete(synchronize_session=False)
            logger.debug(f"   ✓ Deleted {rules_count} rule(s)")
        else:
            logger.debug(f"   ℹ️  Data quality rules module not available, skipping")

        # Delete document metadata
        # Note: Metadata is now stored in Qdrant payloads, not PostgreSQL
        # Qdrant collections are deleted separately when product is deleted
        logger.debug(f"   📋 Step 7: Deleting product record")

        # Now delete the product itself
        db.delete(product)
        logger.debug(f"   ✓ Product record deleted")

        logger.debug(f"   💾 Committing all deletions to database")
        db.commit()
        logger.debug(f"   ✓ Commit successful")

        logger.info(f"✅ DELETE /api/v1/products/{product_id}: SUCCESS | Deleted: {raw_files_count} files, {datasources_count} sources, {artifacts_count} artifacts, {runs_count} runs")
        return {"message": "Product deleted successfully"}

    except Exception as e:
        logger.error(f"❌ delete_product: FAILED - {str(e)}", exc_info=True)
        db.rollback()
        logger.debug(f"   ✓ Database transaction rolled back")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to delete product: {str(e)}")



# --- Sub-module imports: register additional route handlers on this router ---
import primedata.api.products_recommendations  # noqa: F401
import primedata.api.products_analytics  # noqa: F401
import primedata.api.products_chunking  # noqa: F401

