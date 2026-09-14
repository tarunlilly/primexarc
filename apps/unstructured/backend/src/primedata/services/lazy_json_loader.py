"""
Lazy JSON loader service for PrimeData.

Provides transparent loading of JSON fields from either PostgreSQL or S3,
maintaining backward compatibility during the migration.
"""

from typing import Any, Dict, Optional
from uuid import UUID

from primedata.utils.log_utils import get_logger

logger = get_logger(__name__)
from primedata.services.s3_json_storage import load_json_from_s3
from primedata.storage.storage_client import storage_client


def load_product_json_field(product: Any, field_name: str) -> Optional[Any]:
    """Load product JSON field from S3 if path exists, else from DB.

    This function provides backward compatibility:
    - If S3 path exists (e.g., chunk_metrics_path), load from S3
    - Else if DB field exists (e.g., chunk_metrics), return from DB
    - Else return None

    Args:
        product: Product SQLAlchemy model instance
        field_name: Name of the field (e.g., "chunk_metrics", "readiness_fingerprint")

    Returns:
        JSON data (dict/list) or None
    """
    logger.info(f"📦 load_product_json_field ENTRY | product_id={product.id if hasattr(product, 'id') else 'unknown'} | field_name={field_name}")

    try:
        # Check for S3 path field (e.g., chunk_metrics_path)
        path_field_name = f"{field_name}_path"
        s3_path = getattr(product, path_field_name, None)

        logger.debug(f"📋 Checking for S3 path | field={path_field_name} | has_path={s3_path is not None}")

        if s3_path:
            # Load from S3
            logger.debug(f"📦 Loading {field_name} from S3 | path={s3_path}")
            data = load_json_from_s3(s3_path)
            logger.info(f"✅ load_product_json_field | product_id={product.id if hasattr(product, 'id') else 'unknown'} | field_name={field_name} | source=S3 | loaded={data is not None}")
            return data

        # Fallback to DB field
        logger.debug(f"📋 S3 path not found, checking DB field | field={field_name}")
        db_field = getattr(product, field_name, None)
        if db_field is not None:
            logger.debug(f"💾 Loading {field_name} from DB")
            logger.info(f"✅ load_product_json_field | product_id={product.id if hasattr(product, 'id') else 'unknown'} | field_name={field_name} | source=DB")
            return db_field

        # Field doesn't exist
        logger.warning(f"📦 load_product_json_field | field {field_name} not found in S3 or DB")
        return None
    except Exception as e:
        logger.error(f"❌ load_product_json_field | product_id={product.id if hasattr(product, 'id') else 'unknown'} | field_name={field_name} | error={str(e)}", exc_info=True)
        return None


def load_pipeline_run_metrics(pipeline_run: Any) -> Dict[str, Any]:
    """Load pipeline run metrics from S3 if archived, else from DB.

    Args:
        pipeline_run: PipelineRun SQLAlchemy model instance

    Returns:
        Metrics dictionary (empty dict if not found)
    """
    logger.info(f"📦 load_pipeline_run_metrics ENTRY | pipeline_run_id={pipeline_run.id if hasattr(pipeline_run, 'id') else 'unknown'}")

    try:
        # Check if metrics are archived to S3
        metrics_path = getattr(pipeline_run, "metrics_path", None)
        logger.debug(f"📋 Checking for S3 metrics | has_metrics_path={metrics_path is not None}")

        if metrics_path:
            logger.debug(f"📦 Loading metrics from S3 | path={metrics_path}")
            metrics = load_json_from_s3(metrics_path)
            if metrics is not None:
                logger.info(f"✅ load_pipeline_run_metrics | pipeline_run_id={pipeline_run.id if hasattr(pipeline_run, 'id') else 'unknown'} | source=S3 | metrics_keys={len(metrics) if isinstance(metrics, dict) else 'N/A'}")
                return metrics

        # Fallback to DB field
        logger.debug(f"📋 S3 path not found, checking DB field")
        db_metrics = getattr(pipeline_run, "metrics", None)
        if db_metrics:
            logger.debug(f"💾 Loading metrics from DB")
            result = db_metrics if isinstance(db_metrics, dict) else {}
            logger.info(f"✅ load_pipeline_run_metrics | pipeline_run_id={pipeline_run.id if hasattr(pipeline_run, 'id') else 'unknown'} | source=DB | metrics_keys={len(result)}")
            return result

        # Return empty dict if not found
        logger.warning(f"📦 load_pipeline_run_metrics | metrics not found in S3 or DB")
        return {}
    except Exception as e:
        logger.error(f"❌ load_pipeline_run_metrics | pipeline_run_id={pipeline_run.id if hasattr(pipeline_run, 'id') else 'unknown'} | error={str(e)}", exc_info=True)
        return {}


def save_product_json_field_with_auto_storage(
    product: Any,
    field_name: str,
    data: Any,
    threshold: int = 1024 * 1024,  # 1MB default
) -> bool:
    """Save product JSON field, automatically choosing DB or S3 based on size.

    Updates both the DB field and S3 path field as needed.

    Args:
        product: Product SQLAlchemy model instance
        field_name: Name of the field
        data: Python object to save
        threshold: Size threshold for S3 storage

    Returns:
        True if successful, False otherwise
    """
    logger.info(f"📦 save_product_json_field_with_auto_storage ENTRY | product_id={product.id if hasattr(product, 'id') else 'unknown'} | field_name={field_name} | threshold={threshold} bytes")

    try:
        from primedata.services.s3_json_storage import save_json_to_s3, should_save_to_s3

        # Determine if should save to S3
        logger.debug(f"📋 Evaluating storage destination for {field_name}")
        if should_save_to_s3(data, threshold):
            # Save to S3
            logger.debug(f"📦 Data size exceeds threshold, saving to S3")
            s3_path = save_json_to_s3(product.workspace_id, product.id, field_name, data)
            if s3_path:
                # Update S3 path field
                path_field_name = f"{field_name}_path"
                setattr(product, path_field_name, s3_path)
                # Clear DB field
                setattr(product, field_name, None)
                logger.info(f"✅ save_product_json_field_with_auto_storage | product_id={product.id if hasattr(product, 'id') else 'unknown'} | field_name={field_name} | destination=S3 | path={s3_path}")
                return True
            else:
                logger.warning(f"📦 Failed to save {field_name} to S3, keeping in DB")
                # Fallback: save to DB
                setattr(product, field_name, data)
                return False
        else:
            # Save to DB
            logger.debug(f"💾 Data size within threshold, saving to DB")
            setattr(product, field_name, data)
            # Clear S3 path if exists
            path_field_name = f"{field_name}_path"
            if hasattr(product, path_field_name):
                setattr(product, path_field_name, None)
            logger.info(f"✅ save_product_json_field_with_auto_storage | product_id={product.id if hasattr(product, 'id') else 'unknown'} | field_name={field_name} | destination=DB")
            return True
    except Exception as e:
        logger.error(f"❌ save_product_json_field_with_auto_storage | product_id={product.id if hasattr(product, 'id') else 'unknown'} | field_name={field_name} | error={str(e)}", exc_info=True)
        return False



