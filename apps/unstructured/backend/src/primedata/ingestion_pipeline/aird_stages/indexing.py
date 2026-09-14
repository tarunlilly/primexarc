"""
AIRD indexing stage for PrimeData.

Ports AIRD FAISS indexing logic to OpenSearch, with metadata tracking.
Uses OpenSearch (primary) via factory pattern for vector search and indexing.
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

import logging
logger = logging.getLogger(__name__)
from primedata.indexing.embeddings import EmbeddingGenerator
from primedata.core.settings import get_settings
import numpy as np

# Use factory pattern to get OpenSearch client
from primedata.indexing.vector_search_client import get_vector_search_client
from primedata.ingestion_pipeline.aird_stages.base import AirdStage, StageResult, StageStatus
from primedata.services.trust_scoring import get_scoring_weights


def load_metrics_index(metrics: List[Dict[str, Any]]) -> Dict[str, Dict]:
    """
    Build lookups from metrics:
      - by_chunk[(file, chunk_id)] -> full metric dict
      - by_chunk_any[chunk_id] -> full metric dict (file-agnostic fallback)
      - by_section[(file, section)] -> score
      - by_file[file] -> max score
    """
    logger.info(f"🎯 load_metrics_index() entry | metrics_count={len(metrics) if metrics else 0}")
    idx = {"by_chunk": {}, "by_chunk_any": {}, "by_section": {}, "by_file": {}}

    if not metrics:
        logger.warning("⚠️ No metrics provided — scores will default to 0.0")
        return idx

    for m in metrics:
        file = m.get("file")
        score = float(m.get("AI_Trust_Score", 0.0))
        cid = m.get("chunk_id")
        sec = m.get("section")

        if file and cid:
            idx["by_chunk"][(file, cid)] = m  # Store full metric object
        if cid:
            idx["by_chunk_any"][cid] = m  # Store full metric object
        if file and sec:
            idx["by_section"][(file, sec)] = score
        if file:
            idx["by_file"][file] = max(score, idx["by_file"].get(file, 0.0))

    logger.info(f"✅ Metrics index created | by_chunk={len(idx['by_chunk'])}, by_chunk_any={len(idx['by_chunk_any'])}, by_section={len(idx['by_section'])}, by_file={len(idx['by_file'])}")
    return idx


def lookup_score(
    metrics_idx: Dict[str, Dict],
    file_name: str,
    rec: Dict[str, Any],
    alt_files: List[str],
) -> float:
    """Find the best available score for a record using multiple fallbacks."""
    cid = rec.get("chunk_id")
    sec = rec.get("section")

    # 1) exact file+chunk
    if cid and (file_name, cid) in metrics_idx["by_chunk"]:
        logger.debug(f"📋 Score lookup: exact file+chunk match for {file_name}/{cid}")
        metric = metrics_idx["by_chunk"][(file_name, cid)]
        return float(metric.get("AI_Trust_Score", 0.0)) if isinstance(metric, dict) else metric

    # 2) try alternate file tags (jsonl/json/txt)
    for f in alt_files:
        if cid and (f, cid) in metrics_idx["by_chunk"]:
            logger.debug(f"📋 Score lookup: alternate file+chunk match for {f}/{cid}")
            metric = metrics_idx["by_chunk"][(f, cid)]
            return float(metric.get("AI_Trust_Score", 0.0)) if isinstance(metric, dict) else metric
        if sec and (f, sec) in metrics_idx["by_section"]:
            logger.debug(f"📋 Score lookup: alternate file+section match for {f}/{sec}")
            return metrics_idx["by_section"][(f, sec)]

    # 3) chunk-only fallback
    if cid and cid in metrics_idx["by_chunk_any"]:
        logger.debug(f"📋 Score lookup: chunk-only fallback for {cid}")
        metric = metrics_idx["by_chunk_any"][cid]
        return float(metric.get("AI_Trust_Score", 0.0)) if isinstance(metric, dict) else metric

    # 4) section/file or file-only fallback
    if sec and (file_name, sec) in metrics_idx["by_section"]:
        logger.debug(f"📋 Score lookup: section fallback for {file_name}/{sec}")
        return metrics_idx["by_section"][(file_name, sec)]

    default_score = metrics_idx["by_file"].get(file_name, 0.0)
    logger.debug(f"📋 Score lookup: file fallback for {file_name}, score={default_score}")
    return default_score


def lookup_quality_metrics(
    metrics_idx: Dict[str, Dict],
    file_name: str,
    rec: Dict[str, Any],
    alt_files: List[str],
) -> Dict[str, Any]:
    """Find quality metrics (confidence, coherence, noise) for a record."""
    cid = rec.get("chunk_id")
    sec = rec.get("section")

    metric = None

    # 1) exact file+chunk
    if cid and (file_name, cid) in metrics_idx["by_chunk"]:
        metric = metrics_idx["by_chunk"][(file_name, cid)]

    # 2) try alternate file tags
    if not metric:
        for f in alt_files:
            if cid and (f, cid) in metrics_idx["by_chunk"]:
                metric = metrics_idx["by_chunk"][(f, cid)]
                break

    # 3) chunk-only fallback
    if not metric and cid and cid in metrics_idx["by_chunk_any"]:
        metric = metrics_idx["by_chunk_any"][cid]

    if metric and isinstance(metric, dict):
        return {
            "confidence_score": float(metric.get("Chunk_Confidence", 0.0) or 0),
            "coherence_score": float(metric.get("Chunk_Coherence", 0.0) or 0),
            "noise_score": float(metric.get("Noise_Free_Score", 0.0) or 0),
        }

    return {
        "confidence_score": 0.0,
        "coherence_score": 0.0,
        "noise_score": 0.0,
    }



class IndexingStage(AirdStage):
    """Indexing stage that embeds chunks and stores them in Qdrant with metadata."""

    @property
    def stage_name(self) -> str:
        return "indexing"

    def get_required_artifacts(self) -> list[str]:
        """Indexing requires processed JSONL files and metrics."""
        return ["processed_jsonl", "metrics_json"]

    def execute(self, context: Dict[str, Any]) -> StageResult:
        """Execute indexing stage.

        Args:
            context: Stage execution context with:
                - storage: AirdStorageAdapter
                - processed_files: List of processed file stems
                - scoring_result: Optional result from scoring stage

        Returns:
            StageResult with indexing metrics
        """
        started_at = datetime.utcnow()
        storage = context.get("storage")
        processed_files = context.get("processed_files", [])

        if not storage:
            return self._create_result(
                status=StageStatus.FAILED,
                metrics={},
                error="Storage adapter not found in context",
                started_at=started_at,
            )

        if not processed_files:
            # Try to get from previous stage
            preprocess_result = context.get("preprocess_result")
            if preprocess_result and preprocess_result.get("processed_file_list"):
                processed_files = preprocess_result["processed_file_list"]
            else:
                self.logger.warning("No processed files to index")
                return self._create_result(
                    status=StageStatus.SKIPPED,
                    metrics={"reason": "no_processed_files"},
                    started_at=started_at,
                )

        self.logger.info(f"Starting indexing for {len(processed_files)} files")

        # Get database from context (should be provided by get_aird_context)
        db = context.get("db")
        if not db:
            from primedata.db.database import SessionLocal

            db = SessionLocal()
            close_db = True
        else:
            close_db = False

        try:
            # Load metrics for score lookup
            metrics = storage.get_metrics_json()
            metrics_idx = load_metrics_index(metrics) if metrics else {}

            # Get embedding generator from product config or use default
            from primedata.db.models import Product

            product = db.query(Product).filter(Product.id == self.product_id).first()
            if not product:
                if close_db:
                    db.close()
                return self._create_result(
                    status=StageStatus.FAILED,
                    metrics={},
                    error=f"Product {self.product_id} not found",
                    started_at=started_at,
                )

            # Get embedding config
            embedding_config = product.embedding_config or {}

            # Determine model name: prioritize explicit config, then check for Azure OpenAI env vars, then default to minilm
            model_name = embedding_config.get("embedder_name")
            deployment_name = embedding_config.get("deployment_name")

            if not model_name:
                # Check if Azure OpenAI is configured via environment variables
                settings = get_settings()
                if settings.AZURE_OPENAI_ENDPOINT and settings.AZURE_OPENAI_DEPLOYMENT_NAME:
                    model_name = "azure-openai"
                    self.logger.info("🔷 Using Azure OpenAI for embeddings (environment variables configured)")
                else:
                    model_name = "minilm"

            dimension = embedding_config.get("embedding_dimension", 384)

            # Initialize embedding generator with workspace context for API keys
            embedder = EmbeddingGenerator(model_name=model_name, dimension=dimension, workspace_id=self.workspace_id, db=db, deployment_name=deployment_name)
            actual_dimension = embedder.get_dimension()

            # Check if we're using hash-based fallback (which won't give good semantic search results)
            model_info = embedder.get_model_info()
            if model_info.get("fallback_mode"):
                self.logger.error(
                    f"CRITICAL: Embedding model {model_name} is using hash-based fallback. "
                    f"Semantic search will NOT work correctly - results will be random. "
                    f"Check that the API key is configured for OpenAI models or sentence_transformers is installed."
                )
                # Still proceed but log the issue prominently
            else:
                self.logger.info(
                    f"Embedding model {model_name} loaded successfully. "
                    f"Model type: {model_info.get('model_type', 'unknown')}, "
                    f"Dimension: {actual_dimension}"
                )

            # Create OpenSearch collection name using product name for better readability
            self.logger.info(f"Product name from database: '{product.name}'")
            # Get vector search client (uses OpenSearch by default)
            vector_search_client = get_vector_search_client()
            sanitized_product_name = vector_search_client._sanitize_collection_name(product.name)
            self.logger.info(f"Sanitized product name for collection: '{sanitized_product_name}'")
            collection_name = f"ws_{self.workspace_id}__{sanitized_product_name}__v_{self.version}"
            self.logger.info(f"Creating OpenSearch collection: '{collection_name}'")

            if not vector_search_client.is_connected():
                return self._create_result(
                    status=StageStatus.FAILED,
                    metrics={},
                    error="Vector search client (OpenSearch) not connected",
                    started_at=started_at,
                )

            collection_created = vector_search_client.ensure_collection(collection_name, actual_dimension)
            if not collection_created:
                if close_db:
                    db.close()
                return self._create_result(
                    status=StageStatus.FAILED,
                    metrics={},
                    error=(
                        f"Failed to create Qdrant collection '{collection_name}'. "
                        f"This usually indicates a Qdrant server resource limit issue (check 'too many open files' in Qdrant logs). "
                        f"Ensure Qdrant container has ulimits.nofile set to at least 65536."
                    ),
                    started_at=started_at,
                )

            # Process all files - collect all records first, then batch-embed
            all_records_data = []  # Store record data for batch processing
            total_chunks = 0
            import hashlib

            # First pass: Collect all records and their metadata
            for file_stem in processed_files:
                try:
                    # Load processed JSONL
                    records = storage.get_processed_jsonl(file_stem)
                    if not records:
                        self.logger.warning(f"Processed JSONL not found for {file_stem}, skipping")
                        continue

                    processed_file = f"{file_stem}.jsonl"
                    alt_files = [processed_file, f"{file_stem}.json", f"{file_stem}.txt"]

                    # Process each record to collect data
                    for rec in records:
                        if not isinstance(rec, dict):
                            continue

                        text = rec.get("text", "")
                        if not text.strip():
                            continue

                        # Extract metadata
                        chunk_id = rec.get("chunk_id") or f"{file_stem}_{rec.get('section', 'general')}"
                        section = rec.get("section", "general")
                        field_name = rec.get("field_name", section)
                        page = rec.get("page")
                        document_id = rec.get("document_id") or rec.get("doc_scope") or file_stem
                        tags = rec.get("tags", "")

                        # Lookup score
                        score = lookup_score(metrics_idx, processed_file, rec, alt_files)

                        # Lookup quality metrics (confidence, coherence, noise)
                        quality_metrics = lookup_quality_metrics(metrics_idx, processed_file, rec, alt_files) if metrics_idx else {}

                        # Store record data for batch embedding
                        all_records_data.append(
                            {
                                "text": text,
                                "chunk_id": chunk_id,
                                "filename": processed_file,
                                "document_id": document_id,
                                "page": page,
                                "section": section,
                                "field_name": field_name,
                                "tags": tags,
                                "score": score,
                                "quality_metrics": quality_metrics or {},  # Ensure it's always a dict
                                "rec": rec,  # Store full record for metadata creation
                            }
                        )

                        total_chunks += 1

                except Exception as e:
                    self.logger.error(f"Failed to process {file_stem}: {e}", exc_info=True)
                    continue

            if not all_records_data:
                return self._create_result(
                    status=StageStatus.FAILED,
                    metrics={},
                    error="No records to index",
                    started_at=started_at,
                )

            # Log total chunks to process
            total_chunks = len(all_records_data)
            avg_chunk_length = sum(len(r["text"]) for r in all_records_data) / total_chunks if total_chunks > 0 else 0
            self.logger.info(
                f"📊 Total chunks to process: {total_chunks}, " f"average chunk length: {avg_chunk_length:.0f} characters"
            )

            # Batch embed all texts for performance (especially important for OpenAI API)
            # Adaptive batch size based on model dimension to prevent memory issues
            # Large models (>=1024 dim) need very small batches, smaller models can handle larger batches
            model_dimension = actual_dimension
            if model_dimension >= 1024:
                # For very large models like BGE Large, use very small batches to avoid timeout
                # With thousands of chunks, even small batches can take hours
                embedding_batch_size = 3  # Very large models need tiny batches to complete in reasonable time
            elif model_dimension >= 768:
                embedding_batch_size = 15  # Large models need medium batches
            else:
                embedding_batch_size = 100  # Smaller models can handle larger batches

            # Estimate processing time (rough estimate: 10-20 seconds per batch for large models)
            total_batches = (total_chunks + embedding_batch_size - 1) // embedding_batch_size
            if model_dimension >= 1024:
                estimated_minutes = total_batches * 0.5  # ~30 seconds per batch of 3 chunks
            elif model_dimension >= 768:
                estimated_minutes = total_batches * 0.3  # ~18 seconds per batch of 15 chunks
            else:
                estimated_minutes = total_batches * 0.1  # ~6 seconds per batch of 100 chunks

            self.logger.info(
                f"Generating embeddings for {total_chunks} chunks in batches of {embedding_batch_size} "
                f"(model dimension: {model_dimension}, {total_batches} batches, "
                f"estimated time: ~{estimated_minutes:.1f} minutes / ~{estimated_minutes/60:.1f} hours)..."
            )

            # Warn if processing will take a very long time
            if estimated_minutes > 60:
                self.logger.warning(
                    f"⚠️  WARNING: Embedding generation is estimated to take {estimated_minutes/60:.1f} hours. "
                    f"Consider using a faster model (e.g., minilm or e5-base) for large documents, "
                    f"or ensure the task has sufficient timeout (currently 2 hours)."
                )
            all_embeddings = []

            import time

            start_time = time.time()

            for i in range(0, len(all_records_data), embedding_batch_size):
                batch_start_time = time.time()
                batch_records = all_records_data[i : i + embedding_batch_size]
                batch_texts = [r["text"] for r in batch_records]
                batch_num = (i // embedding_batch_size) + 1
                total_batches = (len(all_records_data) + embedding_batch_size - 1) // embedding_batch_size

                # Log batch start with timing info
                elapsed = time.time() - start_time
                avg_time_per_batch = elapsed / max(batch_num - 1, 1)
                remaining_batches = total_batches - batch_num
                estimated_remaining = remaining_batches * avg_time_per_batch

                self.logger.info(
                    f"🔄 Embedding batch {batch_num}/{total_batches} ({len(batch_texts)} chunks, "
                    f"progress: {i}/{len(all_records_data)} chunks, "
                    f"elapsed: {elapsed:.1f}s, est. remaining: {estimated_remaining:.1f}s)..."
                )
                try:
                    # Use smaller internal batch size for sentence transformers to manage memory better
                    batch_embeddings = embedder.embed_batch(batch_texts, batch_size=embedding_batch_size)
                    all_embeddings.extend(batch_embeddings)
                    batch_time = time.time() - batch_start_time
                    self.logger.info(
                        f"✅ Generated {len(batch_embeddings)} embeddings for batch {batch_num}/{total_batches} "
                        f"in {batch_time:.1f}s ({batch_time/len(batch_texts):.2f}s per chunk)"
                    )
                except Exception as e:
                    self.logger.error(
                        f"Failed to generate embeddings for batch {batch_num}/{total_batches}: {e}", exc_info=True
                    )
                    # Fallback to individual embeddings for this batch
                    self.logger.warning(f"Falling back to individual embedding generation for batch {batch_num}")
                    for record_data in batch_records:
                        try:
                            embedding = embedder.embed(record_data["text"])
                            all_embeddings.append(embedding)
                        except Exception as emb_error:
                            self.logger.error(f"Failed to embed chunk {record_data['chunk_id']}: {emb_error}")
                            # Add None as placeholder - will skip this record
                            all_embeddings.append(None)

            # --- Vector quality & embedding health metrics (computed from produced embeddings) ---
            attempted_vectors = len(all_records_data)
            produced_vectors = [e for e in all_embeddings if e is not None]
            produced_count = len(produced_vectors)

            def _safe_float(x: float) -> float:
                try:
                    return float(x)
                except Exception:
                    return 0.0

            def _clip01(x: float) -> float:
                return max(0.0, min(1.0, x))

            vector_metrics: Dict[str, Any] = {}
            if attempted_vectors > 0 and produced_count > 0:
                mat = np.vstack([np.asarray(v, dtype=np.float32).reshape(-1) for v in produced_vectors])
                expected_dim = int(actual_dimension)

                # Dimension consistency: based on observed mismatches before coercion (EmbeddingGenerator.stats)
                dim_mismatches = int(embedder.stats.get("dim_mismatch_vectors", 0.0) or 0.0)
                dim_consistency = (1.0 - (dim_mismatches / max(attempted_vectors, 1))) * 100.0
                dim_consistency = max(0.0, min(100.0, dim_consistency))

                # Valid vectors: no NaN/Inf, correct shape
                nan_inf_mask = ~np.isfinite(mat).all(axis=1)
                nan_inf_count = int(nan_inf_mask.sum())
                valid_ratio = 1.0 - (nan_inf_count / max(produced_count, 1))
                valid_ratio = _clip01(valid_ratio)

                # Non-zero vectors: norm > eps
                norms = np.linalg.norm(mat, axis=1)
                eps = 1e-8
                non_zero_ratio = float((norms > eps).sum()) / float(max(produced_count, 1))
                non_zero_ratio = _clip01(non_zero_ratio)

                # Norm distribution health (robust outlier rate using MAD)
                # norm_health = 1 - outlier_rate, where outliers are far from median.
                median = float(np.median(norms)) if produced_count else 0.0
                abs_dev = np.abs(norms - median)
                mad = float(np.median(abs_dev)) if produced_count else 0.0
                if mad <= 0:
                    outlier_rate = 0.0
                else:
                    # Modified Z-score threshold (~3.5 is common)
                    modified_z = 0.6745 * abs_dev / mad
                    outlier_rate = float((modified_z > 3.5).sum()) / float(max(produced_count, 1))
                norm_health = _clip01(1.0 - outlier_rate)

                # Embedding success rate: real embeddings (not hash-fallback) AND produced (non-None)
                fallback_vectors = int(embedder.stats.get("fallback_vectors", 0.0) or 0.0)
                # Any None embeddings are treated as failures as well
                none_failures = attempted_vectors - produced_count
                successful_embeddings = max(0, attempted_vectors - fallback_vectors - none_failures)
                success_rate = (successful_embeddings / max(attempted_vectors, 1)) * 100.0
                success_rate = max(0.0, min(100.0, success_rate))

                # Vector Quality Score (Help formula): 0.4*valid + 0.3*non_zero + 0.3*norm_health
                vqs = (0.4 * valid_ratio) + (0.3 * non_zero_ratio) + (0.3 * norm_health)
                vqs_pct = max(0.0, min(100.0, vqs * 100.0))

                # Embedding Model Health (proxy): penalize API errors, fallback usage, dim mismatch, outliers
                model_info = embedder.get_model_info()
                fallback_mode = bool(model_info.get("fallback_mode"))
                api_requests = float(embedder.stats.get("api_requests", 0.0) or 0.0)
                api_errors = float(embedder.stats.get("api_errors", 0.0) or 0.0)
                api_error_rate = (api_errors / api_requests) if api_requests > 0 else 0.0
                fallback_rate = float(fallback_vectors) / float(max(attempted_vectors, 1))
                dim_mismatch_rate = float(dim_mismatches) / float(max(attempted_vectors, 1))

                # Response consistency: low CV of norms is better (cap at 1.0)
                mean_norm = float(np.mean(norms)) if produced_count else 0.0
                std_norm = float(np.std(norms)) if produced_count else 0.0
                cv = (std_norm / mean_norm) if mean_norm > 0 else 0.0
                response_consistency = _clip01(1.0 - min(1.0, cv / 0.75))  # heuristic scaling

                if fallback_mode:
                    model_health_pct = 0.0
                else:
                    model_health = (
                        0.30 * _clip01(1.0 - api_error_rate)
                        + 0.25 * _clip01(1.0 - fallback_rate)
                        + 0.20 * _clip01(1.0 - dim_mismatch_rate)
                        + 0.15 * norm_health
                        + 0.10 * response_consistency
                    )
                    model_health_pct = max(0.0, min(100.0, model_health * 100.0))

                # Semantic Search Readiness (Help weights, in percent-space)
                semantic_readiness = (
                    0.25 * dim_consistency
                    + 0.35 * vqs_pct
                    + 0.25 * model_health_pct
                    + 0.15 * success_rate
                )
                semantic_readiness = max(0.0, min(100.0, semantic_readiness))

                vector_metrics = {
                    "Embedding_Dimension_Consistency": round(dim_consistency, 2),
                    "Embedding_Success_Rate": round(success_rate, 2),
                    "Vector_Quality_Score": round(vqs_pct, 2),
                    "Embedding_Model_Health": round(model_health_pct, 2),
                    "Semantic_Search_Readiness": round(semantic_readiness, 2),
                    # Debug/support fields (not shown in UI directly)
                    "vector_metrics_details": {
                        "expected_dim": expected_dim,
                        "attempted_vectors": attempted_vectors,
                        "produced_vectors": produced_count,
                        "fallback_vectors": fallback_vectors,
                        "dim_mismatch_vectors": dim_mismatches,
                        "nan_inf_vectors": nan_inf_count,
                        "valid_ratio": round(valid_ratio, 6),
                        "non_zero_ratio": round(non_zero_ratio, 6),
                        "norm_median": round(_safe_float(median), 6),
                        "norm_mean": round(_safe_float(mean_norm), 6),
                        "norm_std": round(_safe_float(std_norm), 6),
                        "norm_outlier_rate": round(_safe_float(outlier_rate), 6),
                        "norm_health": round(_safe_float(norm_health), 6),
                        "api_requests": int(api_requests),
                        "api_errors": int(api_errors),
                        "api_error_rate": round(_safe_float(api_error_rate), 6),
                        "fallback_mode": bool(model_info.get("fallback_mode")),
                        "model_type": model_info.get("model_type"),
                    },
                }

            # Second pass: Build points with embeddings
            all_points = []
            rag_eval_candidates: List[Dict[str, Any]] = []

            def _first_sentence(text: str) -> str:
                # Simple extraction: take up to first sentence end; fallback to prefix
                if not text:
                    return ""
                for sep in [". ", "? ", "! "]:
                    idx = text.find(sep)
                    if idx != -1 and idx < 300:
                        return text[: idx + 1].strip()
                return text[:250].strip()

            for idx, (record_data, embedding) in enumerate(zip(all_records_data, all_embeddings)):
                if embedding is None:
                    self.logger.warning(f"Skipping chunk {record_data['chunk_id']} due to embedding failure")
                    continue

                embedding_list = embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)

                # Create Qdrant point ID (use chunk_id hash for uniqueness)
                point_id_str = f"{self.product_id}_{record_data['chunk_id']}_{self.version}"
                point_id = int(hashlib.md5(point_id_str.encode()).hexdigest()[:15], 16)

                # Create Qdrant point
                # Store full text (Qdrant supports large payloads, typically up to 64KB per payload)
                max_text_length = 50000  # 50KB should be safe for Qdrant payloads
                stored_text = (
                    record_data["text"][:max_text_length]
                    if len(record_data["text"]) > max_text_length
                    else record_data["text"]
                )

                # Create Qdrant point with all metadata in payload (single source of truth)
                # All metadata is stored in Qdrant payload - no PostgreSQL metadata tables needed
                point = {
                    "id": point_id,
                    "vector": embedding_list,
                    "payload": {
                        "chunk_id": record_data["chunk_id"],
                        "filename": record_data["filename"],
                        "source_file": record_data["filename"],  # Alias for compatibility
                        "document_id": record_data["document_id"],
                        "page": record_data["page"],
                        "page_number": record_data["page"],  # Alias for compatibility
                        "section": record_data["section"],
                        "field_name": record_data["field_name"],
                        "score": record_data["score"],
                        "text": stored_text,
                        "text_length": len(record_data["text"]),
                        "source": record_data["rec"].get("source", "internal"),
                        "audience": record_data["rec"].get("audience", "unknown"),
                        "timestamp": record_data["rec"].get("timestamp", datetime.utcnow().isoformat()),
                        "product_id": str(self.product_id),
                        "version": self.version,  # Add version to payload
                        "collection_id": collection_name,  # Add collection_id to payload
                        "created_at": datetime.utcnow().isoformat(),  # Add created_at timestamp
                        "index_scope": str(self.product_id),
                        "doc_scope": record_data["document_id"],
                        "field_scope": record_data["field_name"],
                        "tags": record_data["tags"],
                        "extra_tags": {"tags": record_data["tags"]} if record_data["tags"] else None,  # For compatibility
                        "token_est": record_data["rec"].get("token_est", 0),
                        # Add quality scores from metrics lookup
                        "confidence_score": (record_data.get("quality_metrics") or {}).get("confidence_score") or record_data["rec"].get("confidence_score"),
                        "coherence_score": (record_data.get("quality_metrics") or {}).get("coherence_score") or record_data["rec"].get("coherence_score"),
                        "noise_score": (record_data.get("quality_metrics") or {}).get("noise_score") or record_data["rec"].get("noise_score"),
                        # Add raw_text for before/after comparison in quality drill-down
                        "raw_text": record_data["rec"].get("raw_text"),
                        "raw_text_length": len(record_data["rec"].get("raw_text", "")),
                    },
                }
                all_points.append(point)

                # Keep some candidates for RAG evaluation (self-retrieval)
                rag_eval_candidates.append(
                    {
                        "point_id": point_id,
                        "query_text": _first_sentence(record_data["text"]),
                        "embedding": embedding,  # may be used to avoid extra embedding calls
                    }
                )

            if not all_points:
                return self._create_result(
                    status=StageStatus.FAILED,
                    metrics={},
                    error="No points to index",
                    started_at=started_at,
                )

            # Upsert to OpenSearch
            success = vector_search_client.upsert_points(collection_name, all_points)
            if not success:
                return self._create_result(
                    status=StageStatus.FAILED,
                    metrics={},
                    error="Failed to upsert points to OpenSearch",
                    started_at=started_at,
                )

            finished_at = datetime.utcnow()

            # Calculate aggregate trust score
            scores = [p["payload"]["score"] for p in all_points]
            avg_trust_score = round(sum(scores) / len(scores), 4) if scores else 0.0

            # --- RAG Performance Metrics (self-retrieval proxy) ---
            rag_metrics: Dict[str, Any] = {}
            try:
                # Use playbook rag_evaluation settings if provided; otherwise default
                playbook = context.get("playbook") or {}
                rag_cfg = playbook.get("rag_evaluation", {}) if isinstance(playbook, dict) else {}
                retrieval_cfg = rag_cfg.get("retrieval_settings", {}) if isinstance(rag_cfg, dict) else {}
                top_k = int(retrieval_cfg.get("top_k", 10) or 10)
                max_queries = int(retrieval_cfg.get("max_queries", 50) or 50)

                # Avoid extra API calls for OpenAI by using existing chunk embeddings as queries
                model_info = embedder.get_model_info()
                is_openai = model_info.get("model_type") == "openai"
                query_mode = "self_embedding" if is_openai else "first_sentence_embed"

                candidates = rag_eval_candidates[: min(len(rag_eval_candidates), max_queries)]
                if candidates:
                    hits = 0
                    ap_sum = 0.0
                    for c in candidates:
                        target_id = c["point_id"]
                        if query_mode == "self_embedding":
                            qvec = c["embedding"]
                        else:
                            qvec = embedder.embed(c["query_text"])
                        qvec_list = qvec.tolist() if hasattr(qvec, "tolist") else list(qvec)

                        results = vector_search_client.search_points(collection_name, [qvec_list], limit=top_k)
                        # search_points returns list of result lists, get first one
                        if results and len(results) > 0:
                            rank = None
                            for i_r, r in enumerate(results[0], start=1):
                                if r.get("id") == target_id:
                                    rank = i_r
                                    break

                            if rank is not None:
                                hits += 1
                                ap_sum += 1.0 / float(rank)

                    qn = float(len(candidates))
                    recall_at_k = (hits / qn) * 100.0 if qn > 0 else 0.0
                    avg_precision_at_k = (ap_sum / qn) * 100.0 if qn > 0 else 0.0
                    coverage = recall_at_k  # for self-retrieval, coverage == hit rate

                    rag_metrics = {
                        "Retrieval_Recall_At_K": round(recall_at_k, 2),
                        "Average_Precision_At_K": round(avg_precision_at_k, 2),
                        "Query_Coverage": round(coverage, 2),
                        "rag_metrics_details": {
                            "top_k": top_k,
                            "queries_evaluated": int(qn),
                            "query_mode": query_mode,
                        },
                    }
            except Exception as e:
                self.logger.warning(f"RAG metric evaluation failed (non-fatal): {e}")

            metrics_result = {
                "collection_name": collection_name,
                "points_indexed": len(all_points),
                "avg_trust_score": avg_trust_score,
            }
            # Merge computed metrics (vector + rag) into stage metrics so downstream can persist them
            metrics_result.update(vector_metrics)
            metrics_result.update(rag_metrics)

            return self._create_result(
                status=StageStatus.SUCCEEDED,
                metrics=metrics_result,
                started_at=started_at,
                finished_at=finished_at,
            )

        except Exception as e:
            self.logger.error(f"Indexing failed: {e}", exc_info=True)
            return self._create_result(
                status=StageStatus.FAILED,
                metrics={},
                error=str(e),
                started_at=started_at,
            )
        finally:
            if close_db:
                db.close()
