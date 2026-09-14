"""
Settings API router for managing workspace and user settings.
"""

from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from primedata.core.scope import ensure_workspace_access
from primedata.db.database import get_db
from primedata.db.models import Workspace
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

router = APIRouter(prefix="/api/v1/settings", tags=["Settings"])

from primedata.utils.logger import get_logger
logger = get_logger(__name__)

class SettingsResponse(BaseModel):
    """Settings response model."""

    workspace_id: str
    openai_api_key: Optional[str] = None  # Masked key (shows only last 4 chars)
    openai_api_key_configured: bool = False


class SettingsUpdateRequest(BaseModel):
    """Settings update request model."""

    openai_api_key: Optional[str] = None


@router.get("/workspace/{workspace_id}", response_model=SettingsResponse)
async def get_workspace_settings(
    workspace_id: UUID, request: Request, db: Session = Depends(get_db)
):
    """
    Get workspace settings.

    Returns settings with masked API keys for security.
    """
    logger.info(f"⚙️ get_workspace_settings: ENTRY workspace_id={workspace_id}")

    try:
        logger.debug(f"   📋 Verifying workspace access")
        # Ensure user has access to the workspace
        ensure_workspace_access(db, request, workspace_id)
        logger.debug(f"   ✓ Workspace access verified")

        logger.debug(f"   📋 Querying workspace: workspace_id={workspace_id}")
        workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()

        if not workspace:
            logger.warning(f"❌ Workspace not found: workspace_id={workspace_id}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

        logger.debug(f"   ✓ Workspace found: name='{workspace.name}'")

        # Get settings from workspace.settings JSON column
        settings = workspace.settings or {}
        openai_key = settings.get("openai_api_key")

        logger.debug(f"   📋 Processing settings: {len(settings)} config entries")

        # Mask the API key for display (show only last 4 characters)
        masked_key = None
        if openai_key:
            masked_key = f"sk-...{openai_key[-4:]}" if len(openai_key) > 4 else "sk-****"
            logger.debug(f"   ✓ OpenAI API key configured and masked")
        else:
            logger.debug(f"   ✓ No OpenAI API key configured")

        response = SettingsResponse(
            workspace_id=str(workspace_id), openai_api_key=masked_key, openai_api_key_configured=bool(openai_key)
        )

        logger.info(f"✅ get_workspace_settings: EXIT workspace_id={workspace_id}, openai_configured={bool(openai_key)}")
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ get_workspace_settings: FAILED workspace_id={workspace_id}, error={str(e)}", exc_info=True)
        raise


@router.patch("/workspace/{workspace_id}", response_model=SettingsResponse)
async def update_workspace_settings(
    workspace_id: UUID,
    request_body: SettingsUpdateRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Update workspace settings.

    Stores API keys securely in the workspace settings JSON column.
    """
    logger.info(f"⚙️ update_workspace_settings: ENTRY workspace_id={workspace_id}, has_openai_key={request_body.openai_api_key is not None}")

    try:
        logger.debug(f"   📋 Verifying workspace access")
        # Ensure user has access to the workspace
        ensure_workspace_access(db, request, workspace_id)
        logger.debug(f"   ✓ Workspace access verified")

        logger.debug(f"   📋 Querying workspace: workspace_id={workspace_id}")
        workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()

        if not workspace:
            logger.warning(f"❌ Workspace not found: workspace_id={workspace_id}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

        logger.debug(f"   ✓ Workspace found: name='{workspace.name}'")

        # Initialize settings if it doesn't exist
        if workspace.settings is None:
            workspace.settings = {}
            logger.debug(f"   📋 Initializing empty settings dict")

        # Update OpenAI API key if provided
        if request_body.openai_api_key is not None:
            logger.debug(f"   📋 Processing OpenAI API key update")

            # If empty string, remove the key
            if request_body.openai_api_key.strip() == "":
                logger.debug(f"   ✓ Empty key provided, removing OpenAI API key from settings")
                workspace.settings.pop("openai_api_key", None)
            else:
                logger.debug(f"   📋 Validating OpenAI API key format")
                # Validate that it starts with sk- (basic validation)
                if not request_body.openai_api_key.startswith("sk-"):
                    logger.warning(f"❌ Invalid OpenAI API key format: does not start with 'sk-'")
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Invalid OpenAI API key format. OpenAI keys should start with 'sk-'",
                    )

                logger.debug(f"   ✓ API key format validated, storing in settings")
                workspace.settings["openai_api_key"] = request_body.openai_api_key.strip()

            # Ensure SQLAlchemy persists JSON changes
            flag_modified(workspace, "settings")
            logger.debug(f"   ✓ Settings marked as modified")

        logger.debug(f"   💾 Persisting settings changes")
        db.commit()
        db.refresh(workspace)
        logger.debug(f"   ✓ Database commit successful")

        # Get updated settings
        settings = workspace.settings or {}
        openai_key = settings.get("openai_api_key")

        # Mask the API key for response
        masked_key = None
        if openai_key:
            masked_key = f"sk-...{openai_key[-4:]}" if len(openai_key) > 4 else "sk-****"
            logger.debug(f"   ✓ OpenAI API key now configured and masked")
        else:
            logger.debug(f"   ✓ OpenAI API key not configured")

        response = SettingsResponse(
            workspace_id=str(workspace_id), openai_api_key=masked_key, openai_api_key_configured=bool(openai_key)
        )

        logger.info(f"✅ update_workspace_settings: EXIT workspace_id={workspace_id}, openai_configured={bool(openai_key)}")
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ update_workspace_settings: FAILED workspace_id={workspace_id}, error={str(e)}", exc_info=True)
        raise



