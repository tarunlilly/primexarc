"""
Products API - Chunking endpoints.

Handles cost estimation, content analysis, chunking preview, auto-configuration,
version promotion, and data quality rule seeding.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from primedata.analysis.content_analyzer import ChunkingConfig, content_analyzer
from primedata.api.products import router
from primedata.core.scope import ensure_product_access
from primedata.core.security import get_current_user
from primedata.db.database import get_db
from primedata.db.models import PipelineRun, PipelineRunStatus, Product
from primedata.utils.logger import get_logger
from pydantic import BaseModel
from sqlalchemy.orm import Session

logger = get_logger(__name__)


class CostEstimateRequest(BaseModel):
    """Request model for cost estimation (M5)."""

    playbook_id: Optional[str] = None  # REGULATORY/SCANNED/TECH/None


class CostEstimateResponse(BaseModel):
    """Response model for cost estimation (M5)."""

    filename: str
    playbook: str
    estimated_tokens: int
    estimated_chunks: int
    price_model: Dict[str, float]
    estimated_cost_usd: float


class ContentAnalysisRequest(BaseModel):
    content: str
    filename: Optional[str] = None


class ContentAnalysisResponse(BaseModel):
    content_type: str
    confidence: float
    recommended_config: Dict[str, Any]
    reasoning: str


class ChunkingPreviewRequest(BaseModel):
    content: str
    config: Dict[str, Any]


class ChunkingPreviewResponse(BaseModel):
    total_chunks: int
    avg_chunk_size: float
    min_chunk_size: int
    max_chunk_size: int
    estimated_retrieval_quality: str
    preview_chunks: List[Dict[str, Any]]


class PromoteVersionRequest(BaseModel):
    """Request model for promoting a version to production."""

    version: int


@router.post("/estimate", response_model=CostEstimateResponse, status_code=status.HTTP_200_OK)
def estimate_cost(
    request: Request,
    file: UploadFile = File(...),
    playbook_id: Optional[str] = Form(None),  # REGULATORY/SCANNED/TECH/None
    db: Session = Depends(get_db)
):
    """
    Estimate cost for creating AI-ready data from a file (M5).

    Lightweight estimate endpoint:
      - Extracts text from file
      - Selects playbook (forced or via router)
      - Reads chunking.max_tokens from that playbook YAML
      - Computes estimated chunks and cost
    Does NOT create a Product or run the full pipeline.
    """
    import math
    import shutil
    import tempfile
    from pathlib import Path

    from primedata.ingestion_pipeline.aird_stages.playbooks.loader import load_playbook_yaml
    from primedata.ingestion_pipeline.aird_stages.playbooks.router import resolve_playbook_file, route_playbook
    from primedata.ingestion_pipeline.aird_stages.utils.text_processing import tokens_estimate

    # Create temp file
    tmp_dir = Path(tempfile.gettempdir()) / "primedata_estimates"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / file.filename

    try:
        # 1) Save temp file
        with tmp_path.open("wb") as buf:
            shutil.copyfileobj(file.file, buf)

        # 2) Extract text - use simple text extraction for estimate
        try:
            # For cost estimation, we'll use a simple text extraction
            # In production, this should match the actual preprocessing extraction logic
            if tmp_path.suffix.lower() == ".txt":
                text = tmp_path.read_text(encoding="utf-8", errors="ignore")
            elif tmp_path.suffix.lower() == ".pdf":
                # Try PDF extraction if available
                try:
                    import PyPDF2

                    with tmp_path.open("rb") as f:
                        pdf_reader = PyPDF2.PdfReader(f)
                        text = "\n".join([page.extract_text() for page in pdf_reader.pages])
                except ImportError:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="PDF extraction requires PyPDF2. Please install it or use a .txt file.",
                    )
            else:
                # Try to read as text
                text = tmp_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            logger.error(f"Failed to extract text: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to extract text for estimate: {e}",
            )

        if not text.strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No text extracted from file.")

        # 3) Choose playbook (forced or via router)
        if playbook_id and playbook_id.upper() in {"REGULATORY", "SCANNED", "TECH"}:
            pb_id = playbook_id.upper()
        else:
            # Use router to select playbook
            pb_id, _ = route_playbook(sample_text=text[:1000], filename=file.filename)

        # 4) Load chunking config to get max_tokens
        playbook_file = resolve_playbook_file(pb_id)
        if not playbook_file:
            # Fallback to default
            chunk_cfg = {"max_tokens": 900}
        else:
            try:
                playbook_data = load_playbook_yaml(playbook_file)
                chunk_cfg = playbook_data.get("chunking", {}) or {}
            except Exception as e:
                logger.warning(f"Failed to load playbook {pb_id}: {e}, using defaults")
                chunk_cfg = {}

        max_tokens = int(chunk_cfg.get("max_tokens", 900) or 900)

        # 5) Estimate tokens using same heuristic as preprocess
        token_est = tokens_estimate(text)

        # 6) Estimate chunk count
        est_chunks = max(1, math.ceil(token_est / max_tokens)) if max_tokens > 0 else 1

        # 7) Simple cost model (adjust to your real infra/API costs)
        PRICE_PREPROC_PER_1K = 0.0001  # $ per 1k tokens for preprocessing
        PRICE_EMBED_PER_1K = 0.0002  # $ per 1k tokens for embedding
        total_per_1k = PRICE_PREPROC_PER_1K + PRICE_EMBED_PER_1K

        est_cost = (token_est / 1000.0) * total_per_1k

        logger.info(
            f"Cost estimate: file={file.filename}, playbook={pb_id}, tokens={token_est}, chunks={est_chunks}, cost=${est_cost:.6f}"
        )

        return CostEstimateResponse(
            filename=file.filename,
            playbook=pb_id,
            estimated_tokens=token_est,
            estimated_chunks=est_chunks,
            price_model={
                "preprocess_per_1k_tokens": PRICE_PREPROC_PER_1K,
                "embed_per_1k_tokens": PRICE_EMBED_PER_1K,
                "total_per_1k_tokens": total_per_1k,
            },
            estimated_cost_usd=round(est_cost, 6),
        )

    finally:
        # Cleanup
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception as e:
            logger.warning(f"Failed to cleanup temp file {tmp_path}: {e}")


@router.post("/{product_id}/analyze-content", response_model=ContentAnalysisResponse)
def analyze_content(
    product_id: UUID,
    request_body: ContentAnalysisRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Analyze content and recommend optimal chunking configuration.
    """
    # Ensure user has access to the product
    product = ensure_product_access(db, request, product_id)

    try:
        # Analyze content
        chunking_config = content_analyzer.analyze_content(request_body.content, request_body.filename)

        return ContentAnalysisResponse(
            content_type=chunking_config.content_type.value,
            confidence=chunking_config.confidence,
            recommended_config={
                "chunk_size": chunking_config.chunk_size,
                "chunk_overlap": chunking_config.chunk_overlap,
                "min_chunk_size": chunking_config.min_chunk_size,
                "max_chunk_size": chunking_config.max_chunk_size,
                "strategy": chunking_config.strategy.value,
            },
            reasoning=chunking_config.reasoning,
        )

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Content analysis failed: {str(e)}")


@router.post("/{product_id}/preview-chunking", response_model=ChunkingPreviewResponse)
def preview_chunking(
    product_id: UUID,
    request_body: ChunkingPreviewRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Preview how content would be chunked with given configuration.
    """
    # Ensure user has access to the product
    product = ensure_product_access(db, request, product_id)

    try:
        # Create ChunkingConfig object from request
        from primedata.analysis.content_analyzer import ChunkingConfig, ChunkingStrategy, ContentType

        config = ChunkingConfig(
            chunk_size=request_body.config.get("chunk_size", 1000),
            chunk_overlap=request_body.config.get("chunk_overlap", 200),
            min_chunk_size=request_body.config.get("min_chunk_size", 100),
            max_chunk_size=request_body.config.get("max_chunk_size", 2000),
            strategy=ChunkingStrategy(request_body.config.get("strategy", "fixed_size")),
            content_type=ContentType(request_body.config.get("content_type", "general")),
            confidence=1.0,
            reasoning="User preview",
        )

        # Generate preview
        preview = content_analyzer.preview_chunking(request_body.content, config)

        return ChunkingPreviewResponse(
            total_chunks=preview["total_chunks"],
            avg_chunk_size=preview["avg_chunk_size"],
            min_chunk_size=preview["min_chunk_size"],
            max_chunk_size=preview["max_chunk_size"],
            estimated_retrieval_quality=preview["estimated_retrieval_quality"],
            preview_chunks=preview["chunks"],
        )

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Chunking preview failed: {str(e)}")


@router.post("/{product_id}/auto-configure-chunking")
async def auto_configure_chunking(
    product_id: UUID, request: Request, db: Session = Depends(get_db)
):
    """
    Automatically configure chunking settings based on product's data sources.
    Uses AirdStorageAdapter to properly extract text from PDFs and other formats.
    """
    # Ensure user has access to the product
    product = ensure_product_access(db, request, product_id)

    try:
        # Use AirdStorageAdapter to properly extract text from files (handles PDFs)
        from primedata.ingestion_pipeline.aird_stages.storage import AirdStorageAdapter
        from primedata.db.models import RawFile
        from primedata.analysis.content_analyzer import content_analyzer

        # Get raw files for the product
        version = product.current_version or 1
        raw_files = db.query(RawFile).filter(
            RawFile.product_id == product_id,
            RawFile.version == version,
            RawFile.status != "DELETED"
        ).limit(3).all()  # Sample first 3 files

        if not raw_files:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No raw files found to analyze. Please run data ingestion first."
            )

        # Use storage adapter to extract text (handles PDFs properly)
        storage = AirdStorageAdapter(
            workspace_id=product.workspace_id,
            product_id=product_id,
            version=version
        )

        sample_content = ""
        filename_hint = None
        for raw_file in raw_files:
            try:
                # Use get_raw_text which handles PDF extraction
                file_stem = raw_file.file_stem
                text = storage.get_raw_text(
                    file_stem,
                    storage_key=raw_file.storage_key,
                    storage_bucket=raw_file.storage_bucket
                )
                if text:
                    sample_content += text[:5000]  # First 5000 chars per file
                    if not filename_hint:
                        filename_hint = raw_file.filename
                    if len(sample_content) > 15000:  # Limit total sample size
                        break
            except Exception as e:
                logger.warning(f"Failed to extract text from {raw_file.filename}: {e}")
                continue

        if not sample_content or len(sample_content.strip()) < 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient content found to analyze. Please ensure files contain extractable text."
            )

        # Analyze content and get recommended configuration
        chunking_config = content_analyzer.analyze_content(
            content=sample_content,
            filename=filename_hint
        )

        # Update product configuration
        current_config = product.chunking_config or {}
        current_config.update(
            {
                "mode": "auto",
                "auto_settings": {
                    "content_type": chunking_config.content_type.value,
                    "model_optimized": True,
                    "confidence_threshold": 0.7,
                },
                "manual_settings": {
                    "chunk_size": chunking_config.chunk_size,
                    "chunk_overlap": chunking_config.chunk_overlap,
                    "min_chunk_size": chunking_config.min_chunk_size,
                    "max_chunk_size": chunking_config.max_chunk_size,
                    "chunking_strategy": chunking_config.strategy.value,
                },
                "last_analyzed": datetime.utcnow().isoformat(),
                "analysis_confidence": chunking_config.confidence,
            }
        )

        product.chunking_config = current_config
        db.commit()

        return {
            "message": "Chunking configuration updated automatically",
            "content_type": chunking_config.content_type.value,
            "confidence": chunking_config.confidence,
            "reasoning": chunking_config.reasoning,
            "recommended_config": {
                "chunk_size": chunking_config.chunk_size,
                "chunk_overlap": chunking_config.chunk_overlap,
                "min_chunk_size": chunking_config.min_chunk_size,
                "max_chunk_size": chunking_config.max_chunk_size,
                "strategy": chunking_config.strategy.value,
            },
        }

    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Auto-configuration failed: {str(e)}")


@router.post("/{product_id}/promote")
async def promote_version(
    product_id: UUID,
    request_body: PromoteVersionRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Promote a specific version to production by setting up a Qdrant alias.
    """
    # Ensure user has access to the product
    product = ensure_product_access(db, request, product_id)

    version = request_body.version

    # Check if the version exists and has succeeded
    pipeline_run = (
        db.query(PipelineRun)
        .filter(
            PipelineRun.product_id == product_id,
            PipelineRun.version == version,
            PipelineRun.status == PipelineRunStatus.SUCCEEDED,
        )
        .first()
    )

    if not pipeline_run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Version {version} not found or has not succeeded")

    try:
        from primedata.indexing.vector_search_client import vector_search_client
        from primedata.db.models import ArtifactType, PipelineArtifact

        if not vector_search_client.is_connected():
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Vector search client not connected")

        vectors_skipped = bool(
            (pipeline_run.metrics or {}).get("vectors_skipped")
            or (pipeline_run.metrics or {}).get("vectors_skip_reason")
            or (product.vector_creation_enabled is False)
        )

        alias_name = None
        collection_name = None
        alias_set = False

        if not vectors_skipped:
            # Prefer the exact collection name recorded during indexing (robust to product renames)
            indexing_artifact = (
                db.query(PipelineArtifact)
                .filter(
                    PipelineArtifact.pipeline_run_id == pipeline_run.id,
                    PipelineArtifact.stage_name == "indexing",
                    PipelineArtifact.artifact_type == ArtifactType.VECTOR,
                )
                .order_by(PipelineArtifact.created_at.desc())
                .first()
            )

            collection_name_hint = None
            if indexing_artifact and isinstance(indexing_artifact.artifact_metadata, dict):
                collection_name_hint = indexing_artifact.artifact_metadata.get("collection_name")

            sanitized_name = vector_search_client._sanitize_collection_name(product.name)
            alias_name_pretty = f"prod_ws_{product.workspace_id}__{sanitized_name}"
            alias_name_legacy = f"prod_ws_{product.workspace_id}__prod_{product_id}"

            if collection_name_hint:
                alias_set = vector_search_client.set_alias(alias_name=alias_name_pretty, collection_name=collection_name_hint)
                # Also set legacy alias for backward compatibility (best-effort)
                vector_search_client.set_alias(alias_name=alias_name_legacy, collection_name=collection_name_hint)
                collection_name = collection_name_hint
                alias_name = alias_name_pretty
            else:
                # Fallback: name/id guessing (older runs may not have artifact metadata)
                alias_set = vector_search_client.set_prod_alias(
                    workspace_id=str(product.workspace_id),
                    product_id=str(product_id),
                    version=version,
                    product_name=product.name,
                )
                if alias_set:
                    alias_name = alias_name_pretty
                    collection_name = vector_search_client.find_collection_name(
                        workspace_id=str(product.workspace_id),
                        product_id=str(product_id),
                        version=version,
                        product_name=product.name,
                    )

            if not alias_set:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Failed to set production alias in vector search backend. "
                        "No vectors/collection found for this version. "
                        "Run the pipeline with vector indexing enabled (or promote a version that has vectors)."
                    ),
                )
        else:
            logger.warning(
                f"Promoting version {version} without Qdrant alias: vectors were skipped for product {product_id}."
            )

        # Update the product's promoted_version
        product.promoted_version = version
        db.commit()
        db.refresh(product)

        if alias_set and not alias_name:
            # Backfill response fields if they were not set above
            sanitized_name = vector_search_client._sanitize_collection_name(product.name)
            alias_name = f"prod_ws_{product.workspace_id}__{sanitized_name}"
        if alias_set and not collection_name:
            collection_name = vector_search_client.find_collection_name(
                workspace_id=str(product.workspace_id),
                product_id=str(product_id),
                version=version,
                product_name=product.name,
            )

        return {
            "message": f"Version {version} promoted to production successfully",
            "promoted_version": version,
            "alias_name": alias_name,
            "collection_name": collection_name,
            "alias_set": alias_set,
            "vectors_skipped": vectors_skipped,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to promote version: {str(e)}")


@router.post("/{product_id}/rules/seed")
async def seed_data_quality_rules(
    product_id: str,
    request_body: dict = None,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Seed default data quality rules for a product."""
    logger.info(f"Seeding default data quality rules | product_id={product_id}")

    try:
        from uuid import UUID
        from ..db.models_enterprise import DataQualityRule, RuleSeverity

        from ..core.scope import ensure_product_access

        # Verify product exists and user has access
        product = ensure_product_access(db, request, UUID(product_id))
        logger.info(f"Product access verified | product_id={product_id}")

        # Default rule sets
        RULE_SETS = {
            "basic": [
                {
                    "name": "Required Fields Check",
                    "description": "Ensure all required fields are present",
                    "rule_type": "required_fields",
                    "severity": "error",
                    "configuration": {"required_fields": ["id", "name"]},
                    "enabled": True,
                },
                {
                    "name": "Duplicate Rate Check",
                    "description": "Limit duplicate records to 10%",
                    "rule_type": "max_duplicate_rate",
                    "severity": "warning",
                    "configuration": {"max_duplicate_rate": 0.1},
                    "enabled": True,
                },
            ],
            "comprehensive": [
                {
                    "name": "Required Fields Check",
                    "description": "Ensure all required fields are present",
                    "rule_type": "required_fields",
                    "severity": "error",
                    "configuration": {"required_fields": ["id", "name"]},
                    "enabled": True,
                },
                {
                    "name": "Duplicate Rate Check",
                    "description": "Limit duplicate records to 10%",
                    "rule_type": "max_duplicate_rate",
                    "severity": "warning",
                    "configuration": {"max_duplicate_rate": 0.1},
                    "enabled": True,
                },
                {
                    "name": "Chunk Coverage Check",
                    "description": "Ensure minimum chunk coverage of 80%",
                    "rule_type": "min_chunk_coverage",
                    "severity": "warning",
                    "configuration": {"min_chunk_coverage": 0.8},
                    "enabled": True,
                },
                {
                    "name": "Bad Extensions Check",
                    "description": "Block invalid file extensions",
                    "rule_type": "bad_extensions",
                    "severity": "error",
                    "configuration": {"blocked_extensions": [".exe", ".dll", ".bat", ".sh"]},
                    "enabled": True,
                },
                {
                    "name": "Freshness Check",
                    "description": "Ensure data is not older than 30 days",
                    "rule_type": "min_freshness",
                    "severity": "warning",
                    "configuration": {"min_freshness_days": 30},
                    "enabled": True,
                },
            ],
            "enterprise": [
                {
                    "name": "Required Fields Check",
                    "description": "Ensure all required fields are present",
                    "rule_type": "required_fields",
                    "severity": "error",
                    "configuration": {"required_fields": ["id", "name", "timestamp"]},
                    "enabled": True,
                },
                {
                    "name": "Duplicate Rate Check",
                    "description": "Limit duplicate records to 5%",
                    "rule_type": "max_duplicate_rate",
                    "severity": "error",
                    "configuration": {"max_duplicate_rate": 0.05},
                    "enabled": True,
                },
                {
                    "name": "Chunk Coverage Check",
                    "description": "Ensure minimum chunk coverage of 95%",
                    "rule_type": "min_chunk_coverage",
                    "severity": "error",
                    "configuration": {"min_chunk_coverage": 0.95},
                    "enabled": True,
                },
                {
                    "name": "Bad Extensions Check",
                    "description": "Block invalid file extensions",
                    "rule_type": "bad_extensions",
                    "severity": "error",
                    "configuration": {"blocked_extensions": [".exe", ".dll", ".bat", ".sh", ".com"]},
                    "enabled": True,
                },
                {
                    "name": "Freshness Check",
                    "description": "Ensure data is not older than 14 days",
                    "rule_type": "min_freshness",
                    "severity": "error",
                    "configuration": {"min_freshness_days": 14},
                    "enabled": True,
                },
                {
                    "name": "File Size Check",
                    "description": "Enforce file size limits",
                    "rule_type": "file_size",
                    "severity": "warning",
                    "configuration": {"max_file_size_mb": 500, "min_file_size_kb": 1},
                    "enabled": True,
                },
                {
                    "name": "Content Length Check",
                    "description": "Enforce content length limits",
                    "rule_type": "content_length",
                    "severity": "warning",
                    "configuration": {"min_content_length": 100, "max_content_length": 1000000},
                    "enabled": True,
                },
            ],
        }

        # Parse request body
        rule_set_name = "basic"
        overwrite = False
        if request_body:
            rule_set_name = request_body.get("rule_set", "basic")
            overwrite = request_body.get("overwrite", False)

        if rule_set_name not in RULE_SETS:
            logger.warning(f"Invalid rule set | rule_set={rule_set_name}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid rule_set. Must be one of: {', '.join(RULE_SETS.keys())}"
            )

        logger.info(f"Using rule set | rule_set={rule_set_name}, overwrite={overwrite}")

        # Get existing rules if not overwriting
        existing_rules = []
        if not overwrite:
            existing_rules = (
                db.query(DataQualityRule)
                .filter(DataQualityRule.product_id == product_id, DataQualityRule.is_current == True)
                .all()
            )
            logger.info(f"Found {len(existing_rules)} existing rules")

        # Create new rules
        created_rules = []
        skipped_count = 0

        for rule_data in RULE_SETS[rule_set_name]:
            # Check if rule already exists (by name and type)
            existing = next(
                (r for r in existing_rules if r.name == rule_data["name"] and r.rule_type == rule_data["rule_type"]),
                None
            )

            if existing and not overwrite:
                logger.debug(f"Skipping existing rule | name={rule_data['name']}")
                skipped_count += 1
                continue

            new_rule = DataQualityRule(
                product_id=product_id,
                workspace_id=product.workspace_id,
                name=rule_data["name"],
                description=rule_data["description"],
                rule_type=rule_data["rule_type"],
                severity=RuleSeverity(rule_data["severity"]),
                configuration=rule_data["configuration"],
                enabled=rule_data["enabled"],
                created_by=current_user.get("sub") if current_user else "system",
                updated_by=None,
            )
            db.add(new_rule)
            created_rules.append(new_rule)
            logger.debug(f"Created rule | name={new_rule.name}")

        # Flush to get IDs
        db.flush()
        logger.info(f"Flushed {len(created_rules)} new rules")

        # Create audit logs
        from ..db.models_enterprise import DataQualityRuleAudit, AuditAction

        for rule in created_rules:
            rule_data_dict = {
                "id": str(rule.id),
                "product_id": str(rule.product_id),
                "workspace_id": str(rule.workspace_id),
                "name": rule.name,
                "description": rule.description,
                "rule_type": rule.rule_type,
                "severity": str(rule.severity),
                "configuration": rule.configuration,
                "enabled": rule.enabled,
            }
            audit_log = DataQualityRuleAudit(
                rule_id=rule.id, action=AuditAction.CREATE, changed_by=None, new_values=rule_data_dict
            )
            db.add(audit_log)

        db.commit()
        logger.info(f"Rules seeded successfully | created={len(created_rules)}, skipped={skipped_count}")

        return {
            "message": "Rules seeded successfully",
            "rule_set": rule_set_name,
            "created": len(created_rules),
            "skipped": skipped_count,
            "rules": [
                {
                    "rule_id": str(rule.id),
                    "name": rule.name,
                    "rule_type": rule.rule_type,
                    "status": "created"
                }
                for rule in created_rules
            ]
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to seed data quality rules | product_id={product_id}, error={str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to seed data quality rules: {str(e)}")
