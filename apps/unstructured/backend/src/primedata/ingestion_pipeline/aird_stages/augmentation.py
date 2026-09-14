"""
AIRD Augmentation Stage for PrimeData — Context Engineering Gap 1.

Enriches processed chunks with external context signals fetched at index time.
For each chunk, a lightweight web search or pre-cached external snippet is
appended as `external_context` in the processed JSONL payload, turning
internal-only chunks into augmented, context-rich records ready for more
accurate RAG.

Design principles:
- Non-blocking: augmentation failures are logged but never fail the pipeline.
- Configurable: enabled/disabled per product via product.use_case_config.
- Budget-aware: limits external fetches to avoid long pipeline runtimes.
- Stored in JSONL only: no schema changes, no extra DB tables.
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from loguru import logger
from primedata.core.constants import AUGMENTATION_MAX_CHUNKS, AUGMENTATION_SNIPPET_MAX_CHARS, AUGMENTATION_MAX_KEYWORDS
from primedata.ingestion_pipeline.aird_stages.base import AirdStage, StageResult, StageStatus


# ── helpers ──────────────────────────────────────────────────────────────────

def _extract_keywords(text: str, max_kw: int = AUGMENTATION_MAX_KEYWORDS) -> List[str]:
    """Extract top-N longest non-stopword keywords from text for building a search query.

    :param text: The input text to extract keywords from.
    :param max_kw: Maximum number of keywords to return.
    :return: List of keyword strings sorted by length (longest first), deduplicated.
    """
    stopwords = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to",
        "for", "of", "with", "by", "from", "is", "are", "was", "were",
        "be", "been", "being", "have", "has", "had", "do", "does", "did",
        "will", "would", "could", "should", "may", "might", "shall",
        "this", "that", "these", "those", "it", "its", "as", "not",
    }
    words = [w.strip(".,;:!?\"'()[]{}").lower() for w in text.split()]
    filtered = [w for w in words if len(w) > 4 and w not in stopwords]
    # Deduplicate while preserving order
    seen = set()
    unique = []
    for w in filtered:
        if w not in seen:
            seen.add(w)
            unique.append(w)
    # Return the longest words as they tend to be most specific
    unique.sort(key=len, reverse=True)
    return unique[:max_kw]


def _fetch_web_snippet(query: str, timeout: float = 5.0) -> Optional[str]:
    """Fetch a short external context snippet via DuckDuckGo Instant Answer API.

    :param query: Search query string to send to DuckDuckGo.
    :param timeout: HTTP request timeout in seconds.
    :return: Snippet text string if found, or None on any failure.
    """
    try:
        import urllib.parse
        import urllib.request

        encoded_q = urllib.parse.quote(query)
        url = f"https://api.duckduckgo.com/?q={encoded_q}&format=json&no_redirect=1&no_html=1&skip_disambig=1"

        req = urllib.request.Request(url, headers={"User-Agent": "PrimeData-Augmentation/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        # Try AbstractText first, then RelatedTopics
        snippet = data.get("AbstractText", "").strip()
        if not snippet:
            topics = data.get("RelatedTopics", [])
            for t in topics:
                if isinstance(t, dict) and t.get("Text"):
                    snippet = t["Text"].strip()
                    break

        return snippet if snippet else None

    except Exception as e:
        logger.debug(f"External fetch failed (non-fatal): {e}")
        return None


# ── stage ────────────────────────────────────────────────────────────────────

class AugmentationStage(AirdStage):
    """
    Augmentation stage: enriches processed JSONL records with external context.

    Reads the processed JSONL files (output of preprocessing), fetches a
    lightweight external snippet for representative chunks, and writes
    augmented JSONL files back to storage. The downstream indexing stage
    will pick up `external_context` from the JSONL payload.

    Configuration (via context["augmentation_config"] or use_case_config):
        enabled (bool): Whether to run this stage. Default False (opt-in).
        max_chunks_to_augment (int): Max chunks to augment (budget). Default 50.
        snippet_max_chars (int): Max chars to store per external snippet. Default 300.
        keyword_count (int): Keywords to extract per chunk. Default 5.
    """

    @property
    def stage_name(self) -> str:
        """Return the unique name of this stage.

        :return: The string 'augmentation'.
        """
        return "augmentation"

    def get_required_artifacts(self) -> list[str]:
        """Return artifacts required by the augmentation stage.

        :return: List containing 'processed_jsonl' as the required input artifact.
        """
        return ["processed_jsonl"]

    def execute(self, context: Dict[str, Any]) -> StageResult:
        """Execute the augmentation stage to enrich chunks with external context snippets.

        :param context: Stage execution context containing 'storage' (AirdStorageAdapter),
            optionally 'augmentation_config' or 'use_case_config' with augmentation settings,
            and 'processed_files' (list of file stems to augment).
        :return: StageResult with augmentation metrics including counts of enriched and skipped chunks.
        """
        started_at = datetime.utcnow()
        storage = context.get("storage")

        if not storage:
            return self._create_result(
                status=StageStatus.FAILED,
                metrics={},
                error="Storage adapter not found in context",
                started_at=started_at,
            )

        # Resolve augmentation config — default is disabled for backward compat
        aug_cfg: Dict[str, Any] = context.get("augmentation_config") or {}

        # Also check use_case_config for an "augmentation" sub-key
        use_case_cfg = context.get("use_case_config") or {}
        if isinstance(use_case_cfg, dict) and "augmentation" in use_case_cfg:
            aug_cfg = {**use_case_cfg["augmentation"], **aug_cfg}

        enabled: bool = bool(aug_cfg.get("enabled", False))
        if not enabled:
            self.logger.info("Augmentation stage skipped (not enabled in config)")
            return self._create_result(
                status=StageStatus.SKIPPED,
                metrics={"reason": "augmentation_disabled"},
                started_at=started_at,
            )

        max_chunks: int = int(aug_cfg.get("max_chunks_to_augment", AUGMENTATION_MAX_CHUNKS))
        snippet_max_chars: int = int(aug_cfg.get("snippet_max_chars", AUGMENTATION_SNIPPET_MAX_CHARS))
        keyword_count: int = int(aug_cfg.get("keyword_count", AUGMENTATION_MAX_KEYWORDS))

        processed_files = context.get("processed_files", [])
        if not processed_files:
            preprocess_result = context.get("preprocess_result")
            if preprocess_result and preprocess_result.get("processed_file_list"):
                processed_files = preprocess_result["processed_file_list"]

        if not processed_files:
            return self._create_result(
                status=StageStatus.SKIPPED,
                metrics={"reason": "no_processed_files"},
                started_at=started_at,
            )

        self.logger.info(
            f"Augmentation: processing {len(processed_files)} files, "
            f"max_chunks={max_chunks}, snippet_max_chars={snippet_max_chars}"
        )

        augmented_count = 0
        failed_count = 0
        skipped_count = 0
        augmented_files: List[str] = []

        for file_stem in processed_files:
            try:
                records = storage.get_processed_jsonl(file_stem)
                if not records:
                    self.logger.warning(f"No records for {file_stem}, skipping")
                    continue

                augmented_records = []
                for rec in records:
                    if not isinstance(rec, dict):
                        augmented_records.append(rec)
                        continue

                    # Budget check
                    if augmented_count >= max_chunks:
                        rec["external_context"] = None
                        rec["augmentation_skipped"] = True
                        augmented_records.append(rec)
                        skipped_count += 1
                        continue

                    text = (rec.get("text") or "").strip()
                    if len(text) < 80:
                        # Too short to extract meaningful keywords
                        rec["external_context"] = None
                        augmented_records.append(rec)
                        skipped_count += 1
                        continue

                    # Build search query from keywords
                    keywords = _extract_keywords(text, max_kw=keyword_count)
                    if not keywords:
                        rec["external_context"] = None
                        augmented_records.append(rec)
                        skipped_count += 1
                        continue

                    query = " ".join(keywords[:3])  # Use top-3 keywords for search
                    snippet = _fetch_web_snippet(query)

                    if snippet:
                        rec["external_context"] = snippet[:snippet_max_chars]
                        rec["external_context_source"] = "duckduckgo_instant"
                        rec["external_context_query"] = query
                        rec["external_context_fetched_at"] = datetime.utcnow().isoformat()
                        augmented_count += 1
                    else:
                        rec["external_context"] = None
                        failed_count += 1

                    augmented_records.append(rec)

                # Write augmented records back to storage
                augmented_jsonl = "\n".join(
                    json.dumps(r, ensure_ascii=False, default=str) for r in augmented_records
                )
                storage.put_artifact(
                    f"{file_stem}.augmented.jsonl",
                    augmented_jsonl,
                    content_type="application/x-ndjson",
                )
                augmented_files.append(file_stem)

            except Exception as e:
                self.logger.error(f"Augmentation failed for {file_stem}: {e}", exc_info=True)
                failed_count += 1
                continue

        finished_at = datetime.utcnow()

        self.logger.info(
            f"Augmentation complete: {augmented_count} chunks enriched, "
            f"{skipped_count} skipped (budget/short), {failed_count} fetch failures"
        )

        return self._create_result(
            status=StageStatus.SUCCEEDED,
            metrics={
                "augmented_chunks": augmented_count,
                "skipped_chunks": skipped_count,
                "failed_fetches": failed_count,
                "augmented_files": augmented_files,
                "max_chunks_budget": max_chunks,
            },
            started_at=started_at,
            finished_at=finished_at,
        )
