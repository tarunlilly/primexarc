"""
Authentication API router — Bouncer (CATS ingress) integration.

Bouncer sits in front of this service and enforces Azure AD authentication.
After login it injects user identity headers into every forwarded request
(configured in infra/deploy.yaml lilly.com/user_info_headers annotation):
  - X-WEBAUTH-EMAIL  — authenticated user's email / UPN
  - X-USER-NAME      — display name
  - X-UPN            — User Principal Name

All endpoints resolve the current user via get_current_user() which reads
these headers. If headers are absent (local dev / internal ingress) the
default user (primedata@lilly.com) is used as a fallback.
"""

import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, status, Depends, Request
from primedata.db.database import get_db
from primedata.db.models import User, Workspace, WorkspaceMember, WorkspaceRole
from pydantic import BaseModel
from sqlalchemy.orm import Session

from primedata.utils.logger import get_logger
logger = get_logger(__name__)

router = APIRouter()

# Default user configuration (fallback for local dev / internal ingress)
# DEFAULT_USER_EMAIL = "primedata@lilly.com"
# DEFAULT_USER_NAME = "PrimeData User"


class UserResponse(BaseModel):
    """User response model."""

    id: str
    email: str
    name: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    timezone: Optional[str] = None
    roles: List[str]
    picture_url: Optional[str] = None


class WorkspaceResponse(BaseModel):
    """Workspace response model."""

    id: str
    name: str
    role: str
    created_at: str


class WorkspaceCreateResponse(BaseModel):
    """Workspace creation response model."""

    id: str
    name: str
    created_at: str


class UserProfileResponse(BaseModel):
    """User profile response model."""

    id: str
    email: str
    name: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    timezone: Optional[str] = None
    picture_url: Optional[str] = None


class UserProfileUpdateRequest(BaseModel):
    """User profile update request model."""

    first_name: Optional[str] = None
    last_name: Optional[str] = None
    timezone: Optional[str] = None


def get_or_create_user_by_email(db: Session, email: str, name: str, user_id: str = None) -> User:
    """Get or create a user by email. Creates workspace on first login."""
    logger.debug(f"📋 get_or_create_user_by_email: Starting lookup for email={email}, user_id={user_id}")

    user = db.query(User).filter(User.email == email).first()

    if not user:
        # Generate user_id if not provided (from header)
        if not user_id:
            import uuid
            user_id = str(uuid.uuid4())
            logger.debug(f"   🔑 Generated new user_id: {user_id}")

        logger.info(f"📝 Creating new user: email={email}, user_id={user_id}, name={name}")

        # Handle None name
        logger.debug(f"   📥 Processing name parameter: name={name}, type={type(name).__name__}")
        safe_name = name if name else "User"
        if safe_name != name:
            logger.warning(f"   ⚠️  Name was None, using fallback: '{safe_name}'")

        first_name = safe_name.split(" ")[0] if " " in safe_name else safe_name
        last_name = safe_name.split(" ", 1)[1] if " " in safe_name else ""
        logger.debug(f"   ✓ Parsed name: first_name='{first_name}', last_name='{last_name}'")

        user = User(
            id=user_id,  # Use provided user_id from header or generate UUID
            email=email,
            name=safe_name,
            first_name=first_name,
            last_name=last_name,
            password_hash=None,
            auth_provider="bouncer",  # Bouncer authentication provider
            roles=["admin"],
            email_verified=True,
        )

        logger.debug(f"   📊 User object created: id={user.id}, email={user.email}")
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info(f"✅ User persisted to database: {user.id} ({user.email})")

        # Create workspace for the user
        logger.debug(f"   🏢 Creating workspace for user {user.email}")
        workspace = Workspace(name=f"{user.name}'s Workspace")
        db.add(workspace)
        db.commit()
        db.refresh(workspace)
        logger.info(f"✅ Workspace created: {workspace.id} ({workspace.name})")

        # Add user to workspace as OWNER
        logger.debug(f"   👤 Adding user as workspace OWNER")
        membership = WorkspaceMember(
            workspace_id=workspace.id, user_id=user.id, role=WorkspaceRole.OWNER
        )
        db.add(membership)
        db.commit()
        logger.info(f"✅ User added to workspace as OWNER: user_id={user.id}, workspace_id={workspace.id}")

        logger.info(f"🎉 User onboarding complete: {user.email} ({user.id})")

    else:
        logger.debug(f"✓ User already exists: email={email}, user_id={user.id}")
        logger.info(f"📌 Returning existing user: {user.email}")

    return user


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """
    FastAPI dependency — resolves the current user from Bouncer-injected headers.

    Bouncer injects X-WEBAUTH-EMAIL and X-USER-NAME on every authenticated request
    (see infra/deploy.yaml lilly.com/user_info_headers). Falls back to the default
    user when headers are absent (local dev / internal ingress without Bouncer).
    """
    # Get user ID from header (x-user-id takes priority)
    user_id = request.headers.get("x-user-id")

    email = (
        request.headers.get("x-user-email")
        or request.headers.get("x-upn")
    )
    name = request.headers.get("x-user-name")

    # Log header values for debugging
    logger.debug(f"Auth headers: x-user-id={user_id}, x-user-email={request.headers.get('x-user-email')}, x-upn={request.headers.get('x-upn')}, x-user-name={name}")

    # Validate required fields
    if not email:
        logger.error("❌ Missing required header: email (x-user-email or x-upn)")
        raise ValueError("Missing email in authentication headers")

    if not user_id:
        logger.error("❌ Missing required header: x-user-id")
        raise ValueError("Missing user_id in authentication headers")

    if not name:
        logger.warning(f"⚠️  Missing x-user-name header for email={email}, will use default")
        name = email.split("@")[0]  # Use part before @ as fallback

    logger.info(f"✅ VALIDATION PASSED:")
    logger.info(f"   📧 Email: {email}")
    logger.info(f"   🔑 User ID: {user_id}")
    logger.info(f"   👤 Name: {name}")

    logger.debug(f"   → Proceeding to get_or_create_user_by_email()")

    return get_or_create_user_by_email(db, email=email, name=name, user_id=user_id)


@router.get("/api/v1/users/me", response_model=UserResponse)
async def get_current_user_info(user: User = Depends(get_current_user)):
    """
    Get current user information.

    Returns the authenticated user resolved from Bouncer-injected headers.
    """
    logger.info(f"🔐 get_current_user_info: ENTRY user_id={user.id}, email={user.email}")

    try:
        logger.debug(f"   📋 Processing roles, type={type(user.roles).__name__}")
        roles_list = []
        if user.roles:
            if isinstance(user.roles, dict):
                logger.debug(f"   📋 Roles is dict with {len(user.roles)} groups")
                for role_group in user.roles.values():
                    if isinstance(role_group, list):
                        roles_list.extend(role_group)
                    elif isinstance(role_group, str):
                        roles_list.append(role_group)
            elif isinstance(user.roles, list):
                roles_list = user.roles
                logger.debug(f"   📋 Roles is list with {len(roles_list)} items")
            elif isinstance(user.roles, str):
                roles_list = [user.roles]
                logger.debug(f"   📋 Roles is string: {user.roles}")

        logger.debug(f"   ✓ Roles processed: {roles_list}")

        response = UserResponse(
            id=str(user.id),
            email=user.email,
            name=user.name,
            first_name=user.first_name,
            last_name=user.last_name,
            timezone=user.timezone,
            roles=roles_list,
            picture_url=user.picture_url,
        )

        logger.info(f"✅ get_current_user_info: EXIT user_id={user.id}, roles_count={len(roles_list)}")
        return response

    except Exception as e:
        logger.error(f"❌ get_current_user_info: FAILED user_id={user.id}, error={str(e)}", exc_info=True)
        raise


@router.get("/api/v1/workspaces/", response_model=List[WorkspaceResponse])
async def get_user_workspaces(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Get the current user's workspaces.
    """
    logger.info(f"🔐 get_user_workspaces: ENTRY user_id={user.id}, email={user.email}")

    try:
        logger.debug(f"   📋 Querying workspace memberships for user_id={user.id}")

        memberships = (
            db.query(WorkspaceMember, Workspace)
            .join(Workspace, WorkspaceMember.workspace_id == Workspace.id)
            .filter(WorkspaceMember.user_id == user.id)
            .all()
        )

        logger.debug(f"   💾 Retrieved {len(memberships)} workspace memberships")

        workspaces = []
        for idx, (membership, workspace) in enumerate(memberships, 1):
            logger.debug(f"   ✓ [{idx}] workspace_id={workspace.id}, name='{workspace.name}', role={membership.role.value}")

            workspaces.append(
                WorkspaceResponse(
                    id=str(workspace.id),
                    name=workspace.name,
                    role=membership.role.value,
                    created_at=workspace.created_at.isoformat(),
                )
            )

        logger.info(f"✅ get_user_workspaces: EXIT user_id={user.id}, workspaces_count={len(workspaces)}")
        return workspaces

    except Exception as e:
        logger.error(f"❌ get_user_workspaces: FAILED user_id={user.id}, error={str(e)}", exc_info=True)
        raise


@router.post("/api/v1/workspaces/", response_model=WorkspaceCreateResponse)
async def create_workspace(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Create a new workspace for the current user.
    """
    logger.info(f"🔐 create_workspace: ENTRY user_id={user.id}, user_name='{user.name}'")

    try:
        logger.debug(f"   📋 Checking for existing workspace memberships")

        # Check if user already has workspaces
        existing_memberships = db.query(WorkspaceMember).filter(
            WorkspaceMember.user_id == user.id
        ).all()

        logger.debug(f"   💾 Found {len(existing_memberships)} existing memberships")

        if existing_memberships:
            logger.debug(f"   ✓ User has existing workspaces, returning first one")
            # Return the first existing workspace
            workspace = db.query(Workspace).filter(
                Workspace.id == existing_memberships[0].workspace_id
            ).first()

            if workspace:
                logger.info(f"✅ create_workspace: EXIT returning existing workspace_id={workspace.id}")
                return WorkspaceCreateResponse(
                    id=str(workspace.id),
                    name=workspace.name,
                    created_at=workspace.created_at.isoformat(),
                )

        # Create new workspace
        logger.debug(f"   📋 Creating new workspace for user_id={user.id}")
        workspace_name = f"{user.name}'s Workspace"
        workspace = Workspace(name=workspace_name)
        db.add(workspace)
        db.commit()
        db.refresh(workspace)

        logger.debug(f"   💾 Workspace persisted: workspace_id={workspace.id}, name='{workspace_name}'")

        # Add user as owner
        logger.debug(f"   📋 Adding user as workspace OWNER")
        membership = WorkspaceMember(
            workspace_id=workspace.id, user_id=user.id, role=WorkspaceRole.OWNER
        )
        db.add(membership)
        db.commit()

        logger.info(f"✅ create_workspace: EXIT created workspace_id={workspace.id}, user_id={user.id}")

        return WorkspaceCreateResponse(
            id=str(workspace.id),
            name=workspace.name,
            created_at=workspace.created_at.isoformat(),
        )

    except Exception as e:
        logger.error(f"❌ create_workspace: FAILED user_id={user.id}, error={str(e)}", exc_info=True)
        raise


@router.put("/api/v1/user/profile", response_model=UserProfileResponse)
async def update_user_profile(
    request_body: UserProfileUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Update the current user's profile information.
    """
    logger.info(f"🔐 update_user_profile: ENTRY user_id={user.id}, email={user.email}")
    logger.debug(f"   📋 Request body: first_name={request_body.first_name}, last_name={request_body.last_name}, timezone={request_body.timezone}")

    try:
        changes_made = []

        # Update user profile fields
        if request_body.first_name is not None:
            old_val = user.first_name
            user.first_name = request_body.first_name
            logger.debug(f"   ✓ first_name: '{old_val}' -> '{user.first_name}'")
            changes_made.append("first_name")

        if request_body.last_name is not None:
            old_val = user.last_name
            user.last_name = request_body.last_name
            logger.debug(f"   ✓ last_name: '{old_val}' -> '{user.last_name}'")
            changes_made.append("last_name")

        if request_body.timezone is not None:
            old_val = user.timezone
            user.timezone = request_body.timezone
            logger.debug(f"   ✓ timezone: '{old_val}' -> '{user.timezone}'")
            changes_made.append("timezone")

        # Update the name field if first_name or last_name changed
        if request_body.first_name is not None or request_body.last_name is not None:
            logger.debug(f"   📋 Recomputing composite name field")
            first_name = (
                request_body.first_name if request_body.first_name is not None else user.first_name
            )
            last_name = (
                request_body.last_name if request_body.last_name is not None else user.last_name
            )

            old_name = user.name
            if first_name and last_name:
                user.name = f"{first_name} {last_name}"
            elif first_name:
                user.name = first_name
            elif last_name:
                user.name = last_name

            logger.debug(f"   ✓ name: '{old_name}' -> '{user.name}'")
            changes_made.append("name")

        logger.debug(f"   💾 Persisting {len(changes_made)} changes: {changes_made}")
        db.commit()
        db.refresh(user)
        logger.debug(f"   ✓ Database commit successful")

        response = UserProfileResponse(
            id=str(user.id),
            email=user.email,
            name=user.name,
            first_name=user.first_name,
            last_name=user.last_name,
            timezone=user.timezone,
            picture_url=user.picture_url,
        )

        logger.info(f"✅ update_user_profile: EXIT user_id={user.id}, changes_count={len(changes_made)}")
        return response

    except Exception as e:
        logger.error(f"❌ update_user_profile: FAILED user_id={user.id}, error={str(e)}", exc_info=True)
        raise