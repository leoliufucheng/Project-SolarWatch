from __future__ import annotations

"""
SolarWatch Text Utilities
===========================
Text cleaning and normalization functions.
Critical for the anti-hallucination validation pipeline —
both raw_content and evidence_quote must be normalized before comparison.
"""
import re
import unicodedata


def normalize_text(text: str) -> str:
    """
    Normalize text for comparison.

    Steps:
        1. Unicode NFKC normalization (compatibility decomposition + compose)
        2. Lowercase
        3. Collapse whitespace (tabs, newlines, multiple spaces → single space)
        4. Strip leading/trailing whitespace

    Why NFKC over NFC:
        European languages (German ä/ö/ü, French é/à) have multiple encoding
        representations. NFKC handles compatibility decomposition (ligatures,
        fullwidth chars, etc.) which is critical for the anti-hallucination
        evidence_quote substring matching in Sprint 3. NFC alone would cause
        false-negative matches on certain character compositions.

    Args:
        text: Raw text to normalize.

    Returns:
        Normalized text string.
    """
    # Unicode NFKC normalization (compatibility decomposition + canonical composition)
    text = unicodedata.normalize("NFKC", text)
    # Lowercase
    text = text.lower()
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text)
    # Strip
    text = text.strip()
    return text


def truncate_text(text: str, max_length: int = 200, suffix: str = "...") -> str:
    """Truncate text to max_length, appending suffix if truncated."""
    if len(text) <= max_length:
        return text
    return text[: max_length - len(suffix)] + suffix


def clean_review_text(text: str) -> str:
    """
    Clean review text for storage.

    Steps:
        1. Strip HTML tags (some scrapers return HTML)
        2. Normalize unicode
        3. Remove control characters (except newlines)
        4. Strip excessive whitespace

    Args:
        text: Raw scraped review text.

    Returns:
        Cleaned text suitable for storage and LLM analysis.
    """
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Unicode NFKC (same as normalize_text for consistency)
    text = unicodedata.normalize("NFKC", text)
    # Remove control chars (keep \n)
    text = re.sub(r"[\x00-\x09\x0b\x0c\x0e-\x1f\x7f]", "", text)
    # Collapse whitespace (keep single newlines)
    text = re.sub(r"[^\S\n]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Strip
    text = text.strip()
    return text
