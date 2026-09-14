"""
AIRD preprocessing stage for PrimeData.

Ports AIRD preprocessing logic with playbook support, adapted for S3/GCS storage.
"""

import json
import logging as logging  # For Airflow compatibility
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import regex as re
logger = logging.getLogger(__name__)

from primedata.ingestion_pipeline.aird_stages.base import AirdStage, StageResult, StageStatus
from primedata.ingestion_pipeline.aird_stages.playbooks import load_playbook_yaml, route_playbook
from primedata.ingestion_pipeline.aird_stages.utils.chunking import (
    char_chunk,
    paragraph_chunk,
    sentence_chunk,
    tokens_estimate,
)
from primedata.ingestion_pipeline.aird_stages.utils.text_processing import (
    apply_normalizers,
    detect_sections_configured,
    normalize_wrapped_lines,
    redact_pii,
    split_pages_by_config,
)
from primedata.analysis.content_analyzer import content_analyzer
from primedata.core.constants import PLAYBOOK_SAMPLE_MAX_CHARS, PLAYBOOK_ROUTING_SAMPLE_CHARS, PDF_CORRUPTION_SPACE_RATIO_THRESHOLD, PDF_CORRUPTION_FIX_MAX_PASSES, PREPROCESSING_PROGRESS_LOG_INTERVAL, UNSUPPORTED_IMAGE_EXTENSIONS
from primedata.ingestion_pipeline.pipeline_config import resolve_content_hint
from primedata.services.noise_detection import calculate_noise_ratio

from primedata.ingestion_pipeline.aird_stages.document_processor import (
    AUDIENCE_PATTERNS,
    DocumentProcessor,
    _audience_for,
    _get_pdf_sample_for_routing,
    _get_text_sample_for_routing,
)


def _build_record(
    stem: str,
    filename: str,
    document_id: str,
    page: int,
    canon_section: str,
    title_raw: str,
    text: str,
    chunk_idx: int,
    chunk_of: int,
    product_id: UUID,
    domain_type: Optional[str] = None,
    raw_text: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a chunk record dictionary with PrimeData metadata structure.

    :param stem: File stem identifier used to construct the chunk_id.
    :param filename: Original filename of the source document.
    :param document_id: Unique document identifier for the source file.
    :param page: Page number where this chunk originated.
    :param canon_section: Canonical (normalized) section name.
    :param title_raw: Raw section title before normalization.
    :param text: The actual chunk text content.
    :param chunk_idx: Zero-based index of this chunk within its section.
    :param chunk_of: Total number of chunks in the section.
    :param product_id: UUID of the product this chunk belongs to.
    :param domain_type: Optional content domain type for domain-adaptive scoring.
    :param raw_text: Optional original unprocessed text for reference.
    :return: Dictionary containing the chunk record with all metadata fields populated.
    """
    logger.debug(f"🎯 _build_record() entry | stem={stem}, page={page}, chunk={chunk_idx}/{chunk_of}, text_length={len(text)}")

    # Calculate noise score (0-100 scale)
    noise_result = calculate_noise_ratio(text)
    noise_score = noise_result.get("noise_ratio", 0.0)  # Returns 0-100

    record = {
        "chunk_id": f"{stem}_p{page}_s{canon_section}_c{chunk_idx}",
        "document_id": document_id,
        "filename": filename,
        "page": page,
        "section_raw": title_raw,
        "section": canon_section,
        "field_name": canon_section,
        "text": text,
        "token_est": tokens_estimate(text),
        "chunk_index": chunk_idx,
        "chunk_of": chunk_of,
        "source": "internal",
        "audience": _audience_for(text, section=title_raw or canon_section, default="general"),
        "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "product_id": str(product_id),
        "index_scope": None,
        "doc_scope": document_id,
        "field_scope": canon_section,
        "tags": "",
        "doc_date": None,
        "raw_text": raw_text,
        "noise_score": noise_score,
    }

    # Add domain_type if provided (for domain-adaptive scoring)
    if domain_type:
        record["domain_type"] = domain_type

    return record


class PreprocessStage(AirdStage):
    """Preprocessing stage that normalizes, chunks, and sections documents."""

    @property
    def stage_name(self) -> str:
        return "preprocess"

    def get_required_artifacts(self) -> list[str]:
        """Preprocessing requires raw text files from ingestion."""
        return []  # Raw files come from ingestion stage

    def execute(self, context: Dict[str, Any]) -> StageResult:
        """Execute the preprocessing stage to normalize, chunk, and section documents.

        :param context: Stage execution context containing 'storage' (AirdStorageAdapter),
            'raw_files' (list of file stems to process), optionally 'playbook_id' (override),
            and 'chunking_config' (product-level chunking configuration).
        :return: StageResult with preprocessing metrics including chunk counts and playbook info.
        """
        logger.info(f"🎯 PreprocessStage.execute() entry | product_id={self.product_id}, version={self.version}, context_keys={list(context.keys())}")
        started_at = datetime.utcnow()

        # Cache context for use in _process_document (for workspace settings lookup)
        self._context_cache = {
            "workspace_id": context.get("workspace_id"),
            "db": context.get("db"),
            "use_case_description": context.get("use_case_description"),
        }

        storage = context.get("storage")
        raw_files = context.get("raw_files", [])
        # Get playbook_id from context or config, but allow None/empty for auto-detection
        initial_playbook_id = context.get("playbook_id") or self.config.get("playbook_id")
        # Normalize empty string to None to allow auto-detection
        if initial_playbook_id == "":
            initial_playbook_id = None
        chunking_config = context.get("chunking_config", {})  # Get product chunking config
        if (
            isinstance(chunking_config, dict)
            and "resolved_settings" not in chunking_config
            and isinstance(chunking_config.get("chunking_config"), dict)
        ):
            chunking_config = chunking_config.get("chunking_config", chunking_config)

        # Track playbook selection metadata for verification
        # Will be updated based on whether playbook is provided or auto-detected
        playbook_selection_metadata = {
            "method": None,  # Will be set to "manual", "auto_detected", or "default"
            "reason": None,
            "detected_at": None,
            "playbook_id": None,  # Will be set when playbook is determined
        }
        context_playbook_selection = context.get("playbook_selection")
        if context_playbook_selection and isinstance(context_playbook_selection, dict):
            playbook_selection_metadata.update(context_playbook_selection)

        logger.info(f"📋 Processing parameters: raw_files={len(raw_files)}, initial_playbook_id={initial_playbook_id}, chunking_config_keys={list(chunking_config.keys()) if chunking_config else []}")

        if not storage:
            return self._create_result(
                status=StageStatus.FAILED,
                metrics={},
                error="Storage adapter not found in context",
                started_at=started_at,
            )

        if not raw_files:
            self.logger.warning("No raw files to process")
            return self._create_result(
                status=StageStatus.SKIPPED,
                metrics={"reason": "no_raw_files"},
                started_at=started_at,
            )

        # Initialize playbook_id for logging (will be reassigned per file in loop)
        playbook_id = initial_playbook_id
        self.logger.info(f"Starting preprocessing for {len(raw_files)} files, playbook={playbook_id}")

        # Get file_stem to storage_key mapping if provided (for accurate file retrieval)
        file_stem_to_storage_key = context.get("file_stem_to_storage_key", {})

        all_records: List[Dict[str, Any]] = []
        total_sections = 0
        total_mid_sentence_ends = 0
        processed_files = []
        failed_files = []
        last_exception = None
        file_chunk_counts: Dict[str, int] = {}
        file_sections_counts: Dict[str, int] = {}
        chunking_config_used: Optional[Dict[str, Any]] = None

        for file_stem in raw_files:
            file_start_time = datetime.utcnow()
            # Use both loguru and std logging for Airflow visibility
            self.logger.info(f"[PreprocessStage] ====== Processing file: {file_stem} ======")
            try:
                # Load raw text - use exact storage_key if available
                file_info = file_stem_to_storage_key.get(file_stem, {})
                storage_key = file_info.get("storage_key")
                storage_bucket = file_info.get("storage_bucket")
                filename = file_info.get("filename", f"{file_stem}.txt")

                file_info_msg = f"[PreprocessStage] File info for {file_stem}: storage_key={storage_key}, storage_bucket={storage_bucket}, filename={filename}"
                self.logger.info(file_info_msg)

                keys_msg = (
                    f"[PreprocessStage] Available file_stem_to_storage_key keys: {list(file_stem_to_storage_key.keys())}"
                )
                self.logger.info(keys_msg)

                # OPTIMIZATION: Route playbook BEFORE loading full file (for performance)
                # Route playbook if not provided
                file_playbook_id = initial_playbook_id  # Use initial_playbook_id for this file
                if not file_playbook_id:
                    # OPTIMIZATION: For playbook routing, only read sample text
                    # This avoids extracting full PDF when we only need first 1000-2000 chars
                    sample_for_playbook = None
                    try:
                        if filename.lower().endswith('.pdf'):
                            # For PDFs, extract only first 2 pages for playbook routing
                            sample_for_playbook = _get_pdf_sample_for_routing(
                                storage, file_stem, storage_key, storage_bucket,
                                max_chars=PLAYBOOK_SAMPLE_MAX_CHARS, log=self.logger,
                            )
                        else:
                            # For text files, read only first N chars
                            sample_for_playbook = _get_text_sample_for_routing(
                                storage, file_stem, storage_key, storage_bucket,
                                max_chars=PLAYBOOK_SAMPLE_MAX_CHARS, log=self.logger,
                            )
                    except Exception as e:
                        self.logger.warning(f"Failed to get sample for playbook routing: {e}, will use filename only")
                        sample_for_playbook = None

                    # Use sample if available, otherwise use filename only
                    if sample_for_playbook:
                        chosen_id, reason = route_playbook(
                            sample_text=sample_for_playbook[:PLAYBOOK_ROUTING_SAMPLE_CHARS],
                            filename=file_stem
                        )
                        file_playbook_id = chosen_id
                        # Update selection metadata for auto-detection (only on first file)
                        if playbook_selection_metadata.get("method") is None:
                            playbook_selection_metadata["method"] = "auto_detected"
                            playbook_selection_metadata["playbook_id"] = chosen_id
                            playbook_selection_metadata["reason"] = reason
                            playbook_selection_metadata["detected_at"] = datetime.utcnow().isoformat() + "Z"
                        self.logger.info(f"Auto-routed to playbook {file_playbook_id} ({reason}) using sample text")
                    else:
                        # Fallback: use filename only for routing
                        chosen_id, reason = route_playbook(sample_text=None, filename=file_stem)
                        file_playbook_id = chosen_id
                        if playbook_selection_metadata.get("method") is None:
                            playbook_selection_metadata["method"] = "auto_detected"
                            playbook_selection_metadata["playbook_id"] = chosen_id
                            playbook_selection_metadata["reason"] = reason
                            playbook_selection_metadata["detected_at"] = datetime.utcnow().isoformat() + "Z"
                        self.logger.info(f"Auto-routed to playbook {file_playbook_id} ({reason}) using filename only")
                else:
                    # Playbook was provided, mark as manual (only on first file)
                    if playbook_selection_metadata.get("method") is None:
                        playbook_selection_metadata["method"] = "manual"
                        playbook_selection_metadata["playbook_id"] = file_playbook_id

                # NOW load full file for actual processing
                if storage_key:
                    load_msg = f"[PreprocessStage] Loading raw file {file_stem} from exact storage key: {storage_key} (bucket: {storage_bucket or 'primedata-raw'})"
                    self.logger.info(load_msg)
                    try:
                        self.logger.info(
                            f"[PreprocessStage] About to call storage.get_raw_text(file_stem={file_stem}, storage_key={storage_key}, storage_bucket={storage_bucket})"
                        )
                        raw_text = storage.get_raw_text(file_stem, storage_key=storage_key, storage_bucket=storage_bucket)
                        self.logger.info(
                            f"[PreprocessStage] storage.get_raw_text() returned: {'None' if raw_text is None else f'{len(raw_text)} characters'}"
                        )
                    except Exception as e:
                        self.logger.error(
                            f"[PreprocessStage] Exception while calling storage.get_raw_text() for {file_stem}: {type(e).__name__}: {str(e)}",
                            exc_info=True,
                        )
                        import traceback

                        self.logger.error(f"[PreprocessStage] get_raw_text() traceback:\n{traceback.format_exc()}")
                        raw_text = None
                else:
                    self.logger.warning(
                        f"[PreprocessStage] No storage_key found for {file_stem} in file_stem_to_storage_key map. Using constructed path (.txt extension)"
                    )
                    try:
                        raw_text = storage.get_raw_text(file_stem)
                    except Exception as e:
                        self.logger.error(
                            f"[PreprocessStage] Exception while calling storage.get_raw_text() (constructed path) for {file_stem}: {type(e).__name__}: {str(e)}",
                            exc_info=True,
                        )
                        import traceback

                        self.logger.error(
                            f"[PreprocessStage] get_raw_text() (constructed) traceback:\n{traceback.format_exc()}"
                        )
                        raw_text = None

                if not raw_text:
                    # Check if it's an image file (expected to fail)
                    is_image_file = filename.lower().endswith(UNSUPPORTED_IMAGE_EXTENSIONS)
                    if is_image_file:
                        warn_msg = (
                            f"[PreprocessStage] ⚠️ Skipping image file {file_stem} (filename: {filename}). "
                            f"Image files cannot be extracted as text. "
                            f"Supported formats: PDF, DOCX, DOC, TXT, HTML, JSON, CSV"
                        )
                        self.logger.warning(warn_msg)
                        failed_files.append(file_stem)
                        continue
                    else:
                        error_msg = (
                            f"[PreprocessStage] ❌ Raw text extraction FAILED for {file_stem}. "
                            f"storage key: {storage_key if storage_key else 'constructed path'}, "
                            f"Bucket: {storage_bucket or 'primedata-raw'}, "
                            f"Filename: {filename}. "
                            f"File may be missing from storage, corrupted, or in unsupported format. "
                            f"Supported formats: PDF, DOCX, DOC, TXT, HTML, JSON, CSV"
                        )
                        # Use both loguru and std logging for Airflow visibility
                        self.logger.error(error_msg)
                        failed_files.append(file_stem)
                        continue

                self.logger.info(
                    f"[PreprocessStage] ✓ Successfully loaded raw text for {file_stem}: {len(raw_text)} characters"
                )

                # Validate raw_text has content
                if not raw_text or len(raw_text.strip()) == 0:
                    error_msg = f"[PreprocessStage] ❌ Raw text is empty for {file_stem} after extraction"
                    self.logger.error(error_msg)
                    failed_files.append(file_stem)
                    continue

                # Log preview of raw text
                preview = raw_text[:200].replace('\n', '\\n')
                self.logger.debug(f"[PreprocessStage] Raw text preview for {file_stem}: {preview}...")

                # Store raw text to S3/GCS for later retrieval (e.g., by chunk quality API)
                try:
                    storage.put_raw_text(file_stem, raw_text)
                    self.logger.info(f"[PreprocessStage] ✅ Stored raw text to S3/GCS for {file_stem}")
                except Exception as e:
                    self.logger.warning(f"[PreprocessStage] ⚠️ Failed to store raw text to S3/GCS: {e}")
                    # Don't fail the entire preprocessing - continue without raw text storage

                # Route playbook if not provided
                file_playbook_id = initial_playbook_id  # Use initial playbook_id for this file
                if not file_playbook_id:
                    # Auto-detect playbook
                    chosen_id, reason = route_playbook(sample_text=raw_text[:PLAYBOOK_ROUTING_SAMPLE_CHARS], filename=file_stem)
                    file_playbook_id = chosen_id
                    # Update selection metadata for auto-detection (only on first file)
                    if playbook_selection_metadata.get("method") is None:
                        playbook_selection_metadata["method"] = "auto_detected"
                        playbook_selection_metadata["playbook_id"] = chosen_id
                        playbook_selection_metadata["reason"] = reason
                        playbook_selection_metadata["detected_at"] = datetime.utcnow().isoformat() + "Z"
                    self.logger.info(f"Auto-routed to playbook {file_playbook_id} ({reason})")
                else:
                    # Playbook was provided, mark as manual (only on first file)
                    if playbook_selection_metadata.get("method") is None:
                        playbook_selection_metadata["method"] = "manual"
                        playbook_selection_metadata["playbook_id"] = file_playbook_id

                # Use file_playbook_id for this file's processing
                playbook_id = file_playbook_id

                # Load playbook (support custom playbooks from database)
                try:
                    workspace_id = context.get("workspace_id")
                    db_session = context.get("db")
                    playbook = load_playbook_yaml(
                        playbook_id, workspace_id=str(workspace_id) if workspace_id else None, db_session=db_session
                    )
                except Exception as e:
                    self.logger.error(f"Failed to load playbook {playbook_id}: {e}, using empty config")
                    playbook = {}

                # Process document
                self.logger.info(
                    f"[PreprocessStage] About to process document {file_stem}: "
                    f"text_length={len(raw_text)}, playbook_id={playbook_id}, "
                    f"chunking_config_mode={chunking_config.get('mode') if chunking_config else 'None'}, "
                    f"has_resolved_settings={'resolved_settings' in (chunking_config or {})}"
                )

                records, stats = self._process_document(
                    raw_text=raw_text,
                    file_stem=file_stem,
                    filename=f"{file_stem}.txt",
                    playbook=playbook,
                    playbook_id=playbook_id,
                    chunking_config=chunking_config,  # Pass product chunking config
                )

                self.logger.info(
                    f"[PreprocessStage] Document processing completed for {file_stem}: "
                    f"records={len(records)}, sections={stats.get('sections', 0)}, "
                    f"chunks={stats.get('chunks', 0)}"
                )

                all_records.extend(records)
                file_chunk_counts[file_stem] = stats.get("chunks", 0)
                file_sections_counts[file_stem] = stats.get("sections", 0)
                total_sections += stats.get("sections", 0)
                total_mid_sentence_ends += stats.get("mid_sentence_ends", 0)
                if not chunking_config_used and stats.get("chunking_config_used"):
                    chunking_config_used = stats.get("chunking_config_used")
                processed_files.append(file_stem)

                # Store processed JSONL for this file
                storage.put_processed_jsonl(file_stem, records)

                # Store manifest
                manifest = {
                    "filename": f"{file_stem}.txt",
                    "stem": file_stem,
                    "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                    "playbook_id": playbook_id,
                    "stats": stats,
                }
                storage.put_manifest(file_stem, manifest)

            except Exception as e:
                error_msg = f"[PreprocessStage] ❌ EXCEPTION while processing {file_stem}: {type(e).__name__}: {str(e)}"
                self.logger.exception(f"Preprocess failed for file_stem={file_stem}")
                self.logger.error(error_msg, exc_info=True)
                import traceback

                self.logger.error(f"[PreprocessStage] Full traceback for {file_stem}:\n{traceback.format_exc()}")
                self.logger.error(f"[PreprocessStage] Exception details for {file_stem}: {repr(e)}")
                last_exception = error_msg
                failed_files.append(file_stem)
            finally:
                file_duration = (datetime.utcnow() - file_start_time).total_seconds()
                self.logger.info(f"[PreprocessStage] ====== Finished processing {file_stem} in {file_duration:.2f}s ======")

        if not all_records:
            failure_reason = "No records produced from preprocessing"
            if last_exception:
                failure_reason = f"{failure_reason}. Last error: {last_exception}"
            return self._create_result(
                status=StageStatus.FAILED,
                metrics={
                    "processed_files": len(processed_files),
                    "failed_files": len(failed_files),
                    "failed_file_list": failed_files,
                },
                error=failure_reason,
                started_at=started_at,
            )

        # Calculate aggregate metrics
        total_chunks = len(all_records)
        mid_sentence_rate = round(total_mid_sentence_ends / max(total_chunks, 1), 4)

        # Ensure playbook_id is set from selection metadata if available
        final_playbook_id = playbook_selection_metadata.get("playbook_id") or playbook_id

        # Store aggregate metrics
        metrics_list = [
            {
                "file_stem": stem,
                "playbook_id": final_playbook_id,
                "sections": file_sections_counts.get(stem, 0),
                "chunks": file_chunk_counts.get(stem, 0),
                "mid_sentence_boundary_rate": mid_sentence_rate,
            }
            for stem in processed_files
        ]
        storage.put_metrics_json(metrics_list)

        finished_at = datetime.utcnow()

        # Build artifacts map
        artifacts = {
            "processed_jsonl": f"processed/{self.product_id}/v{self.version}/",
            "metrics_json": f"processed/{self.product_id}/v{self.version}/metrics.json",
        }

        metrics = {
            "playbook_id": final_playbook_id,
            "playbook_selection": playbook_selection_metadata,  # Include selection metadata
            "processed_files": len(processed_files),
            "failed_files": len(failed_files),
            "total_sections": total_sections,
            "total_chunks": total_chunks,
            "mid_sentence_boundary_rate": mid_sentence_rate,
            "processed_file_list": processed_files,
            "file_chunk_counts": file_chunk_counts,
            "chunking_config_used": chunking_config_used,
        }

        return self._create_result(
            status=StageStatus.SUCCEEDED,
            metrics=metrics,
            artifacts=artifacts,
            started_at=started_at,
            finished_at=finished_at,
        )

    def _process_document(
        self,
        raw_text: str,
        file_stem: str,
        filename: str,
        playbook: Dict[str, Any],
        playbook_id: str,
        chunking_config: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Process a single document through the preprocessing pipeline.

        Delegates to DocumentProcessor for the actual processing logic.

        :param raw_text: The full raw text content of the document.
        :param file_stem: File stem identifier for naming chunks and artifacts.
        :param filename: Original filename of the document.
        :param playbook: Loaded playbook configuration dictionary.
        :param playbook_id: Identifier of the playbook being used.
        :param chunking_config: Optional product-level chunking configuration that overrides playbook settings.
        :return: Tuple of (records_list, stats_dict) where records_list contains chunk records
            and stats_dict contains processing statistics.
        """
        processor = DocumentProcessor(self.product_id, self.logger)
        return processor.process(
            raw_text, file_stem, filename, playbook, playbook_id,
            chunking_config, getattr(self, '_context_cache', {})
        )
