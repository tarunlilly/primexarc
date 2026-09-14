"""
Playbook router for AIRD preprocessing.

Routes documents to appropriate playbooks based on content heuristics.
"""

import re
from pathlib import Path
from typing import Dict, Optional

import logging
logger = logging.getLogger(__name__)

from .loader import get_playbook_dir, load_playbook_yaml


def _index_playbooks() -> Dict[str, Path]:
    """
    Build an in-memory index of available playbooks.

    Returns:
        dict mapping canonical lower-case name -> Path to YAML
        e.g. {'tech': /.../TECH.yaml, 'scanned': /.../SCANNED.yaml}
    """
    logger.debug("📚 _index_playbooks() ENTRY")
    playbook_dir = get_playbook_dir()
    if not playbook_dir:
        logger.warning("⚠️ No playbook directory configured")
        return {}

    index: Dict[str, Path] = {}
    for p in playbook_dir.glob("*.yaml"):
        stem = p.stem  # e.g. "TECH"
        key = stem.strip().lower()
        index[key] = p
        logger.debug(f"✓ Indexed playbook: {key} -> {p.name}")

    logger.info(f"✅ Playbook index built: {len(index)} playbooks found")
    return index


_PLAYBOOK_INDEX: Dict[str, Path] = _index_playbooks()


def refresh_index() -> None:
    """Rebuild the playbook index (if you add files at runtime)."""
    logger.debug("📚 refresh_index() ENTRY")
    global _PLAYBOOK_INDEX
    _PLAYBOOK_INDEX = _index_playbooks()
    logger.debug(f"✓ Index refreshed with {len(_PLAYBOOK_INDEX)} playbooks")


def list_playbooks() -> Dict[str, Path]:
    """
    Return the current (lower-case) name -> Path mapping.
    """
    return dict(_PLAYBOOK_INDEX)


def resolve_playbook_file(playbook_id: Optional[str]) -> Optional[Path]:
    """
    Accepts 'tech', 'TECH', 'Tech', 'scanned', etc. Returns a Path to the YAML.
    Falls back to TECH.yaml (if present) or the first YAML in folder.

    Args:
        playbook_id: name/id string (case-insensitive); can be None

    Returns:
        Path to the resolved YAML file, or None if not found
    """
    if not _PLAYBOOK_INDEX:
        refresh_index()

    if not playbook_id:
        # default to TECH if available
        if "tech" in _PLAYBOOK_INDEX:
            return _PLAYBOOK_INDEX["tech"]
        # else first available yaml
        if _PLAYBOOK_INDEX:
            return next(iter(_PLAYBOOK_INDEX.values()))
        return None

    pid = str(playbook_id).strip().lower()
    if pid in _PLAYBOOK_INDEX:
        return _PLAYBOOK_INDEX[pid]

    # Try normalized matching (strip hyphens/underscores/spaces)
    pid_norm = re.sub(r"[-_ ]+", "", pid)
    for k, v in _PLAYBOOK_INDEX.items():
        if re.sub(r"[-_ ]+", "", k) == pid_norm:
            return v

    # Fallbacks
    if "tech" in _PLAYBOOK_INDEX:
        return _PLAYBOOK_INDEX["tech"]
    if _PLAYBOOK_INDEX:
        return next(iter(_PLAYBOOK_INDEX.values()))
    return None


def route_playbook(sample_text: Optional[str] = None, filename: Optional[str] = None) -> tuple[str, str]:
    """
    Very simple heuristic router that returns a *playbook ID string* and reason.
    Update heuristics as your classification needs grow.

    Args:
        sample_text: optional text to guide routing
        filename: optional filename to guide routing

    Returns:
        Tuple of (playbook_id, reason) e.g., ('TECH', 'default') or ('SCANNED', 'ocr_keywords')
    """
    logger.info(f"📚 route_playbook() ENTRY: filename={filename}, sample_len={len(sample_text) if sample_text else 0}")

    # Always operate on the current index
    if not _PLAYBOOK_INDEX:
        logger.debug("📋 Index empty, refreshing...")
        refresh_index()

    def has(pb_name: str) -> bool:
        return pb_name.lower() in _PLAYBOOK_INDEX

    if not sample_text and not filename:
        # prefer TECH
        default_id = "TECH" if has("TECH") else (next(iter(_PLAYBOOK_INDEX)).upper() if _PLAYBOOK_INDEX else "TECH")
        logger.info(f"✅ route_playbook() EXIT: no sample/filename, routing to default: {default_id}")
        return (default_id, "default")

    txt = (sample_text or "").lower()
    fn_lower = (filename or "").lower()

    # Check for scanned/OCR indicators
    if any(k in txt or k in fn_lower for k in ("scanned", "ocr", "image", "tesseract")) and has("SCANNED"):
        logger.info(f"✅ route_playbook() EXIT: ocr_keywords detected, routing to SCANNED")
        return ("SCANNED", "ocr_keywords")

    # Check for banking/finance indicators (before regulatory, as banking docs may have regulatory terms)
    banking_keywords = (
        "banking", "financial", "finance", "bank", "capital", "liquidity", "solvency",
        "credit risk", "market risk", "balance sheet", "income statement", "interest rate",
        "basel", "crd", "crr", "eba", "ecb", "ssm", "supervision", "auditor", "supervisor"
    )
    if any(k in txt or k in fn_lower for k in banking_keywords) and has("FINANCIAL"):
        logger.info(f"✅ route_playbook() EXIT: banking/finance keywords detected, routing to FINANCIAL")
        return ("FINANCIAL", "banking_finance_keywords")

    # Check for regulatory indicators
    regulatory_keywords = (
        "label", "regulatory", "prescribing information", "safety", "fda", "ema",
        "compliance", "regulation", "guidelines", "directive", "framework", "requirement"
    )
    if any(k in txt or k in fn_lower for k in regulatory_keywords) and has("REGULATORY"):
        logger.info(f"✅ route_playbook() EXIT: regulatory keywords detected, routing to REGULATORY")
        return ("REGULATORY", "regulatory_keywords")

    # Default to TECH
    default_id = "TECH" if has("TECH") else (next(iter(_PLAYBOOK_INDEX)).upper() if _PLAYBOOK_INDEX else "TECH")
    logger.info(f"✅ route_playbook() EXIT: no specific match, routing to default: {default_id}")
    return (default_id, "default")
