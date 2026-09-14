"""
Auto-detection functions for playbook and chunking configuration.

This module contains functions responsible for sampling raw files and
auto-detecting the optimal playbook and chunking configuration based
on content analysis. Extracted from dag_tasks.py for modularity.
"""

from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from primedata.db.models import Product, RawFile
from primedata.ingestion_pipeline.pipeline_config import resolve_content_hint
from primedata.utils.logger import get_logger

logger = get_logger(__name__)


def sample_files_for_analysis(
    raw_file_records: List[RawFile], max_files: int = 5, max_per_datasource: int = 2
) -> List[RawFile]:
    """
    Sample representative files from raw file records for content analysis.

    Strategy:
    - Group files by data_source_id to ensure representation across datasources
    - Randomly select 1-2 files per datasource (up to max_files total)
    - Prioritize files with diverse extensions/types for better analysis

    Args:
        raw_file_records: List of RawFile records to sample from
        max_files: Maximum total files to sample (default: 5)
        max_per_datasource: Maximum files per datasource (default: 2)

    Returns:
        List of sampled RawFile records
    """
    import random

    if not raw_file_records:
        return []

    # Group files by data_source_id (None is treated as a single group)
    files_by_datasource: Dict[Optional[UUID], List[RawFile]] = {}
    for record in raw_file_records:
        ds_id = record.data_source_id
        if ds_id not in files_by_datasource:
            files_by_datasource[ds_id] = []
        files_by_datasource[ds_id].append(record)

    logger.info(f"Grouped {len(raw_file_records)} files into {len(files_by_datasource)} datasource(s)")

    # Sample files: up to max_per_datasource per datasource, up to max_files total
    sampled_files: List[RawFile] = []

    # Shuffle datasources to randomize selection order
    datasource_ids = list(files_by_datasource.keys())
    random.shuffle(datasource_ids)

    for ds_id in datasource_ids:
        if len(sampled_files) >= max_files:
            break

        files_in_datasource = files_by_datasource[ds_id]

        # Prioritize files with diverse extensions for better analysis
        # Sort by extension diversity (prefer .pdf, .txt, .html, .docx, etc.)
        def extension_diversity_key(record: RawFile) -> int:
            ext = Path(record.filename).suffix.lower()
            # Priority order: pdf > txt > html > docx > others
            priority_exts = {'.pdf': 5, '.txt': 4, '.html': 3, '.htm': 3, '.docx': 2, '.doc': 2}
            return priority_exts.get(ext, 1)

        files_in_datasource_sorted = sorted(files_in_datasource, key=extension_diversity_key, reverse=True)

        # Randomly select up to max_per_datasource files from this datasource
        num_to_sample = min(max_per_datasource, len(files_in_datasource_sorted), max_files - len(sampled_files))
        if num_to_sample > 0:
            # Randomly shuffle and take first num_to_sample
            random.shuffle(files_in_datasource_sorted)
            sampled_files.extend(files_in_datasource_sorted[:num_to_sample])

    logger.info(f"Sampled {len(sampled_files)} files from {len(raw_file_records)} total files across {len(files_by_datasource)} datasource(s)")
    for sampled in sampled_files:
        logger.info(f"  - {sampled.filename} (datasource: {sampled.data_source_id}, extension: {Path(sampled.filename).suffix})")

    return sampled_files


def extract_text_sample_from_file(
    storage: Any, raw_file: RawFile, max_chars: Optional[int] = 5000
) -> Optional[str]:
    """
    Extract text sample from a raw file for analysis.

    Args:
        storage: AirdStorageAdapter instance
        raw_file: RawFile record
        max_chars: Maximum characters to extract (default: 5000). Use None for full text.

    Returns:
        Text sample or None if extraction fails
    """
    try:
        filename = raw_file.filename
        file_stem = raw_file.file_stem
        storage_key = raw_file.storage_key
        storage_bucket = raw_file.storage_bucket

        # Extract text based on file type
        if filename.lower().endswith('.pdf'):
            # For PDFs, try to extract first 2-3 pages (roughly 2000-5000 chars)
            try:
                text = storage.get_raw_text(file_stem, storage_key=storage_key, storage_bucket=storage_bucket)
                if text:
                    return text if max_chars is None else text[:max_chars]
            except Exception as e:
                logger.warning(f"Failed to extract text from PDF {filename}: {e}")
                return None
        else:
            # For text files, read directly
            try:
                text = storage.get_raw_text(file_stem, storage_key=storage_key, storage_bucket=storage_bucket)
                if text:
                    return text if max_chars is None else text[:max_chars]
            except Exception as e:
                logger.warning(f"Failed to extract text from {filename}: {e}")
                return None

        return None
    except Exception as e:
        logger.warning(f"Error extracting text sample from {raw_file.filename}: {e}")
        return None


def auto_detect_playbook_and_chunking(
    product: Product,
    raw_file_records: List[RawFile],
    storage: Any,
    db: Session,
) -> Dict[str, Any]:
    """
    Auto-detect playbook and chunking configuration from sampled files.

    Args:
        product: Product instance to update
        raw_file_records: List of RawFile records to sample from
        storage: AirdStorageAdapter instance for reading files
        db: Database session

    Returns:
        Dict with detected playbook_id and chunking_config updates, or empty dict if no detection needed
    """
    from primedata.ingestion_pipeline.aird_stages.playbooks import route_playbook
    from primedata.analysis.content_analyzer import build_representative_sample, content_analyzer

    updates = {}
    needs_playbook_detection = product.playbook_id is None
    needs_chunking_detection = (
        product.chunking_config
        and isinstance(product.chunking_config, dict)
        and product.chunking_config.get("mode") == "auto"
    )

    if not needs_playbook_detection and not needs_chunking_detection:
        logger.info("No auto-detection needed: playbook_id is set and chunking mode is not auto")
        return updates

    if not raw_file_records:
        logger.warning("No raw files available for auto-detection")
        return updates

    # Sample files for analysis
    sampled_files = sample_files_for_analysis(raw_file_records, max_files=5, max_per_datasource=2)
    if not sampled_files:
        logger.warning("No files sampled for auto-detection")
        return updates

    # Collect text samples and analyze
    playbook_detections = []
    chunking_analyses = []
    sample_files_analyzed = []

    hint_reason = None
    content_hint = resolve_content_hint(product.playbook_id, product.use_case_description)
    if content_hint and product.use_case_description:
        hint_reason = "use_case_description"
    elif content_hint and product.playbook_id:
        hint_reason = "playbook_id"

    confidence_threshold = 0.7
    if product.chunking_config and isinstance(product.chunking_config, dict):
        auto_settings = product.chunking_config.get("auto_settings", {})
        if isinstance(auto_settings, dict):
            confidence_threshold = auto_settings.get("confidence_threshold", confidence_threshold)

    for raw_file in sampled_files:
        try:
            # Extract full text for representative sampling
            full_text = extract_text_sample_from_file(storage, raw_file, max_chars=None)
            text_sample = build_representative_sample(full_text or "", chunk=5000, max_total=20000)

            if not text_sample or len(text_sample.strip()) < 100:
                logger.warning(f"Skipping {raw_file.filename}: insufficient text content ({len(text_sample or '')} chars)")
                continue

            sample_files_analyzed.append({
                "filename": raw_file.filename,
                "file_stem": raw_file.file_stem,
                "data_source_id": str(raw_file.data_source_id) if raw_file.data_source_id else None,
                "chars_extracted": len(text_sample),
                "full_text_length": len(full_text or ""),
            })

            # Auto-detect playbook if needed
            if needs_playbook_detection:
                try:
                    playbook_id, reason = route_playbook(sample_text=text_sample, filename=raw_file.filename)
                    playbook_detections.append((playbook_id, reason))
                    logger.info(f"Detected playbook for {raw_file.filename}: {playbook_id} ({reason})")
                except Exception as e:
                    logger.warning(f"Failed to detect playbook for {raw_file.filename}: {e}")

            # Auto-detect chunking config if needed
            if needs_chunking_detection:
                try:
                    chunking_config = content_analyzer.analyze_content(
                        content=text_sample,
                        filename=raw_file.filename,
                        hint=content_hint,
                        full_text_length=len(full_text or ""),
                    )
                    chunking_analyses.append(chunking_config)
                    logger.info(
                        f"Analyzed chunking for {raw_file.filename}: "
                        f"content_type={chunking_config.content_type.value}, "
                        f"confidence={chunking_config.confidence:.2f}, "
                        f"chunk_size={chunking_config.chunk_size}"
                    )
                except Exception as e:
                    logger.warning(f"Failed to analyze chunking for {raw_file.filename}: {e}")

        except Exception as e:
            logger.warning(f"Error processing {raw_file.filename} for auto-detection: {e}")
            continue

    # Determine most common/relevant playbook
    if needs_playbook_detection and playbook_detections:
        playbook_counts = Counter([pb_id for pb_id, _ in playbook_detections])
        most_common_playbook, count = playbook_counts.most_common(1)[0]
        total_detections = len(playbook_detections)

        # Get reason from most common playbook
        most_common_reason = next((reason for pb_id, reason in playbook_detections if pb_id == most_common_playbook), "auto_detected")

        logger.info(f"Auto-detected playbook: {most_common_playbook} ({count}/{total_detections} files, reason: {most_common_reason})")

        updates["playbook_id"] = most_common_playbook
        updates["playbook_selection"] = {
            "method": "auto_detected",
            "playbook_id": most_common_playbook,
            "reason": most_common_reason,
            "detected_at": datetime.utcnow().isoformat() + "Z",
            "confidence": count / total_detections if total_detections > 0 else 0.0,
            "files_analyzed": len(sample_files_analyzed),
        }

    # Determine optimal chunking configuration
    if needs_chunking_detection and chunking_analyses:
        # Use the most confident analysis, or aggregate if multiple
        if len(chunking_analyses) == 1:
            best_analysis = chunking_analyses[0]
        else:
            # Aggregate: use most common content type, average chunk sizes, highest confidence
            content_type_counts = Counter([a.content_type.value for a in chunking_analyses])
            most_common_content_type = content_type_counts.most_common(1)[0][0]

            # Find analysis with most common content type and highest confidence
            best_analysis = max(
                [a for a in chunking_analyses if a.content_type.value == most_common_content_type],
                key=lambda a: a.confidence,
                default=chunking_analyses[0],
            )

        logger.info(
            f"Auto-detected chunking config: content_type={best_analysis.content_type.value}, "
            f"confidence={best_analysis.confidence:.2f}, "
            f"chunk_size={best_analysis.chunk_size}, "
            f"chunk_overlap={best_analysis.chunk_overlap}"
        )

        # Update chunking_config with resolved_settings
        # Preserve existing auto_settings and manual_settings for backward compatibility
        current_config = product.chunking_config or {}
        if not isinstance(current_config, dict):
            current_config = {}

        resolved_settings = {
            "content_type": best_analysis.content_type.value,
            "chunk_size": best_analysis.chunk_size,
            "chunk_overlap": best_analysis.chunk_overlap,
            "min_chunk_size": best_analysis.min_chunk_size,
            "max_chunk_size": best_analysis.max_chunk_size,
            "chunking_strategy": best_analysis.strategy.value,
            "confidence": best_analysis.confidence,
            "reasoning": best_analysis.reasoning,
            "confidence_threshold": confidence_threshold,
            "confidence_met": best_analysis.confidence >= confidence_threshold,
            "evidence": best_analysis.evidence,
            "hint_applied": bool(best_analysis.evidence and best_analysis.evidence.get("hint_applied")),
            "hint_reason": hint_reason,
        }

        # Preserve existing settings (backward compatibility)
        updated_config = {
            "mode": current_config.get("mode", "auto"),  # Preserve mode
            "resolved_settings": resolved_settings,  # Add/update resolved_settings
            "last_analyzed": datetime.utcnow().isoformat() + "Z",
            "analysis_confidence": best_analysis.confidence,
            "sample_files_analyzed": sample_files_analyzed,
            # Preserve existing auto_settings and manual_settings
            "auto_settings": current_config.get("auto_settings", {}),
            "manual_settings": current_config.get("manual_settings", {}),
            # Preserve other fields (e.g., preprocessing_flags, optimization_mode)
            **{k: v for k, v in current_config.items() if k not in ["resolved_settings", "last_analyzed", "analysis_confidence", "sample_files_analyzed", "mode"]}
        }

        updates["chunking_config"] = updated_config

        logger.info(f"Updated chunking_config with resolved_settings: {resolved_settings}")
        if best_analysis.confidence < confidence_threshold:
            logger.info(
                "Auto-detected chunking confidence %.2f below threshold %.2f; "
                "resolved_settings will be treated as low confidence.",
                best_analysis.confidence,
                confidence_threshold,
            )

    return updates
