"""
Playbooks API router.

Provides endpoints for listing and retrieving playbook configurations.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

import yaml
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from primedata.core.scope import ensure_workspace_access
from primedata.db.database import get_db
from primedata.db.models import CustomPlaybook
from primedata.ingestion_pipeline.aird_stages.playbooks import list_playbooks, load_playbook_yaml, refresh_index
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from primedata.utils.logger import get_logger
logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/playbooks", tags=["Playbooks"])


class PlaybookInfo(BaseModel):
    """Playbook information."""

    id: str
    description: str
    path: str


class PlaybookResponse(BaseModel):
    """Full playbook configuration response."""

    id: str
    description: str
    config: Dict[str, Any]


@router.get("/{playbook_id}/yaml")
async def get_playbook_yaml(
    playbook_id: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Get playbook YAML content as plain text.
    Supports both built-in and custom playbooks.
    """
    logger.info(f"📚 get_playbook_yaml: ENTRY playbook_id={playbook_id}")

    try:
        logger.debug(f"   📋 Attempting custom playbook lookup")
        # Try custom playbook first (if table exists)
        try:
            custom_playbook = (
                db.query(CustomPlaybook)
                .filter(CustomPlaybook.playbook_id == playbook_id.upper(), CustomPlaybook.is_active == True)
                .first()
            )

            if custom_playbook:
                logger.debug(f"   ✓ Custom playbook found: id={custom_playbook.id}, workspace_id={custom_playbook.workspace_id}")
                from primedata.core.scope import ensure_workspace_access

                ensure_workspace_access(db, request, custom_playbook.workspace_id)
                logger.debug(f"   ✓ Workspace access verified")
                logger.info(f"✅ get_playbook_yaml: EXIT playbook_id={playbook_id}, is_custom=True")
                return {"yaml": custom_playbook.yaml_content, "is_custom": True}
        except Exception as db_error:
            # If table doesn't exist or other DB error, log and continue to file-based lookup
            if "does not exist" in str(db_error) or "UndefinedTable" in str(type(db_error).__name__):
                logger.debug(f"   📋 Custom playbooks table unavailable, trying file-based: {type(db_error).__name__}")
            else:
                logger.warning(f"⚠️ Error querying custom playbooks, falling back to file-based: {str(db_error)}", exc_info=True)

        logger.debug(f"   📋 Attempting built-in playbook file lookup")
        # Try built-in playbook
        from primedata.ingestion_pipeline.aird_stages.playbooks.router import resolve_playbook_file

        playbook_path = resolve_playbook_file(playbook_id)

        if playbook_path and playbook_path.exists():
            logger.debug(f"   ✓ Playbook file found: {playbook_path}")
            with open(playbook_path, "r", encoding="utf-8") as f:
                yaml_content = f.read()
            logger.info(f"✅ get_playbook_yaml: EXIT playbook_id={playbook_id}, is_custom=False")
            return {"yaml": yaml_content, "is_custom": False}

        logger.warning(f"❌ Playbook not found: playbook_id={playbook_id}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Playbook '{playbook_id}' not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ get_playbook_yaml: FAILED playbook_id={playbook_id}, error={str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get playbook YAML: {str(e)}")


@router.get("/", response_model=List[PlaybookInfo])
async def list_available_playbooks(
    request: Request,
    workspace_id: Optional[UUID] = None,
    db: Session = Depends(get_db)
):
    """
    List all available playbooks.

    Returns all playbooks found in the configured playbook directory,
    including TECH, SCANNED, REGULATORY, and any other playbooks.
    """
    logger.info(f"📚 list_available_playbooks: ENTRY workspace_id={workspace_id}")

    try:
        logger.debug(f"   📋 Refreshing playbook index")
        # Refresh the playbook index to ensure we have the latest playbooks
        refresh_index()

        logger.debug(f"   📋 Listing playbooks")
        playbook_map = list_playbooks()

        if not playbook_map:
            logger.warning(f"⚠️ No playbooks found in configured directory")
            logger.info(f"✅ list_available_playbooks: EXIT playbooks_count=0")
            return []

        playbooks = []

        logger.debug(f"   💾 Found {len(playbook_map)} playbooks, sorting by ID")
        # Sort by playbook ID (case-insensitive) for consistent ordering
        sorted_items = sorted(playbook_map.items(), key=lambda x: x[0].lower())

        for idx, (playbook_id, path) in enumerate(sorted_items, 1):
            try:
                logger.debug(f"   ✓ [{idx}] Loading playbook: {playbook_id}")
                # Load playbook to get description and actual ID from YAML
                config = load_playbook_yaml(playbook_id)
                # Use the ID from the YAML file, or fallback to uppercase version of the key
                playbook_id_from_yaml = config.get("id", playbook_id.upper())
                playbooks.append(
                    PlaybookInfo(
                        id=playbook_id_from_yaml,
                        description=config.get("description", "No description"),
                        path=str(path),
                    )
                )
            except Exception as e:
                logger.warning(f"⚠️ Failed to load playbook {playbook_id}: {str(e)}")
                # Still include it with minimal info using the filename as ID
                playbooks.append(
                    PlaybookInfo(
                        id=playbook_id.upper(),
                        description="Playbook available but failed to load",
                        path=str(path),
                    )
                )

        # Add custom playbooks if workspace_id is provided
        if workspace_id:
            logger.debug(f"   📋 Checking for custom playbooks in workspace: {workspace_id}")
            try:
                from primedata.core.scope import ensure_workspace_access

                ensure_workspace_access(db, request, workspace_id)
                logger.debug(f"   ✓ Workspace access verified")

                custom_playbooks = (
                    db.query(CustomPlaybook)
                    .filter(CustomPlaybook.workspace_id == workspace_id, CustomPlaybook.is_active == True)
                    .all()
                )

                logger.debug(f"   💾 Found {len(custom_playbooks)} custom playbooks")

                for custom_pb in custom_playbooks:
                    logger.debug(f"   ✓ Adding custom playbook: {custom_pb.playbook_id}")
                    playbooks.append(
                        PlaybookInfo(
                            id=custom_pb.playbook_id,
                            description=custom_pb.description or f"Custom playbook: {custom_pb.name}",
                            path=f"custom:{custom_pb.id}",  # Mark as custom
                        )
                    )
            except Exception as e:
                logger.warning(f"⚠️ Failed to load custom playbooks: {str(e)}")

        logger.info(f"✅ list_available_playbooks: EXIT playbooks_count={len(playbooks)}")
        return playbooks

    except Exception as e:
        logger.error(f"❌ list_available_playbooks: FAILED error={str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to list playbooks")


@router.get("/{playbook_id}", response_model=PlaybookResponse)
async def get_playbook(
    playbook_id: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Get playbook configuration by ID.
    Supports both built-in playbooks (from files) and custom playbooks (from database).
    """
    logger.info(f"📚 get_playbook: ENTRY playbook_id={playbook_id}")

    try:
        logger.debug(f"   📋 Attempting custom playbook lookup")
        # First try to load from database (custom playbooks) - if table exists
        try:
            custom_playbook = (
                db.query(CustomPlaybook)
                .filter(CustomPlaybook.playbook_id == playbook_id.upper(), CustomPlaybook.is_active == True)
                .first()
            )

            if custom_playbook:
                logger.debug(f"   ✓ Custom playbook found: id={custom_playbook.id}, workspace_id={custom_playbook.workspace_id}")
                # Check workspace access
                from primedata.core.scope import ensure_workspace_access

                ensure_workspace_access(db, request, custom_playbook.workspace_id)
                logger.debug(f"   ✓ Workspace access verified")

                # Parse YAML content
                try:
                    logger.debug(f"   📋 Parsing YAML content")
                    config = yaml.safe_load(custom_playbook.yaml_content)
                    logger.debug(f"   ✓ YAML parsed successfully")

                    response = PlaybookResponse(
                        id=config.get("id", custom_playbook.playbook_id),
                        description=custom_playbook.description or config.get("description", "Custom playbook"),
                        config=config,
                    )
                    logger.info(f"✅ get_playbook: EXIT playbook_id={playbook_id}, is_custom=True")
                    return response

                except yaml.YAMLError as e:
                    logger.error(f"❌ Failed to parse custom playbook YAML: {str(e)}", exc_info=True)
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Invalid YAML in custom playbook: {str(e)}"
                    )
        except Exception as db_error:
            # If table doesn't exist, just skip custom playbook lookup
            if "does not exist" in str(db_error) or "UndefinedTable" in str(type(db_error).__name__):
                logger.debug(f"   📋 Custom playbooks table unavailable, trying file-based: {type(db_error).__name__}")
            else:
                logger.warning(f"⚠️ Error querying custom playbooks, falling back to file-based: {str(db_error)}", exc_info=True)

        logger.debug(f"   📋 Attempting built-in playbook file lookup")
        # Fallback to built-in playbooks (from files)
        config = load_playbook_yaml(playbook_id)
        logger.debug(f"   ✓ Built-in playbook loaded: id={config.get('id', playbook_id.upper())}")

        response = PlaybookResponse(
            id=config.get("id", playbook_id.upper()),
            description=config.get("description", "No description"),
            config=config,
        )
        logger.info(f"✅ get_playbook: EXIT playbook_id={playbook_id}, is_custom=False")
        return response

    except FileNotFoundError:
        logger.warning(f"❌ Playbook not found: playbook_id={playbook_id}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Playbook '{playbook_id}' not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ get_playbook: FAILED playbook_id={playbook_id}, error={str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to load playbook: {str(e)}")


# Custom Playbook Endpoints


class CustomPlaybookCreateRequest(BaseModel):
    name: str
    playbook_id: str
    description: Optional[str] = None
    yaml_content: str
    base_playbook_id: Optional[str] = None


class CustomPlaybookUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    yaml_content: Optional[str] = None


class CustomPlaybookResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)  # Pydantic v2 syntax

    id: UUID
    workspace_id: UUID
    owner_user_id: str
    name: str
    playbook_id: str
    description: Optional[str]
    yaml_content: str
    base_playbook_id: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime]


@router.post("/custom", response_model=CustomPlaybookResponse, status_code=status.HTTP_201_CREATED)
async def create_custom_playbook(
    request_body: CustomPlaybookCreateRequest,
    request: Request,
    workspace_id: UUID = Query(..., description="Workspace ID"),
    db: Session = Depends(get_db)
):
    """
    Create a custom playbook based on an existing playbook or from scratch.
    """
    logger.info(f"📚 create_custom_playbook: ENTRY workspace_id={workspace_id}, playbook_id={request_body.playbook_id}")

    try:
        from primedata.core.scope import ensure_workspace_access
        from primedata.core.user_utils import get_user_id

        logger.debug(f"   📋 Verifying workspace access")
        ensure_workspace_access(db, request, workspace_id)
        logger.debug(f"   ✓ Workspace access verified")

        logger.debug(f"   📋 Validating YAML content")
        # Validate YAML
        try:
            config = yaml.safe_load(request_body.yaml_content)
            if not isinstance(config, dict):
                logger.warning(f"❌ YAML is not a dictionary")
                raise ValueError("YAML must be a dictionary")
            logger.debug(f"   ✓ YAML is dictionary")

            # Ensure playbook has required fields
            if "id" not in config:
                config["id"] = request_body.playbook_id.upper()
                logger.debug(f"   ✓ Added id field: {config['id']}")

        except yaml.YAMLError as e:
            logger.warning(f"❌ Invalid YAML syntax: {str(e)}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid YAML: {str(e)}")
        except Exception as e:
            logger.warning(f"❌ Invalid playbook configuration: {str(e)}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid playbook configuration: {str(e)}")

        logger.debug(f"   📋 Checking for duplicate playbook_id in workspace")
        # Check if playbook_id already exists in this workspace
        try:
            existing = (
                db.query(CustomPlaybook)
                .filter(
                    CustomPlaybook.workspace_id == workspace_id,
                    CustomPlaybook.playbook_id == request_body.playbook_id.upper(),
                    CustomPlaybook.is_active == True,
                )
                .first()
            )

            if existing:
                logger.warning(f"❌ Duplicate playbook_id: {request_body.playbook_id} in workspace {workspace_id}")
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Playbook with ID '{request_body.playbook_id}' already exists in this workspace",
                )

            logger.debug(f"   ✓ playbook_id is unique in workspace")

        except HTTPException:
            raise
        except Exception as db_error:
            # If table doesn't exist, provide a helpful error message
            if "does not exist" in str(db_error) or "UndefinedTable" in str(type(db_error).__name__):
                logger.error(f"❌ Custom playbooks table does not exist")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Custom playbooks feature is not available. Please run the database migration first: 'alembic upgrade head'",
                )
            # Re-raise other database errors
            raise

        logger.debug(f"   💾 Creating custom playbook record")
        # Create custom playbook
        custom_playbook = CustomPlaybook(
            workspace_id=workspace_id,
            owner_user_id=None,
            name=request_body.name,
            playbook_id=request_body.playbook_id.upper(),
            description=request_body.description,
            yaml_content=request_body.yaml_content,
            config=config,  # Store parsed YAML for quick access
            base_playbook_id=request_body.base_playbook_id.upper() if request_body.base_playbook_id else None,
            is_active=True,
        )

        db.add(custom_playbook)
        db.commit()
        db.refresh(custom_playbook)
        logger.debug(f"   ✓ Custom playbook persisted: id={custom_playbook.id}")

        logger.info(f"✅ create_custom_playbook: EXIT workspace_id={workspace_id}, playbook_id={custom_playbook.playbook_id}")

        return CustomPlaybookResponse.model_validate(custom_playbook)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ create_custom_playbook: FAILED workspace_id={workspace_id}, error={str(e)}", exc_info=True)
        raise


@router.get("/custom", response_model=List[CustomPlaybookResponse])
async def list_custom_playbooks(
    request: Request,
    workspace_id: UUID = Query(..., description="Workspace ID"),
    db: Session = Depends(get_db)
):
    """
    List all custom playbooks in a workspace.
    """
    logger.info(f"📚 list_custom_playbooks: ENTRY workspace_id={workspace_id}")

    try:
        from primedata.core.scope import ensure_workspace_access

        logger.debug(f"   📋 Verifying workspace access")
        ensure_workspace_access(db, request, workspace_id)
        logger.debug(f"   ✓ Workspace access verified")

        logger.debug(f"   📋 Querying custom playbooks")
        try:
            custom_playbooks = (
                db.query(CustomPlaybook)
                .filter(CustomPlaybook.workspace_id == workspace_id, CustomPlaybook.is_active == True)
                .all()
            )

            logger.debug(f"   💾 Retrieved {len(custom_playbooks)} custom playbooks")

            result = [CustomPlaybookResponse.model_validate(pb) for pb in custom_playbooks]
            logger.info(f"✅ list_custom_playbooks: EXIT workspace_id={workspace_id}, playbooks_count={len(result)}")
            return result

        except Exception as db_error:
            # If table doesn't exist, return empty list
            if "does not exist" in str(db_error) or "UndefinedTable" in str(type(db_error).__name__):
                logger.debug(f"   📋 Custom playbooks table not available, returning empty list")
                logger.info(f"✅ list_custom_playbooks: EXIT workspace_id={workspace_id}, playbooks_count=0")
                return []
            raise

    except Exception as e:
        logger.error(f"❌ list_custom_playbooks: FAILED workspace_id={workspace_id}, error={str(e)}", exc_info=True)
        raise


@router.get("/custom/{playbook_id}", response_model=CustomPlaybookResponse)
async def get_custom_playbook(
    playbook_id: str,
    request: Request,
    workspace_id: UUID = Query(..., description="Workspace ID"),
    db: Session = Depends(get_db)
):
    """
    Get a specific custom playbook.
    """
    logger.info(f"📚 get_custom_playbook: ENTRY workspace_id={workspace_id}, playbook_id={playbook_id}")

    try:
        from primedata.core.scope import ensure_workspace_access

        logger.debug(f"   📋 Verifying workspace access")
        ensure_workspace_access(db, request, workspace_id)
        logger.debug(f"   ✓ Workspace access verified")

        logger.debug(f"   📋 Querying custom playbook")
        try:
            custom_playbook = (
                db.query(CustomPlaybook)
                .filter(
                    CustomPlaybook.workspace_id == workspace_id,
                    CustomPlaybook.playbook_id == playbook_id.upper(),
                    CustomPlaybook.is_active == True,
                )
                .first()
            )

            if not custom_playbook:
                logger.warning(f"❌ Custom playbook not found: playbook_id={playbook_id}, workspace_id={workspace_id}")
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Custom playbook '{playbook_id}' not found")

            logger.debug(f"   ✓ Custom playbook found: id={custom_playbook.id}")
            logger.info(f"✅ get_custom_playbook: EXIT workspace_id={workspace_id}, playbook_id={playbook_id}")

            return CustomPlaybookResponse.model_validate(custom_playbook)

        except HTTPException:
            raise
        except Exception as db_error:
            # If table doesn't exist, return 404
            if "does not exist" in str(db_error) or "UndefinedTable" in str(type(db_error).__name__):
                logger.warning(f"❌ Custom playbooks table not available: {type(db_error).__name__}")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Custom playbook '{playbook_id}' not found. Custom playbooks feature is not available. Please run the database migration first.",
                )
            raise

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ get_custom_playbook: FAILED workspace_id={workspace_id}, playbook_id={playbook_id}, error={str(e)}", exc_info=True)
        raise


@router.patch("/custom/{playbook_id}", response_model=CustomPlaybookResponse)
async def update_custom_playbook(
    playbook_id: str,
    request_body: CustomPlaybookUpdateRequest,
    request: Request,
    workspace_id: UUID = Query(..., description="Workspace ID"),
    db: Session = Depends(get_db)
):
    """
    Update a custom playbook.
    """
    logger.info(f"📚 update_custom_playbook: ENTRY workspace_id={workspace_id}, playbook_id={playbook_id}")

    try:
        from primedata.core.scope import ensure_workspace_access
        from sqlalchemy.orm.attributes import flag_modified

        logger.debug(f"   📋 Verifying workspace access")
        ensure_workspace_access(db, request, workspace_id)
        logger.debug(f"   ✓ Workspace access verified")

        logger.debug(f"   📋 Querying custom playbook")
        try:
            custom_playbook = (
                db.query(CustomPlaybook)
                .filter(
                    CustomPlaybook.workspace_id == workspace_id,
                    CustomPlaybook.playbook_id == playbook_id.upper(),
                    CustomPlaybook.is_active == True,
                )
                .first()
            )

            if not custom_playbook:
                logger.warning(f"❌ Custom playbook not found: playbook_id={playbook_id}, workspace_id={workspace_id}")
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Custom playbook '{playbook_id}' not found")

            logger.debug(f"   ✓ Custom playbook found: id={custom_playbook.id}")

            changes_made = []

            # Update fields
            if request_body.name is not None:
                old_name = custom_playbook.name
                custom_playbook.name = request_body.name
                logger.debug(f"   ✓ name: '{old_name}' -> '{custom_playbook.name}'")
                changes_made.append("name")

            if request_body.description is not None:
                old_desc = custom_playbook.description
                custom_playbook.description = request_body.description
                logger.debug(f"   ✓ description: '{old_desc}' -> '{custom_playbook.description}'")
                changes_made.append("description")

            if request_body.yaml_content is not None:
                logger.debug(f"   📋 Validating YAML content")
                # Validate YAML
                try:
                    config = yaml.safe_load(request_body.yaml_content)
                    if not isinstance(config, dict):
                        logger.warning(f"❌ YAML is not a dictionary")
                        raise ValueError("YAML must be a dictionary")

                    logger.debug(f"   ✓ YAML validated")
                    custom_playbook.yaml_content = request_body.yaml_content
                    custom_playbook.config = config
                    flag_modified(custom_playbook, "config")
                    logger.debug(f"   ✓ yaml_content and config updated")
                    changes_made.append("yaml_content")

                except yaml.YAMLError as e:
                    logger.warning(f"❌ Invalid YAML syntax: {str(e)}")
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid YAML: {str(e)}")

            logger.debug(f"   💾 Persisting {len(changes_made)} changes: {changes_made}")
            db.commit()
            db.refresh(custom_playbook)
            logger.debug(f"   ✓ Database commit successful")

            logger.info(f"✅ update_custom_playbook: EXIT workspace_id={workspace_id}, playbook_id={playbook_id}, changes_count={len(changes_made)}")

            return CustomPlaybookResponse.model_validate(custom_playbook)

        except HTTPException:
            raise
        except Exception as db_error:
            # If table doesn't exist, provide helpful error
            if "does not exist" in str(db_error) or "UndefinedTable" in str(type(db_error).__name__):
                logger.error(f"❌ Custom playbooks table does not exist")
                db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Custom playbooks feature is not available. Please run the database migration first: 'alembic upgrade head'",
                )
            # Re-raise other database errors
            db.rollback()
            raise

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ update_custom_playbook: FAILED workspace_id={workspace_id}, playbook_id={playbook_id}, error={str(e)}", exc_info=True)
        raise


@router.delete("/custom/{playbook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_custom_playbook(
    playbook_id: str,
    request: Request,
    workspace_id: UUID = Query(..., description="Workspace ID"),
    db: Session = Depends(get_db)
):
    """
    Delete (soft delete) a custom playbook.
    """
    logger.info(f"📚 delete_custom_playbook: ENTRY workspace_id={workspace_id}, playbook_id={playbook_id}")

    try:
        from primedata.core.scope import ensure_workspace_access

        logger.debug(f"   📋 Verifying workspace access")
        ensure_workspace_access(db, request, workspace_id)
        logger.debug(f"   ✓ Workspace access verified")

        logger.debug(f"   📋 Querying custom playbook")
        try:
            custom_playbook = (
                db.query(CustomPlaybook)
                .filter(
                    CustomPlaybook.workspace_id == workspace_id,
                    CustomPlaybook.playbook_id == playbook_id.upper(),
                    CustomPlaybook.is_active == True,
                )
                .first()
            )

            if not custom_playbook:
                logger.warning(f"❌ Custom playbook not found: playbook_id={playbook_id}, workspace_id={workspace_id}")
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Custom playbook '{playbook_id}' not found")

            logger.debug(f"   ✓ Custom playbook found: id={custom_playbook.id}")

            # Soft delete
            logger.debug(f"   💾 Soft-deleting playbook: setting is_active=False")
            custom_playbook.is_active = False
            db.commit()
            logger.debug(f"   ✓ Playbook soft-deleted from database")

            logger.info(f"✅ delete_custom_playbook: EXIT workspace_id={workspace_id}, playbook_id={playbook_id}")

            return None

        except HTTPException:
            raise
        except Exception as db_error:
            # If table doesn't exist, return 404
            if "does not exist" in str(db_error) or "UndefinedTable" in str(type(db_error).__name__):
                logger.warning(f"❌ Custom playbooks table not available: {type(db_error).__name__}")
                db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Custom playbook '{playbook_id}' not found. Custom playbooks feature is not available.",
                )
            # Re-raise other database errors
            db.rollback()
            raise

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ delete_custom_playbook: FAILED workspace_id={workspace_id}, playbook_id={playbook_id}, error={str(e)}", exc_info=True)
        raise
