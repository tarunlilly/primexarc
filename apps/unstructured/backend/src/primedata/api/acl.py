"""
ACL API endpoints for PrimeData.

Provides CRUD operations for Access Control Lists.
"""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from primedata.core.scope import allowed_workspaces, ensure_product_access
from primedata.db.database import get_db
from primedata.db.models import ACL, ACLAccessType
from primedata.services.acl import create_acl as create_acl_service
from primedata.services.acl import delete_acls as delete_acls_service
from primedata.services.acl import (
    get_acls_for_product,
    get_acls_for_user,
)
from pydantic import BaseModel
from sqlalchemy.orm import Session

from primedata.utils.logger import get_logger
logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/acl", tags=["access control"])


class ACLCreateRequest(BaseModel):
    """Request model for creating an ACL entry."""

    user_id: str
    product_id: UUID
    access_type: ACLAccessType
    index_scope: Optional[str] = None
    doc_scope: Optional[str] = None
    field_scope: Optional[str] = None


class ACLResponse(BaseModel):
    """Response model for ACL entry."""

    id: UUID
    user_id: str
    product_id: UUID
    access_type: ACLAccessType
    index_scope: Optional[str]
    doc_scope: Optional[str]
    field_scope: Optional[str]
    created_at: str

    class Config:
        from_attributes = True


@router.post("/", response_model=ACLResponse, status_code=status.HTTP_201_CREATED)
async def create_acl(
    entry: ACLCreateRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Create an ACL entry.

    Requires access to the product being ACL'd.
    """
    logger.info(f"🔑 create_acl: ENTRY user_id={entry.user_id}, product_id={entry.product_id}, access_type={entry.access_type}")

    try:
        logger.debug(f"   📋 Verifying product access")
        # Ensure user has access to the product
        product = ensure_product_access(db, request, entry.product_id)

        if not product:
            logger.warning(f"❌ Product not found or access denied: product_id={entry.product_id}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found or access denied")

        logger.debug(f"   ✓ Product access verified: product_id={product.id}")

        logger.debug(f"   📋 Creating ACL with service layer")
        # Create ACL
        acl = create_acl_service(
            db=db,
            user_id=entry.user_id,
            product_id=entry.product_id,
            access_type=entry.access_type,
            index_scope=entry.index_scope,
            doc_scope=entry.doc_scope,
            field_scope=entry.field_scope,
        )

        logger.debug(f"   ✓ ACL created: id={acl.id}")

        response = ACLResponse(
            id=acl.id,
            user_id=acl.user_id,
            product_id=acl.product_id,
            access_type=acl.access_type,
            index_scope=acl.index_scope,
            doc_scope=acl.doc_scope,
            field_scope=acl.field_scope,
            created_at=acl.created_at.isoformat() if acl.created_at else "",
        )

        logger.info(f"✅ create_acl: EXIT acl_id={acl.id}, user_id={entry.user_id}, product_id={entry.product_id}, access_type={entry.access_type}")
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ create_acl: FAILED user_id={entry.user_id}, product_id={entry.product_id}, error={str(e)}", exc_info=True)
        raise


@router.get("/", response_model=List[ACLResponse])
async def list_acls(
    request: Request,
    user_id: Optional[str] = None,
    product_id: Optional[UUID] = None,
    db: Session = Depends(get_db)
):
    """
    List ACL entries, optionally filtered by user_id or product_id.

    If product_id is provided, ensures user has access to that product.
    """
    logger.info(f"🔑 list_acls: ENTRY user_id={user_id}, product_id={product_id}")

    try:
        logger.debug(f"   📋 Validating request parameters")

        # If product_id is provided, ensure access
        if product_id:
            logger.debug(f"   📋 Verifying product access: product_id={product_id}")
            product = ensure_product_access(db, request, product_id)

            if not product:
                logger.warning(f"❌ Product not found or access denied: product_id={product_id}")
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found or access denied")

            logger.debug(f"   ✓ Product access verified")

        logger.debug(f"   📋 Querying ACLs: user_id={user_id}, product_id={product_id}")

        # Get ACLs with workspace filtering for security
        if user_id:
            logger.debug(f"   📋 Fetching ACLs for user_id={user_id}")
            acls = get_acls_for_user(db, user_id, product_id)
            logger.debug(f"   💾 Retrieved {len(acls)} ACLs for user")

        elif product_id:
            logger.debug(f"   📋 Fetching ACLs for product_id={product_id}")
            acls = get_acls_for_product(db, product_id, None)
            logger.debug(f"   💾 Retrieved {len(acls)} ACLs for product")

        else:
            logger.debug(f"   📋 Fetching ACLs for all accessible workspaces")
            # List ACLs only for products in user's accessible workspaces
            # This prevents users from seeing ACLs for products they don't have access to
            from primedata.db.models import Product

            allowed_workspace_ids = allowed_workspaces(request, db)
            logger.debug(f"   ✓ User has access to {len(allowed_workspace_ids)} workspaces")

            # Get product IDs from accessible workspaces
            accessible_products = db.query(Product.id).filter(Product.workspace_id.in_(allowed_workspace_ids)).subquery()
            acls = db.query(ACL).filter(ACL.product_id.in_(accessible_products)).all()
            logger.debug(f"   💾 Retrieved {len(acls)} ACLs across accessible workspaces")

        # Build response list
        result = [
            ACLResponse(
                id=acl.id,
                user_id=acl.user_id,
                product_id=acl.product_id,
                access_type=acl.access_type,
                index_scope=acl.index_scope,
                doc_scope=acl.doc_scope,
                field_scope=acl.field_scope,
                created_at=acl.created_at.isoformat() if acl.created_at else "",
            )
            for acl in acls
        ]

        logger.info(f"✅ list_acls: EXIT acls_count={len(result)}, user_id={user_id}, product_id={product_id}")
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ list_acls: FAILED user_id={user_id}, product_id={product_id}, error={str(e)}", exc_info=True)
        raise


@router.delete("/", status_code=status.HTTP_200_OK)
async def delete_acls(
    request: Request,
    acl_id: Optional[UUID] = None,
    user_id: Optional[str] = None,
    product_id: Optional[UUID] = None,
    db: Session = Depends(get_db)
):
    """
    Delete ACL entries matching the given criteria.

    If product_id is provided, ensures user has access to that product.
    """
    logger.info(f"🔑 delete_acls: ENTRY acl_id={acl_id}, user_id={user_id}, product_id={product_id}")

    try:
        logger.debug(f"   📋 Validating delete criteria")

        # If product_id is provided, ensure access
        if product_id:
            logger.debug(f"   📋 Verifying product access: product_id={product_id}")
            product = ensure_product_access(db, request, product_id)

            if not product:
                logger.warning(f"❌ Product not found or access denied: product_id={product_id}")
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found or access denied")

            logger.debug(f"   ✓ Product access verified")

        logger.debug(f"   📋 Calling delete service: acl_id={acl_id}, user_id={user_id}, product_id={product_id}")
        # Delete ACLs
        count = delete_acls_service(db, acl_id, user_id, product_id)

        logger.debug(f"   💾 Deleted {count} ACL entries")
        logger.info(f"✅ delete_acls: EXIT deleted_count={count}")

        return {"deleted": count}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ delete_acls: FAILED acl_id={acl_id}, user_id={user_id}, product_id={product_id}, error={str(e)}", exc_info=True)
        raise
