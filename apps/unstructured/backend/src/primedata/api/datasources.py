"""
DataSources API router.
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from primedata.api.billing import check_billing_limits
from primedata.connectors.azure_blob import AzureBlobConnector
from primedata.connectors.folder import FolderConnector
from primedata.connectors.s3 import S3Connector
from primedata.connectors.web import WebConnector
from primedata.core.scope import ensure_product_access
from primedata.db.database import get_db
from primedata.db.models import DataSource, DataSourceType, Product, RawFile, RawFileStatus
from primedata.ingestion_pipeline.artifact_registry import calculate_checksum
from primedata.storage.storage_client import storage_client
from primedata.storage.paths import raw_prefix, safe_filename
from primedata.storage.bucket_registry import BucketRegistry, BucketType
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy.orm import Session

from primedata.utils.logger import get_logger
logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/datasources", tags=["DataSources"])


class DataSourceCreateRequest(BaseModel):
    workspace_id: UUID
    product_id: UUID
    name: Optional[str] = "Unnamed Data Source"
    type: DataSourceType
    config: Dict[str, Any] = {}

    @field_validator("type", mode="before")
    @classmethod
    def normalize_type(cls, v):
        """Convert incoming type strings to uppercase for case-insensitive matching."""
        if isinstance(v, str):
            return v.upper()
        return v


class DataSourceUpdateRequest(BaseModel):
    name: Optional[str] = None
    config: Optional[Dict[str, Any]] = None


class DataSourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)  # Pydantic v2 syntax

    id: UUID
    workspace_id: UUID
    product_id: UUID
    name: str
    type: DataSourceType
    config: Dict[str, Any]
    last_cursor: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class TestConnectionResponse(BaseModel):
    ok: bool
    message: str


class TestConfigRequest(BaseModel):
    type: DataSourceType
    config: Dict[str, Any]

    @field_validator("type", mode="before")
    @classmethod
    def normalize_type(cls, v):
        """Convert incoming type strings to uppercase for case-insensitive matching."""
        if isinstance(v, str):
            return v.upper()
        return v



@router.post("/", response_model=DataSourceResponse)
async def create_datasource(
    request_body: DataSourceCreateRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Create a new data source for a product.
    """
    logger.info(f"📝 CREATE_DATASOURCE: Starting | type={request_body.type}, product_id={request_body.product_id}, workspace_id={request_body.workspace_id}, name={request_body.name}")

    try:
        # Ensure user has access to the product and its workspace
        logger.debug(f"   📋 Step 1: Verifying user access to product {request_body.product_id}")
        product = ensure_product_access(db, request, request_body.product_id)
        logger.debug(f"   ✓ Step 1 complete: User has access to product {request_body.product_id}")

        # Verify that the provided workspace_id matches the product's workspace
        logger.debug(f"   📋 Step 2: Validating workspace_id match (provided={request_body.workspace_id}, product={product.workspace_id})")
        if product.workspace_id != request_body.workspace_id:
            logger.warning(f"   ❌ Step 2 failed: Workspace mismatch | provided={request_body.workspace_id}, actual={product.workspace_id}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Workspace ID does not match product's workspace")
        logger.debug(f"   ✓ Step 2 complete: Workspace IDs match")

        # Check billing limits for data source creation
        logger.debug(f"   📋 Step 3: Checking billing limits for datasource creation")
        current_datasource_count = db.query(DataSource).filter(DataSource.product_id == request_body.product_id).count()
        logger.debug(f"   💾 Database query: Found {current_datasource_count} existing datasources for product {request_body.product_id}")

        if not check_billing_limits(str(product.workspace_id), "max_data_sources_per_product", current_datasource_count, db):
            logger.warning(f"   ❌ Step 3 failed: Data source limit exceeded | workspace={product.workspace_id}, current_count={current_datasource_count}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Data source limit exceeded. Please upgrade your plan to add more data sources.",
            )
        logger.debug(f"   ✓ Step 3 complete: Billing limits check passed")

        # Create new data source
        logger.debug(f"   📋 Step 4: Creating new DataSource record | type={request_body.type}, name={request_body.name or 'Unnamed Data Source'}")

        # Normalize config: convert comma-separated patterns to lists
        logger.debug(f"   📋 Step 4a: Normalizing config patterns")
        normalized_config = _normalize_config_patterns(request_body.config)
        logger.debug(f"   ✓ Config normalized | include={normalized_config.get('include')}, exclude={normalized_config.get('exclude')}")

        datasource = DataSource(
            workspace_id=request_body.workspace_id,
            product_id=request_body.product_id,
            name=request_body.name or "Unnamed Data Source",
            type=request_body.type,
            config=normalized_config,
        )

        db.add(datasource)
        db.commit()
        db.refresh(datasource)
        logger.debug(f"   💾 Database operation: Created datasource with id={datasource.id}")
        logger.debug(f"   ✓ Step 4 complete: DataSource persisted to database")

        logger.info(f"✅ CREATE_DATASOURCE: SUCCESS | datasource_id={datasource.id}, type={datasource.type}")
        return DataSourceResponse.model_validate(datasource)

    except HTTPException:
        logger.debug(f"   ❌ CREATE_DATASOURCE: HTTP exception raised, propagating")
        raise
    except Exception as e:
        logger.error(f"   ❌ CREATE_DATASOURCE: FAILED | error={str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create datasource: {str(e)}")


@router.get("/", response_model=List[DataSourceResponse])
async def list_datasources(
    request: Request,
    product_id: Optional[UUID] = Query(None, description="Filter by product ID"),
    db: Session = Depends(get_db)
):
    """
    List data sources. If product_id is provided, filter by that product.
    Otherwise, return data sources from all accessible workspaces.
    """
    logger.info(f"📊 LIST_DATASOURCES: Starting | product_id={product_id}")

    try:
        from primedata.core.scope import allowed_workspaces

        if product_id:
            # Ensure user has access to the product and get the product's workspace
            logger.debug(f"   📋 Step 1: Filtering by product_id={product_id}")
            logger.debug(f"   📋 Step 2: Verifying user access to product")
            product = ensure_product_access(db, request, product_id)
            logger.debug(f"   ✓ Step 2 complete: User has access to product {product_id}")

            logger.debug(f"   📋 Step 3: Querying datasources for product")
            query = db.query(DataSource).filter(DataSource.product_id == product_id)
            datasources = query.all()
            logger.debug(f"   💾 Database query result: Found {len(datasources)} datasources for product {product_id}")
        else:
            # No product_id provided - filter by allowed workspaces
            logger.debug(f"   📋 Step 1: No product_id filter - fetching allowed workspaces")
            allowed_workspace_ids = allowed_workspaces(request, db)
            logger.debug(f"   ✓ Step 1 complete: User has access to {len(allowed_workspace_ids)} workspaces")

            logger.debug(f"   📋 Step 2: Querying datasources across allowed workspaces")
            query = db.query(DataSource).filter(DataSource.workspace_id.in_(allowed_workspace_ids))
            datasources = query.all()
            logger.debug(f"   💾 Database query result: Found {len(datasources)} total datasources")

        result = [DataSourceResponse.model_validate(datasource) for datasource in datasources]
        logger.info(f"✅ LIST_DATASOURCES: SUCCESS | datasources_returned={len(result)}")
        return result

    except Exception as e:
        logger.error(f"   ❌ LIST_DATASOURCES: FAILED | error={str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to list datasources: {str(e)}")


@router.get("/{datasource_id}", response_model=DataSourceResponse)
async def get_datasource(
    datasource_id: UUID, request: Request, db: Session = Depends(get_db)
):
    """
    Get a specific data source by ID.
    """
    logger.info(f"📊 GET_DATASOURCE: Starting | datasource_id={datasource_id}")

    try:
        # Get the data source
        logger.debug(f"   📋 Step 1: Querying datasource by id={datasource_id}")
        datasource = db.query(DataSource).filter(DataSource.id == datasource_id).first()

        if not datasource:
            logger.warning(f"   ❌ Step 1 failed: Datasource not found | datasource_id={datasource_id}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data source not found")

        logger.debug(f"   ✓ Step 1 complete: Found datasource type={datasource.type}, product_id={datasource.product_id}")

        # Ensure user has access to the product
        logger.debug(f"   📋 Step 2: Verifying user access to product {datasource.product_id}")
        ensure_product_access(db, request, datasource.product_id)
        logger.debug(f"   ✓ Step 2 complete: User has access")

        result = DataSourceResponse.model_validate(datasource)
        logger.info(f"✅ GET_DATASOURCE: SUCCESS | datasource_id={datasource_id}, type={datasource.type}")
        return result

    except HTTPException:
        logger.debug(f"   ❌ GET_DATASOURCE: HTTP exception raised, propagating")
        raise
    except Exception as e:
        logger.error(f"   ❌ GET_DATASOURCE: FAILED | datasource_id={datasource_id}, error={str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get datasource: {str(e)}")


@router.patch("/{datasource_id}", response_model=DataSourceResponse)
async def update_datasource(
    datasource_id: UUID,
    request_body: DataSourceUpdateRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Update a data source's configuration.
    """
    logger.info(f"📝 UPDATE_DATASOURCE: Starting | datasource_id={datasource_id}, name={request_body.name}, config_provided={request_body.config is not None}")

    try:
        # Get the data source
        logger.debug(f"   📋 Step 1: Querying datasource by id={datasource_id}")
        datasource = db.query(DataSource).filter(DataSource.id == datasource_id).first()

        if not datasource:
            logger.warning(f"   ❌ Step 1 failed: Datasource not found | datasource_id={datasource_id}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data source not found")

        logger.debug(f"   ✓ Step 1 complete: Found datasource type={datasource.type}")

        # Ensure user has access to the product
        logger.debug(f"   📋 Step 2: Verifying user access to product {datasource.product_id}")
        ensure_product_access(db, request, datasource.product_id)
        logger.debug(f"   ✓ Step 2 complete: User has access")

        # Update name if provided
        if request_body.name is not None:
            logger.debug(f"   📋 Step 3: Updating name | old_name={datasource.name}, new_name={request_body.name}")
            datasource.name = request_body.name
            logger.debug(f"   ✓ Step 3 complete: Name updated")

        # Update configuration
        if request_body.config is not None:
            logger.debug(f"   📋 Step 4: Updating configuration | config_keys={list(request_body.config.keys())}")
            datasource.config = request_body.config
            logger.debug(f"   ✓ Step 4 complete: Configuration updated")

        logger.debug(f"   📋 Step 5: Persisting changes to database")
        db.commit()
        db.refresh(datasource)
        logger.debug(f"   💾 Database operation: Datasource updated and refreshed")
        logger.debug(f"   ✓ Step 5 complete: Changes committed")

        result = DataSourceResponse.model_validate(datasource)
        logger.info(f"✅ UPDATE_DATASOURCE: SUCCESS | datasource_id={datasource_id}")
        return result

    except HTTPException:
        logger.debug(f"   ❌ UPDATE_DATASOURCE: HTTP exception raised, propagating")
        raise
    except Exception as e:
        logger.error(f"   ❌ UPDATE_DATASOURCE: FAILED | datasource_id={datasource_id}, error={str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to update datasource: {str(e)}")




def _normalize_config_patterns(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize config patterns: convert comma-separated strings to lists.

    Handles:
    - inclusion_patterns: "*.pdf,*.docx" → include: ["*.pdf", "*.docx"]
    - exclusion_patterns: "*.tmp,*.log" → exclude: ["*.tmp", "*.log"]
    - Also normalizes any existing include/exclude lists

    Args:
        config: Configuration dictionary

    Returns:
        Normalized configuration with include/exclude as lists
    """
    normalized = config.copy()

    # Handle inclusion_patterns (comma-separated string)
    if "inclusion_patterns" in normalized:
        patterns_str = normalized.pop("inclusion_patterns")
        logger.debug(f"  📋 Converting inclusion_patterns: {patterns_str}")
        if isinstance(patterns_str, str):
            # Split by comma and strip whitespace
            patterns_list = [p.strip() for p in patterns_str.split(",") if p.strip()]
            normalized["include"] = patterns_list
            logger.debug(f"  ✓ Converted to include list: {patterns_list}")
        elif isinstance(patterns_str, list):
            normalized["include"] = patterns_str
            logger.debug(f"  ✓ Already a list: {patterns_str}")

    # Handle exclusion_patterns (comma-separated string)
    if "exclusion_patterns" in normalized:
        patterns_str = normalized.pop("exclusion_patterns")
        logger.debug(f"  📋 Converting exclusion_patterns: {patterns_str}")
        if isinstance(patterns_str, str):
            # Split by comma and strip whitespace
            patterns_list = [p.strip() for p in patterns_str.split(",") if p.strip()]
            normalized["exclude"] = patterns_list
            logger.debug(f"  ✓ Converted to exclude list: {patterns_list}")
        elif isinstance(patterns_str, list):
            normalized["exclude"] = patterns_str
            logger.debug(f"  ✓ Already a list: {patterns_str}")

    # Ensure include/exclude are lists (normalize field names for S3 connector)
    if "include" in normalized and isinstance(normalized["include"], str):
        logger.debug(f"  📋 Converting include string to list")
        normalized["include"] = [p.strip() for p in normalized["include"].split(",") if p.strip()]
        logger.debug(f"  ✓ include converted: {normalized['include']}")

    if "exclude" in normalized and isinstance(normalized["exclude"], str):
        logger.debug(f"  📋 Converting exclude string to list")
        normalized["exclude"] = [p.strip() for p in normalized["exclude"].split(",") if p.strip()]
        logger.debug(f"  ✓ exclude converted: {normalized['exclude']}")

    # Normalize S3 field names for S3Connector compatibility
    if "s3_bucket_name" in normalized:
        logger.debug(f"  📋 Renaming s3_bucket_name → bucket_name")
        normalized["bucket_name"] = normalized.pop("s3_bucket_name")

    if "s3_region" in normalized:
        logger.debug(f"  📋 Renaming s3_region → region")
        normalized["region"] = normalized.pop("s3_region")

    if "s3_prefix" in normalized:
        logger.debug(f"  📋 Renaming s3_prefix → prefix")
        normalized["prefix"] = normalized.pop("s3_prefix")

    # Remove zone_type if present (not used by connectors)
    if "zone_type" in normalized:
        logger.debug(f"  📋 Removing zone_type (not used by connectors)")
        normalized.pop("zone_type")

    return normalized


def _test_connector_config(datasource_type: DataSourceType, config: Dict[str, Any]) -> Tuple[bool, str]:
    """Helper function to test connector configuration."""
    logger.info(f"🔐 TEST_CONNECTOR_CONFIG: Starting | datasource_type={datasource_type}")

    try:
        if datasource_type == DataSourceType.WEB:
            # Convert single URL to list format expected by WebConnector
            logger.debug(f"   📋 Web connector configuration")
            test_config = config.copy()
            if "url" in test_config and "urls" not in test_config:
                test_config["urls"] = [test_config["url"]]
                logger.debug(f"   ✓ Converted single URL to urls list")

            logger.debug(f"   📋 Creating WebConnector instance and testing connection")
            connector = WebConnector(test_config)
            success, message = connector.test_connection()
            logger.info(f"✅ TEST_CONNECTOR_CONFIG: Web connector test | success={success}, message={message}")
            return success, message

        elif datasource_type == DataSourceType.FOLDER:
            logger.debug(f"   📋 Folder connector configuration")
            # Check if this is upload mode (no path provided) or path mode
            has_path = config.get("path") or config.get("root_path")

            if not has_path:
                # Upload mode - no path needed, files will be uploaded via API
                logger.debug(f"   ✓ Upload mode detected (no root_path)")
                logger.info(f"✅ TEST_CONNECTOR_CONFIG: Folder connector (upload mode) | success=True")
                return True, "Folder datasource configured for file uploads. Use the upload endpoint to add files."

            # Path mode - test the server-side path
            logger.debug(f"   📋 Path mode detected - testing server-side path")
            # Convert 'path' to 'root_path' format expected by FolderConnector
            test_config = config.copy()
            if "path" in test_config and "root_path" not in test_config:
                test_config["root_path"] = test_config["path"]
                logger.debug(f"   ✓ Converted path to root_path: {test_config['root_path']}")

            # Convert 'file_types' to 'include' patterns
            if "file_types" in test_config and "include" not in test_config:
                file_types = test_config["file_types"]
                if isinstance(file_types, str):
                    # Split comma-separated file types
                    test_config["include"] = [ft.strip() for ft in file_types.split(",") if ft.strip()]
                elif isinstance(file_types, list):
                    test_config["include"] = file_types
                else:
                    test_config["include"] = ["*"]  # Default to all files
                logger.debug(f"   ✓ Converted file_types to include patterns: {test_config['include']}")

            logger.debug(f"   📋 Creating FolderConnector instance and testing connection")
            connector = FolderConnector(test_config)
            success, message = connector.test_connection()
            logger.info(f"✅ TEST_CONNECTOR_CONFIG: Folder connector test | success={success}, message={message}")
            return success, message

        elif datasource_type == DataSourceType.AWS_S3:
            logger.debug(f"   📋 AWS S3 connector configuration")
            logger.debug(f"   📋 Creating S3Connector instance and testing connection")
            connector = S3Connector(config)
            success, message = connector.test_connection()
            logger.info(f"✅ TEST_CONNECTOR_CONFIG: S3 connector test | success={success}, message={message}")
            return success, message

        elif datasource_type == DataSourceType.AZURE_BLOB:
            logger.debug(f"   📋 Azure Blob connector configuration")
            logger.debug(f"   📋 Creating AzureBlobConnector instance and testing connection")
            connector = AzureBlobConnector(config)
            success, message = connector.test_connection()
            logger.info(f"✅ TEST_CONNECTOR_CONFIG: Azure Blob connector test | success={success}, message={message}")
            return success, message

        else:
            logger.warning(f"   ❌ Unsupported datasource_type: {datasource_type.value}")
            return False, f"Test connection not supported for data source type: {datasource_type.value}"

    except Exception as e:
        logger.error(f"   ❌ TEST_CONNECTOR_CONFIG: FAILED | datasource_type={datasource_type}, error={str(e)}", exc_info=True)
        return False, f"Test connection failed: {str(e)}"


@router.post("/test-config", response_model=TestConnectionResponse)
async def test_config(request_body: TestConfigRequest):
    """
    Test connection configuration without creating a data source.
    """
    logger.info(f"🔐 TEST_CONFIG: Starting | datasource_type={request_body.type}")

    try:
        logger.debug(f"   📋 Step 1: Testing connector configuration for {request_body.type}")
        success, message = _test_connector_config(request_body.type, request_body.config)
        logger.debug(f"   ✓ Step 1 complete: success={success}, message={message}")

        logger.info(f"✅ TEST_CONFIG: SUCCESS | type={request_body.type}, ok={success}")
        return TestConnectionResponse(ok=success, message=message)

    except Exception as e:
        logger.error(f"   ❌ TEST_CONFIG: FAILED | error={str(e)}", exc_info=True)
        return TestConnectionResponse(ok=False, message=f"Error testing configuration: {str(e)}")


@router.post("/{datasource_id}/test-connection", response_model=TestConnectionResponse)
async def test_connection(
    datasource_id: UUID, request: Request, db: Session = Depends(get_db)
):
    """
    Test connection to a data source using connector dispatch.
    """
    logger.info(f"🔐 TEST_CONNECTION: Starting | datasource_id={datasource_id}")

    try:
        # Get the data source
        logger.debug(f"   📋 Step 1: Querying datasource by id={datasource_id}")
        datasource = db.query(DataSource).filter(DataSource.id == datasource_id).first()

        if not datasource:
            logger.warning(f"   ❌ Step 1 failed: Datasource not found | datasource_id={datasource_id}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data source not found")

        logger.debug(f"   ✓ Step 1 complete: Found datasource type={datasource.type}")

        # Ensure user has access to the product
        logger.debug(f"   📋 Step 2: Verifying user access to product {datasource.product_id}")
        ensure_product_access(db, request, datasource.product_id)
        logger.debug(f"   ✓ Step 2 complete: User has access")

        # Test connection using helper function
        logger.debug(f"   📋 Step 3: Testing connector configuration")
        success, message = _test_connector_config(datasource.type, datasource.config)
        logger.debug(f"   ✓ Step 3 complete: Test result | success={success}")

        logger.info(f"✅ TEST_CONNECTION: SUCCESS | datasource_id={datasource_id}, ok={success}")
        return TestConnectionResponse(ok=success, message=message)

    except HTTPException:
        logger.debug(f"   ❌ TEST_CONNECTION: HTTP exception raised, propagating")
        raise
    except Exception as e:
        logger.error(f"   ❌ TEST_CONNECTION: FAILED | datasource_id={datasource_id}, error={str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Connection test failed: {str(e)}")



@router.post("/{datasource_id}/upload-files")
async def upload_files(
    datasource_id: UUID,
    request: Request,
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db)
):
    """
    Upload files to a folder-type datasource.
    Files are stored directly in S3/GCS and RawFile records are created.
    This bypasses the need for a server-side path.

    Configuration from environment variables:
    - S3_METADATA_BUCKET: Bucket name for file storage (default: "primedata-raw")
    - S3_METADATA_PATH: Path prefix in bucket (default: calculated via raw_prefix())
    """
    logger.info(f"📤 UPLOAD_FILES: Starting | datasource_id={datasource_id}, files_count={len(files)}")

    try:
        # Get the data source
        logger.debug(f"   📋 Step 1: Querying datasource by id={datasource_id}")
        datasource = db.query(DataSource).filter(DataSource.id == datasource_id).first()

        if not datasource:
            logger.warning(f"   ❌ Step 1 failed: Datasource not found | datasource_id={datasource_id}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data source not found")

        logger.debug(f"   ✓ Step 1 complete: Found datasource type={datasource.type}")

        # Only allow for folder type
        if datasource.type != DataSourceType.FOLDER:
            logger.warning(f"   ❌ Step 2 failed: Invalid datasource type for upload | type={datasource.type}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=f"File upload only supported for folder datasources"
            )

        logger.debug(f"   ✓ Step 2 complete: Datasource type is FOLDER")

        # Ensure user has access
        logger.debug(f"   📋 Step 3: Verifying user access to product {datasource.product_id}")
        ensure_product_access(db, request, datasource.product_id)
        logger.debug(f"   ✓ Step 3 complete: User has access")

        # Get product version
        logger.debug(f"   📋 Step 4: Querying product by id={datasource.product_id}")
        product = db.query(Product).filter(Product.id == datasource.product_id).first()

        if not product:
            logger.warning(f"   ❌ Step 4 failed: Product not found | product_id={datasource.product_id}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

        version = product.current_version or 1
        logger.debug(f"   ✓ Step 4 complete: Using product version={version}")

        # Get bucket and path prefix from environment variables
        logger.debug(f"   📋 Step 5: Determining storage bucket and path prefix")
        storage_bucket = BucketRegistry.get_bucket(BucketType.RAW)

        # Always use raw_prefix() to ensure files are saved in workspace/product/version hierarchy
        # raw_prefix() automatically includes S3_METADATA_PATH if set
        storage_path_prefix = raw_prefix(datasource.workspace_id, datasource.product_id, version)
        logger.debug(f"   📋 Storage prefix generated: {storage_path_prefix}")

        logger.debug(f"   ✓ Step 5 complete: bucket={storage_bucket}, prefix={storage_path_prefix}")

        logger.info(
            f"   📊 Upload configuration | product={datasource.product_id}, version={version}, "
            f"bucket={storage_bucket}, prefix={storage_path_prefix}"
        )

        uploaded_files = []
        errors = []

        logger.debug(f"   📋 Step 6: Processing {len(files)} files for upload")

        for idx, file in enumerate(files, 1):
            try:
                logger.debug(f"   📋 File {idx}/{len(files)}: {file.filename}")

                content = await file.read()
                file_size = len(content)
                logger.debug(f"   📊 File size: {file_size} bytes")

                # Calculate checksum for integrity validation
                file_checksum = calculate_checksum(content, algorithm="sha256")
                logger.debug(f"   ✓ Checksum calculated: {file_checksum[:16]}...")

                # Generate safe key
                safe_key = safe_filename(file.filename)
                key = f"{storage_path_prefix}{safe_key}"
                logger.debug(f"   📋 Storage key: {key}")

                # Determine content type
                content_type = file.content_type or "application/octet-stream"
                logger.debug(f"   📋 Content type: {content_type}")

                # Upload directly to S3/GCS
                logger.debug(f"   📨 Uploading to storage...")
                success = storage_client.put_bytes(storage_bucket, key, content, content_type)

                if success:
                    # Log the S3 path where file was uploaded
                    s3_path = f"s3://{storage_bucket}/{key}"
                    logger.info(
                        f"   ✓ File uploaded successfully | "
                        f"local={file.filename}, size={file_size} bytes, "
                        f"s3={s3_path}, checksum={file_checksum[:16]}..."
                    )

                    # Create RawFile record (same as sync-full does)
                    logger.debug(f"   📋 Creating RawFile record")
                    file_stem = Path(file.filename).stem
                    filename = Path(file.filename).name

                    # Check if file already exists
                    existing = (
                        db.query(RawFile)
                        .filter(
                            RawFile.product_id == datasource.product_id, RawFile.version == version, RawFile.file_stem == file_stem
                        )
                        .first()
                    )

                    if not existing:
                        raw_file = RawFile(
                            workspace_id=datasource.workspace_id,
                            product_id=datasource.product_id,
                            data_source_id=datasource.id,
                            version=version,
                            filename=filename,
                            file_stem=file_stem,
                            storage_key=key,
                            storage_bucket=storage_bucket,
                            file_size=file_size,
                            content_type=content_type,
                            status=RawFileStatus.INGESTED,
                            file_checksum=file_checksum,
                        )
                        db.add(raw_file)
                        logger.info(f"   💾 RawFile record created | filename={filename}, key={key}")
                        uploaded_files.append({"filename": filename, "size": file_size, "key": key})
                    else:
                        logger.warning(f"   ⚠️ File already exists in version {version}: {filename}")
                        errors.append(f"File {filename} already exists")
                else:
                    logger.error(f"   ❌ Storage upload failed for {file.filename}")
                    errors.append(f"Failed to upload {file.filename}")

            except Exception as e:
                logger.error(f"   ❌ Error uploading file {file.filename}: {e}", exc_info=True)
                errors.append(f"Error uploading {file.filename}: {str(e)}")

        logger.debug(f"   📋 Step 7: Committing all RawFile records to database")
        db.commit()
        logger.debug(f"   💾 All records committed | uploaded={len(uploaded_files)}, errors={len(errors)}")

        logger.info(f"✅ UPLOAD_FILES: SUCCESS | uploaded_count={len(uploaded_files)}, error_count={len(errors)}")

        return {
            "success": len(errors) == 0,
            "uploaded_count": len(uploaded_files),
            "error_count": len(errors),
            "uploaded_files": uploaded_files,
            "errors": errors,
        }

    except HTTPException:
        logger.debug(f"   ❌ UPLOAD_FILES: HTTP exception raised, propagating")
        raise
    except Exception as e:
        logger.error(f"   ❌ UPLOAD_FILES: FAILED | datasource_id={datasource_id}, error={str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Upload failed: {str(e)}")


@router.delete("/{datasource_id}")
async def delete_datasource(
    datasource_id: UUID, request: Request, db: Session = Depends(get_db)
):
    """
    Delete a data source.
    """
    logger.info(f"🗑️ DELETE_DATASOURCE: Starting | datasource_id={datasource_id}")

    try:
        # Get the data source
        logger.debug(f"   📋 Step 1: Querying datasource by id={datasource_id}")
        datasource = db.query(DataSource).filter(DataSource.id == datasource_id).first()

        if not datasource:
            logger.warning(f"   ❌ Step 1 failed: Datasource not found | datasource_id={datasource_id}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data source not found")

        logger.debug(f"   ✓ Step 1 complete: Found datasource type={datasource.type}, product_id={datasource.product_id}")

        # Ensure user has access to the product
        logger.debug(f"   📋 Step 2: Verifying user access to product {datasource.product_id}")
        ensure_product_access(db, request, datasource.product_id)
        logger.debug(f"   ✓ Step 2 complete: User has access")

        # Check if there are any raw files associated with this data source
        logger.debug(f"   📋 Step 3: Checking for associated raw files")
        raw_files_count = db.query(RawFile).filter(RawFile.data_source_id == datasource_id).count()
        logger.debug(f"   💾 Database query: Found {raw_files_count} raw files for datasource")

        if raw_files_count > 0:
            # Set data_source_id to NULL for all associated raw files
            logger.debug(f"   📋 Step 4: Unlinking {raw_files_count} raw files from datasource")
            db.query(RawFile).filter(RawFile.data_source_id == datasource_id).update(
                {RawFile.data_source_id: None}, synchronize_session=False
            )
            logger.info(f"   ✓ Unlinked {raw_files_count} raw files from datasource {datasource_id}")
            logger.debug(f"   ✓ Step 4 complete: Raw files unlinked")
        else:
            logger.debug(f"   ℹ️ No raw files to unlink")

        # Delete the data source
        logger.debug(f"   📋 Step 5: Deleting datasource record")
        db.delete(datasource)
        logger.debug(f"   ✓ Step 5 complete: Datasource marked for deletion")

        logger.debug(f"   📋 Step 6: Committing changes to database")
        db.commit()
        logger.debug(f"   💾 Changes committed successfully")

        logger.info(f"✅ DELETE_DATASOURCE: SUCCESS | datasource_id={datasource_id}, raw_files_unlinked={raw_files_count}")

        return {"message": "Data source deleted successfully"}

    except HTTPException:
        logger.debug(f"   ❌ DELETE_DATASOURCE: HTTP exception raised, propagating")
        raise
    except Exception as e:
        logger.error(f"   ❌ DELETE_DATASOURCE: FAILED | datasource_id={datasource_id}, error={str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to delete datasource: {str(e)}")


import primedata.api.datasources_sync  # noqa: F401 - registers routes
