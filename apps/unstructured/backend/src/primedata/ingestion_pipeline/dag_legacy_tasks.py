"""
Legacy pipeline task functions extracted from dag_primedata_v1.py.

These functions implement the original (non-AIRD) data processing tasks:
- ingest_from_datasources: Ingest data from configured data sources to raw storage
- chunk: Chunk cleaned documents into smaller pieces
- embed: Generate embeddings for chunks
- index_legacy: Legacy indexing to OpenSearch (backward compatibility)
- validate: Validate pipeline results and compute metrics
- validate_data_quality: Validate data quality against configured rules
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from primedata.connectors.azure_blob import AzureBlobConnector
from primedata.connectors.folder import FolderConnector
from primedata.connectors.s3 import S3Connector
from primedata.connectors.web import WebConnector
from primedata.db.database import SessionLocal, get_db
from primedata.db.models import DataSource, DataSourceType, DqViolation, PipelineRun, Product
from primedata.dq.validator import DataQualityValidator
from primedata.indexing.embeddings import EmbeddingGenerator
from primedata.indexing.vector_search_client import get_vector_search_client
from primedata.storage.paths import chunk_prefix, clean_prefix, embed_prefix, raw_prefix
from primedata.storage.storage_client import storage_client

logger = logging.getLogger(__name__)


def ingest_from_datasources(get_dag_params, **context) -> Dict[str, Any]:
    """Ingest data from all data sources to raw storage."""
    params = get_dag_params(**context)
    workspace_id = params["workspace_id"]
    product_id = params["product_id"]
    version = params["version"]

    logger.info(f"Starting ingestion for product {product_id}, version {version}")

    # Get database session
    db = next(get_db())

    try:
        # Get product and data sources
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            raise ValueError(f"Product {product_id} not found")

        data_sources = db.query(DataSource).filter(DataSource.product_id == product_id).all()
        if not data_sources:
            raise ValueError(f"No data sources found for product {product_id}")

        # Check if raw data already exists
        raw_prefix_path = raw_prefix(workspace_id, product_id, version)
        existing_objects = storage_client.list_objects("primedata-raw", raw_prefix_path)

        if existing_objects:
            logger.info(f"Raw data already exists for version {version}, skipping ingestion")
            return {"status": "skipped", "message": "Raw data already exists", "files_count": len(existing_objects)}

        # Ingest from each data source
        total_files = 0
        total_bytes = 0
        total_errors = 0

        for ds in data_sources:
            logger.info(f"Processing data source: {ds.name} (type: {ds.type})")

            try:
                if ds.type == DataSourceType.WEB:
                    config = ds.config.copy()
                    if "url" in config and "urls" not in config:
                        config["urls"] = [config["url"]]
                    connector = WebConnector(config)
                    result = connector.sync_full("primedata-raw", raw_prefix_path)

                elif ds.type == DataSourceType.FOLDER:
                    config = ds.config.copy()
                    if "path" in config and "root_path" not in config:
                        config["root_path"] = config["path"]

                    # Convert file_types to include patterns
                    if "file_types" in config and "include" not in config:
                        file_types = config["file_types"]
                        if isinstance(file_types, str):
                            config["include"] = [ft.strip() for ft in file_types.split(",") if ft.strip()]
                        elif isinstance(file_types, list):
                            config["include"] = file_types
                        else:
                            config["include"] = ["*"]

                    connector = FolderConnector(config)
                    result = connector.sync_full("primedata-raw", raw_prefix_path)

                elif ds.type == DataSourceType.AWS_S3:
                    connector = S3Connector(ds.config)
                    result = connector.sync_full("primedata-raw", raw_prefix_path)

                elif ds.type == DataSourceType.AZURE_BLOB:
                    connector = AzureBlobConnector(ds.config)
                    result = connector.sync_full("primedata-raw", raw_prefix_path)

                else:
                    logger.warning(f"Unsupported data source type: {ds.type.value}")
                    continue

                total_files += result["files"]
                total_bytes += result["bytes"]
                total_errors += result["errors"]

                logger.info(
                    f"Data source {ds.name}: {result['files']} files, {result['bytes']} bytes, {result['errors']} errors"
                )

            except Exception as e:
                logger.error(f"Error processing data source {ds.name}: {e}")
                total_errors += 1

        logger.info(f"Ingestion completed: {total_files} files, {total_bytes} bytes, {total_errors} errors")

        return {"status": "completed", "files_count": total_files, "bytes_count": total_bytes, "errors_count": total_errors}

    finally:
        db.close()


def chunk(get_dag_params, **context) -> Dict[str, Any]:
    """Chunk cleaned documents into smaller pieces."""
    params = get_dag_params(**context)
    workspace_id = params["workspace_id"]
    product_id = params["product_id"]
    version = params["version"]
    chunking_config = params["chunking_config"]

    logger.info(f"Starting chunking for product {product_id}, version {version}")
    logger.info(f"Using chunking config: {chunking_config}")

    clean_prefix_path = clean_prefix(workspace_id, product_id, version)
    chunk_prefix_path = chunk_prefix(workspace_id, product_id, version)

    # Get cleaned objects
    clean_objects = storage_client.list_objects("primedata-clean", clean_prefix_path)

    if not clean_objects:
        raise ValueError("No cleaned data found for chunking")

    # Use chunking configuration from product settings
    chunk_size = chunking_config.get("chunk_size", 1000)
    chunk_overlap = chunking_config.get("chunk_overlap", 200)
    min_chunk_size = chunking_config.get("min_chunk_size", 100)
    max_chunk_size = chunking_config.get("max_chunk_size", 2000)
    chunking_strategy = chunking_config.get("chunking_strategy", "fixed_size")

    chunks_created = 0

    for obj in clean_objects:
        try:
            # Download cleaned content
            clean_content = storage_client.get_object("primedata-clean", obj["name"])
            if not clean_content:
                continue

            text = clean_content.decode("utf-8", errors="ignore")

            # Simple chunking by character count
            chunks = []
            start = 0

            # Debug: Log text length and content preview
            logger.info(f"Text length: {len(text)}, preview: {text[:100]}...")

            while start < len(text):
                end = min(start + chunk_size, len(text))
                chunk_text = text[start:end]

                # Skip empty chunks but continue processing
                if not chunk_text.strip():
                    start += 1  # Move forward by 1 character
                    continue

                # Apply min/max chunk size filtering
                chunk_length = len(chunk_text.strip())
                if chunk_length < min_chunk_size:
                    # Chunk too small, try to extend it
                    if end < len(text):
                        # Try to extend to next sentence or word boundary
                        extended_end = min(end + (min_chunk_size - chunk_length), len(text))
                        extended_chunk = text[start:extended_end]
                        if len(extended_chunk.strip()) >= min_chunk_size:
                            chunk_text = extended_chunk
                            end = extended_end
                        else:
                            # Skip this chunk if we can't make it big enough
                            start += 1
                            continue
                    else:
                        # At end of text, skip small chunks
                        start += 1
                        continue

                if chunk_length > max_chunk_size:
                    # Chunk too large, try to split at sentence boundary
                    # For now, just truncate (could be improved with smarter splitting)
                    chunk_text = chunk_text[:max_chunk_size]
                    end = start + max_chunk_size

                chunk_index = len(chunks)
                chunks.append(
                    {
                        "text": chunk_text.strip(),
                        "source_file": obj["name"],
                        "chunk_index": chunk_index,
                        "start_char": start,
                        "end_char": end,
                    }
                )

                # Move start position forward with overlap
                step_size = max(1, chunk_size - chunk_overlap)
                start = start + step_size

                # Safety check to prevent infinite loops
                if start >= len(text):
                    break

            # Save chunks as JSONL
            for i, chunk_item in enumerate(chunks):
                chunk_key = f"{chunk_prefix_path}{Path(obj['name']).stem}_chunk_{i:04d}.json"
                chunk_json = json.dumps(chunk_item, indent=2)

                if storage_client.put_bytes("primedata-chunk", chunk_key, chunk_json.encode("utf-8"), "application/json"):
                    chunks_created += 1

            logger.info(f"Created {len(chunks)} chunks from {obj['name']}")

        except Exception as e:
            logger.error(f"Error chunking {obj['name']}: {e}")

    logger.info(f"Chunking completed: {chunks_created} chunks created")

    return {"status": "completed", "chunks_created": chunks_created}


def embed(get_dag_params, **context) -> Dict[str, Any]:
    """Generate embeddings for chunks."""
    params = get_dag_params(**context)
    workspace_id = params["workspace_id"]
    product_id = params["product_id"]
    version = params["version"]
    embedder_name = params["embedder_name"]
    dim = params["dim"]
    deployment_name = params.get("deployment_name")

    logger.info(f"Starting embedding for product {product_id}, version {version}")
    logger.info(f"Embedding Configuration:")
    logger.info(f"   Model: {embedder_name}")
    logger.info(f"   Dimension: {dim}")

    # Show Azure OpenAI details if configured
    if "embedding-3" in embedder_name or "ada" in embedder_name or embedder_name == "azure-openai":
        from primedata.core.settings import get_settings
        s = get_settings()
        logger.info(f"   Provider: Azure OpenAI")
        logger.info(f"   Endpoint: {s.AZURE_OPENAI_ENDPOINT}")
        logger.info(f"   Deployment: {embedder_name}")
        logger.info(f"   API Version: {s.AZURE_OPENAI_API_VERSION}")
        logger.info(f"   Auth: Service Principal (Client Credentials via Graph API)")
        logger.info(f"   Scope: {s.AZURE_OPENAI_SCOPE}")
    elif embedder_name == "openai":
        logger.info(f"   Provider: OpenAI")
        logger.info(f"   Auth: OpenAI API Key")
    else:
        logger.info(f"   Provider: Registry Model")
        logger.info(f"   Type: Local or configured model")

    chunk_prefix_path = chunk_prefix(workspace_id, product_id, version)
    embed_prefix_path = embed_prefix(workspace_id, product_id, version)

    # Get chunk objects
    chunk_objects = storage_client.list_objects("primedata-chunk", chunk_prefix_path)

    if not chunk_objects:
        raise ValueError("No chunks found for embedding")

    # Initialize embedding generator
    logger.info(f"Initializing EmbeddingGenerator({embedder_name}, {dim})")
    embedder = EmbeddingGenerator(embedder_name, dim, deployment_name=deployment_name)
    logger.info(f"EmbeddingGenerator initialized successfully")

    embeddings_created = 0
    vectors_data = []

    for obj in chunk_objects:
        try:
            # Download chunk
            chunk_content = storage_client.get_object("primedata-chunk", obj["name"])
            if not chunk_content:
                continue

            chunk_data = json.loads(chunk_content.decode("utf-8"))
            text = chunk_data["text"]

            # Generate embedding
            embedding = embedder.embed(text)

            # Store embedding data
            embedding_data = {
                "chunk_id": f"{Path(obj['name']).stem}",
                "text": text,
                "embedding": embedding.tolist(),
                "source_file": chunk_data["source_file"],
                "chunk_index": chunk_data["chunk_index"],
                "metadata": {"start_char": chunk_data["start_char"], "end_char": chunk_data["end_char"]},
            }

            # Save embedding as JSON
            embed_key = f"{embed_prefix_path}{Path(obj['name']).stem}.json"
            embed_json = json.dumps(embedding_data, indent=2)

            if storage_client.put_bytes("primedata-embed", embed_key, embed_json.encode("utf-8"), "application/json"):
                embeddings_created += 1
                vectors_data.append(
                    {
                        "id": embedding_data["chunk_id"],
                        "vector": embedding,
                        "payload": {
                            "text": text,
                            "source_file": chunk_data["source_file"],
                            "chunk_index": chunk_data["chunk_index"],
                            "metadata": embedding_data["metadata"],
                        },
                    }
                )

        except Exception as e:
            logger.error(f"Error embedding {obj['name']}: {e}")

    logger.info(f"Embedding completed: {embeddings_created} embeddings created using {embedder_name}")
    logger.info(f"Embedding Statistics:")
    logger.info(f"   Total embeddings: {embeddings_created}")
    logger.info(f"   Model used: {embedder_name}")
    logger.info(f"   Dimension: {dim}")
    logger.info(f"   Status: SUCCESS")

    # Store vectors data for indexing task
    context["task_instance"].xcom_push(key="vectors_data", value=vectors_data)

    return {"status": "completed", "embeddings_created": embeddings_created, "dimension": dim}


def index_legacy(get_dag_params, **context) -> Dict[str, Any]:
    """Legacy indexing function (kept for backward compatibility)."""
    params = get_dag_params(**context)
    workspace_id = params["workspace_id"]
    product_id = params["product_id"]
    version = params["version"]
    dim = params.get("dim", 384)

    logger.info(f"Starting legacy indexing for product {product_id}, version {version}")

    # Get vectors data from previous task
    vectors_data = context["task_instance"].xcom_pull(key="vectors_data")

    if not vectors_data:
        raise ValueError("No vectors data found for indexing")

    # Initialize OpenSearch client (uses factory pattern for automatic backend selection)
    vector_search_client = get_vector_search_client()

    # Create collection name
    collection_name = f"ws_{workspace_id}__prod_{product_id}__v_{version}"

    # Ensure collection exists
    vector_search_client.ensure_collection(collection_name, dim)

    # Prepare points for upsert
    points = []
    for i, vector_data in enumerate(vectors_data):
        # Use a hash-based approach to create unique integer IDs
        import hashlib

        unique_string = f"{vector_data['payload']['source_file']}_{vector_data['payload']['chunk_index']}"
        unique_id = int(hashlib.md5(unique_string.encode()).hexdigest()[:8], 16)
        points.append(
            {
                "id": unique_id,  # Use unique integer IDs based on hash
                "vector": vector_data["vector"].tolist(),
                "payload": vector_data["payload"],
            }
        )

    # Upsert points to OpenSearch
    vector_search_client.upsert_points(collection_name, points)

    logger.info(f"Indexing completed: {len(points)} points indexed to OpenSearch collection {collection_name}")

    return {"status": "completed", "points_indexed": len(points), "collection_name": collection_name}


def validate(get_dag_params, **context) -> Dict[str, Any]:
    """Validate pipeline results and compute metrics."""
    params = get_dag_params(**context)
    workspace_id = params["workspace_id"]
    product_id = params["product_id"]
    version = params["version"]

    logger.info(f"Starting validation for product {product_id}, version {version}")

    # Get database session
    db = next(get_db())

    try:
        # Compute metrics
        raw_objects = storage_client.list_objects("primedata-raw", raw_prefix(workspace_id, product_id, version))
        clean_objects = storage_client.list_objects("primedata-clean", clean_prefix(workspace_id, product_id, version))
        chunk_objects = storage_client.list_objects("primedata-chunk", chunk_prefix(workspace_id, product_id, version))
        embed_objects = storage_client.list_objects("primedata-embed", embed_prefix(workspace_id, product_id, version))

        # Calculate basic metrics
        doc_count = len(raw_objects)
        chunk_count = len(chunk_objects)

        # Calculate average tokens (rough estimate: 1 token ~ 4 characters)
        total_chars = 0
        for obj in clean_objects:
            content = storage_client.get_object("primedata-clean", obj["name"])
            if content:
                total_chars += len(content.decode("utf-8", errors="ignore"))

        avg_tokens = total_chars / max(doc_count, 1) / 4  # Rough estimate

        # Calculate duplicate rate (simplified: check for identical chunk texts)
        chunk_texts = set()
        duplicates = 0
        for obj in chunk_objects:
            content = storage_client.get_object("primedata-chunk", obj["name"])
            if content:
                chunk_data = json.loads(content.decode("utf-8"))
                text = chunk_data["text"]
                if text in chunk_texts:
                    duplicates += 1
                else:
                    chunk_texts.add(text)

        dup_rate = duplicates / max(chunk_count, 1)

        metrics = {
            "doc_count": doc_count,
            "chunk_count": chunk_count,
            "avg_tokens": round(avg_tokens, 2),
            "dup_rate": round(dup_rate, 4),
            "embed_count": len(embed_objects),
        }

        logger.info(f"Validation metrics: {metrics}")

        # Store metrics in PipelineRun
        dag_run_id = context["dag_run"].run_id
        pipeline_run = (
            db.query(PipelineRun)
            .filter(PipelineRun.product_id == product_id, PipelineRun.version == version, PipelineRun.dag_run_id == dag_run_id)
            .first()
        )

        if pipeline_run:
            pipeline_run.metrics = metrics
            pipeline_run.status = "succeeded"
            pipeline_run.finished_at = datetime.utcnow()
            db.commit()

        return {"status": "completed", "metrics": metrics}

    finally:
        db.close()


def validate_data_quality(get_dag_params, **context) -> Dict[str, Any]:
    """Validate data quality against configured rules."""
    import asyncio

    params = get_dag_params(**context)
    workspace_id = params["workspace_id"]
    product_id = params["product_id"]
    version = params["version"]
    pipeline_run_id = context.get("dag_run", {}).get("run_id", "")

    logger.info(f"Starting data quality validation for product {product_id}, version {version}")

    # Get database session
    db = SessionLocal()

    try:
        # Initialize data quality validator
        validator = DataQualityValidator(storage_client)

        # Run validation using asyncio.run for async function
        report = asyncio.run(
            validator.validate_product_data(
                product_id=product_id, version=version, pipeline_run_id=pipeline_run_id, workspace_id=workspace_id
            )
        )

        # Save violations to database
        violations_saved = 0
        for violation in report.violations:
            db_violation = DqViolation(
                product_id=product_id,
                version=version,
                pipeline_run_id=pipeline_run_id,
                rule_name=violation.rule_name,
                rule_type=violation.rule_type,
                severity=violation.severity,
                message=violation.message,
                details=violation.details,
                affected_count=violation.affected_count,
                total_count=violation.total_count,
                violation_rate=violation.violation_rate,
            )
            db.add(db_violation)
            violations_saved += 1

        db.commit()

        logger.info(f"Data quality validation completed: {violations_saved} violations saved")

        return {
            "status": "completed",
            "violations_found": len(report.violations),
            "violations_saved": violations_saved,
            "has_errors": report.has_errors,
            "has_warnings": report.has_warnings,
            "quality_score": report.overall_quality_score,
        }

    except Exception as e:
        logger.error(f"Data quality validation failed: {e}")
        db.rollback()
        return {"status": "failed", "error": str(e)}
    finally:
        db.close()
