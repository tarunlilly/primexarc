"""
Text processing utilities for AIRD preprocessing.

Ports text normalization, PII redaction, and section detection from AIRD.
"""

from typing import Any, Dict, List, Optional, Tuple

import regex as re
import logging
logger = logging.getLogger(__name__)

# Regex patterns for PII detection
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}\b", re.I)
PHONE_RE = re.compile(r"(?:\+?\d[\s\-\.)/]*)?(?:\(?\d{3}\)?[\s\-\./]*)?\d{3}[\s\-\./]*\d{4}")
SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

# Header detection patterns
TITLECASE_RE = re.compile(r"^[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+$")
ALLCAPS_RE = re.compile(r"^[A-Z0-9][A-Z0-9 &'\-]{6,}$")
NUMBERED_RE = re.compile(r"^(\d+)[\.\)]\s+(.+)$")

# Sentence splitting regex
SENT_SPLIT_RE = re.compile(r"(?<!\b[A-Z])[.!?。۔؟]+(?=\s+[A-Z0-9\"'])")


def _compile_flags(flag_str: Optional[str]) -> int:
    """Compile regex flags from string (e.g., 'MULTILINE|IGNORECASE')."""
    if not flag_str:
        return 0
    flags = 0
    for f in flag_str.split("|"):
        f = f.strip().upper()
        if f == "MULTILINE":
            flags |= re.MULTILINE
        if f == "IGNORECASE":
            flags |= re.IGNORECASE
    return flags


def normalize_wrapped_lines(text: str) -> str:
    """
    Comprehensive PDF text normalization.

    Fixes common PDF line-wrap artifacts:
    - De-hyphenate: 'exam-\nple' -> 'example'
    - Join wrapped lines into sentences/paragraphs using heuristics
    - Remove excessive whitespace
    - Preserve paragraph boundaries (blank lines)

    This is critical for PDFs which often have hard line breaks that break
    paragraph detection and chunking.
    """
    logger.debug(f"🧩 normalize_wrapped_lines() ENTRY: text_len={len(text)}")
    if not text:
        return ""

    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # De-hyphenate: "exam-\nple" -> "example"
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    logger.debug(f"📋 De-hyphenation done")

    # Remove excessive whitespace (but preserve newlines for paragraph detection)
    text = re.sub(r"[ \t]+", " ", text)

    # Join lines that look like hard-wrapped sentences:
    # If a line doesn't end with sentence punctuation and next line starts lowercase -> join.
    lines = [ln.strip() for ln in text.split("\n")]
    out = []
    for ln in lines:
        if not ln:
            out.append("")  # keep blank lines (para breaks)
            continue

        if not out:
            out.append(ln)
            continue

        prev = out[-1]
        if prev == "":
            out.append(ln)
            continue

        # Check if previous line ends with sentence punctuation
        prev_ends_sentence = bool(re.search(r'[.!?]["\')\]]*\s*$', prev))
        # Check if current line starts with lowercase (likely continuation)
        next_starts_lower = bool(re.match(r"^[a-z]", ln))

        # Join typical wrap: previous doesn't end sentence AND next starts lowercase
        if (not prev_ends_sentence) and next_starts_lower:
            out[-1] = prev + " " + ln
        else:
            out.append(ln)

    # Re-collapse multiple blank lines to max 2 (paragraph boundaries)
    normalized = "\n".join(out)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)

    result = normalized.strip()
    logger.debug(f"✓ normalize_wrapped_lines() EXIT: input={len(text)}, output={len(result)}")
    return result


def redact_pii(text: str) -> str:
    """Redact PII (emails, phones, SSNs) from text."""
    t = EMAIL_RE.sub("[redacted_email]", text)
    t = PHONE_RE.sub("[redacted_phone]", t)
    t = SSN_RE.sub("[SSN]", t)
    return t


def apply_normalizers(text: str, steps: Optional[List[Dict[str, Any]]]) -> str:
    """Apply regex-based normalization steps from playbook."""
    out = text
    for step in steps or []:
        pat = step.get("pattern")
        if not pat:
            logger.warning(f"Normalizer step missing 'pattern' field, skipping: {step}")
            continue

        # Handle YAML parsing issue: sometimes patterns are parsed as lists (e.g., [\u2018\u2019])
        # Convert list to string character class pattern
        if isinstance(pat, list):
            # Convert list of characters to regex character class string
            pat = "[" + "".join(str(c) for c in pat) + "]"
            logger.debug(f"Converted list pattern to string: {pat}")

        if not isinstance(pat, str):
            logger.warning(f"Normalizer pattern must be string or list, got {type(pat)}: {pat}, skipping")
            continue

        repl = step.get("replace", "")
        flag_val = step.get("flags")
        # Handle flags: can be string, None, or other types
        if isinstance(flag_val, str):
            flags = _compile_flags(flag_val)
        elif flag_val is None:
            flags = 0
        else:
            # If flags is not a string or None, log and use 0
            logger.warning(
                f"Unexpected flags type in normalizer (expected str or None, got {type(flag_val)}): {flag_val}, using 0"
            )
            flags = 0
        try:
            out = re.sub(pat, repl, out, flags=flags)
        except (re.error, TypeError) as e:
            logger.warning(
                f"Bad regex pattern in normalizer: {pat}, error: {e}, flags type: {type(flags)}, flags value: {flags}"
            )
            # ignore bad regex in config; continue
            pass
    return out


def split_pages_by_config(text: str, page_fences: Optional[List[Dict[str, Any]]]) -> List[Dict[str, int]]:
    """
    If a page fence pattern is defined, split text into {page, text} blocks.
    Otherwise produce a single page.
    """
    if not page_fences:
        return [{"page": 1, "text": text.strip()}]

    for fence in page_fences:
        flags = _compile_flags(fence.get("flags"))
        pattern = fence.get("pattern", r"^$")
        lines = text.splitlines()
        pages, curr, page = [], [], 1
        found_any_marker = False

        for line in lines:
            if re.match(pattern, line, flags=flags):
                found_any_marker = True
                if curr:
                    pages.append({"page": page, "text": "\n".join(curr).strip()})
                    curr = []
                # Try to extract page number from the marker line
                m = re.search(r"PAGE\s+(\d+)", line, flags=re.IGNORECASE)
                if m:
                    page = int(m.group(1))
                else:
                    # If no page number found, increment from last page
                    page = pages[-1]["page"] + 1 if pages else 1
                continue
            curr.append(line)

        # Add the last page if there's remaining content
        if curr:
            pages.append({"page": page, "text": "\n".join(curr).strip()})

        # If we found any markers and have multiple pages, return them
        # Also return if we have at least one page (even if only one marker was found)
        if found_any_marker and len(pages) > 0:
            return pages
        # If we found markers but only got one page, that's still valid (single-page document)
        if found_any_marker:
            return pages

    # No patterns matched, return single page
    return [{"page": 1, "text": text.strip()}]


def detect_sections_configured(
    text: str,
    header_specs: Optional[List[Dict[str, Any]]],
    aliases: Optional[Dict[str, str]],
) -> List[Tuple[str, str, str]]:
    """
    Use header rules from playbook to split into sections.
    Returns tuples: (title_raw, canonical_section, body_text)
    """
    lines = text.splitlines()
    sections, buf, title_raw = [], [], "Introduction"
    aliases = aliases or {}

    def flush():
        nonlocal buf
        if buf:
            canon = aliases.get(title_raw, _canon_from_title(title_raw))
            sections.append((title_raw, canon, "\n".join(buf).strip()))
            buf = []

    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        is_header = False
        # explicit header rules first
        for spec in header_specs or []:
            pat = spec.get("pattern")
            flags = _compile_flags(spec.get("flags"))
            if pat and re.match(pat, line, flags=flags):
                flush()
                title_raw = line
                is_header = True
                break
        if is_header:
            continue
        # fallback heuristics: numbered, TitleCase (>=2 words), ALLCAPS long
        if NUMBERED_RE.match(line) or TITLECASE_RE.match(line) or (ALLCAPS_RE.match(line) and len(line.split()) >= 2):
            flush()
            title_raw = line
            continue
        buf.append(line)

    flush()
    if not sections:
        return [("Introduction", "introduction", text.strip())]
    return sections


def _canon_from_title(title: str) -> str:
    """Convert title to canonical section name."""
    t = re.sub(r"\s+", " ", (title or "").strip().lower())
    # a small alias map inline; playbook aliases still take precedence
    ALIASES = {
        "executive summary": "executive_summary",
        "table of contents": "table_of_contents",
        "conclusions": "conclusions",
        "conclusion": "conclusions",
        "abstract": "abstract",
        "introduction": "introduction",
        "background": "background",
    }
    if t in ALIASES:
        return ALIASES[t]
    return re.sub(r"[^a-z0-9]+", "_", t)[:40] or "section"


def apply_enhanced_normalization(text: str) -> str:
    """
    Apply enhanced normalization patterns to improve text quality.
    More aggressive than standard normalization.
    """
    logger.debug(f"🧩 apply_enhanced_normalization() ENTRY: text_len={len(text)}")
    # Check if text is already corrupted (spaces between characters) - if so, skip normalization
    # This can happen with bad PDF extraction
    if len(text) > 100:
        sample = text[:500]
        # Check if more than 30% of characters are spaces (indicating corruption)
        space_ratio = sample.count(" ") / len(sample) if len(sample) > 0 else 0
        if space_ratio > 0.3:
            logger.warning(
                "⚠️ Text appears to be corrupted (excessive spaces), skipping enhanced normalization to avoid further corruption"
            )
            return text

    out = text

    # Enhanced character normalization
    # Fix common OCR errors and encoding issues
    replacements = [
        # Remove control characters except \n, \t, \r
        (r"[\x00-\x08\x0B-\x0C\x0E-\x1F]", ""),
        # Normalize whitespace more aggressively
        (r"[ \t]+", " "),  # Multiple spaces/tabs to single space
        (r"\n[ \t]+", "\n"),  # Remove leading spaces on new lines
        (r"[ \t]+\n", "\n"),  # Remove trailing spaces before newlines
        # Fix punctuation spacing (but be careful not to break words)
        (r" +([,.!?;:])", r"\1"),  # Remove space before punctuation
        (r"([,.!?;:])([^\s])", r"\1 \2"),  # Ensure space after punctuation (if missing)
        # Fix quote normalization (more comprehensive)
        (r"[\u2018\u2019\u2032]", "'"),  # Various single quotes to standard
        (r"[\u201C\u201D\u2033]", '"'),  # Various double quotes to standard
        (r"[\u2013\u2014\u2015]", "-"),  # Various dashes to hyphen
        # Fix ellipsis
        (r"\.{4,}", "..."),  # More than 3 dots -> ellipsis
        # Remove excessive line breaks but preserve paragraphs
        (r"\n{4,}", "\n\n\n"),  # More than 3 newlines -> 3
    ]

    applied_count = 0
    for pattern, replacement in replacements:
        try:
            new_out = re.sub(pattern, replacement, out)
            if new_out != out:
                applied_count += 1
            out = new_out
        except (re.error, TypeError) as e:
            logger.warning(f"❌ Enhanced normalization pattern failed: {pattern}, error: {e}")
            continue

    logger.debug(f"📋 Applied {applied_count} normalization patterns")

    # Final cleanup
    out = out.strip()
    logger.debug(f"✓ apply_enhanced_normalization() EXIT: input={len(text)}, output={len(out)}, patterns_applied={applied_count}")

    return out


def apply_error_correction(text: str) -> str:
    """
    Apply basic error correction to fix common typos and OCR errors.
    Uses pattern-based fixes and optionally spellchecker if available.
    """
    logger.debug(f"🧩 apply_error_correction() ENTRY: text_len={len(text)}")
    # Check if text is already corrupted (spaces between characters) - if so, skip error correction
    # This can happen with bad PDF extraction
    if len(text) > 100:
        sample = text[:500]
        # Check if more than 30% of characters are spaces (indicating corruption)
        space_ratio = sample.count(" ") / len(sample) if len(sample) > 0 else 0
        if space_ratio > 0.3:
            logger.warning(
                "⚠️ Text appears to be corrupted (excessive spaces), skipping error correction to avoid further corruption"
            )
            return text

    try:
        from spellchecker import SpellChecker

        spell = SpellChecker()
        HAS_SPELLCHECKER = True
        logger.debug("📋 Spellchecker available")
    except ImportError:
        HAS_SPELLCHECKER = False
        logger.debug("⚠️ Spellchecker library not available, using pattern-based correction only")

    out = text

    # Pattern-based fixes (don't require external libraries)
    # Only fix clear OCR errors, avoid patterns that could corrupt valid text
    pattern_fixes = [
        # Common OCR word errors (using word boundaries to avoid false positives)
        (r"\bteh\b", "the"),
        (r"\badn\b", "and"),
        (r"\btha\b", "that"),
        (r"\btaht\b", "that"),
        (r"\bhte\b", "the"),
        # Fix excessive repeated letters (4+ repeats -> 2)
        (r"([a-z])\1{3,}", r"\1\1"),
        # Fix missing space after sentence-ending punctuation (but only if next char is uppercase letter)
        (r"([.!?])([A-Z][a-z])", r"\1 \2"),
    ]

    applied_count = 0
    for pattern, replacement in pattern_fixes:
        try:
            new_out = re.sub(pattern, replacement, out, flags=re.IGNORECASE)
            if new_out != out:
                applied_count += 1
            out = new_out
        except (re.error, TypeError) as e:
            logger.warning(f"❌ Error correction pattern failed: {pattern}, error: {e}")
            continue

    logger.debug(f"📋 Applied {applied_count} error correction patterns")
    logger.debug(f"✓ apply_error_correction() EXIT: input={len(text)}, output={len(out)}")

    # Disable spellchecker-based correction for now - it's too risky and can corrupt valid text
    # The pattern-based fixes above are safer and sufficient for common OCR errors

    return out
