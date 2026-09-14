"""
Context Assembly Service for PrimeData.

Assembles semantically retrieved chunks into a coherent, structured
context block ready for direct LLM prompt injection. This is the
"context engineering" layer — going beyond individual chunk search
to produce rich, attributed, freshness-stamped context windows.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _deduplicate_chunks(chunks: List[Dict[str, Any]], similarity_threshold: float = 0.95) -> List[Dict[str, Any]]:
    """
    Remove near-duplicate chunks based on text overlap.
    Keeps the chunk with the higher similarity score.
    """
    seen: List[str] = []
    unique: List[Dict[str, Any]] = []

    for chunk in chunks:
        text = (chunk.get("text") or "").strip().lower()
        if not text:
            continue

        is_dup = False
        for prev_text in seen:
            # Jaccard similarity on word sets
            a = set(text.split())
            b = set(prev_text.split())
            if not a or not b:
                continue
            jaccard = len(a & b) / len(a | b)
            if jaccard >= similarity_threshold:
                is_dup = True
                break

        if not is_dup:
            seen.append(text)
            unique.append(chunk)

    return unique


def _order_chunks(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Order chunks for coherent reading:
    1. Same document chunks are grouped together
    2. Within a document, ordered by page then chunk_index
    3. Cross-document ordering: by descending similarity score (most relevant first)
    """
    # Group by document
    doc_groups: Dict[str, List[Dict[str, Any]]] = {}
    for chunk in chunks:
        doc = chunk.get("doc_path") or chunk.get("filename") or "unknown"
        doc_groups.setdefault(doc, []).append(chunk)

    # Sort within each document by page, then chunk_index
    for doc in doc_groups:
        doc_groups[doc].sort(
            key=lambda c: (
                c.get("meta", {}).get("page") or 0,
                c.get("meta", {}).get("chunk_index") or 0,
            )
        )

    # Sort documents by the max score of their top chunk
    sorted_docs = sorted(
        doc_groups.items(),
        key=lambda kv: max(c.get("score", 0.0) for c in kv[1]),
        reverse=True,
    )

    ordered: List[Dict[str, Any]] = []
    for _, doc_chunks in sorted_docs:
        ordered.extend(doc_chunks)

    return ordered


def _detect_conflicts(chunks: List[Dict[str, Any]]) -> List[str]:
    """
    Simple heuristic to flag potential conflicts between chunks.
    Currently detects negation patterns across different-source chunks.
    """
    conflicts: List[str] = []
    negation_words = {"not", "no", "never", "cannot", "can't", "won't", "doesn't", "don't", "isn't", "aren't"}

    texts = [(c.get("doc_path", ""), (c.get("text") or "").lower()) for c in chunks]
    seen_key_terms: Dict[str, str] = {}  # term -> source doc

    for doc, text in texts:
        words = set(text.split())
        neg_hits = words & negation_words
        if neg_hits:
            for term in words - neg_hits - {"the", "a", "an", "is", "are", "was"}:
                if len(term) > 4 and term in seen_key_terms and seen_key_terms[term] != doc:
                    conflicts.append(
                        f"Potential conflict: term '{term}' appears with negation in '{doc}' "
                        f"but positively in '{seen_key_terms[term]}'"
                    )
                    break
        else:
            for term in words - {"the", "a", "an", "is", "are", "was"}:
                if len(term) > 4:
                    seen_key_terms.setdefault(term, doc)

    return conflicts[:3]  # Return at most 3 conflict hints


def assemble_context(
    chunks: List[Dict[str, Any]],
    query: str,
    max_tokens: int = 4000,
    deduplicate: bool = True,
    detect_conflicts: bool = True,
) -> Dict[str, Any]:
    """
    Assemble a coherent context block from retrieved chunks.

    Args:
        chunks: List of PlaygroundResult-like dicts with text, score, doc_path, meta.
        query: Original query string (used for attribution header).
        max_tokens: Approximate token budget for the assembled context.
        deduplicate: Whether to remove near-duplicate chunks.
        detect_conflicts: Whether to run conflict detection.

    Returns:
        ContextBlock dict with:
            - context_text: Formatted string ready for LLM injection
            - sources: List of attributed sources with freshness
            - token_estimate: Estimated token count
            - conflicts: List of detected conflict hints
            - freshness_summary: Min/max/avg freshness across chunks
            - assembly_metadata: Stats about the assembly process
    """
    if not chunks:
        return {
            "context_text": "",
            "sources": [],
            "token_estimate": 0,
            "conflicts": [],
            "freshness_summary": {},
            "assembly_metadata": {"total_chunks": 0, "deduplicated": 0, "truncated": False},
        }

    # Step 1: Deduplicate
    original_count = len(chunks)
    if deduplicate:
        chunks = _deduplicate_chunks(chunks)
    dedup_count = original_count - len(chunks)

    # Step 2: Order for coherence
    chunks = _order_chunks(chunks)

    # Step 3: Budget-aware truncation (~4 chars per token estimate)
    chars_budget = max_tokens * 4
    truncated = False
    selected: List[Dict[str, Any]] = []
    used_chars = 0

    for chunk in chunks:
        text = (chunk.get("text") or "").strip()
        if not text:
            continue
        if used_chars + len(text) > chars_budget:
            truncated = True
            break
        selected.append(chunk)
        used_chars += len(text)

    # Step 4: Build formatted context text with section headers and attribution
    lines: List[str] = []
    lines.append(f"## Context for: {query}\n")

    sources: List[Dict[str, Any]] = []
    freshness_scores: List[float] = []

    current_doc = None
    for i, chunk in enumerate(selected, 1):
        doc_path = chunk.get("doc_path") or chunk.get("filename") or "Unknown source"
        section = chunk.get("section") or chunk.get("meta", {}).get("section") or ""
        score = chunk.get("score", 0.0)
        text = (chunk.get("text") or "").strip()
        freshness = chunk.get("meta", {}).get("context_freshness_score") or chunk.get("context_freshness_score")
        ingested_at = chunk.get("meta", {}).get("timestamp") or chunk.get("timestamp")

        # Section header when document changes
        if doc_path != current_doc:
            current_doc = doc_path
            lines.append(f"\n### Source: {doc_path}")
            if ingested_at:
                lines.append(f"*Last updated: {ingested_at[:10] if len(ingested_at) >= 10 else ingested_at}*")

        # Sub-section if available
        if section and section.lower() not in ("general", "unknown", ""):
            lines.append(f"\n**Section: {section}**")

        lines.append(f"\n{text}")

        # Collect source attribution
        source_entry = {
            "index": i,
            "doc_path": doc_path,
            "section": section,
            "similarity_score": round(score, 4),
            "ingested_at": ingested_at,
            "freshness_score": freshness,
        }
        if chunk.get("presigned_url"):
            source_entry["presigned_url"] = chunk["presigned_url"]
        sources.append(source_entry)

        if freshness is not None:
            freshness_scores.append(float(freshness))

    # Step 5: Conflict detection
    conflicts: List[str] = []
    if detect_conflicts and len(selected) > 1:
        conflicts = _detect_conflicts(selected)

    # Step 6: Freshness summary
    freshness_summary: Dict[str, Any] = {}
    if freshness_scores:
        freshness_summary = {
            "min": round(min(freshness_scores), 2),
            "max": round(max(freshness_scores), 2),
            "avg": round(sum(freshness_scores) / len(freshness_scores), 2),
            "stale_chunks": sum(1 for f in freshness_scores if f < 40.0),
        }

    context_text = "\n".join(lines).strip()

    return {
        "context_text": context_text,
        "sources": sources,
        "token_estimate": len(context_text) // 4,
        "conflicts": conflicts,
        "freshness_summary": freshness_summary,
        "assembly_metadata": {
            "total_chunks": original_count,
            "deduplicated": dedup_count,
            "selected_chunks": len(selected),
            "truncated": truncated,
            "assembled_at": datetime.now(timezone.utc).isoformat(),
        },
    }
