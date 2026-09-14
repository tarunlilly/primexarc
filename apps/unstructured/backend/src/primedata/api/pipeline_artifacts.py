"""
Pipeline artifact endpoints.

These route handlers are registered on the shared router from pipeline.py.
"""

import os
from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from primedata.api.pipeline import router
from primedata.core.scope import ensure_product_access
from primedata.db.database import get_db
from primedata.db.models import ArtifactStatus, PipelineArtifact, Product
from primedata.indexing.vector_search_client import get_vector_search_client
from primedata.storage.storage_client import storage_client
from primedata.utils.logger import get_logger

logger = get_logger(__name__)


class PipelineArtifactResponse(BaseModel):
    """Response model for pipeline artifact information."""

    id: str
    stage_name: str
    artifact_name: str
    artifact_type: str
    file_size: int
    created_at: str
    download_url: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None


@router.get("/artifacts")
async def get_pipeline_artifacts(
    product_id: UUID,
    version: Optional[int] = Query(None, description="Version number (defaults to latest)"),
    request_obj: Request = None,
    db: Session = Depends(get_db)
):
    """
    Get pipeline artifacts for a product and version.
    Returns artifacts grouped by stage from successful pipeline runs.
    """
    logger.info(f"🔄 ENTER get_pipeline_artifacts - product_id={product_id}, version={version}")
    try:
        # Ensure user has access to the product
        logger.debug(f"🔄 🔐 Verifying access to product_id={product_id}")
        product = ensure_product_access(db, request_obj, product_id)
        logger.debug(f"🔄 ✓ Access verified")

        # Determine version
        if version is None:
            version = product.current_version
            logger.debug(f"🔄 Auto-detected latest version: {version}")
        else:
            logger.debug(f"🔄 Using explicit version: {version}")

        # Get artifacts for this product and version
        logger.debug(f"💾 Querying database for artifacts - product_id={product_id}, version={version}")
        artifacts = (
            db.query(PipelineArtifact)
            .filter(
                PipelineArtifact.product_id == product_id,
                PipelineArtifact.version == version,
                PipelineArtifact.status == ArtifactStatus.ACTIVE,  # Only show active artifacts
            )
            .order_by(PipelineArtifact.stage_name, PipelineArtifact.created_at.desc())
            .all()
        )
        logger.debug(f"💾 Retrieved {len(artifacts)} active artifacts from database")

        # Get vector search client for vector artifacts
        vector_search_client = get_vector_search_client()
        logger.debug(f"🔄 Initialized vector search client for vector artifacts")

        # Artifact display names mapping
        artifact_display_names = {
            "fingerprint": "AI Readiness Fingerprint",
            "trust_report": "AI Trust Report",
            "validation_summary": "Validation Summary",
            "processed_chunks": "Processed Chunks",
            "metrics": "Trust Metrics",
            "vectors": "Vector Index",
        }

        # Artifact descriptions
        artifact_descriptions = {
            "fingerprint": "AI readiness metrics and fingerprint data",
            "trust_report": "Comprehensive AI trust assessment report",
            "validation_summary": "AI validation results and compliance summary",
            "processed_chunks": "Cleaned and chunked document data",
            "metrics": "Trust scoring and quality metrics",
            "vectors": "Embedded vector index metadata",
        }

        result = []
        logger.debug(f"📋 Processing {len(artifacts)} artifacts for URL generation and metadata")
        for idx, artifact in enumerate(artifacts, 1):
            # Generate presigned URL for download (only for non-vector artifacts)
            download_url = None
            file_size = artifact.file_size

            # For vector artifacts, get size from Elasticsearch collection
            if artifact.artifact_type.value.lower() == 'vector':
                logger.debug(f"🔄 {idx}/{len(artifacts)} Processing vector artifact {artifact.artifact_name}")
                try:
                    # Find collection name for this product/version
                    collection_name = vector_search_client.find_collection_name(
                        workspace_id=str(product.workspace_id),
                        product_id=str(product.id),
                        version=version,
                        product_name=product.name,
                    )

                    if collection_name and vector_search_client.is_connected():
                        logger.debug(f"🔄 Retrieving collection info for {collection_name}")
                        collection_info = vector_search_client.get_collection_info(collection_name)
                        if collection_info:
                            points_count = collection_info.get("points_count", 0)
                            vector_size = collection_info.get("config", {}).get("vector_size", 0)
                            # Estimate size: points_count * (vector_size * 4 bytes per float32 + payload overhead)
                            # Rough estimate: vector_size * 4 bytes per point + 1KB payload overhead per point
                            estimated_bytes = points_count * (vector_size * 4 + 1024)
                            file_size = estimated_bytes
                            logger.debug(f"✓ Calculated vector artifact size: {estimated_bytes} bytes ({points_count} points, {vector_size} dims)")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to get Elasticsearch collection size for vector artifact: {e}")
                    # Keep original file_size if available
            else:
                logger.debug(f"🔄 {idx}/{len(artifacts)} Processing non-vector artifact {artifact.artifact_name}")
                # For non-vector artifacts, generate presigned URL
                # Skip artifacts that don't have files in storage
                if not artifact.storage_bucket or artifact.storage_bucket.lower() in ("none", "elasticsearch"):
                    # These artifacts don't have physical files in S3/GCS
                    # - "none": Metadata-only artifacts (e.g., policy evaluation results)
                    # - "elasticsearch": Vector artifacts stored in Elasticsearch indices
                    logger.debug(
                        f"📋 Artifact {artifact.id} has storage_bucket='{artifact.storage_bucket}', "
                        f"skipping presigned URL generation (no file in storage)"
                    )
                    download_url = None
                elif not artifact.storage_key or artifact.storage_key.strip() == "":
                    logger.warning(
                        f"⚠️ Artifact {artifact.id} has invalid storage_key: '{artifact.storage_key}'. "
                        f"Skipping presigned URL generation."
                    )
                    download_url = None
                else:
                    try:
                        logger.debug(f"🔄 Generating presigned URL for artifact {artifact.id} from {artifact.storage_bucket}")
                        # Generate download URL (attachment) for downloading files
                        download_url = storage_client.presign(
                            artifact.storage_bucket,
                            artifact.storage_key,
                            expiry=3600,  # 1 hour expiry
                            inline=False,  # Explicit for downloads
                        )

                        # Validate the presigned URL
                        if download_url:
                            # Check if it's a valid signed URL (contains signature parameters)
                            if 'X-Goog-Signature' in download_url or 'Signature' in download_url or 'Expires' in download_url:
                                logger.debug(f"✓ Generated valid presigned URL for artifact {artifact.id}")
                            else:
                                # If it's a direct GCS URL without signature, it won't work for private blobs
                                logger.warning(f"⚠️ Presigned URL for artifact {artifact.id} doesn't contain signature parameters")
                                download_url = None
                        else:
                            logger.warning(
                                f"⚠️ Failed to generate presigned URL for artifact {artifact.id} "
                                f"(bucket={artifact.storage_bucket}, key={artifact.storage_key[:50] if artifact.storage_key else 'None'}...)"
                            )
                    except Exception as e:
                        # Log the full exception details to understand what's failing
                        error_type = type(e).__name__
                        error_msg = str(e)
                        logger.warning(
                            f"❌ Failed to generate presigned URL for artifact {artifact.id}: {error_type}: {error_msg}. "
                            f"Bucket: '{artifact.storage_bucket}', Key: '{artifact.storage_key[:80] if artifact.storage_key else 'None'}...'",
                            exc_info=True
                        )
                        download_url = None

            # Get display name
            display_name = artifact_display_names.get(artifact.artifact_name, artifact.artifact_name.replace("_", " ").title())

            # Get description
            description = artifact_descriptions.get(artifact.artifact_name)

            result.append(
                PipelineArtifactResponse(
                    id=str(artifact.id),
                    stage_name=artifact.stage_name,
                    artifact_name=artifact.artifact_name,
                    artifact_type=artifact.artifact_type.value,
                    file_size=file_size,  # Use calculated size for vectors
                    created_at=artifact.created_at.isoformat() if artifact.created_at else "",
                    download_url=download_url,  # Only set if presigned URL was successfully generated
                    display_name=display_name,
                    description=description,
                )
            )

        logger.info(f"✅ EXIT get_pipeline_artifacts - product_id={product_id}, version={version}, returned {len(result)} artifacts")
        return {"artifacts": result, "total": len(result)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ EXIT get_pipeline_artifacts FAILED - product_id={product_id}: {e}", exc_info=True)
        raise


@router.get("/artifacts/{artifact_id}/content")
async def get_artifact_content(
    artifact_id: UUID,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Get artifact content by ID. Acts as a proxy to avoid CORS issues.
    Returns the file content with proper content-type headers.
    """
    logger.info(f"📦 ENTER get_artifact_content - artifact_id={artifact_id}")
    try:
        # Get the artifact
        logger.debug(f"📦 💾 Querying database for artifact_id={artifact_id}")
        artifact = db.query(PipelineArtifact).filter(PipelineArtifact.id == artifact_id).first()
        if not artifact:
            logger.warning(f"⚠️ Artifact not found: artifact_id={artifact_id}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact not found")

        logger.debug(f"📦 ✓ Found artifact: {artifact.artifact_name}")

        # Ensure user has access to the product
        logger.debug(f"📦 🔐 Verifying access to product_id={artifact.product_id}")
        ensure_product_access(db, request, artifact.product_id)
        logger.debug(f"📦 ✓ Access verified")

        # Check if artifact has storage info
        if not artifact.storage_bucket or not artifact.storage_key:
            logger.warning(f"⚠️ Artifact {artifact_id} does not have storage information")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Artifact does not have storage information"
            )

        logger.debug(f"📦 Storage location: {artifact.storage_bucket}/{artifact.storage_key[:50]}...")

        # Skip vector artifacts
        if artifact.artifact_type.value.lower() == 'vector':
            logger.warning(f"⚠️ Attempted to retrieve vector artifact {artifact_id} as file")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Vector artifacts cannot be viewed as files. Use the RAG Playground to query them."
            )

        try:
            # Fetch file content from storage
            logger.debug(f"📦 Fetching file content from {artifact.storage_bucket}")

            # The artifact.storage_key is now the full S3 key as stored by put_artifact()
            # which includes the metadata path + subfolder + file path
            # Use S3_METADATA_BUCKET if set (same as put_bytes does)
            storage_bucket = os.getenv("S3_METADATA_BUCKET", artifact.storage_bucket)
            logger.debug(f"📦 Using bucket={storage_bucket}, key={artifact.storage_key}")

            file_content = storage_client.get_bytes(storage_bucket, artifact.storage_key)
            logger.debug(f"📦 Retrieved artifact: {artifact.storage_key}")

            if not file_content:
                logger.warning(f"⚠️ Artifact file not found in storage for artifact_id={artifact_id}")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Artifact file not found in storage"
                )

            logger.debug(f"📦 ✓ Retrieved {len(file_content)} bytes from storage")

            # Determine content type based on artifact type or file extension
            content_type = "application/octet-stream"
            if artifact.artifact_type.value.lower() == 'json':
                content_type = "application/json"
            elif artifact.artifact_type.value.lower() == 'csv':
                content_type = "text/csv"
            elif artifact.artifact_type.value.lower() == 'pdf':
                content_type = "application/pdf"
            elif artifact.artifact_type.value.lower() == 'jsonl':
                content_type = "application/x-ndjson"
            elif artifact.storage_key.endswith('.json'):
                content_type = "application/json"
            elif artifact.storage_key.endswith('.csv'):
                content_type = "text/csv"
            elif artifact.storage_key.endswith('.pdf'):
                content_type = "application/pdf"
            elif artifact.storage_key.endswith('.jsonl'):
                content_type = "application/x-ndjson"
            elif artifact.storage_key.endswith('.txt'):
                content_type = "text/plain"

            logger.debug(f"📦 Content-Type: {content_type}")

            from fastapi.responses import Response
            response = Response(
                content=file_content,
                media_type=content_type,
                headers={
                    "Content-Disposition": "inline",
                    "Cache-Control": "private, max-age=3600",
                }
            )
            logger.info(f"✅ EXIT get_artifact_content - artifact_id={artifact_id}, size={len(file_content)} bytes, type={content_type}")
            return response
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Failed to fetch artifact content for artifact_id={artifact_id}: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to fetch artifact content: {str(e)}"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ EXIT get_artifact_content FAILED - artifact_id={artifact_id}: {e}", exc_info=True)
        raise
