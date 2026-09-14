"""
Workspace access control and scoping utilities.
"""

from typing import List, Optional
from uuid import UUID

from fastapi import HTTPException, Request, status
from primedata.db.models import Product, Workspace, WorkspaceMember, WorkspaceRole
from primedata.utils.log_utils import get_logger
from sqlalchemy.orm import Session
from .exceptions import (
    WorkspaceAccessDeniedError,
    WorkspaceNotFoundError,
    ProductAccessDeniedError,
    ProductNotFoundError,
    AuthenticationError,
)

logger = get_logger(__name__)


def allowed_workspaces(request: Request, db: Optional[Session] = None) -> List[UUID]:
    """Get list of workspace IDs that the current user has access to.

    :param request: FastAPI request object with user state.
    :param db: Optional database session to query actual workspace memberships.
    :return: List of workspace UUIDs the user can access.
    :raises AuthenticationError: If user is not authenticated.
    """
    # ENTRY LOG
    logger.info(f"🔐 [allowed_workspaces] ENTRY | db_provided={db is not None}")

    # CRITICAL: Ensure request is not None - this prevents security bypass
    if request is None:
        logger.error("❌ Request object is None - CRITICAL SECURITY ERROR")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Request object is missing. This is a server configuration error.",
        )

    # Extract user info from headers
    user_id_header = request.headers.get("x-user-id")
    user_email_header = request.headers.get("x-user-email")
    user_name_header = request.headers.get("x-user-name")

    logger.debug(f"📋 Header extraction | user_id={user_id_header}, email={user_email_header}, name={user_name_header}")

    # If headers are provided, use them directly (no UUID conversion)
    if user_id_header and user_email_header:
        logger.info(f"✓ Header-based authentication | user_id={user_id_header}")
        # Store user info as-is, no UUID conversion
        request.state.user = {
            "sub": user_id_header,  # Use as-is, no conversion
            "email": user_email_header,
            "name": user_name_header or "Unknown User",
        }

    # Fallback to request.state.user if set by middleware
    if not hasattr(request.state, "user") or not request.state.user:
        logger.warning("⚠️ No user info in headers or request.state, checking db fallback")
        # Development mode: return all workspaces if not authenticated
        if db:
            # Return all workspaces for unauthenticated requests
            logger.debug("📋 Querying all workspaces (unauthenticated mode)")
            all_workspaces = db.query(Workspace).all()
            workspace_count = len(all_workspaces)
            logger.info(f"✅ Retrieved {workspace_count} workspaces (unauthenticated)")
            return [w.id for w in all_workspaces]
        logger.warning("❌ No authentication available and no db fallback")
        return []

    user_id_str = request.state.user["sub"]

    # If database session is provided, query workspace memberships
    # Use user_id_str directly without any UUID conversion
    if db:
        try:
            logger.debug(f"📋 Querying memberships for user_id={user_id_str}")
            # Try to use user_id_str directly in the query
            # The database will handle the type conversion if needed
            memberships = db.query(WorkspaceMember).filter(WorkspaceMember.user_id == user_id_str).all()
            membership_count = len(memberships)
            logger.info(f"💾 Found {membership_count} workspace memberships for user {user_id_str}")
            workspace_ids = [m.workspace_id for m in memberships]
            logger.info(f"✅ [allowed_workspaces] EXIT | workspace_count={membership_count} | workspaces={workspace_ids}")
            return workspace_ids
        except Exception as e:
            logger.error(f"❌ Error querying workspace memberships for user {user_id_str}: {e}", exc_info=True)
            # Return empty list on error
            return []

    # Fallback: use workspaces from user token/state (only when no DB session is provided)
    logger.debug("📋 Fallback: using workspaces from token/state")
    user_workspaces = request.state.user.get("workspaces", [])
    logger.debug(f"✓ Token workspaces: {user_workspaces}")

    # Handle both string and UUID workspace IDs
    result = []
    for ws_id in user_workspaces:
        if isinstance(ws_id, str):
            try:
                result.append(UUID(ws_id))
            except ValueError:
                # Skip invalid UUID strings
                logger.debug(f"⚠️ Skipping invalid UUID string: {ws_id}")
                continue
        elif isinstance(ws_id, UUID):
            result.append(ws_id)

    logger.info(f"✅ [allowed_workspaces] EXIT | workspace_count={len(result)} | workspaces={result}")
    return result


def ensure_workspace_access(db: Session, request: Request, workspace_id: UUID, roles: Optional[List[str]] = None) -> Workspace:
    """Ensure the current user has access to the specified workspace.

    :param db: Database session.
    :param request: FastAPI request object with user state.
    :param workspace_id: UUID of the workspace to check access for.
    :param roles: Optional list of required roles (if None, any role is sufficient).
    :return: Workspace object if access is granted.
    :raises AuthenticationError: If user is not authenticated.
    :raises WorkspaceNotFoundError: If workspace does not exist.
    :raises WorkspaceAccessDeniedError: If user lacks access or required role.
    """
    # ENTRY LOG
    logger.info(f"🔐 [ensure_workspace_access] ENTRY | workspace_id={workspace_id} | required_roles={roles}")

    # CRITICAL: Ensure request is not None - this prevents security bypass
    if request is None:
        logger.error("❌ Request object is None - CRITICAL SECURITY ERROR")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Request object is missing. This is a server configuration error.",
        )

    # Extract user info from headers first
    user_id_header = request.headers.get("x-user-id")
    user_email_header = request.headers.get("x-user-email")

    logger.debug(f"📋 Header extraction | user_id={user_id_header}, email={user_email_header}")

    if user_id_header and user_email_header:
        # Store in request.state for consistency (use as-is, no conversion)
        logger.debug("✓ Using header-based authentication")
        request.state.user = {
            "sub": user_id_header,
            "email": user_email_header,
            "name": request.headers.get("x-user-name", "Unknown User"),
        }
    elif not hasattr(request.state, "user") or not request.state.user:
        logger.error(f"❌ User not authenticated for workspace_id={workspace_id}")
        raise AuthenticationError("User not authenticated")

    user_id_str = request.state.user["sub"]
    logger.debug(f"✓ Authenticated user_id={user_id_str}")

    # Get workspace
    logger.debug(f"📋 Querying workspace | workspace_id={workspace_id}")
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()

    if not workspace:
        logger.error(f"❌ Workspace not found | workspace_id={workspace_id}")
        raise WorkspaceNotFoundError()

    logger.debug(f"✓ Workspace found | name={workspace.name}")

    # Check database membership using user_id_str directly
    logger.debug(f"📋 Checking workspace membership | user_id={user_id_str}")
    try:
        membership = (
            db.query(WorkspaceMember)
            .filter(WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == user_id_str)
            .first()
        )
        if membership:
            logger.debug(f"💾 Found membership record | role={membership.role.value}")
    except Exception as e:
        logger.error(f"❌ Error checking workspace membership for user {user_id_str}: {e}", exc_info=True)
        membership = None

    if not membership:
        # Check if workspace is in allowed list (fallback for non-database cases)
        logger.debug("📋 No membership found, checking allowed_workspaces fallback")
        allowed_workspace_ids = allowed_workspaces(request, db)
        logger.debug(f"✓ Allowed workspaces: {allowed_workspace_ids}")
        if workspace_id not in allowed_workspace_ids:
            logger.error(f"❌ Workspace access denied | workspace_id={workspace_id} | user_id={user_id_str}")
            raise WorkspaceAccessDeniedError()
        logger.info(f"✅ Access granted via allowed_workspaces fallback")

    # If specific roles are required, check user's role in this workspace
    if roles and membership:
        logger.debug(f"📋 Checking required roles | required={roles} | user_role={membership.role.value}")
        if membership.role.value not in roles:
            logger.error(f"❌ Required role not found | required={roles} | current={membership.role.value}")
            raise WorkspaceAccessDeniedError(
                message=f"Required role not found. Required: {roles}, Current: {membership.role.value}"
            )
        logger.info(f"✅ User has required role | role={membership.role.value}")

    logger.info(f"✅ [ensure_workspace_access] EXIT | workspace_id={workspace_id} | user_id={user_id_str} | access=GRANTED")
    return workspace


def ensure_product_access(db: Session, request: Request, product_id: UUID) -> Product:
    """Ensure the current user has access to the specified product.

    :param db: Database session.
    :param request: FastAPI request object with user state.
    :param product_id: UUID of the product to check access for.
    :return: Product object if access is granted.
    :raises AuthenticationError: If user is not authenticated.
    :raises ProductNotFoundError: If product does not exist.
    :raises ProductAccessDeniedError: If user lacks access to the product's workspace.
    """
    # ENTRY LOG
    logger.info(f"🔐 [ensure_product_access] ENTRY | product_id={product_id}")

    # CRITICAL: Ensure request is not None - this prevents security bypass
    if request is None:
        logger.error("❌ Request object is None - CRITICAL SECURITY ERROR")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Request object is missing. This is a server configuration error.",
        )

    # Extract user info from headers first
    user_id_header = request.headers.get("x-user-id")
    user_email_header = request.headers.get("x-user-email")

    logger.debug(f"📋 Header extraction | user_id={user_id_header}, email={user_email_header}")

    if user_id_header and user_email_header:
        # Store in request.state for consistency (use as-is, no conversion)
        logger.debug("✓ Using header-based authentication")
        request.state.user = {
            "sub": user_id_header,
            "email": user_email_header,
            "name": request.headers.get("x-user-name", "Unknown User"),
        }
    elif not hasattr(request.state, "user") or not request.state.user:
        logger.error(f"❌ User not authenticated for product_id={product_id}")
        raise AuthenticationError("User not authenticated")

    user_id_str = request.state.user["sub"]
    logger.debug(f"✓ Authenticated user_id={user_id_str}")

    # Get the product
    logger.debug(f"📋 Querying product | product_id={product_id}")
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        logger.error(f"❌ Product not found | product_id={product_id}")
        raise ProductNotFoundError()

    logger.debug(f"✓ Product found | workspace_id={product.workspace_id}")

    # Check workspace access
    logger.debug(f"📋 Verifying workspace access for product workspace")
    try:
        ensure_workspace_access(db, request, product.workspace_id)
        logger.info(f"✅ Workspace access verified")
    except WorkspaceAccessDeniedError:
        logger.error(f"❌ Workspace access denied for product | product_id={product_id} | workspace_id={product.workspace_id}")
        raise ProductAccessDeniedError()

    logger.info(f"✅ [ensure_product_access] EXIT | product_id={product_id} | user_id={user_id_str} | access=GRANTED")
    return product
