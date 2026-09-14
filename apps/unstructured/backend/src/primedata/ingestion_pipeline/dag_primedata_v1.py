"""
PrimeData Pipeline DAG v1

This DAG orchestrates the complete data processing pipeline:
1. Ingest from data sources to raw storage
2. Preprocess and clean data
3. Chunk documents
4. Generate embeddings
5. Index to Qdrant
6. Validate and finalize
"""

import json
import logging
import os

# Import PrimeData modules
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

from airflow import DAG
from airflow.models import Variable
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago

sys.path.append("/opt/airflow/dags/primedata")

from primedata.connectors.azure_blob import AzureBlobConnector
from primedata.connectors.folder import FolderConnector
from primedata.connectors.s3 import S3Connector
from primedata.connectors.web import WebConnector
from primedata.db.database import SessionLocal, get_db
from primedata.db.models import DataSource, DataSourceType, DqViolation, PipelineRun, Product, ProductStatus
from primedata.dq.validator import DataQualityValidator
from primedata.indexing.embeddings import EmbeddingGenerator
from primedata.indexing.vector_search_client import get_vector_search_client
from primedata.ingestion_pipeline.aird_stages.config import get_aird_config
from primedata.ingestion_pipeline.aird_stages.storage import AirdStorageAdapter

# AIRD stages integration (M0)
from primedata.ingestion_pipeline.aird_stages.tracking import StageTracker, track_stage_execution
from primedata.storage.storage_client import storage_client
from primedata.storage.paths import chunk_prefix, clean_prefix, embed_prefix, raw_prefix

# Legacy task functions (extracted)
from primedata.ingestion_pipeline.dag_legacy_tasks import (
    chunk as _chunk_impl,
    embed as _embed_impl,
    index_legacy as _index_legacy_impl,
    ingest_from_datasources as _ingest_impl,
    validate as _validate_impl,
    validate_data_quality as _validate_dq_impl,
)

logger = logging.getLogger(__name__)

# Default arguments for the DAG
default_args = {
    "owner": "primedata",
    "depends_on_past": False,
    "start_date": days_ago(1),
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

# Create the DAG
dag = DAG(
    "primedata_simple",
    default_args=default_args,
    description="PrimeData complete pipeline v1",
    schedule_interval=None,  # Manual trigger only
    catchup=False,
    tags=["primedata", "pipeline"],
    params={
        "workspace_id": None,  # Must be provided when triggering the DAG
        "product_id": None,  # Required parameter
        "version": None,  # Will be computed if not provided
        "embedder_name": "azure-openai",  # Default embedder - using Azure OpenAI
        "dim": 1536,  # Default embedding dimension for text-embedding-3-small
    },
)


def get_dag_params(**context) -> Dict[str, Any]:
    """Extract and validate DAG parameters."""
    logger.info(f"🔄 ENTRY: get_dag_params()")
    params = context["params"]
    logger.debug(f"   📋 Params keys: {list(params.keys())}")

    # Get required parameters
    workspace_id = params.get("workspace_id")
    product_id = params.get("product_id")
    version = params.get("version")

    # Get embedding configuration from backend
    # Backend sends embedding_config with embedder_name and embedding_dimension
    embedding_config = params.get("embedding_config", {})

    # Extract from embedding_config sent by backend (required)
    if embedding_config:
        embedder_name = embedding_config.get("embedder_name")
        dim = int(embedding_config.get("embedding_dimension"))
        deployment_name = embedding_config.get("deployment_name")

        if not embedder_name or not dim:
            raise ValueError("embedding_config must include embedder_name and embedding_dimension")

        # Log embedding model details
        logger.info(f"📊 Airflow DAG: Embedding Configuration Received from Backend")
        logger.info(f"   ├─ Embedder Name: {embedder_name}")
        logger.info(f"   ├─ Embedding Dimension: {dim}")
        if deployment_name:
            logger.info(f"   ├─ Deployment Name: {deployment_name}")

        # If Azure deployment, log additional details
        if "embedding-3" in embedder_name or "ada" in embedder_name or embedder_name == "azure-openai":
            from primedata.core.settings import get_settings
            s = get_settings()
            logger.info(f"   ├─ Provider: Azure OpenAI")
            logger.info(f"   ├─ Endpoint: {s.AZURE_OPENAI_ENDPOINT}")
            logger.info(f"   ├─ API Version: {s.AZURE_OPENAI_API_VERSION}")
            logger.info(f"   └─ Auth: Service Principal (Client Credentials via Graph API)")

        logger.debug(f"Full config: {embedding_config}")
    else:
        # Fallback to direct params if embedding_config not provided
        embedder_name = params.get("embedder_name")
        dim = int(params.get("dim", 0))
        deployment_name = params.get("deployment_name")

        if not embedder_name or dim <= 0:
            raise ValueError("Either embedding_config or (embedder_name + dim) must be provided in DAG params")
        logger.info(f"📋 Using direct params: embedder_name={embedder_name}, dim={dim}")

    # Get chunking configuration
    chunking_config = params.get(
        "chunking_config",
        {
            "chunk_size": 1000,
            "chunk_overlap": 200,
            "min_chunk_size": 100,
            "max_chunk_size": 2000,
            "chunking_strategy": "fixed_size",
        },
    )

    # Get AIRD-specific parameters (M0)
    playbook_id = params.get("playbook_id")  # Optional playbook override
    logger.debug(f"   📋 Extracted: workspace_id={workspace_id}, product_id={product_id}, version={version}")
    logger.debug(f"   📋 Chunking strategy: {chunking_config.get('chunking_strategy')}")

    if not product_id:
        error_msg = "product_id parameter is required"
        logger.error(f"   ❌ {error_msg}")
        raise ValueError(error_msg)

    # Log embedding model configuration with visual indicators
    logger.info(f"📊 EMBEDDING CONFIGURATION:")
    logger.info(f"   Model: {embedder_name}")
    logger.info(f"   Dimension: {dim}")
    if embedder_name == "azure-openai":
        logger.info(f"   Provider: Azure OpenAI ☁️")
        logger.info(f"   Authentication: Service Principal (Graph API) 🔐")
    elif embedder_name == "minilm":
        logger.info(f"   Provider: Local (fastembed) 📦")
    elif embedder_name == "openai":
        logger.info(f"   Provider: OpenAI 🔑")

    logger.info(
        f"✅ EXIT: get_dag_params() -> workspace_id={workspace_id}, product_id={product_id}, version={version}, embedder={embedder_name}, dim={dim}"
    )
    if playbook_id:
        logger.debug(f"   📋 AIRD playbook: {playbook_id}")

    return {
        "workspace_id": workspace_id,
        "product_id": product_id,
        "version": version,
        "embedder_name": embedder_name,
        "dim": dim,
        "deployment_name": deployment_name,
        "chunking_config": chunking_config,
        "playbook_id": playbook_id,  # AIRD playbook parameter
    }


def get_aird_context(**context) -> Dict[str, Any]:
    """Get AIRD stage execution context.

    This helper function provides context for AIRD stages including:
    - Pipeline parameters
    - Storage adapter
    - Database session
    - Pipeline run tracking

    Args:
        context: Airflow task context

    Returns:
        Dictionary with AIRD context (storage, tracker, config, etc.)
    """
    logger.info(f"🔄 ENTRY: get_aird_context()")
    params = get_dag_params(**context)
    workspace_id = params["workspace_id"]
    product_id = params["product_id"]
    version = params["version"]
    logger.debug(f"   📋 workspace_id={workspace_id}, product_id={product_id}, version={version}")

    # Get database session
    logger.debug(f"   💾 Creating database session")
    db = next(get_db())

    # Get pipeline run
    logger.debug(f"   💾 Querying pipeline run")
    pipeline_run = db.query(PipelineRun).filter(PipelineRun.product_id == product_id, PipelineRun.version == version).first()

    if not pipeline_run:
        logger.warning(f"   ⚠️  Pipeline run not found for product {product_id}, version {version}")
        pipeline_run = None
    else:
        logger.debug(f"   ✅ Found pipeline run {pipeline_run.id}")

    # Create storage adapter
    logger.debug(f"   📁 Creating storage adapter")
    storage = AirdStorageAdapter(
        workspace_id=workspace_id,
        product_id=product_id,
        version=version,
    )

    # Create stage tracker (if pipeline run exists)
    tracker = None
    if pipeline_run:
        logger.debug(f"   📊 Creating stage tracker")
        tracker = StageTracker(db, pipeline_run)

    # Get AIRD config
    logger.debug(f"   📋 Loading AIRD config")
    aird_config = get_aird_config()

    logger.info(f"✅ EXIT: get_aird_context() -> Context ready with storage, tracker, and config")

    return {
        "workspace_id": workspace_id,
        "product_id": product_id,
        "version": version,
        "storage": storage,
        "tracker": tracker,
        "db": db,
        "pipeline_run": pipeline_run,
        "config": aird_config,
        "playbook_id": params.get("playbook_id"),
    }


# Wrapper functions that bind get_dag_params to extracted legacy tasks
def ingest_from_datasources(**context) -> Dict[str, Any]:
    """Ingest data from all data sources to raw storage."""
    return _ingest_impl(get_dag_params, **context)


def chunk(**context) -> Dict[str, Any]:
    """Chunk cleaned documents into smaller pieces."""
    return _chunk_impl(get_dag_params, **context)


def embed(**context) -> Dict[str, Any]:
    """Generate embeddings for chunks."""
    return _embed_impl(get_dag_params, **context)


def index_legacy(**context) -> Dict[str, Any]:
    """Legacy indexing function (kept for backward compatibility)."""
    return _index_legacy_impl(get_dag_params, **context)


def validate(**context) -> Dict[str, Any]:
    """Validate pipeline results and compute metrics."""
    return _validate_impl(get_dag_params, **context)


def validate_data_quality(**context) -> Dict[str, Any]:
    """Validate data quality against configured rules."""
    return _validate_dq_impl(get_dag_params, **context)


def preprocess(**context) -> Dict[str, Any]:
    """Preprocess and clean raw data using AIRD preprocessing stage (M1)."""
    params = get_dag_params(**context)
    workspace_id = params["workspace_id"]
    product_id = params["product_id"]
    version = params["version"]
    playbook_id = params.get("playbook_id")

    logger.info(f"Starting AIRD preprocessing for product {product_id}, version {version}, playbook={playbook_id}")

    # Get AIRD context
    aird_context = get_aird_context(**context)
    storage = aird_context["storage"]
    tracker = aird_context.get("tracker")
    db = aird_context["db"]

    try:
        # Get product to check playbook_id
        product = db.query(Product).filter(Product.id == product_id).first()
        if product and product.playbook_id and not playbook_id:
            playbook_id = product.playbook_id
            logger.info(f"Using playbook from product: {playbook_id}")

        # List raw files from storage
        raw_prefix_path = raw_prefix(workspace_id, product_id, version)
        raw_objects = storage_client.list_objects("primedata-raw", raw_prefix_path)

        if not raw_objects:
            logger.warning(f"No raw files found at {raw_prefix_path}")
            return {"status": "skipped", "message": "No raw files to process", "files_count": 0}

        # Extract file stems (remove .txt extension)
        raw_files = []
        for obj in raw_objects:
            if obj["name"].endswith(".txt"):
                # Extract stem from path like "ws/.../prod/.../v/1/raw/filename.txt"
                stem = Path(obj["name"]).stem
                raw_files.append(stem)

        if not raw_files:
            logger.warning("No .txt files found in raw storage")
            return {"status": "skipped", "message": "No .txt files to process", "files_count": 0}

        logger.info(f"Found {len(raw_files)} raw files to process: {raw_files}")

        # Create preprocessing stage
        from primedata.ingestion_pipeline.aird_stages.preprocess import PreprocessStage

        preprocess_stage = PreprocessStage(
            product_id=product_id,
            version=version,
            workspace_id=workspace_id,
            config={"playbook_id": playbook_id} if playbook_id else {},
        )

        # Execute preprocessing
        stage_context = {
            "storage": storage,
            "raw_files": raw_files,
            "playbook_id": playbook_id,
        }

        result = preprocess_stage.execute(stage_context)

        # Track stage result
        if tracker:
            tracker.record_stage_result(result)

        # Update product preprocessing stats
        if product and result.status.value == "succeeded":
            product.preprocessing_stats = result.metrics
            if playbook_id:
                product.playbook_id = playbook_id
            db.commit()

        logger.info(f"Preprocessing completed: {result.status.value}, chunks={result.metrics.get('total_chunks', 0)}")

        return {
            "status": result.status.value,
            "files_count": result.metrics.get("processed_files", 0),
            "total_chunks": result.metrics.get("total_chunks", 0),
            "playbook_id": result.metrics.get("playbook_id"),
            "mid_sentence_boundary_rate": result.metrics.get("mid_sentence_boundary_rate"),
        }

    except Exception as e:
        logger.error(f"Preprocessing failed: {e}", exc_info=True)
        if tracker:
            from primedata.ingestion_pipeline.aird_stages.base import StageResult, StageStatus

            error_result = StageResult(
                status=StageStatus.FAILED,
                stage_name="preprocess",
                product_id=product_id,
                version=version,
                metrics={},
                error=str(e),
            )
            tracker.record_stage_result(error_result)
        raise
    finally:
        db.close()


def index(**context) -> Dict[str, Any]:
    """Index embeddings to Qdrant using AIRD indexing stage (M4)."""
    params = get_dag_params(**context)
    workspace_id = params["workspace_id"]
    product_id = params["product_id"]
    version = params["version"]

    logger.info(f"Starting AIRD indexing for product {product_id}, version {version}")

    aird_context = get_aird_context(**context)
    storage = aird_context["storage"]
    tracker = aird_context.get("tracker")
    db = aird_context["db"]

    try:
        from primedata.ingestion_pipeline.aird_stages.indexing import IndexingStage

        indexing_stage = IndexingStage(
            product_id=product_id,
            version=version,
            workspace_id=workspace_id,
        )

        # Get processed files from preprocessing
        preprocess_result = context.get("task_instance").xcom_pull(task_ids="preprocess")
        processed_files = preprocess_result.get("processed_file_list", []) if preprocess_result else []

        stage_context = {
            "storage": storage,
            "processed_files": processed_files,
            "preprocess_result": preprocess_result,
            "db": db,  # Pass db from context
        }

        result = indexing_stage.execute(stage_context)

        if tracker:
            tracker.record_stage_result(result)

        logger.info(f"Indexing completed: {result.status.value}, points={result.metrics.get('points_indexed', 0)}")

        return {
            "status": result.status.value,
            "points_indexed": result.metrics.get("points_indexed", 0),
            "collection_name": result.metrics.get("collection_name"),
            "avg_trust_score": result.metrics.get("avg_trust_score", 0.0),
        }

    except Exception as e:
        logger.error(f"Indexing failed: {e}", exc_info=True)
        if tracker:
            from primedata.ingestion_pipeline.aird_stages.base import StageResult, StageStatus

            error_result = StageResult(
                status=StageStatus.FAILED,
                stage_name="indexing",
                product_id=product_id,
                version=version,
                metrics={},
                error=str(e),
            )
            tracker.record_stage_result(error_result)
        raise
    finally:
        db.close()


def score(**context) -> Dict[str, Any]:
    """Score processed chunks using AIRD scoring stage."""
    params = get_dag_params(**context)
    workspace_id = params["workspace_id"]
    product_id = params["product_id"]
    version = params["version"]

    logger.info(f"Starting AIRD scoring for product {product_id}, version {version}")

    aird_context = get_aird_context(**context)
    storage = aird_context["storage"]
    tracker = aird_context.get("tracker")
    db = aird_context["db"]

    try:
        from primedata.ingestion_pipeline.aird_stages.scoring import ScoringStage

        scoring_stage = ScoringStage(
            product_id=product_id,
            version=version,
            workspace_id=workspace_id,
        )

        # Get processed files from preprocessing
        preprocess_result = context.get("task_instance").xcom_pull(task_ids="preprocess")
        processed_files = preprocess_result.get("processed_file_list", []) if preprocess_result else []

        # Load playbook for AI-Ready metrics (noise patterns, coherence settings)
        playbook_id = params.get("playbook_id")
        if not playbook_id:
            # Try to get from product
            from primedata.db.models import Product
            product = db.query(Product).filter(Product.id == product_id).first()
            if product and product.playbook_id:
                playbook_id = product.playbook_id

        playbook = {}
        if playbook_id:
            try:
                from primedata.ingestion_pipeline.aird_stages.playbooks import load_playbook_yaml
                playbook = load_playbook_yaml(playbook_id, workspace_id=str(workspace_id), db_session=db)
                logger.info(f"Loaded playbook {playbook_id} for scoring stage (keys: {list(playbook.keys())[:10]})")
                # Log if AI-Ready sections are present
                if "noise_patterns" in playbook:
                    logger.info(f"Playbook {playbook_id} has noise_patterns section")
                if "coherence" in playbook:
                    logger.info(f"Playbook {playbook_id} has coherence section")
            except Exception as e:
                logger.warning(f"Failed to load playbook {playbook_id}: {e}, using empty playbook", exc_info=True)

        stage_context = {
            "storage": storage,
            "processed_files": processed_files,
            "preprocess_result": preprocess_result,
            "playbook": playbook,
            "playbook_id": playbook_id,
        }

        result = scoring_stage.execute(stage_context)

        if tracker:
            tracker.record_stage_result(result)

        logger.info(f"Scoring completed: {result.status.value}, chunks={result.metrics.get('total_chunks', 0)}")

        return {
            "status": result.status.value,
            "total_chunks": result.metrics.get("total_chunks", 0),
            "avg_trust_score": result.metrics.get("avg_trust_score", 0.0),
        }
    except Exception as e:
        logger.error(f"Scoring failed: {e}", exc_info=True)
        if tracker:
            from primedata.ingestion_pipeline.aird_stages.base import StageResult, StageStatus

            error_result = StageResult(
                status=StageStatus.FAILED,
                stage_name="scoring",
                product_id=product_id,
                version=version,
                metrics={},
                error=str(e),
            )
            tracker.record_stage_result(error_result)
        raise
    finally:
        db.close()


def fingerprint(**context) -> Dict[str, Any]:
    """Generate readiness fingerprint from metrics."""
    params = get_dag_params(**context)
    workspace_id = params["workspace_id"]
    product_id = params["product_id"]
    version = params["version"]

    logger.info(f"Starting fingerprint generation for product {product_id}, version {version}")

    aird_context = get_aird_context(**context)
    storage = aird_context["storage"]
    tracker = aird_context.get("tracker")
    db = aird_context["db"]

    try:
        from primedata.ingestion_pipeline.aird_stages.fingerprint import FingerprintStage

        fingerprint_stage = FingerprintStage(
            product_id=product_id,
            version=version,
            workspace_id=workspace_id,
        )

        # Get scoring result
        scoring_result = context.get("task_instance").xcom_pull(task_ids="score")

        # Get preprocess result for preprocessing stats
        preprocess_result = context.get("task_instance").xcom_pull(task_ids="preprocess")

        stage_context = {
            "storage": storage,
            "scoring_result": scoring_result,
            "preprocess_result": preprocess_result,  # Add preprocessing stats for Chunk Boundary Quality
        }

        result = fingerprint_stage.execute(stage_context)

        if tracker:
            tracker.record_stage_result(result)

        # Update product with fingerprint
        product = db.query(Product).filter(Product.id == product_id).first()
        if product and result.status.value == "succeeded":
            fingerprint = result.metrics.get("fingerprint", {})
            product.readiness_fingerprint = fingerprint
            product.trust_score = fingerprint.get("AI_Trust_Score")
            db.commit()

        logger.info(
            f"Fingerprint generation completed: {result.status.value}, trust_score={result.metrics.get('trust_score', 0.0)}"
        )

        return {
            "status": result.status.value,
            "trust_score": result.metrics.get("trust_score", 0.0),
        }
    except Exception as e:
        logger.error(f"Fingerprint generation failed: {e}", exc_info=True)
        if tracker:
            from primedata.ingestion_pipeline.aird_stages.base import StageResult, StageStatus

            error_result = StageResult(
                status=StageStatus.FAILED,
                stage_name="fingerprint",
                product_id=product_id,
                version=version,
                metrics={},
                error=str(e),
            )
            tracker.record_stage_result(error_result)
        raise
    finally:
        db.close()


def policy(**context) -> Dict[str, Any]:
    """Evaluate policy against fingerprint."""
    params = get_dag_params(**context)
    workspace_id = params["workspace_id"]
    product_id = params["product_id"]
    version = params["version"]

    logger.info(f"Starting policy evaluation for product {product_id}, version {version}")

    aird_context = get_aird_context(**context)
    storage = aird_context["storage"]
    tracker = aird_context.get("tracker")
    db = aird_context["db"]

    try:
        from primedata.ingestion_pipeline.aird_stages.policy import PolicyStage

        policy_stage = PolicyStage(
            product_id=product_id,
            version=version,
            workspace_id=workspace_id,
        )

        # Get fingerprint result
        fingerprint_result = context.get("task_instance").xcom_pull(task_ids="fingerprint")

        stage_context = {
            "storage": storage,
            "fingerprint_result": fingerprint_result,
        }

        result = policy_stage.execute(stage_context)

        if tracker:
            tracker.record_stage_result(result)

        # Update product with policy status
        product = db.query(Product).filter(Product.id == product_id).first()
        if product and result.status.value in ("succeeded", "failed"):
            product.policy_status = "passed" if result.metrics.get("policy_passed") else "failed"
            product.policy_violations = result.metrics.get("violations", [])

            # Update product status based on policy
            if not result.metrics.get("policy_passed"):
                product.status = ProductStatus.FAILED_POLICY
            elif product.status == ProductStatus.DRAFT:
                product.status = ProductStatus.READY

            db.commit()

        logger.info(f"Policy evaluation completed: passed={result.metrics.get('policy_passed', False)}")

        return {
            "status": result.status.value,
            "policy_passed": result.metrics.get("policy_passed", False),
            "violations": result.metrics.get("violations", []),
        }
    except Exception as e:
        logger.error(f"Policy evaluation failed: {e}", exc_info=True)
        if tracker:
            from primedata.ingestion_pipeline.aird_stages.base import StageResult, StageStatus

            error_result = StageResult(
                status=StageStatus.FAILED,
                stage_name="policy",
                product_id=product_id,
                version=version,
                metrics={},
                error=str(e),
            )
            tracker.record_stage_result(error_result)
        raise
    finally:
        db.close()


def validation(**context) -> Dict[str, Any]:
    """Generate validation summary CSV."""
    params = get_dag_params(**context)
    workspace_id = params["workspace_id"]
    product_id = params["product_id"]
    version = params["version"]

    logger.info(f"Starting validation summary generation for product {product_id}, version {version}")

    aird_context = get_aird_context(**context)
    storage = aird_context["storage"]
    tracker = aird_context.get("tracker")
    db = aird_context["db"]

    try:
        from primedata.ingestion_pipeline.aird_stages.validation import ValidationStage

        validation_stage = ValidationStage(
            product_id=product_id,
            version=version,
            workspace_id=workspace_id,
        )

        stage_context = {
            "storage": storage,
        }

        result = validation_stage.execute(stage_context)

        if tracker:
            tracker.record_stage_result(result)

        # Update product with validation summary path
        product = db.query(Product).filter(Product.id == product_id).first()
        if product and result.status.value == "succeeded" and result.artifacts:
            product.validation_summary_path = result.artifacts.get("validation_summary_csv")
            db.commit()

        logger.info(f"Validation summary generation completed: {result.status.value}")

        return {
            "status": result.status.value,
            "entries_processed": result.metrics.get("entries_processed", 0),
        }
    except Exception as e:
        logger.error(f"Validation summary generation failed: {e}", exc_info=True)
        if tracker:
            from primedata.ingestion_pipeline.aird_stages.base import StageResult, StageStatus

            error_result = StageResult(
                status=StageStatus.FAILED,
                stage_name="validation",
                product_id=product_id,
                version=version,
                metrics={},
                error=str(e),
            )
            tracker.record_stage_result(error_result)
        raise
    finally:
        db.close()


def reporting(**context) -> Dict[str, Any]:
    """Generate PDF trust report."""
    params = get_dag_params(**context)
    workspace_id = params["workspace_id"]
    product_id = params["product_id"]
    version = params["version"]

    logger.info(f"Starting PDF report generation for product {product_id}, version {version}")

    aird_context = get_aird_context(**context)
    storage = aird_context["storage"]
    tracker = aird_context.get("tracker")
    db = aird_context["db"]

    try:
        from primedata.ingestion_pipeline.aird_stages.reporting import ReportingStage

        reporting_stage = ReportingStage(
            product_id=product_id,
            version=version,
            workspace_id=workspace_id,
        )

        stage_context = {
            "storage": storage,
        }

        result = reporting_stage.execute(stage_context)

        if tracker:
            tracker.record_stage_result(result)

        # Update product with trust report path
        product = db.query(Product).filter(Product.id == product_id).first()
        if product and result.status.value == "succeeded" and result.artifacts:
            product.trust_report_path = result.artifacts.get("trust_report_pdf")
            db.commit()

        logger.info(f"PDF report generation completed: {result.status.value}")

        return {
            "status": result.status.value,
            "pdf_size_bytes": result.metrics.get("pdf_size_bytes", 0),
        }
    except Exception as e:
        logger.error(f"PDF report generation failed: {e}", exc_info=True)
        if tracker:
            from primedata.ingestion_pipeline.aird_stages.base import StageResult, StageStatus

            error_result = StageResult(
                status=StageStatus.FAILED,
                stage_name="reporting",
                product_id=product_id,
                version=version,
                metrics={},
                error=str(e),
            )
            tracker.record_stage_result(error_result)
        raise
    finally:
        db.close()


def finalize(**context) -> Dict[str, Any]:
    """Finalize pipeline by updating product status."""
    params = get_dag_params(**context)
    product_id = params["product_id"]
    version = params["version"]

    logger.info(f"Finalizing pipeline for product {product_id}, version {version}")

    # Get database session
    db = next(get_db())

    try:
        # Update product status and version
        product = db.query(Product).filter(Product.id == product_id).first()
        if product:
            product.status = "ready"
            if version and version > product.current_version:
                product.current_version = version
            db.commit()
            logger.info(f"Product {product_id} status updated to 'ready', version {version}")

        return {"status": "completed", "product_status": "ready", "version": version}

    finally:
        db.close()


# Define tasks
ingest_task = PythonOperator(
    task_id="ingest_from_datasources",
    python_callable=ingest_from_datasources,
    dag=dag,
)

preprocess_task = PythonOperator(
    task_id="preprocess",
    python_callable=preprocess,
    dag=dag,
)

chunk_task = PythonOperator(
    task_id="chunk",
    python_callable=chunk,
    dag=dag,
)

embed_task = PythonOperator(
    task_id="embed",
    python_callable=embed,
    dag=dag,
)

index_task = PythonOperator(
    task_id="index",
    python_callable=index,
    dag=dag,
)

validate_task = PythonOperator(
    task_id="validate",
    python_callable=validate,
    dag=dag,
)

validate_dq_task = PythonOperator(
    task_id="validate_data_quality",
    python_callable=validate_data_quality,
    dag=dag,
)

finalize_task = PythonOperator(
    task_id="finalize",
    python_callable=finalize,
    dag=dag,
)

score_task = PythonOperator(
    task_id="score",
    python_callable=score,
    dag=dag,
)

fingerprint_task = PythonOperator(
    task_id="fingerprint",
    python_callable=fingerprint,
    dag=dag,
)

policy_task = PythonOperator(
    task_id="policy",
    python_callable=policy,
    dag=dag,
)

validation_task = PythonOperator(
    task_id="validation",
    python_callable=validation,
    dag=dag,
)

reporting_task = PythonOperator(
    task_id="reporting",
    python_callable=reporting,
    dag=dag,
)

# Define task dependencies
# Validation and reporting are optional and can run in parallel after policy
(
    ingest_task
    >> preprocess_task
    >> score_task
    >> fingerprint_task
    >> policy_task
    >> [validation_task, reporting_task]
    >> chunk_task
    >> embed_task
    >> index_task
    >> validate_task
    >> validate_dq_task
    >> finalize_task
)
