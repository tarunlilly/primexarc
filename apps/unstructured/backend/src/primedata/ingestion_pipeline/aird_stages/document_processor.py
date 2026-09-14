"""
Document processing logic extracted from PreprocessStage.

Contains the DocumentProcessor class which handles the core document preprocessing
pipeline: normalization, page splitting, chunking, and record building.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import regex as re

logger = logging.getLogger(__name__)

from primedata.analysis.content_analyzer import content_analyzer
from primedata.core.constants import (
    PDF_CORRUPTION_FIX_MAX_PASSES,
    PDF_CORRUPTION_SPACE_RATIO_THRESHOLD,
    PLAYBOOK_SAMPLE_MAX_CHARS,
    PREPROCESSING_PROGRESS_LOG_INTERVAL,
)
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
from primedata.ingestion_pipeline.aird_stages.chunking_config_resolver import resolve_chunking_config
from primedata.ingestion_pipeline.aird_stages.optimization.chunk_optimizer import (
    create_optimization_stats,
    optimize_chunk,
)
from primedata.ingestion_pipeline.pipeline_config import resolve_content_hint
from primedata.services.noise_detection import calculate_noise_ratio

# Audience patterns (aligned with AIRD) - ordered by specificity
AUDIENCE_PATTERNS = {
    "hcp": r"\b(hcp|physician|prescriber|clinical|doctor|nurse|clinician|healthcare provider)\b",
    "executive": r"\b(executive|vp|vice president|steerco|cxo|ceo|cto|cfo|board|director|leadership|management)\b",
    "patient": r"\b(patient|caregiver|consumer|user)\b",
    "regulatory": r"\b(regulatory|compliance|sop|policy|regulation|fda|ema|regulatory authority)\b",
    "finance": r"\b(p&l|profit.*loss|variance|forecast|budget|kpi|quarter|quarterly|financial|revenue|earnings|income statement)\b",
    "ops": r"\b(monitoring|deployment|incident|runbook|oncall|slo|sla|kubernetes|cluster|operations|infrastructure)\b",
    "dev": r"\b(api|cli|sdk|endpoint|json|yaml|code|pipeline|ci/cd|developer|engineer|programmer)\b",
    "general": r"\b(overview|introduction|getting started|guide|tutorial|documentation|help|support)\b",
}


def _audience_for(text: str, section: str = "", default: str = "general") -> str:
    """Detect the target audience from text and section name using regex patterns.

    :param text: The chunk text content to analyze for audience indicators.
    :param section: The section heading or name to include in pattern matching.
    :param default: Fallback audience label if no patterns match.
    :return: Detected audience string (e.g., 'hcp', 'executive', 'dev', 'general').
    """
    logger.debug(f"_audience_for() entry | section={section[:50]}, text_length={len(text)}")
    # Combine text and section for better detection
    search_text = f"{section} {text}".lower()

    # Score each audience pattern
    scores = {}
    for name, pat in AUDIENCE_PATTERNS.items():
        matches = len(re.findall(pat, search_text, flags=re.IGNORECASE))
        if matches > 0:
            scores[name] = matches
            logger.debug(f"Audience pattern '{name}' matched {matches} times")

    if scores:
        # Return the audience with the highest score (most matches)
        audience = max(scores.items(), key=lambda x: x[1])[0]
        logger.debug(f"Detected audience: {audience}")
        return audience

    logger.debug(f"Using default audience: {default}")
    return default


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
    logger.debug(f"_build_record() entry | stem={stem}, page={page}, chunk={chunk_idx}/{chunk_of}, text_length={len(text)}")

    # Forensic warning: chunk text shouldn't be tiny. If it is, log loudly so
    # the bug that's emitting near-empty chunks (currently unknown source) can
    # be traced from pipeline logs. Keep raw_text length alongside for context.
    if len(text) < 20:
        logger.warning(
            f"_build_record received suspiciously short chunk text: "
            f"text_len={len(text)} chars (text={text!r}), "
            f"raw_text_len={len(raw_text) if raw_text else 0}, "
            f"stem={stem}, page={page}, section={canon_section}, "
            f"chunk={chunk_idx}/{chunk_of}"
        )

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


def _get_pdf_sample_for_routing(
    storage,
    file_stem: str,
    storage_key: Optional[str],
    storage_bucket: Optional[str],
    max_chars: int = PLAYBOOK_SAMPLE_MAX_CHARS,
    log: Optional[logging.Logger] = None,
) -> Optional[str]:
    """Extract sample text from a PDF for playbook routing without loading the full file.

    :param storage: Storage adapter instance used for file access.
    :param file_stem: File stem identifier for the PDF document.
    :param storage_key: Optional explicit S3/GCS key for the PDF file.
    :param storage_bucket: Optional bucket name override (defaults to 'primedata-raw').
    :param max_chars: Maximum number of characters to extract from the first pages.
    :param log: Optional logger instance.
    :return: Sample text string from the first 2 pages, or None if extraction fails.
    """
    _log = log or logger
    try:
        from io import BytesIO
        from primedata.storage.storage_client import storage_client

        storage_client = storage_client
        bucket = storage_bucket or "primedata-raw"
        key = storage_key or f"{storage._get_raw_prefix()}{file_stem}.pdf"

        # Get PDF bytes
        pdf_data = storage_client.get_bytes(bucket, key)
        if not pdf_data:
            return None

        # Extract only first 2 pages
        try:
            from pypdf import PdfReader
            pdf_file = BytesIO(pdf_data)
            reader = PdfReader(pdf_file)

            text_parts = []
            for i, page in enumerate(reader.pages[:2]):  # Only first 2 pages
                try:
                    page_text = page.extract_text()
                    text_parts.append(page_text)
                    if len(''.join(text_parts)) > max_chars:
                        break
                except Exception:
                    continue

            sample_text = '\n'.join(text_parts)
            return sample_text[:max_chars] if sample_text else None
        except ImportError:
            # Fallback to PyPDF2
            try:
                from PyPDF2 import PdfReader
                pdf_file = BytesIO(pdf_data)
                reader = PdfReader(pdf_file)
                text_parts = []
                for page in reader.pages[:2]:  # Only first 2 pages
                    text_parts.append(page.extract_text())
                sample_text = '\n'.join(text_parts)
                return sample_text[:max_chars] if sample_text else None
            except Exception:
                return None
    except Exception as e:
        _log.warning(f"Failed to extract PDF sample for routing: {e}")
        return None


def _get_text_sample_for_routing(
    storage,
    file_stem: str,
    storage_key: Optional[str],
    storage_bucket: Optional[str],
    max_chars: int = PLAYBOOK_SAMPLE_MAX_CHARS,
    log: Optional[logging.Logger] = None,
) -> Optional[str]:
    """Read the first N characters of a text file for playbook routing without loading the full file.

    :param storage: Storage adapter instance used for file access.
    :param file_stem: File stem identifier for the text document.
    :param storage_key: Optional explicit S3/GCS key for the file.
    :param storage_bucket: Optional bucket name override (defaults to 'primedata-raw').
    :param max_chars: Maximum number of characters to read from the file.
    :param log: Optional logger instance.
    :return: Sample text string, or None if reading fails.
    """
    _log = log or logger
    try:
        from primedata.storage.storage_client import storage_client

        storage_client = storage_client
        bucket = storage_bucket or "primedata-raw"
        key = storage_key or f"{storage._get_raw_prefix()}{file_stem}.txt"

        # Get object bytes
        data = storage_client.get_bytes(bucket, key)
        if not data:
            return None

        # Try to decode as UTF-8 and return first max_chars
        try:
            text = data.decode("utf-8", errors="ignore")
            return text[:max_chars]
        except Exception:
            return None
    except Exception as e:
        _log.warning(f"Failed to read text sample for routing: {e}")
        return None


def _extract_enhanced_metadata(rec: Dict[str, Any], chunk_text: str, preprocessing_flags: Dict[str, Any]) -> None:
    """Extract enhanced metadata (dates, author, version) from chunk text and update the record in-place.

    :param rec: The chunk record dict to update.
    :param chunk_text: The chunk text to extract metadata from.
    :param preprocessing_flags: Preprocessing flags dict with extraction settings.
    """
    if not (preprocessing_flags.get("force_metadata_extraction") or preprocessing_flags.get("additional_metadata_fields")):
        return

    import re as regex_module

    # Try to extract dates from text
    date_patterns = [
        r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b",
        r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b",
        r"\b\d{4}-\d{2}-\d{2}\b",
    ]

    dates_found = []
    for pattern in date_patterns:
        matches = regex_module.findall(pattern, chunk_text, regex_module.IGNORECASE)
        dates_found.extend(matches[:3])

    if dates_found:
        rec["doc_date"] = dates_found[0]
        if preprocessing_flags.get("additional_metadata_fields"):
            existing_tags = rec.get("tags", "")
            if existing_tags:
                rec["tags"] = f"{existing_tags}; dates:{','.join(dates_found[:3])}"
            else:
                rec["tags"] = f"dates:{','.join(dates_found[:3])}"

    # Extract additional metadata if additional_fields flag is set
    if preprocessing_flags.get("additional_metadata_fields"):
        author_pattern = r"(?:By|Author|Written by|Created by):\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)"
        author_match = regex_module.search(author_pattern, chunk_text, regex_module.IGNORECASE)
        if author_match:
            author = author_match.group(1)
            existing_tags = rec.get("tags", "")
            if existing_tags:
                rec["tags"] = f"{existing_tags}; author:{author}"
            else:
                rec["tags"] = f"author:{author}"

        version_pattern = r"\b(v|version|ver|v\.)\s*(\d+(?:\.\d+)+)\b"
        version_matches = regex_module.findall(version_pattern, chunk_text, regex_module.IGNORECASE)
        if version_matches:
            versions = [m[1] for m in version_matches[:2]]
            existing_tags = rec.get("tags", "")
            if existing_tags:
                rec["tags"] = f"{existing_tags}; versions:{','.join(versions)}"
            else:
                rec["tags"] = f"versions:{','.join(versions)}"


class DocumentProcessor:
    """Processes a single document through the preprocessing pipeline.

    Handles normalization, page splitting, chunking, optimization, and record building.
    """

    def __init__(self, product_id: UUID, log: logging.Logger):
        """Initialize the document processor.

        :param product_id: UUID of the product being processed.
        :param log: Logger instance for output.
        """
        self.product_id = product_id
        self.logger = log
        self._context_cache: Dict[str, Any] = {}
        self._page_boundaries: List[Dict[str, Any]] = []
        self._optimization_config: Dict[str, Any] = {}
        self._chunk_optimization_stats: Optional[Dict[str, Any]] = None

    def process(
        self,
        raw_text: str,
        file_stem: str,
        filename: str,
        playbook: Dict[str, Any],
        playbook_id: str,
        chunking_config: Optional[Dict[str, Any]] = None,
        context_cache: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Process a single document through the preprocessing pipeline.

        :param raw_text: The full raw text content of the document.
        :param file_stem: File stem identifier for naming chunks and artifacts.
        :param filename: Original filename of the document.
        :param playbook: Loaded playbook configuration dictionary.
        :param playbook_id: Identifier of the playbook being used.
        :param chunking_config: Optional product-level chunking configuration that overrides playbook settings.
        :param context_cache: Optional context cache with workspace_id, db, use_case_description.
        :return: Tuple of (records_list, stats_dict) where records_list contains chunk records
            and stats_dict contains processing statistics.
        """
        if context_cache:
            self._context_cache = context_cache

        # 1) Basic normalization (unwrap + PII redaction) - but NOT line-joining normalizers yet
        # We need to preserve page markers for page splitting
        unwrapped = normalize_wrapped_lines(raw_text)
        redacted = redact_pii(unwrapped)

        # 2) Split into pages FIRST (before applying normalizers that join lines)
        # This preserves page markers which are needed for correct page detection
        pages = split_pages_by_config(redacted, playbook.get("page_fences", []))

        # Log page splitting results
        if len(pages) > 1:
            self.logger.info(f"Split text into {len(pages)} pages (page numbers: {[p['page'] for p in pages]})")
        else:
            self.logger.warning(
                f"Page splitting found only {len(pages)} page(s). Page markers may be missing or not matching patterns."
            )

        # 3) Now apply normalizers to each page separately (after page markers have been used)
        # Filter out normalizers that join lines across page boundaries (we'll apply those per-page)
        line_joining_patterns = [
            r"(?m)(?<![.!?])\r?\n(?!\r?\n)",  # Join continuation lines
            r"(?m)\r?\n(?=[a-z])",  # Join lowercase-leading lines
        ]
        pre_normalizers = playbook.get("pre_normalizers", [])
        safe_normalizers = []
        line_joining_normalizers = []

        for norm in pre_normalizers:
            pattern = norm.get("pattern", "")
            if isinstance(pattern, list):
                pattern = "[" + "".join(str(c) for c in pattern) + "]"
            if not isinstance(pattern, str):
                self.logger.warning(
                    f"Normalizer pattern must be string or list, got {type(pattern)}: {pattern}, skipping"
                )
                continue
            # Check if this normalizer joins lines (could affect page markers)
            is_line_joiner = any(re.search(pat, pattern) for pat in line_joining_patterns)
            if is_line_joiner:
                line_joining_normalizers.append(norm)
            else:
                safe_normalizers.append(norm)

        # 4) Apply normalizers to each page
        normalized_pages = []
        for page_data in pages:
            page_text = page_data["text"]
            page_num = page_data["page"]

            # Apply all normalizers to this page
            normalized_text = apply_normalizers(page_text, pre_normalizers)
            normalized_pages.append({"page": page_num, "text": normalized_text})

        # 5) Fix PDF extraction corruption: spaces between characters (e.g., "B e z o s" -> "Bezos")
        cleaned_pages = []
        for page_data in normalized_pages:
            page_text = page_data["text"]
            page_num = page_data["page"]

            if len(page_text) > 100:
                sample = page_text[:1000]
                space_ratio = sample.count(" ") / len(sample) if len(sample) > 0 else 0
                if space_ratio > PDF_CORRUPTION_SPACE_RATIO_THRESHOLD:
                    self.logger.warning(
                        f"Detected PDF extraction corruption on page {page_num} (space ratio: {space_ratio:.2%}), attempting to fix..."
                    )
                    for _ in range(PDF_CORRUPTION_FIX_MAX_PASSES):
                        old_page_text = page_text
                        page_text = re.sub(r"([A-Za-z0-9]) ([A-Za-z0-9])", r"\1\2", page_text)
                        if page_text == old_page_text:
                            break
                    self.logger.info(f"Applied fix for PDF extraction corruption on page {page_num}")

            cleaned_pages.append({"page": page_num, "text": page_text})

        # Log cleaned pages summary
        total_cleaned_chars = sum(len(p.get("text", "")) for p in cleaned_pages)
        pages_with_content = [p for p in cleaned_pages if p.get("text", "").strip()]
        self.logger.info(
            f"Text cleaning completed for {file_stem}: "
            f"{len(cleaned_pages)} total pages, {len(pages_with_content)} pages with content, "
            f"{total_cleaned_chars:,} total characters"
        )

        if len(pages_with_content) == 0:
            error_msg = f"No pages with content after cleaning for {file_stem}. All pages are empty."
            self.logger.error(error_msg)
            return [], {"sections": 0, "chunks": 0, "mid_sentence_ends": 0, "chunking_config_used": {}}

        # Combine pages back into single text for optimization (which works at document level)
        cleaned = "\n".join([f"\n=== PAGE {p['page']} ===\n{p['text']}" for p in cleaned_pages])

        # Store page mapping for later use in chunk creation
        self._page_boundaries = []
        offset = 0
        for p in cleaned_pages:
            self._page_boundaries.append({"page": p["page"], "start": offset, "end": offset + len(p["text"])})
            offset += len(p["text"]) + 2  # +2 for "\n\n" separator

        # Apply pattern-based optimization at document level (fast, free)
        preprocessing_flags = {}
        optimization_mode = "pattern"  # Default to pattern-based
        llm_config = None
        quality_threshold = 75

        if chunking_config:
            preprocessing_flags = chunking_config.get("preprocessing_flags", {})
            optimization_mode = chunking_config.get("optimization_mode", "pattern")
            quality_threshold = preprocessing_flags.get("llm_quality_threshold", 75)

            # Prepare LLM config if LLM or hybrid mode is enabled (for per-chunk optimization)
            if optimization_mode in ["llm", "hybrid"]:
                # Try to get LLM API key from workspace settings first, then environment
                llm_api_key = None

                # Get workspace_id and db from cached context
                workspace_id = None
                db_session = None

                if self._context_cache:
                    workspace_id = self._context_cache.get("workspace_id")
                    db_session = self._context_cache.get("db")

                # Try to get from workspace settings
                if workspace_id and db_session:
                    try:
                        from uuid import UUID as UUIDType

                        from primedata.db.models import Workspace

                        # Convert string UUID to UUID object if needed
                        if isinstance(workspace_id, str):
                            workspace_id = UUIDType(workspace_id)

                        workspace = db_session.query(Workspace).filter(Workspace.id == workspace_id).first()

                        if workspace and workspace.settings:
                            llm_api_key = workspace.settings.get("openai_api_key")
                            if llm_api_key:
                                self.logger.info(
                                    f"Using OpenAI API key from workspace settings for {optimization_mode} optimization (per-chunk)"
                                )
                    except Exception as e:
                        self.logger.warning(f"Failed to fetch API key from workspace settings: {e}")

                # Fallback to environment variable if not found in workspace settings
                if not llm_api_key:
                    import os

                    llm_api_key = os.getenv("OPENAI_API_KEY")
                    if llm_api_key:
                        self.logger.info(
                            f"Using OPENAI_API_KEY from environment variable for {optimization_mode} optimization (per-chunk)"
                        )

                if llm_api_key:
                    llm_config = {
                        "api_key": llm_api_key,
                        "model": preprocessing_flags.get("llm_model", "gpt-4-turbo-preview"),
                        "base_url": preprocessing_flags.get("llm_base_url"),  # Optional
                    }
                else:
                    self.logger.warning(
                        f"Optimization mode is '{optimization_mode}' but OPENAI_API_KEY not found in workspace settings or environment. "
                        "Falling back to pattern-based optimization."
                    )
                    optimization_mode = "pattern"  # Fallback to pattern-based

        # Apply pattern-based optimization at document level
        if optimization_mode in ["pattern", "llm", "hybrid"]:
            try:
                from primedata.ingestion_pipeline.aird_stages.optimization.pattern_based import PatternBasedOptimizer

                pattern_optimizer = PatternBasedOptimizer()
                cleaned = pattern_optimizer.optimize(cleaned, preprocessing_flags)

                self.logger.info(f"Pattern-based optimization applied at document level")

            except ImportError as e:
                self.logger.warning(f"Pattern optimizer not available ({e}). Using legacy pattern-based optimization.")
                # Fallback to legacy pattern-based optimization
                if preprocessing_flags.get("enhanced_normalization"):
                    from primedata.ingestion_pipeline.aird_stages.utils.text_processing import apply_enhanced_normalization

                    self.logger.info("Applying enhanced normalization (legacy method)")
                    cleaned = apply_enhanced_normalization(cleaned)

                if preprocessing_flags.get("error_correction"):
                    from primedata.ingestion_pipeline.aird_stages.utils.text_processing import apply_error_correction

                    self.logger.info("Applying error correction (legacy method)")
                    cleaned = apply_error_correction(cleaned)
            except Exception as e:
                self.logger.error(f"Pattern-based optimization failed: {e}. Using original text.", exc_info=True)
                # Continue with original cleaned text

        # Call Cortex LLM for noise reduction analysis
        self.logger.info("Cortex noise reduction: starting call")
        try:
            from primedata.services.cortex_client import call_cortex_model

            cortex_result = call_cortex_model(
                prompt=cleaned[:2000],
                model_context="noise_reduction",
            )
            if cortex_result:
                self.logger.info(f"Cortex noise reduction result: {cortex_result}")
            else:
                self.logger.info("Cortex noise reduction: no result returned (credentials missing or API error)")
        except Exception as cortex_err:
            self.logger.info(f"Cortex noise reduction call skipped: {cortex_err}")

        # Store optimization config for per-chunk LLM optimization (if needed)
        self._optimization_config = {
            "mode": optimization_mode,
            "llm_config": llm_config,
            "quality_threshold": quality_threshold,
            "preprocessing_flags": preprocessing_flags,
        }

        # Re-split into pages after optimization
        if self._page_boundaries:
            pages = split_pages_by_config(cleaned, playbook.get("page_fences", []))
            if len(pages) == 1 and len(self._page_boundaries) > 1:
                # Fall back to stored page info - split by stored boundaries
                pages = []
                text_offset = 0
                for boundary in self._page_boundaries:
                    page_text = cleaned[boundary["start"] : min(boundary["end"], len(cleaned))]
                    if page_text.strip():
                        pages.append({"page": boundary["page"], "text": page_text})
                    text_offset = boundary["end"]
        else:
            pages = split_pages_by_config(cleaned, playbook.get("page_fences", []))

        # Log re-split results
        self.logger.info(
            f"Re-split after optimization for {file_stem}: "
            f"{len(pages)} pages found, {len(cleaned):,} total characters"
        )

        # Validate that we have pages with content
        if not pages:
            self.logger.error(f"No pages found after optimization and re-splitting for {file_stem}.")
            return [], {
                "error": "No pages after processing",
                "sections": 0, "chunks": 0, "sections_detected": 0,
                "mid_sentence_ends": 0, "chunking_config_used": None,
            }

        # Filter to pages with actual content
        pages_with_content = [p for p in pages if p.get("text", "").strip()]
        if not pages_with_content:
            self.logger.error(
                f"All pages are empty after processing for {file_stem}. "
                f"Original text length: {len(raw_text)}, Cleaned text length: {len(cleaned)}."
            )
            return [], {
                "error": "All pages empty after processing",
                "sections": 0, "chunks": 0, "sections_detected": 0,
                "mid_sentence_ends": 0, "chunking_config_used": None,
            }

        if len(pages_with_content) < len(pages):
            self.logger.warning(
                f"After processing: {len(pages_with_content)} pages with content (out of {len(pages)} total)."
            )
        pages = pages_with_content

        # Log page content summary
        total_chars = sum(len(p.get("text", "")) for p in pages)
        self.logger.info(
            f"Page summary for {file_stem}: {len(pages)} pages, {total_chars:,} total chars, "
            f"{total_chars // len(pages):,} avg chars/page"
        )
        for i, page_data in enumerate(pages[:3]):
            preview = page_data.get("text", "")[:150].replace('\n', '\\n')
            self.logger.debug(f"Page {page_data.get('page', i+1)} preview: {preview}...")

        # Check for enhanced metadata extraction flag from chunking_config
        preprocessing_flags = {}
        if chunking_config:
            preprocessing_flags = chunking_config.get("preprocessing_flags", {})

        # 3) Resolve chunking configuration (product config overrides playbook defaults)
        chunking_params = resolve_chunking_config(
            chunking_config=chunking_config,
            playbook=playbook,
            playbook_id=playbook_id,
            cleaned_text=cleaned,
            filename=filename,
            context_cache=self._context_cache,
            log=self.logger,
        )

        # Unpack resolved parameters
        strategy = chunking_params.strategy
        max_tokens = chunking_params.max_tokens
        overlap_sents = chunking_params.overlap_sents
        hard_overlap = chunking_params.hard_overlap
        chunk_size = chunking_params.chunk_size
        chunk_overlap = chunking_params.chunk_overlap
        resolved_chunking_config = chunking_params.resolved_chunking_config
        detected_domain_type = chunking_params.detected_domain_type
        confidence = chunking_params.confidence
        confidence_threshold = chunking_params.confidence_threshold
        confidence_met = chunking_params.confidence_met

        # Log final chunking settings being used for processing
        self.logger.info(
            f"Final chunking settings for {file_stem}: "
            f"mode={chunking_config.get('mode', 'auto') if chunking_config else 'auto'}, "
            f"strategy={strategy}, chunk_size={chunk_size}, chunk_overlap={chunk_overlap}, "
            f"confidence={confidence}, confidence_threshold={confidence_threshold}, confidence_met={confidence_met}"
        )

        # 4) Process pages and sections
        records: List[Dict[str, Any]] = []
        sections_detected = 0
        mid_sentence_ends = 0
        chunks_before_rules = 0

        # Log chunking configuration being used
        self.logger.info(
            f"Chunking configuration for {file_stem}: "
            f"strategy={strategy}, max_tokens={max_tokens}, "
            f"overlap_sents={overlap_sents}, hard_overlap={hard_overlap}"
        )

        # Validate configuration before processing
        if max_tokens <= 0:
            error_msg = f"Invalid chunking configuration: max_tokens={max_tokens}. Falling back to 900."
            self.logger.error(error_msg)
            max_tokens = 900
            chunk_size = max_tokens

        # First, estimate total chunks for progress tracking
        estimated_chunks = 0
        total_text_length = 0
        for page_data in pages:
            page_text = page_data["text"]
            total_text_length += len(page_text)
            try:
                sections = detect_sections_configured(
                    page_text,
                    playbook.get("headers", []),
                    playbook.get("section_aliases", {}),
                )
                for title_raw, canon_section, body_text in sections:
                    if strategy == "paragraph":
                        para_overlap = max(1, int(overlap_sents / 2))
                        chunks = paragraph_chunk(body_text, max_tokens, para_overlap, hard_overlap)
                    elif strategy == "sentence":
                        chunks = sentence_chunk(body_text, max_tokens, overlap_sents, hard_overlap)
                    elif strategy == "char":
                        chunks = char_chunk(body_text, max_tokens, hard_overlap)
                    else:
                        chunks = sentence_chunk(body_text, max_tokens, overlap_sents, hard_overlap)
                    estimated_chunks += len(chunks)
            except Exception as e:
                self.logger.warning(f"Error estimating chunks for page {page_data.get('page', '?')}: {e}", exc_info=True)

        # Log initial progress info
        opt_mode = self._optimization_config.get("mode", "pattern")
        if opt_mode in ["llm", "hybrid"]:
            self.logger.info(
                f"Starting chunk processing: ~{estimated_chunks} chunks, ~{total_text_length:,} characters, mode={opt_mode}"
            )

        # Track progress for periodic logging
        chunks_processed = 0
        chars_processed = 0
        last_progress_log_time = datetime.utcnow()
        PROGRESS_LOG_INTERVAL = PREPROCESSING_PROGRESS_LOG_INTERVAL

        for page_data in pages:
            page_text = page_data["text"]
            page_num = page_data["page"]

            # Validate page has content
            if not page_text.strip():
                self.logger.warning(f"Skipping empty page {page_num} for {file_stem}")
                continue

            # Detect sections
            try:
                sections = detect_sections_configured(
                    page_text,
                    playbook.get("headers", []),
                    playbook.get("section_aliases", {}),
                )
                sections_detected += len(sections)

                # Log if no sections detected
                if not sections:
                    self.logger.warning(
                        f"No sections detected on page {page_num} for {file_stem}. "
                        f"Page text length: {len(page_text)}, Preview: {page_text[:100]}..."
                    )
                    if page_text:
                        first_lines = "\n".join(page_text.split("\n")[:3])
                        self.logger.debug(f"First 3 lines of page {page_num}: {first_lines}")
                    sections = [(f"Page {page_num}", "full_page", page_text)]
                    sections_detected += 1
            except Exception as e:
                self.logger.error(
                    f"Error detecting sections on page {page_num} for {file_stem}: {e}",
                    exc_info=True
                )
                continue

            # Process each section
            for title_raw, canon_section, body_text in sections:
                # Validate section has content
                if not body_text.strip():
                    self.logger.warning(
                        f"Skipping empty section '{canon_section}' on page {page_num} for {file_stem}"
                    )
                    continue
                # Chunk the section based on strategy
                if strategy == "paragraph":
                    para_overlap = max(1, int(overlap_sents / 2))
                    chunks = paragraph_chunk(body_text, max_tokens, para_overlap, hard_overlap)
                elif strategy == "sentence":
                    chunks = sentence_chunk(body_text, max_tokens, overlap_sents, hard_overlap)
                elif strategy == "char":
                    chunks = char_chunk(body_text, max_tokens, hard_overlap)
                else:
                    chunks = sentence_chunk(body_text, max_tokens, overlap_sents, hard_overlap)

                # Log if chunks are empty
                if not chunks:
                    self.logger.error(
                        f"No chunks created for section '{canon_section}' on page {page_num} for {file_stem}. "
                        f"Body text length: {len(body_text)}, Strategy: {strategy}, Max tokens: {max_tokens}, "
                        f"Overlap sentences: {overlap_sents}, Hard overlap: {hard_overlap}"
                    )
                    if body_text:
                        preview = body_text[:200].replace('\n', '\\n')
                        self.logger.debug(f"First 200 chars of body_text for section '{canon_section}': {preview}")
                    self.logger.warning(
                        f"Falling back to single chunk for section '{canon_section}' on page {page_num}."
                    )
                    chunks = [body_text]

                chunks_before_rules += len(chunks)

                # Log first few chunks for debugging
                if chunks_processed == 0:
                    self.logger.info(
                        f"First chunk created: section='{canon_section}', page={page_num}, "
                        f"chunk_length={len(chunks[0])}, total_chunks_in_section={len(chunks)}"
                    )

                # Build records for each chunk
                for idx, chunk_text in enumerate(chunks):
                    # Check for mid-sentence boundary
                    chunk_stripped = chunk_text.strip()
                    chunk_tokens = tokens_estimate(chunk_text)

                    ends_with_punctuation = bool(re.search(r"[.!?]['\")\]]*\s*$", chunk_stripped))
                    ends_with_word_boundary = bool(re.search(r"\w\s*$", chunk_stripped))

                    is_mid_sentence = not ends_with_punctuation and (not ends_with_word_boundary or len(chunk_stripped) < 20)

                    if is_mid_sentence:
                        mid_sentence_ends += 1
                        if chunks_processed < 10 or mid_sentence_ends <= 5:
                            self.logger.warning(
                                f"Mid-sentence break detected in chunk {chunks_processed + 1} "
                                f"(section: {canon_section}, page: {page_num}, tokens: {chunk_tokens}): "
                                f"'{chunk_stripped[-50:]}...'"
                            )

                    # Diagnostic logging: log chunk statistics periodically
                    if chunks_processed < 5 or (chunks_processed % 50 == 0):
                        self.logger.info(
                            f"Chunk {chunks_processed + 1}: tokens={chunk_tokens}, "
                            f"chars={len(chunk_text)}, ends_with_punct={ends_with_punctuation}, "
                            f"mid_sentence={is_mid_sentence}"
                        )

                    # Track progress
                    chunks_processed += 1
                    chars_processed += len(chunk_text)

                    # Log progress periodically
                    if opt_mode in ["llm", "hybrid"] and chunks_processed % PROGRESS_LOG_INTERVAL == 0:
                        elapsed_time = (datetime.utcnow() - last_progress_log_time).total_seconds()
                        chunks_per_sec = PROGRESS_LOG_INTERVAL / max(elapsed_time, 0.1)
                        remaining_chunks = estimated_chunks - chunks_processed
                        estimated_remaining_sec = remaining_chunks / max(chunks_per_sec, 0.1)
                        estimated_remaining_min = estimated_remaining_sec / 60

                        progress_msg = (
                            f"Progress: {chunks_processed}/{estimated_chunks} chunks processed "
                            f"({chunks_processed*100//max(estimated_chunks, 1)}%), "
                            f"{chars_processed:,}/{total_text_length:,} chars ({chars_processed*100//max(total_text_length, 1)}%), "
                            f"~{estimated_remaining_min:.1f} min remaining"
                        )
                        self.logger.info(progress_msg)
                        last_progress_log_time = datetime.utcnow()

                    # Apply per-chunk LLM/hybrid optimization if needed
                    opt_config = self._optimization_config
                    opt_mode = opt_config.get("mode", "pattern")

                    if opt_mode in ["llm", "hybrid"] and opt_config.get("llm_config"):
                        # Initialize stats if not already done
                        if self._chunk_optimization_stats is None:
                            self._chunk_optimization_stats = create_optimization_stats()

                        optimized_chunk_text = optimize_chunk(
                            chunk_text=chunk_text,
                            chunk_idx=idx,
                            optimization_config=opt_config,
                            stats=self._chunk_optimization_stats,
                            log=self.logger,
                        )
                    else:
                        optimized_chunk_text = chunk_text

                    # Build record with optimized chunk text
                    rec = _build_record(
                        stem=file_stem,
                        filename=filename,
                        document_id=file_stem,
                        page=page_num,
                        canon_section=canon_section,
                        title_raw=title_raw,
                        text=optimized_chunk_text,
                        chunk_idx=idx,
                        chunk_of=len(chunks),
                        product_id=self.product_id,
                        domain_type=detected_domain_type,
                        raw_text=raw_text,
                    )

                    # Log domain_type for verification (only log first chunk to avoid spam)
                    if idx == 0:
                        if detected_domain_type:
                            self.logger.info(f"Record {rec['chunk_id']} has domain_type: {detected_domain_type}")
                        else:
                            self.logger.warning(f"Record {rec['chunk_id']} missing domain_type (detected_domain_type was None)")

                    # Enhanced metadata extraction if flag is set
                    _extract_enhanced_metadata(rec, chunk_text, preprocessing_flags)

                    # Apply audience rules from playbook
                    aud = rec["audience"]
                    for rule in playbook.get("audience_rules", []) or []:
                        try:
                            pat = rule.get("pattern")
                            if pat and (
                                re.search(pat, title_raw, flags=re.IGNORECASE)
                                or re.search(pat, chunk_text, flags=re.IGNORECASE)
                            ):
                                aud = rule.get("audience", aud)
                                break
                        except re.error:
                            pass
                    rec["audience"] = aud

                    records.append(rec)

        # Log final progress
        if opt_mode in ["llm", "hybrid"]:
            final_progress_msg = (
                f"Chunk processing complete: {chunks_processed} chunks processed, "
                f"{chars_processed:,} characters processed"
            )
            self.logger.info(final_progress_msg)

        # Log per-chunk optimization summary if LLM/hybrid mode was used
        if self._chunk_optimization_stats is not None:
            stats_data = self._chunk_optimization_stats
            opt_mode = self._optimization_config.get("mode", "pattern")

            if opt_mode in ["llm", "hybrid"]:
                summary_msg = (
                    f"Per-chunk optimization summary: "
                    f"{stats_data['llm_optimized']}/{stats_data['total_chunks']} chunks optimized with LLM, "
                    f"{stats_data['skipped_high_quality']} skipped (already high quality >=75%), "
                    f"{stats_data['pattern_only']} pattern-only, "
                    f"{stats_data['failed']} failed, "
                    f"total cost=${stats_data['total_cost']:.4f}"
                )
                self.logger.info(summary_msg)

            # Reset stats for next document
            self._chunk_optimization_stats = None

        # Calculate stats
        total_chunks = len(records)
        mid_sentence_rate = round(mid_sentence_ends / max(total_chunks, 1), 4)

        # Log comprehensive summary
        self.logger.info(
            f"Processing summary for {file_stem}: "
            f"pages={len(pages)}, sections_detected={sections_detected}, "
            f"total_chunks={total_chunks}, mid_sentence_rate={mid_sentence_rate:.4f}, "
            f"chunks_before_rules={chunks_before_rules}"
        )

        # If no records were created, provide detailed diagnostic info
        if total_chunks == 0:
            self.logger.error(
                f"No records created for {file_stem}! "
                f"Pages processed: {len(pages)}, Sections detected: {sections_detected}, "
                f"Strategy: {strategy}, Max tokens: {max_tokens}, "
                f"chunk_size={chunk_size}, chunk_overlap={chunk_overlap}"
            )
            if pages and pages[0].get("text"):
                sample_page = pages[0]["text"]
                self.logger.error(
                    f"Sample page text (first 500 chars): {sample_page[:500]}"
                )

        stats = {
            "playbook_id": playbook_id,
            "sections": sections_detected,
            "chunks": total_chunks,
            "mid_sentence_boundary_rate": mid_sentence_rate,
            "mid_sentence_ends": mid_sentence_ends,
            "chunking_config_used": resolved_chunking_config,
        }

        return records, stats
