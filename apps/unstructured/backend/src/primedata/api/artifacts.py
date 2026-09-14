"""
Artifacts API router for listing and accessing stored data.
"""

import json
from typing import Any, Dict, List, Optional
from uuid import UUID
import io

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from primedata.core.scope import ensure_product_access, ensure_workspace_access
from primedata.db.database import get_db
from primedata.db.models import Product
from primedata.storage.storage_client import storage_client
from primedata.storage.paths import raw_prefix, artifacts_prefix
from primedata.core.constants import BUCKET_RAW, BUCKET_EXPORTS
from pydantic import BaseModel
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/v1/artifacts", tags=["Artifacts"])

from primedata.utils.logger import get_logger
logger = get_logger(__name__)


class ArtifactInfo(BaseModel):
    name: str
    size: int
    last_modified: str
    url: str
    content_type: Optional[str] = None


class RawArtifactsResponse(BaseModel):
    artifacts: List[ArtifactInfo]
    total_files: int
    total_bytes: int
    prefix: str


class ArtifactPreviewResponse(BaseModel):
    """Response model for artifact preview."""
    artifact_id: str
    type: str  # jsonl, json, csv, pdf, txt
    preview_type: str  # text, image, html
    content: str
    total_lines: int
    preview_lines: int
    has_more: bool
    format_info: Optional[Dict[str, Any]] = None


class VectorPreviewItem(BaseModel):
    """Single vector preview item."""
    id: str
    content_preview: str
    vector_sample: List[float]
    vector_dimension: int
    magnitude: float


class VectorPreviewResponse(BaseModel):
    """Response model for vector preview."""
    artifact_id: str
    type: str
    embeddings: List[VectorPreviewItem]
    total: int
    preview_count: int
    statistics: Dict[str, Any]


@router.get("/raw", response_model=RawArtifactsResponse)
async def list_raw_artifacts(
    request: Request,
    product_id: UUID = Query(..., description="Product ID"),
    version: Optional[int] = Query(None, description="Version number (defaults to latest)"),
    db: Session = Depends(get_db)
):
    """
    List raw artifacts for a product and version.
    """
    logger.info(f"📦 ENTER list_raw_artifacts - product_id={product_id}, version={version}")
    try:
        # Get the product
        logger.debug(f"📦 💾 Querying database for product_id={product_id}")
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            logger.warning(f"⚠️ Product not found: product_id={product_id}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

        logger.debug(f"📦 ✓ Found product: {product.name}")

        # Ensure user has access to the product
        logger.debug(f"📦 🔐 Verifying access to product_id={product_id}")
        ensure_product_access(db, request, product_id)
        logger.debug(f"📦 ✓ Access verified")

        # Determine version
        if version is None:
            version = product.current_version
            logger.debug(f"📦 Auto-detected latest version: {version}")
        else:
            logger.debug(f"📦 Using explicit version: {version}")

        # Generate prefix
        logger.debug(f"📦 📋 Generating storage prefixes for listing")
        prefix = raw_prefix(product.workspace_id, product_id, version)
        logger.debug(f"📦 Raw prefix: {prefix}")

        # Also include artifacts (M3: validation summary and trust report)
        artifacts_prefix_path = artifacts_prefix(product.workspace_id, product_id, version)
        logger.debug(f"📦 Artifacts prefix: {artifacts_prefix_path}")

        # List objects from storage
        try:
            logger.debug(f"📦 Listing raw artifacts from primedata-raw bucket with prefix={prefix}")
            objects = storage_client.list_objects(BUCKET_RAW, prefix)
            logger.debug(f"📦 ✓ Found {len(objects)} raw artifacts")

            artifacts = []
            total_bytes = 0

            # Process raw artifacts
            logger.debug(f"📦 📋 Processing {len(objects)} raw artifacts for URL generation")
            for idx, obj in enumerate(objects, 1):
                # Generate presigned URL
                logger.debug(f"📦 {idx}/{len(objects)} Generating presigned URL for {obj['name'].split('/')[-1]}")
                presigned_url = storage_client.presign(BUCKET_RAW, obj["name"], expiry=3600)

                if presigned_url:
                    artifact_info = ArtifactInfo(
                        name=obj["name"].split("/")[-1],  # Just the filename
                        size=obj["size"],
                        last_modified=obj["last_modified"] if obj["last_modified"] else "",
                        url=presigned_url,
                        content_type=obj.get("content_type"),
                    )
                    artifacts.append(artifact_info)
                    total_bytes += obj["size"]
                    logger.debug(f"✓ Added raw artifact: {artifact_info.name} ({obj['size']} bytes)")
                else:
                    logger.warning(f"⚠️ Failed to generate presigned URL for {obj['name']}")

            # Add artifacts from primedata-exports bucket (M3: validation summary and trust report)
            logger.debug(f"📦 Listing artifacts from primedata-exports bucket with prefix={artifacts_prefix_path}")
            try:
                artifact_objects = storage_client.list_objects(BUCKET_EXPORTS, artifacts_prefix_path)
                logger.debug(f"📦 ✓ Found {len(artifact_objects)} export artifacts")

                logger.debug(f"📦 📋 Processing {len(artifact_objects)} export artifacts for URL generation")
                for idx, obj in enumerate(artifact_objects, 1):
                    logger.debug(f"📦 {idx}/{len(artifact_objects)} Generating presigned URL for {obj['name'].split('/')[-1]}")
                    presigned_url = storage_client.presign(BUCKET_EXPORTS, obj["name"], expiry=3600)
                    if presigned_url:
                        artifact_info = ArtifactInfo(
                            name=obj["name"].split("/")[-1],  # Just the filename
                            size=obj["size"],
                            last_modified=obj["last_modified"] if obj["last_modified"] else "",
                            url=presigned_url,
                            content_type=obj.get("content_type"),
                        )
                        artifacts.append(artifact_info)
                        total_bytes += obj["size"]
                        logger.debug(f"✓ Added export artifact: {artifact_info.name} ({obj['size']} bytes)")
                    else:
                        logger.warning(f"⚠️ Failed to generate presigned URL for {obj['name']}")
            except Exception as e:
                logger.warning(f"⚠️ Failed to list artifacts from exports bucket: {e}")

            result = RawArtifactsResponse(
                artifacts=artifacts,
                total_files=len(artifacts),
                total_bytes=total_bytes,
                prefix=prefix
            )
            logger.info(f"✅ EXIT list_raw_artifacts - product_id={product_id}, version={version}, total_files={len(artifacts)}, total_bytes={total_bytes}")
            return result

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Failed to list artifacts from storage: {e}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to list artifacts: {str(e)}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ EXIT list_raw_artifacts FAILED - product_id={product_id}: {e}", exc_info=True)
        raise


@router.get("/{artifact_id}/preview", response_model=ArtifactPreviewResponse)
async def get_artifact_preview(
    artifact_id: str,
    request: Request,
    lines: int = Query(50, ge=1, le=1000, description="Number of lines to preview"),
    db: Session = Depends(get_db)
):
    """
    Get preview of artifact content (first N lines).

    Supports: jsonl, json, csv, pdf (text), txt
    """
    logger.info(f"📦 ENTER get_artifact_preview - artifact_id={artifact_id}, lines={lines}")

    try:
        # Validate artifact_id format (should be a path in S3)
        if not artifact_id or "/" in artifact_id.lstrip("/"):
            # artifact_id could be just the filename or full S3 path
            pass

        logger.debug(f"📦 Fetching artifact content from S3 | artifact_id={artifact_id}")

        # Try to get the artifact from storage
        # artifact_id could be in BUCKET_RAW or BUCKET_EXPORTS
        artifact_content = None
        bucket_used = None
        file_type = "txt"

        # Try different buckets and determine file type
        try:
            # Try exports bucket first (for generated artifacts)
            artifact_content = await storage_client.get_object(BUCKET_EXPORTS, artifact_id)
            bucket_used = BUCKET_EXPORTS
            logger.debug(f"📦 Found artifact in exports bucket")
        except Exception as e:
            logger.debug(f"📦 Not in exports bucket, trying raw bucket | error={str(e)}")
            try:
                # Try raw bucket
                artifact_content = await storage_client.get_object(BUCKET_RAW, artifact_id)
                bucket_used = BUCKET_RAW
                logger.debug(f"📦 Found artifact in raw bucket")
            except Exception as e2:
                logger.error(f"❌ Artifact not found in any bucket | artifact_id={artifact_id}, error={str(e2)}")
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Artifact not found: {artifact_id}")

        # Determine file type from artifact_id
        if artifact_id.endswith(".jsonl"):
            file_type = "jsonl"
        elif artifact_id.endswith(".json"):
            file_type = "json"
        elif artifact_id.endswith(".csv"):
            file_type = "csv"
        elif artifact_id.endswith(".pdf"):
            file_type = "pdf"
        else:
            file_type = "txt"

        # Parse content
        if isinstance(artifact_content, bytes):
            content_str = artifact_content.decode("utf-8", errors="ignore")
        else:
            content_str = str(artifact_content)

        # Split into lines and get preview
        content_lines = content_str.split("\n")
        total_lines = len(content_lines)
        preview_lines_list = content_lines[:lines]
        preview_content = "\n".join(preview_lines_list)

        logger.info(f"✅ EXIT get_artifact_preview - artifact_id={artifact_id}, total_lines={total_lines}, preview_lines={len(preview_lines_list)}")

        return ArtifactPreviewResponse(
            artifact_id=artifact_id,
            type=file_type,
            preview_type="text",
            content=preview_content,
            total_lines=total_lines,
            preview_lines=len(preview_lines_list),
            has_more=len(preview_lines_list) < total_lines,
            format_info={
                "encoding": "utf-8",
                "size_bytes": len(content_str.encode("utf-8")),
                "file_type": file_type
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ EXIT get_artifact_preview FAILED - artifact_id={artifact_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get artifact preview: {str(e)}")


@router.get("/{artifact_id}/vector-preview", response_model=VectorPreviewResponse)
async def get_vector_preview(
    artifact_id: str,
    request: Request,
    limit: int = Query(10, ge=1, le=100, description="Number of vectors to preview"),
    db: Session = Depends(get_db)
):
    """
    Get preview of vectorized embeddings for an artifact.

    Returns sample vectors with content preview and statistics.
    """
    logger.info(f"📦 ENTER get_vector_preview - artifact_id={artifact_id}, limit={limit}")

    try:
        from primedata.indexing.vector_search_client import get_vector_search_client

        # Get vector search client
        vector_search_client = get_vector_search_client()
        logger.debug(f"📦 Vector search client initialized")

        # Try to find collection for this artifact
        # artifact_id format: typically includes workspace_id, product_id, version
        # For simplicity, we'll search for collections containing artifact_id

        # Parse artifact_id to extract product and version info if available
        # Expected format: ws/{workspace}/prod/{product}/v/{version}/...
        parts = artifact_id.split("/")

        workspace_id = None
        product_id = None
        version = None

        # Try to extract workspace, product, version from path
        try:
            for i, part in enumerate(parts):
                if part == "ws" and i + 1 < len(parts):
                    workspace_id = parts[i + 1]
                elif part == "prod" and i + 1 < len(parts):
                    product_id = parts[i + 1]
                elif part == "v" and i + 1 < len(parts):
                    version = int(parts[i + 1])
        except Exception:
            pass

        if not workspace_id or not product_id or version is None:
            logger.warning(f"⚠️ Could not parse artifact_id for collection | artifact_id={artifact_id}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid artifact_id format")

        # Get collection name
        collection_name = vector_search_client.get_collection_name(workspace_id, product_id, version)
        if not collection_name:
            logger.warning(f"⚠️ No collection found for artifact | artifact_id={artifact_id}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No embeddings found for artifact")

        logger.debug(f"📦 Collection found | collection_name={collection_name}")

        # Retrieve sample vectors
        embeddings = []
        total_count = 0
        vector_stats = {
            "avg_magnitude": 0.0,
            "vector_range": {"min": 0.0, "max": 0.0},
            "dimension": 0
        }

        try:
            # Scroll through vectors and collect samples
            sample_count = 0
            magnitudes = []
            min_val = float('inf')
            max_val = float('-inf')

            for point in vector_search_client.scroll_points(collection_name, batch_size=min(limit, 100)):
                total_count += 1

                if sample_count < limit:
                    # Extract vector and metadata
                    vector = point.get("vector", [])
                    payload = point.get("payload", {})

                    # Calculate magnitude
                    magnitude = sum(v**2 for v in vector) ** 0.5 if vector else 0.0
                    magnitudes.append(magnitude)

                    # Track range
                    if vector:
                        min_val = min(min_val, min(vector))
                        max_val = max(max_val, max(vector))

                    # Store sample with dimension info
                    if vector_stats["dimension"] == 0 and vector:
                        vector_stats["dimension"] = len(vector)

                    # Note: chunks stored in OpenSearch use "text" field, not "chunk_text"
                    chunk_text = payload.get("text") or payload.get("chunk_text", "")
                    embeddings.append(VectorPreviewItem(
                        id=str(point.get("id", "")),
                        content_preview=chunk_text[:100],
                        vector_sample=vector[:20] if len(vector) > 20 else vector,  # Sample first 20 dims
                        vector_dimension=len(vector),
                        magnitude=magnitude
                    ))
                    sample_count += 1

                if total_count > 10000:  # Safety limit
                    break

            # Calculate statistics
            if magnitudes:
                vector_stats["avg_magnitude"] = sum(magnitudes) / len(magnitudes)
                vector_stats["vector_range"] = {
                    "min": min_val if min_val != float('inf') else 0.0,
                    "max": max_val if max_val != float('-inf') else 0.0
                }

            logger.info(f"✅ EXIT get_vector_preview - artifact_id={artifact_id}, total={total_count}, preview_count={len(embeddings)}")

            return VectorPreviewResponse(
                artifact_id=artifact_id,
                type="embedding",
                embeddings=embeddings,
                total=total_count,
                preview_count=len(embeddings),
                statistics=vector_stats
            )

        except Exception as e:
            logger.error(f"❌ Error retrieving vectors | artifact_id={artifact_id}, error={str(e)}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve vector preview: {str(e)}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ EXIT get_vector_preview FAILED - artifact_id={artifact_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get vector preview: {str(e)}")
