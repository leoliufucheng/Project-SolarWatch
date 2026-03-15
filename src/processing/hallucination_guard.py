from __future__ import annotations

"""
SolarWatch Hallucination Guard
================================
Anti-hallucination validation module.

Core responsibility: Verify that the LLM-generated evidence_quote actually
exists within the original review content.

Design principle: "Rather miss a valid match than accept a fabrication."
  - High recall tolerance, zero tolerance for false passes.

Three-level validation strategy:
  Level 1 — Exact substring match (after NFKC normalization)
  Level 2 — Fuzzy sliding window match (SequenceMatcher, threshold ≥ 0.85)
  Level 3 — Token set overlap (bag-of-words, threshold ≥ 0.85)

Default: strict_mode=True → only Level 1 passes.
"""
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Optional

from src.utils.text_utils import normalize_text


@dataclass
class ValidationResult:
    """Result of evidence quote validation."""
    is_valid: bool
    raw_content: str
    evidence_quote: str
    similarity_score: float  # 0.0 - 1.0
    failure_reason: Optional[str] = field(default=None)


def validate_evidence_quote(
    raw_content: str,
    evidence_quote: str,
    strict_mode: bool = True,
    similarity_threshold: float = 0.85,
) -> ValidationResult:
    """
    Validate that evidence_quote is a genuine excerpt from raw_content.

    Three-level strategy:
      Level 1 — Exact substring: normalize(quote) in normalize(content)
      Level 2 — Fuzzy match: sliding window with SequenceMatcher ≥ threshold
      Level 3 — Token overlap: |quote_tokens ∩ content_tokens| / |quote_tokens| ≥ threshold

    Args:
        raw_content:         Original review text from database.
        evidence_quote:      LLM-generated evidence quote to verify.
        strict_mode:         If True, only Level 1 passes (production default).
        similarity_threshold: Threshold for Level 2 and Level 3.

    Returns:
        ValidationResult with is_valid, similarity_score, and failure_reason.
    """
    # Edge case: empty quote
    if not evidence_quote or not evidence_quote.strip():
        return ValidationResult(
            is_valid=False,
            raw_content=raw_content,
            evidence_quote=evidence_quote,
            similarity_score=0.0,
            failure_reason="Empty evidence quote",
        )

    # --- Preprocessing ---
    norm_content = normalize_text(raw_content)
    norm_quote = normalize_text(evidence_quote)

    # --- Level 1: Exact substring match (after normalization) ---
    if norm_quote in norm_content:
        return ValidationResult(
            is_valid=True,
            raw_content=raw_content,
            evidence_quote=evidence_quote,
            similarity_score=1.0,
        )

    if strict_mode:
        return ValidationResult(
            is_valid=False,
            raw_content=raw_content,
            evidence_quote=evidence_quote,
            similarity_score=0.0,
            failure_reason="STRICT: Exact substring match failed",
        )

    # --- Level 2: Fuzzy sliding window match ---
    quote_len = len(norm_quote)
    best_ratio = 0.0

    if quote_len > 0 and len(norm_content) >= quote_len:
        for i in range(len(norm_content) - quote_len + 1):
            window = norm_content[i : i + quote_len]
            ratio = SequenceMatcher(None, norm_quote, window).ratio()
            best_ratio = max(best_ratio, ratio)
            if best_ratio >= similarity_threshold:
                return ValidationResult(
                    is_valid=True,
                    raw_content=raw_content,
                    evidence_quote=evidence_quote,
                    similarity_score=best_ratio,
                )

    # --- Level 3: Token set overlap ---
    quote_tokens = set(norm_quote.split())
    content_tokens = set(norm_content.split())

    if quote_tokens:
        overlap = len(quote_tokens & content_tokens) / len(quote_tokens)
        if overlap >= similarity_threshold:
            return ValidationResult(
                is_valid=True,
                raw_content=raw_content,
                evidence_quote=evidence_quote,
                similarity_score=overlap,
            )

    return ValidationResult(
        is_valid=False,
        raw_content=raw_content,
        evidence_quote=evidence_quote,
        similarity_score=best_ratio,
        failure_reason=f"All levels failed. Best similarity: {best_ratio:.2f}",
    )
