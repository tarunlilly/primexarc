"""
DataSources sync-full route handler.

Extracted from datasources.py to reduce file size.
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from primedata.api.datasources import router, _normalize_config_patterns
from primedata.connectors.azure_blob import AzureBlobConnector
from primedata.connectors.folder import FolderConnector
from primedata.connectors.s3 import S3Connector
from primedata.connectors.web import WebConnector
from primedata.core.scope import ensure_product_access
from primedata.db.database import get_db
from primedata.db.models import DataSource, DataSourceType, Product, RawFile, RawFileStatus
from primedata.ingestion_pipeline.artifact_registry import calculate_checksum
from primedata.storage.storage_client import storage_client
from primedata.storage.paths import raw_prefix
from primedata.storage.bucket_registry import BucketRegistry, BucketType
from primedata.api.billing import calculate_workspace_raw_files_size_mb
from primedata.core.plan_limits import get_plan_limit

from primedata.utils.logger import get_logger
logger = get_logger(__name__)


class SyncFullRequest(BaseModel):
    version: Optional[int] = None


class SyncFullResponse(BaseModel):
    version: int
    files: int
    bytes: int
    errors: int
    duration: float
    prefix: str
    details: Dict[str, Any]


@router.post("/{datasource_id}/sync-full", response_model=SyncFullResponse)
async def sync_full(
    datasource_id: UUID,
    request_body: SyncFullRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Perform full synchronization of a data source.

    This endpoint:
    1. Syncs files from the data source to storage (S3 or GCS)
    2. Creates RawFile records in the database
    3. Updates product version if needed
    4. Updates data source last_cursor with sync details

    For folder datasources in upload mode (no root_path), queries existing
    uploaded files from the current version and processes them for the new version.
    """
    logger.info(f"🔄 SYNC_FULL: Starting | datasource_id={datasource_id}, requested_version={request_body.version}")

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

        # Get the product to determine version
        logger.debug(f"   📋 Step 3: Querying product by id={datasource.product_id}")
        product = db.query(Product).filter(Product.id == datasource.product_id).first()

        if not product:
            logger.warning(f"   ❌ Step 3 failed: Product not found | product_id={datasource.product_id}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

        logger.debug(f"   ✓ Step 3 complete: Found product, current_version={product.current_version}")

        # Determine version
        version = request_body.version or (product.current_version or 0) + 1
        logger.info(f"   📊 Sync version determined: {version} (current={product.current_version})")

        # Generate output prefix
        output_prefix = raw_prefix(datasource.workspace_id, datasource.product_id, version)
        logger.debug(f"   📋 Storage prefix generated: {output_prefix}")

        # Dispatch to appropriate connector
        logger.debug(f"   📋 Step 4: Dispatching to connector for datasource type={datasource.type}")

        # Normalize config patterns before using
        logger.debug(f"   📋 Normalizing datasource config patterns")
        normalized_config = _normalize_config_patterns(datasource.config)
        logger.debug(f"   ✓ Config normalized")

        result = None

        if datasource.type == DataSourceType.WEB:
            logger.debug(f"   📨 Web connector mode: syncing from {len(normalized_config.get('urls', []))} URLs")
            config = normalized_config.copy()
            if "url" in config and "urls" not in config:
                config["urls"] = [config["url"]]
                logger.debug(f"   ✓ Converted single URL to urls list")

            connector = WebConnector(config)
            raw_bucket = BucketRegistry.get_bucket(BucketType.RAW)
            result = connector.sync_full(raw_bucket, output_prefix)
            logger.debug(f"   💾 Web connector result: files={result.get('files', 0)}, bytes={result.get('bytes', 0)}")

        elif datasource.type == DataSourceType.FOLDER:
            logger.debug(f"   📂 Folder connector mode")
            # Convert 'path' to 'root_path' format expected by FolderConnector
            config = normalized_config.copy()
            root_path = config.get("root_path") or config.get("path", "")

            # Special handling for upload mode (no root_path configured)
            if not root_path:
                logger.debug(f"   📋 Upload mode detected (no root_path) - querying existing uploaded files")

                # Query existing RawFile records for this datasource
                # Check all versions, not just current_version, since files might have been uploaded
                # before current_version was set, or to version 1 when current_version was None
                # First try current_version, then try version 1, then try any version
                current_version = product.current_version or 1

                # Try to find files in current_version first
                logger.debug(f"   💾 Query attempt 1: Looking for files in version {current_version}")
                existing_files = (
                    db.query(RawFile).filter(RawFile.data_source_id == datasource_id, RawFile.version == current_version).all()
                )
                logger.debug(f"   ✓ Query result: Found {len(existing_files)} files in version {current_version}")

                # If no files found in current_version, try version 1 (common case when product is new)
                if len(existing_files) == 0 and current_version != 1:
                    logger.debug(f"   💾 Query attempt 2: No files in {current_version}, trying version 1")
                    existing_files = (
                        db.query(RawFile).filter(RawFile.data_source_id == datasource_id, RawFile.version == 1).all()
                    )
                    logger.debug(f"   ✓ Query result: Found {len(existing_files)} files in version 1")
                    if len(existing_files) > 0:
                        current_version = 1  # Update to use version 1 for the rest of the logic

                # If still no files, try any version (last resort)
                if len(existing_files) == 0:
                    logger.debug(f"   💾 Query attempt 3: No files found, searching any version...")
                    any_version_files = (
                        db.query(RawFile)
                        .filter(RawFile.data_source_id == datasource_id)
                        .order_by(RawFile.version.desc())
                        .limit(1)
                        .all()
                    )
                    logger.debug(f"   ✓ Query result: Found {len(any_version_files)} file(s) across any version")

                    if any_version_files:
                        # Use the version of the most recent file
                        found_file = any_version_files[0]
                        current_version = found_file.version
                        logger.debug(f"   📋 Using version {current_version} from file: {found_file.filename}")

                        logger.debug(f"   💾 Query attempt 4: Fetching all files in version {current_version}")
                        existing_files = (
                            db.query(RawFile)
                            .filter(RawFile.data_source_id == datasource_id, RawFile.version == current_version)
                            .all()
                        )
                        logger.debug(f"   ✓ Query result: Found {len(existing_files)} file(s) in version {current_version}")
                    else:
                        logger.warning(f"   ❌ No files found for datasource {datasource_id} in any version!")
                        # Check if ANY files exist for this datasource at all
                        total_files = db.query(RawFile).filter(RawFile.data_source_id == datasource_id).count()
                        logger.debug(f"   📊 Total files for datasource {datasource_id}: {total_files}")

                logger.debug(f"   📊 Upload mode: Final count = {len(existing_files)} files from version {current_version}")

                if len(existing_files) == 0:
                    logger.warning(f"   ⚠️ No RawFile records found. Checking storage directly...")
                    # Fallback: List files directly from storage (in case files exist but RawFile records don't)
                    try:
                        raw_bucket = BucketRegistry.get_bucket(BucketType.RAW)
                        storage_objects = storage_client.list_objects(raw_bucket, output_prefix)
                        logger.debug(f"   💾 Storage query: Found {len(storage_objects)} objects with prefix {output_prefix}")

                        if len(storage_objects) > 0:
                            # Convert storage objects to files_processed format
                            files_processed = []
                            total_bytes = 0

                            for obj in storage_objects:
                                object_key = obj.get("name", "")
                                if object_key.startswith(output_prefix):
                                    filename = object_key[len(output_prefix) :]
                                else:
                                    filename = Path(object_key).name

                                file_size = obj.get("size", 0)
                                files_processed.append(
                                    {
                                        "path": filename,
                                        "key": object_key,
                                        "size": file_size,
                                        "content_type": obj.get("content_type", "application/octet-stream"),
                                    }
                                )
                                total_bytes += file_size

                            logger.debug(f"   📊 Converted {len(files_processed)} storage objects to files_processed format")

                            result = {
                                "files": len(files_processed),
                                "bytes": total_bytes,
                                "errors": 0,
                                "duration": 0.0,
                                "details": {
                                    "files_processed": files_processed,
                                    "files_failed": [],
                                    "files_skipped": [],
                                    "message": f"Found {len(files_processed)} files in storage (no database records found)",
                                },
                            }
                        else:
                            logger.error(f"   ❌ No files found in storage or database for datasource {datasource_id}")
                            # Return empty result
                            result = {
                                "files": 0,
                                "bytes": 0,
                                "errors": 0,
                                "duration": 0.0,
                                "details": {
                                    "files_processed": [],
                                    "files_failed": [],
                                    "files_skipped": [],
                                    "message": "No files found. Please upload files first using the upload endpoint.",
                                },
                            }
                    except Exception as e:
                        logger.error(f"   ❌ Error listing files from storage: {e}", exc_info=True)
                        # Return empty result
                        result = {
                            "files": 0,
                            "bytes": 0,
                            "errors": 0,
                            "duration": 0.0,
                            "details": {
                                "files_processed": [],
                                "files_failed": [],
                                "files_skipped": [],
                                "message": f"Error checking storage: {str(e)}",
                            },
                        }
                else:
                    # Convert RawFile records to sync result format
                    logger.debug(f"   📋 Converting {len(existing_files)} RawFile records to sync result format")
                    files_processed = []
                    total_bytes = 0

                    for raw_file in existing_files:
                        # For the new version, we need to copy the file to the new version's prefix
                        # Generate new key with new version prefix
                        old_key = raw_file.storage_key
                        # Extract filename from old key
                        old_prefix = raw_prefix(datasource.workspace_id, datasource.product_id, current_version)
                        if old_key.startswith(old_prefix):
                            filename = old_key[len(old_prefix) :]
                        else:
                            filename = Path(old_key).name

                        new_key = f"{output_prefix}{filename}"

                        # Copy file to new version location if versions differ
                        file_checksum = raw_file.file_checksum  # Use existing checksum if available
                        if version != current_version:
                            try:
                                logger.debug(f"   📋 Copying file: {old_key} -> {new_key}")
                                logger.debug(f"       Source: {raw_bucket}/{old_key}")
                                logger.debug(f"       Destination: {raw_bucket}/{new_key}")
                                # Copy from old location to new location
                                raw_bucket = BucketRegistry.get_bucket(BucketType.RAW)
                                old_content = storage_client.get_bytes(raw_bucket, old_key)
                                logger.debug(f"       ✓ Successfully read {len(old_content)} bytes from source")
                                if old_content:
                                    # Calculate checksum from content if not already available
                                    if not file_checksum:
                                        file_checksum = calculate_checksum(old_content, algorithm="sha256")

                                    storage_client.put_bytes(
                                        raw_bucket,
                                        new_key,
                                        old_content,
                                        raw_file.content_type or "application/octet-stream",
                                    )
                                    logger.debug(f"   ✓ File copied successfully")
                            except Exception as e:
                                logger.warning(f"   ⚠️ Failed to copy file {old_key} to {new_key}: {e}")
                                # Continue anyway - we'll use the old key
                                new_key = old_key
                                # If we couldn't copy, use the old file's checksum
                                file_checksum = raw_file.file_checksum

                        files_processed.append(
                            {
                                "path": raw_file.filename,  # Use filename as path
                                "key": new_key,  # Use new key for new version
                                "size": raw_file.file_size or 0,
                                "content_type": raw_file.content_type or "application/octet-stream",
                                "checksum": file_checksum,  # Include checksum in file_info
                            }
                        )
                        total_bytes += raw_file.file_size or 0

                    logger.debug(f"   📊 Conversion complete: {len(files_processed)} files, {total_bytes} bytes total")

                    # Create result in the same format as connector.sync_full
                    result = {
                        "files": len(files_processed),
                        "bytes": total_bytes,
                        "errors": 0,
                        "duration": 0.0,
                        "details": {
                            "files_processed": files_processed,
                            "files_failed": [],
                            "files_skipped": [],
                            "message": f"Found {len(files_processed)} previously uploaded files from version {current_version}",
                        },
                    }
            else:
                # Normal folder sync from server path
                logger.debug(f"   📂 Path mode: syncing from root_path={root_path}")
                if "path" in config and "root_path" not in config:
                    config["root_path"] = config["path"]

                # Convert 'file_types' to 'include' patterns
                if "file_types" in config and "include" not in config:
                    file_types = config["file_types"]
                    if isinstance(file_types, str):
                        # Split comma-separated file types
                        config["include"] = [ft.strip() for ft in file_types.split(",") if ft.strip()]
                    elif isinstance(file_types, list):
                        config["include"] = file_types
                    else:
                        config["include"] = ["*"]  # Default to all files
                    logger.debug(f"   ✓ Configured file_types filters: {config['include']}")

                logger.debug(f"   📋 Creating FolderConnector and syncing")
                connector = FolderConnector(config)
                raw_bucket = BucketRegistry.get_bucket(BucketType.RAW)
                result = connector.sync_full(raw_bucket, output_prefix)
                logger.debug(f"   💾 Folder connector result: files={result.get('files', 0)}, bytes={result.get('bytes', 0)}")

        elif datasource.type == DataSourceType.AWS_S3:
            logger.debug(f"   📨 AWS S3 connector mode")
            connector = S3Connector(normalized_config)
            raw_bucket = BucketRegistry.get_bucket(BucketType.RAW)
            result = connector.sync_full(raw_bucket, output_prefix)
            logger.debug(f"   💾 S3 connector result: files={result.get('files', 0)}, bytes={result.get('bytes', 0)}")

        elif datasource.type == DataSourceType.AZURE_BLOB:
            logger.debug(f"   📨 Azure Blob connector mode")
            connector = AzureBlobConnector(normalized_config)
            raw_bucket = BucketRegistry.get_bucket(BucketType.RAW)
            result = connector.sync_full(raw_bucket, output_prefix)
            logger.debug(f"   💾 Azure Blob connector result: files={result.get('files', 0)}, bytes={result.get('bytes', 0)}")

        else:
            logger.error(f"   ❌ Unsupported datasource type: {datasource.type.value}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Sync not supported for data source type: {datasource.type.value}",
            )

        logger.debug(f"   ✓ Step 4 complete: Connector sync completed successfully")

        # Check raw files size limit before creating RawFile records
        logger.debug(f"   📋 Step 5: Checking raw files size limits")
        from primedata.db.models import BillingProfile

        billing_profile = db.query(BillingProfile).filter(
            BillingProfile.workspace_id == datasource.workspace_id
        ).first()

        if billing_profile:
            plan_name = billing_profile.plan.value.lower() if hasattr(billing_profile.plan, "value") else str(billing_profile.plan).lower()
            max_size_mb = get_plan_limit(plan_name, "max_raw_files_size_mb")
            logger.debug(f"   💾 Billing profile found: plan={plan_name}, max_size_mb={max_size_mb}")

            if max_size_mb != -1:  # If not unlimited
                # Calculate current workspace total size
                current_size_mb = calculate_workspace_raw_files_size_mb(str(datasource.workspace_id), db)

                # Calculate new files size from sync result (bytes to MB)
                new_files_bytes = result.get("bytes", 0)
                new_files_size_mb = new_files_bytes / (1024 * 1024)

                # Check if adding new files would exceed limit
                total_size_mb = current_size_mb + new_files_size_mb

                logger.debug(f"   📊 Size check: current={current_size_mb:.2f}MB + new={new_files_size_mb:.2f}MB = total={total_size_mb:.2f}MB (limit={max_size_mb}MB)")

                if total_size_mb > max_size_mb:
                    logger.warning(f"   ❌ Size limit exceeded: {total_size_mb:.2f}MB > {max_size_mb}MB")
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Raw files size limit exceeded. Current usage: {current_size_mb:.2f} MB, "
                               f"adding {new_files_size_mb:.2f} MB would exceed the limit of {max_size_mb} MB. "
                               f"Please upgrade your plan or remove some files."
                    )
                logger.debug(f"   ✓ Size check passed")
        else:
            logger.debug(f"   ℹ️ No billing profile found, skipping size limit check")

        logger.debug(f"   ✓ Step 5 complete: Size limit validation passed")

        logger.debug(f"   ✓ Step 5 complete: Size limit validation passed")

        # Store raw file records in database
        logger.debug(f"   📋 Step 6: Processing and storing RawFile records")
        details = result.get("details", {})

        # Handle both folder connector (files_processed) and web connector (urls_processed)
        files_processed = details.get("files_processed", [])
        urls_processed = details.get("urls_processed", [])

        files_created = 0
        logger.debug(f"   📊 Files to process: {len(files_processed)} from connector, {len(urls_processed)} from URLs")

        # Process folder connector files
        for file_info in files_processed:
            try:
                # Extract file stem from the original path or storage key
                file_path = file_info.get("path", "")
                source_key = file_info.get("key", "")  # Key in SOURCE bucket
                storage_key = file_info.get("storage_key", "")  # Key in DESTINATION bucket

                # Get file stem (filename without extension)
                if file_path:
                    file_stem = Path(file_path).stem
                    filename = Path(file_path).name
                elif storage_key:
                    # Extract from storage key if path not available
                    filename = Path(storage_key).name
                    file_stem = Path(storage_key).stem
                else:
                    logger.debug(f"   ⚠️ Skipping file_info with no path or storage_key")
                    continue

                logger.debug(f"   📋 Processing file: {filename} (stem={file_stem})")
                logger.debug(f"       Source key (in source bucket): {source_key}")
                logger.debug(f"       Storage key (in destination bucket): {storage_key}")

                # Check if file already exists (avoid duplicates)
                existing = (
                    db.query(RawFile)
                    .filter(
                        RawFile.product_id == datasource.product_id, RawFile.version == version, RawFile.file_stem == file_stem
                    )
                    .first()
                )

                if not existing:
                    # Calculate checksum from file in storage
                    file_checksum = file_info.get("checksum")  # Check if connector provided checksum
                    if not file_checksum and storage_key:
                        logger.debug(f"   📋 Calculating checksum for {storage_key}")
                        logger.debug(f"       Reading from destination bucket={raw_bucket}, key={storage_key}")
                        try:
                            # Download file to calculate checksum
                            raw_bucket = BucketRegistry.get_bucket(BucketType.RAW)
                            logger.debug(f"       Resolved bucket from registry: {raw_bucket}")
                            file_content = storage_client.get_bytes(raw_bucket, storage_key)
                            if file_content:
                                file_checksum = calculate_checksum(file_content, algorithm="sha256")
                                logger.debug(f"   ✓ Checksum calculated: {file_checksum[:16]}...")
                            else:
                                # Fallback: use a placeholder if we can't read the file
                                logger.warning(f"   ⚠️ Could not read file {storage_key} to calculate checksum")
                                file_checksum = ""  # This will fail, but at least we tried
                        except Exception as e:
                            logger.warning(f"   ⚠️ Failed to calculate checksum for {storage_key}: {e}")
                            logger.warning(f"       Bucket={raw_bucket}, Key={storage_key}")
                            logger.warning(f"       Error type: {type(e).__name__}")
                            file_checksum = ""  # This will fail, but at least we tried

                    if not file_checksum:
                        logger.error(f"   ❌ Could not determine checksum for file {storage_key}")
                        raise ValueError(f"Could not determine checksum for file {storage_key}")

                    logger.debug(f"   💾 Creating RawFile record: filename={filename}, size={file_info.get('size', 0)}")
                    raw_bucket = BucketRegistry.get_bucket(BucketType.RAW)
                    raw_file = RawFile(
                        workspace_id=datasource.workspace_id,
                        product_id=datasource.product_id,
                        data_source_id=datasource.id,
                        version=version,
                        filename=filename,
                        file_stem=file_stem,
                        storage_key=storage_key,
                        storage_bucket=raw_bucket,
                        file_size=file_info.get("size", 0),
                        content_type=file_info.get("content_type", "application/octet-stream"),
                        status=RawFileStatus.INGESTED,
                        file_checksum=file_checksum,
                    )
                    db.add(raw_file)
                    files_created += 1
                    logger.debug(f"   ✓ RawFile created and queued for database (total queued: {files_created})")

                else:
                    logger.debug(f"   ℹ️ RawFile already exists for {file_stem}, skipping duplicate")

            except Exception as e:
                # Log error but don't fail the entire sync
                logger.warning(f"   ⚠️ Failed to store raw file record: {e}")

        # Process web connector files (URLs)
        for url_info in urls_processed:
            try:
                filename = url_info.get("filename", "")
                if not filename:
                    logger.debug(f"   ⚠️ Skipping URL file with no filename")
                    continue

                logger.debug(f"   📋 Processing URL file: {filename}")

                # Generate storage key from prefix and filename
                storage_key = f"{output_prefix}{filename}"
                file_stem = Path(filename).stem

                # Check if file already exists (avoid duplicates)
                existing = (
                    db.query(RawFile)
                    .filter(
                        RawFile.product_id == datasource.product_id, RawFile.version == version, RawFile.file_stem == file_stem
                    )
                    .first()
                )

                if not existing:
                    # Calculate checksum from file in storage
                    file_checksum = url_info.get("checksum")  # Check if connector provided checksum
                    if not file_checksum:
                        logger.debug(f"   📋 Calculating checksum for URL file {storage_key}")
                        logger.debug(f"       Reading from bucket={raw_bucket}, key={storage_key}")
                        try:
                            # Download file to calculate checksum
                            raw_bucket = BucketRegistry.get_bucket(BucketType.RAW)
                            logger.debug(f"       Resolved bucket from registry: {raw_bucket}")
                            file_content = storage_client.get_bytes(raw_bucket, storage_key)
                            if file_content:
                                file_checksum = calculate_checksum(file_content, algorithm="sha256")
                                logger.debug(f"   ✓ Checksum calculated: {file_checksum[:16]}...")
                            else:
                                logger.warning(f"   ⚠️ Could not read URL file {storage_key} to calculate checksum")
                                file_checksum = ""
                        except Exception as e:
                            logger.warning(f"   ⚠️ Failed to calculate checksum for URL file {storage_key}: {e}")
                            logger.warning(f"       Bucket={raw_bucket}, Key={storage_key}")
                            logger.warning(f"       Error type: {type(e).__name__}")
                            file_checksum = ""

                    if not file_checksum:
                        logger.error(f"   ❌ Could not determine checksum for URL file {storage_key}")
                        raise ValueError(f"Could not determine checksum for file {storage_key}")

                    logger.debug(f"   💾 Creating RawFile record for URL: filename={filename}, size={url_info.get('size', 0)}")
                    raw_bucket = BucketRegistry.get_bucket(BucketType.RAW)
                    raw_file = RawFile(
                        workspace_id=datasource.workspace_id,
                        product_id=datasource.product_id,
                        data_source_id=datasource.id,
                        version=version,
                        filename=filename,
                        file_stem=file_stem,
                        storage_key=storage_key,
                        storage_bucket=raw_bucket,
                        file_size=url_info.get("size", 0),
                        content_type="text/html",  # Web connector stores HTML
                        status=RawFileStatus.INGESTED,
                        file_checksum=file_checksum,
                    )
                    db.add(raw_file)
                    files_created += 1
                    logger.debug(f"   ✓ RawFile created for URL and queued for database (total queued: {files_created})")

                else:
                    logger.debug(f"   ℹ️ RawFile already exists for URL {file_stem}, skipping duplicate")

            except Exception as e:
                # Log error but don't fail the entire sync
                logger.warning(f"   ⚠️ Failed to store raw file record from URL: {e}")

        # Update product version if this was a new version
        logger.debug(f"   📋 Step 7: Finalizing product and datasource records")
        if version > (product.current_version or 0):
            logger.debug(f"   📋 Updating product version: {product.current_version} -> {version}")
            product.current_version = version
            logger.debug(f"   ✓ Product version updated")

        # Update data source last_cursor with sync details
        logger.debug(f"   📋 Updating datasource last_cursor with sync metadata")
        datasource.last_cursor = {
            "last_sync_at": datetime.utcnow().isoformat(),
            "version": version,
            "files_synced": result["files"],
            "bytes_synced": result["bytes"],
            "errors": result["errors"],
            "files_created": files_created,
        }
        logger.debug(f"   ✓ Datasource last_cursor updated | files_synced={result['files']}, files_created={files_created}")

        logger.debug(f"   📋 Step 8: Committing all changes to database")
        db.commit()
        logger.debug(f"   💾 All changes committed successfully")

        logger.info(f"✅ SYNC_FULL: SUCCESS | version={version}, files={result['files']}, bytes={result['bytes']}, files_created={files_created}, errors={result['errors']}")

        return SyncFullResponse(
            version=version,
            files=result["files"],
            bytes=result["bytes"],
            errors=result["errors"],
            duration=result["duration"],
            prefix=output_prefix,
            details=result["details"],
        )

    except HTTPException:
        db.rollback()
        logger.debug(f"   ❌ SYNC_FULL: HTTP exception raised, rolling back and propagating")
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"   ❌ SYNC_FULL: FAILED | datasource_id={datasource_id}, error={str(e)}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Sync failed: {str(e)}")
