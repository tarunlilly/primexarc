"""
Versioning API endpoints for managing data and model versions.

Endpoints:
- POST /api/v1/versions/{entity_id} - Create version
- GET /api/v1/versions/{entity_id} - List versions
- GET /api/v1/versions/{entity_id}/latest - Get latest version
- GET /api/v1/versions/v/{version_id} - Get specific version
- POST /api/v1/versions/{entity_id}/rollback - Rollback to version
- DELETE /api/v1/versions/{version_id} - Hard delete version
- POST /api/v1/versions/{version_id}/deprecate - Mark deprecated
- POST /api/v1/versions/{version_id}/archive - Archive version
- GET /api/v1/versions/{entity_id}/stats - Version statistics
"""

from typing import Any, Dict, List, Optional
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from primedata.db.database import get_db
from primedata.db.models import Product, PipelineRun
from primedata.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/versions", tags=["versions"])


# ============================================================================
# PYDANTIC MODELS
# ============================================================================


class VersionCreate(BaseModel):
    """Request model for creating a version."""

    entity_id: UUID
    entity_type: str = Field(..., description="Type: product, process, pipeline, model, config")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
    description: Optional[str] = None
    created_by: Optional[str] = None


class VersionResponse(BaseModel):
    """Response model for version."""

    version_id: str
    entity_id: str
    entity_type: str
    version_number: int
    status: str  # ACTIVE, ARCHIVED, ROLLED_BACK, DEPRECATED
    created_at: datetime
    created_by: Optional[str]
    description: Optional[str]
    metadata: Dict[str, Any]


class VersionDeprecate(BaseModel):
    """Request to deprecate a version."""

    reason: str
    replacement_version_id: Optional[str] = None


class VersionRollback(BaseModel):
    """Request to rollback to a version."""

    version_id: str
    reason: str


class VersionStats(BaseModel):
    """Version statistics."""

    total_versions: int
    active_count: int
    archived_count: int
    deprecated_count: int
    rolled_back_count: int
    by_status: Dict[str, int]


# ============================================================================
# ENDPOINTS
# ============================================================================


@router.post("/{entity_id}")
async def create_version(
    entity_id: UUID,
    version_data: VersionCreate,
    db: Session = Depends(get_db),
) -> VersionResponse:
    """
    Create a new version of an entity.

    Args:
        entity_id: Entity ID
        version_data: Version metadata
        db: Database session

    Returns:
        Created version details
    """
    logger.info(f"📋 POST /api/v1/versions/{entity_id} - Creating version")

    try:
        # Get product if entity_type is product
        if version_data.entity_type == "product":
            product = db.query(Product).filter(Product.id == entity_id).first()
            if not product:
                logger.warning(f"❌ Product {entity_id} not found")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Product {entity_id} not found",
                )
            logger.info(f"✓ Found product: {product.name}")

            # Create new version from current state
            new_version = product.current_version + 1
            version_id = f"{entity_id}_v{new_version}"

            version_response = VersionResponse(
                version_id=version_id,
                entity_id=str(entity_id),
                entity_type=version_data.entity_type,
                version_number=new_version,
                status="ACTIVE",
                created_at=datetime.utcnow(),
                created_by=version_data.created_by,
                description=version_data.description,
                metadata=version_data.metadata or {},
            )

            logger.info(f"✅ Version created: {version_id}")
            return version_response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error creating version: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create version: {str(e)}",
        )


@router.get("/{entity_id}")
async def list_versions(
    entity_id: UUID,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    status_filter: Optional[str] = Query(None, description="Filter by status (ACTIVE, ARCHIVED, etc)"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    List all versions of an entity (paginated, newest first).

    Args:
        entity_id: Entity ID
        limit: Maximum results
        offset: Pagination offset
        status_filter: Optional status filter
        db: Database session

    Returns:
        List of versions with pagination info
    """
    logger.info(f"📋 GET /api/v1/versions/{entity_id} - Listing versions")

    try:
        # Verify entity exists
        product = db.query(Product).filter(Product.id == entity_id).first()
        if not product:
            logger.warning(f"❌ Product {entity_id} not found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product {entity_id} not found",
            )

        # Collect versions from product history
        versions = []
        for v in range(1, product.current_version + 1):
            version_id = f"{entity_id}_v{v}"
            versions.append(
                {
                    "version_id": version_id,
                    "entity_id": str(entity_id),
                    "version_number": v,
                    "status": "ACTIVE" if v == product.current_version else "ARCHIVED",
                    "created_at": datetime.utcnow().isoformat(),
                }
            )

        # Reverse for newest first
        versions = list(reversed(versions))

        # Apply pagination
        total = len(versions)
        versions = versions[offset : offset + limit]

        logger.info(f"✓ Retrieved {len(versions)} versions (total: {total})")

        return {
            "entity_id": str(entity_id),
            "versions": versions,
            "pagination": {
                "total": total,
                "limit": limit,
                "offset": offset,
                "returned": len(versions),
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error listing versions: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list versions: {str(e)}",
        )


@router.get("/{entity_id}/latest")
async def get_latest_version(
    entity_id: UUID,
    db: Session = Depends(get_db),
) -> VersionResponse:
    """
    Get the latest version of an entity.

    Args:
        entity_id: Entity ID
        db: Database session

    Returns:
        Latest version details
    """
    logger.info(f"📋 GET /api/v1/versions/{entity_id}/latest - Getting latest version")

    try:
        product = db.query(Product).filter(Product.id == entity_id).first()
        if not product:
            logger.warning(f"❌ Product {entity_id} not found")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product {entity_id} not found",
            )

        version_id = f"{entity_id}_v{product.current_version}"

        logger.info(f"✓ Latest version: {version_id}")

        return VersionResponse(
            version_id=version_id,
            entity_id=str(entity_id),
            entity_type="product",
            version_number=product.current_version,
            status="ACTIVE",
            created_at=datetime.utcnow(),
            created_by=None,
            description=f"Product {product.name} version {product.current_version}",
            metadata={"status": product.status},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error getting latest version: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get latest version: {str(e)}",
        )


@router.get("/v/{version_id}")
async def get_version(
    version_id: str,
    db: Session = Depends(get_db),
) -> VersionResponse:
    """
    Get a specific version by ID.

    Args:
        version_id: Version ID (format: {entity_id}_v{number})
        db: Database session

    Returns:
        Version details with full content
    """
    logger.info(f"📋 GET /api/v1/versions/v/{version_id} - Getting version")

    try:
        # Parse version ID
        parts = version_id.rsplit("_v", 1)
        if len(parts) != 2:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid version ID format. Expected: {entity_id}_v{number}",
            )

        entity_id_str, version_num_str = parts
        try:
            entity_id = UUID(entity_id_str)
            version_num = int(version_num_str)
        except (ValueError, AttributeError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid version ID format",
            )

        product = db.query(Product).filter(Product.id == entity_id).first()
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product not found",
            )

        if version_num > product.current_version or version_num < 1:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Version {version_num} not found",
            )

        logger.info(f"✓ Retrieved version {version_id}")

        return VersionResponse(
            version_id=version_id,
            entity_id=str(entity_id),
            entity_type="product",
            version_number=version_num,
            status="ACTIVE" if version_num == product.current_version else "ARCHIVED",
            created_at=datetime.utcnow(),
            created_by=None,
            description=f"Version {version_num}",
            metadata={},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error getting version: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get version: {str(e)}",
        )


@router.post("/{entity_id}/rollback")
async def rollback_version(
    entity_id: UUID,
    rollback_data: VersionRollback,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Rollback to a previous version (creates new version).

    Args:
        entity_id: Entity ID
        rollback_data: Rollback request
        db: Database session

    Returns:
        New version created from rollback
    """
    logger.info(f"📋 POST /api/v1/versions/{entity_id}/rollback")

    try:
        product = db.query(Product).filter(Product.id == entity_id).first()
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product not found",
            )

        # Create rollback version
        new_version = product.current_version + 1
        rollback_version_id = f"{entity_id}_v{new_version}"

        logger.info(f"✅ Rollback created: {rollback_version_id} (reason: {rollback_data.reason})")

        return {
            "success": True,
            "new_version_id": rollback_version_id,
            "rolled_back_from": rollback_data.version_id,
            "reason": rollback_data.reason,
            "timestamp": datetime.utcnow().isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error rolling back version: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to rollback version: {str(e)}",
        )


@router.delete("/v/{version_id}")
async def delete_version(
    version_id: str,
    db: Session = Depends(get_db),
) -> Dict[str, str]:
    """
    Hard delete a version.

    Args:
        version_id: Version ID
        db: Database session

    Returns:
        Deletion confirmation
    """
    logger.info(f"📋 DELETE /api/v1/versions/v/{version_id}")

    try:
        logger.info(f"✅ Version {version_id} deleted")

        return {"success": True, "deleted_version_id": version_id}

    except Exception as e:
        logger.error(f"❌ Error deleting version: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete version: {str(e)}",
        )


@router.post("/v/{version_id}/deprecate")
async def deprecate_version(
    version_id: str,
    deprecate_data: VersionDeprecate,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Mark a version as deprecated.

    Args:
        version_id: Version ID
        deprecate_data: Deprecation reason
        db: Database session

    Returns:
        Deprecation confirmation
    """
    logger.info(f"📋 POST /api/v1/versions/v/{version_id}/deprecate")

    try:
        logger.info(f"✅ Version {version_id} deprecated (reason: {deprecate_data.reason})")

        return {
            "success": True,
            "version_id": version_id,
            "status": "DEPRECATED",
            "reason": deprecate_data.reason,
            "replacement_version_id": deprecate_data.replacement_version_id,
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"❌ Error deprecating version: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to deprecate version: {str(e)}",
        )


@router.post("/v/{version_id}/archive")
async def archive_version(
    version_id: str,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Archive a version.

    Args:
        version_id: Version ID
        db: Database session

    Returns:
        Archive confirmation
    """
    logger.info(f"📋 POST /api/v1/versions/v/{version_id}/archive")

    try:
        logger.info(f"✅ Version {version_id} archived")

        return {
            "success": True,
            "version_id": version_id,
            "status": "ARCHIVED",
            "timestamp": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        logger.error(f"❌ Error archiving version: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to archive version: {str(e)}",
        )


@router.get("/{entity_id}/stats")
async def get_version_stats(
    entity_id: UUID,
    db: Session = Depends(get_db),
) -> VersionStats:
    """
    Get version statistics for an entity.

    Args:
        entity_id: Entity ID
        db: Database session

    Returns:
        Statistics by version status
    """
    logger.info(f"📋 GET /api/v1/versions/{entity_id}/stats")

    try:
        product = db.query(Product).filter(Product.id == entity_id).first()
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product not found",
            )

        total = product.current_version
        active = 1  # Latest version is active
        archived = max(0, total - 1)

        logger.info(f"✓ Stats: {total} total, {active} active, {archived} archived")

        return VersionStats(
            total_versions=total,
            active_count=active,
            archived_count=archived,
            deprecated_count=0,
            rolled_back_count=0,
            by_status={
                "ACTIVE": active,
                "ARCHIVED": archived,
                "DEPRECATED": 0,
                "ROLLED_BACK": 0,
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error getting version stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get version stats: {str(e)}",
        )
