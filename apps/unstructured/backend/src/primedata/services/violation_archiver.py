"""
Violation archiver service for PrimeData.

Archives old data quality violations to S3 to reduce PostgreSQL storage costs.
"""

import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

from primedata.utils.log_utils import get_logger

logger = get_logger(__name__)
from primedata.db.models import DqViolation
from primedata.services.s3_json_storage import METADATA_BUCKET, METADATA_PATH, save_json_to_s3
from primedata.storage.storage_client import storage_client
from sqlalchemy import and_
from sqlalchemy.orm import Session


def archive_old_violations(
    db: Session, days: int = 90, batch_size: int = 1000, hard_delete: bool = False
) -> dict:
    """Archive violations older than specified days to S3.

    Args:
        db: Database session
        days: Number of days to keep violations in DB (default: 90)
        batch_size: Number of violations to process per batch (default: 1000)
        hard_delete: If True, delete from DB after archiving (default: False)

    Returns:
        Dictionary with archiving statistics
    """
    logger.info(f"🗑️ archive_old_violations() ENTRY: days={days}, batch_size={batch_size}, hard_delete={hard_delete}")
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    logger.debug(f"📋 Cutoff date: {cutoff_date.isoformat()}")

    # Find violations older than cutoff that haven't been archived yet
    logger.debug(f"📋 Querying violations older than {days} days")
    violations_to_archive = (
        db.query(DqViolation)
        .filter(and_(DqViolation.created_at < cutoff_date, DqViolation.archived_to_s3 == False))  # Not yet archived
        .limit(batch_size)
        .all()
    )

    logger.info(f"✅ Found {len(violations_to_archive)} violations to archive")

    archived_count = 0
    failed_count = 0
    deleted_count = 0

    # Group violations by product_id and version for efficient archiving
    logger.debug(f"📋 Grouping violations by product_id and version")
    violations_by_product = {}
    for violation in violations_to_archive:
        key = (violation.product_id, violation.version)
        if key not in violations_by_product:
            violations_by_product[key] = []
        violations_by_product[key].append(violation)

    logger.debug(f"✓ Grouped into {len(violations_by_product)} product/version combinations")

    for (product_id, version), violations in violations_by_product.items():
        try:
            logger.debug(f"📋 Processing {len(violations)} violations for product {product_id} v{version}")
            # Convert violations to JSON-serializable format
            violations_data = []
            for v in violations:
                violations_data.append(
                    {
                        "id": str(v.id),
                        "product_id": str(v.product_id),
                        "version": v.version,
                        "pipeline_run_id": str(v.pipeline_run_id) if v.pipeline_run_id else None,
                        "rule_name": v.rule_name,
                        "rule_type": v.rule_type,
                        "severity": v.severity.value,
                        "message": v.message,
                        "details": v.details,
                        "affected_count": v.affected_count,
                        "total_count": v.total_count,
                        "violation_rate": v.violation_rate,
                        "created_at": v.created_at.isoformat() if v.created_at else None,
                    }
                )

            # Save to S3 as JSON under METADATA_PATH
            # Path: {METADATA_PATH}/{workspace_id}/prod/{product_id}/v/{version}/violations/{timestamp}.json
            from primedata.db.models import Product

            product = db.query(Product).filter(Product.id == product_id).first()
            if not product:
                logger.warning(f"⚠️ Product {product_id} not found, skipping violations")
                failed_count += len(violations)
                continue

            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            s3_key = f"{METADATA_PATH}/{product.workspace_id}/prod/{product_id}/v/{version}/violations/archived_{timestamp}.json"

            logger.debug(f"📋 Saving to S3: {s3_key}")
            success = storage_client.put_json(METADATA_BUCKET, s3_key, violations_data)

            if success:
                # Mark violations as archived
                for v in violations:
                    v.archived_to_s3 = True
                    v.archived_at = datetime.utcnow()

                archived_count += len(violations)

                # Hard delete if requested
                if hard_delete:
                    logger.debug(f"📋 Hard-deleting {len(violations)} violations")
                    for v in violations:
                        db.delete(v)
                    deleted_count += len(violations)

                logger.info(f"✅ Archived {len(violations)} violations for product {product_id} v{version} to S3: {s3_key}")
            else:
                failed_count += len(violations)
                logger.error(f"❌ Failed to archive violations for product {product_id} v{version}")
        except Exception as e:
            failed_count += len(violations)
            logger.error(f"❌ Error archiving violations for product {product_id} v{version}: {e}", exc_info=True)

    # Commit all changes
    if archived_count > 0:
        logger.debug(f"📋 Committing changes to database")
        db.commit()
        logger.info(f"✅ Archived {archived_count} violations, failed {failed_count}, deleted {deleted_count}")

    return {
        "archived_count": archived_count,
        "failed_count": failed_count,
        "deleted_count": deleted_count,
        "cutoff_date": cutoff_date.isoformat(),
    }


def load_archived_violations(product_id: UUID, version: int) -> List[Dict[str, Any]]:
    """Load archived violations from S3 for a product/version.

    Args:
        product_id: Product UUID
        version: Version number

    Returns:
        List of violation dictionaries
    """
    logger.info(f"🗑️ load_archived_violations() ENTRY: product_id={product_id}, version={version}")

    try:
        from primedata.db.database import get_db
        from primedata.db.models import Product

        db = next(get_db())
        logger.debug(f"📋 Looking up product {product_id}")
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            logger.error(f"❌ Product {product_id} not found")
            return []

        # List all archived violation files for this product/version
        prefix = f"{METADATA_PATH}/{product.workspace_id}/prod/{product_id}/v/{version}/violations/"
        logger.debug(f"📋 Listing S3 objects under: {prefix}")
        objects = storage_client.list_objects(METADATA_BUCKET, prefix=prefix)

        all_violations = []
        objects_count = 0
        for obj in objects:
            if obj["name"].startswith(prefix) and "archived_" in obj["name"]:
                logger.debug(f"📋 Loading violations from: {obj['name']}")
                violations = storage_client.get_json(METADATA_BUCKET, obj["name"])
                if violations:
                    all_violations.extend(violations)
                    objects_count += 1

        logger.info(f"✅ load_archived_violations() EXIT: Loaded {len(all_violations)} violations from {objects_count} archives")
        return all_violations
    except Exception as e:
        logger.error(f"❌ Error loading archived violations for product {product_id} v{version}: {e}", exc_info=True)
        return []



