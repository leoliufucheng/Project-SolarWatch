from __future__ import annotations

"""
SolarWatch Hallucination Guard Tests
=======================================
Tests for the three-level anti-hallucination validation pipeline.

Coverage:
  - Level 1: Exact substring match (German, Italian, Spanish, English)
  - Level 2: Fuzzy match (minor LLM edits)
  - Level 3: Token overlap (word reordering)
  - Edge cases: empty quotes, very short quotes, unicode
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.processing.hallucination_guard import validate_evidence_quote


# ─── Level 1: Exact Substring Match (strict_mode=True) ────


class TestLevel1ExactMatch:
    """Tests for Level 1 — normalized exact substring matching."""

    def test_exact_match_german(self):
        """German text should match exactly after normalization."""
        content = "Die App stürzt nach dem Update ständig ab. Sehr ärgerlich!"
        quote = "App stürzt nach dem Update ständig ab"
        result = validate_evidence_quote(content, quote)
        assert result.is_valid is True
        assert result.similarity_score == 1.0

    def test_exact_match_italian(self):
        """Italian text with accents should match."""
        content = "L'app è lentissima, non si riesce a configurare l'inverter"
        quote = "non si riesce a configurare l'inverter"
        result = validate_evidence_quote(content, quote)
        assert result.is_valid is True

    def test_exact_match_spanish(self):
        """Spanish text should match."""
        content = "La aplicación no conecta con el inversor después de la actualización"
        quote = "no conecta con el inversor"
        result = validate_evidence_quote(content, quote)
        assert result.is_valid is True

    def test_case_insensitive(self):
        """Match should be case-insensitive after normalization."""
        content = "Die APP funktioniert nicht mehr"
        quote = "die app funktioniert nicht mehr"
        result = validate_evidence_quote(content, quote)
        assert result.is_valid is True

    def test_whitespace_normalization(self):
        """Multiple spaces/tabs should be normalized to single space."""
        content = "Die  App   stürzt\tab"
        quote = "Die App stürzt ab"
        result = validate_evidence_quote(content, quote)
        assert result.is_valid is True

    def test_fabricated_quote_strict(self):
        """A fabricated quote should FAIL in strict mode."""
        content = "Die App ist gut und funktioniert einwandfrei"
        quote = "The app crashes every time I open it"  # fabricated
        result = validate_evidence_quote(content, quote, strict_mode=True)
        assert result.is_valid is False
        assert "STRICT" in result.failure_reason

    def test_empty_quote(self):
        """Empty quote should always fail."""
        content = "Some review content"
        result = validate_evidence_quote(content, "")
        assert result.is_valid is False
        assert "Empty" in result.failure_reason

    def test_whitespace_only_quote(self):
        """Whitespace-only quote should fail."""
        content = "Some review content"
        result = validate_evidence_quote(content, "   \n\t  ")
        assert result.is_valid is False


# ─── Level 2: Fuzzy Match (strict_mode=False) ─────────────


class TestLevel2FuzzyMatch:
    """Tests for Level 2 — SequenceMatcher sliding window."""

    def test_minor_punctuation_change(self):
        """Quote with slight punctuation change should pass fuzzy match."""
        content = "Die App stürzt nach dem Update ab, sehr ärgerlich"
        # LLM dropped comma
        quote = "Die App stürzt nach dem Update ab sehr ärgerlich"
        result = validate_evidence_quote(
            content, quote, strict_mode=False, similarity_threshold=0.85
        )
        assert result.is_valid is True
        assert result.similarity_score >= 0.85

    def test_completely_fabricated_fails_fuzzy(self):
        """Completely fabricated quote should fail even in fuzzy mode."""
        content = "Gute App, funktioniert super mit meiner PV Anlage"
        quote = "Application crashes on startup every single time"
        result = validate_evidence_quote(
            content, quote, strict_mode=False, similarity_threshold=0.85
        )
        assert result.is_valid is False


# ─── Level 3: Token Overlap (strict_mode=False) ───────────


class TestLevel3TokenOverlap:
    """Tests for Level 3 — bag-of-words token overlap."""

    def test_word_reorder_passes(self):
        """Reordered words should pass at token overlap level."""
        content = "Update nach der App stürzt ab ständig"
        # Same words, different order
        quote = "App stürzt ständig ab nach Update"
        result = validate_evidence_quote(
            content, quote, strict_mode=False, similarity_threshold=0.85
        )
        assert result.is_valid is True

    def test_insufficient_overlap_fails(self):
        """Low token overlap should fail."""
        content = "Die App funktioniert einwandfrei"
        quote = "Das Programm hat Probleme beim Start"  # barely overlaps
        result = validate_evidence_quote(
            content, quote, strict_mode=False, similarity_threshold=0.85
        )
        assert result.is_valid is False


# ─── Unicode Edge Cases ────────────────────────────────────


class TestUnicodeEdgeCases:
    """Tests for Unicode normalization edge cases."""

    def test_german_umlauts(self):
        """German umlauts (ä, ö, ü) should normalize correctly."""
        content = "Ärgerlich, die Übersicht zeigt falsche Werte für den Wechselrichter"
        quote = "Übersicht zeigt falsche Werte"
        result = validate_evidence_quote(content, quote)
        assert result.is_valid is True

    def test_polish_characters(self):
        """Polish special characters should be handled."""
        content = "Aplikacja się zawiesza po każdej aktualizacji"
        quote = "zawiesza po każdej aktualizacji"
        result = validate_evidence_quote(content, quote)
        assert result.is_valid is True

    def test_romanian_characters(self):
        """Romanian diacritics should be handled."""
        content = "Aplicația nu funcționează corect după actualizare"
        quote = "nu funcționează corect"
        result = validate_evidence_quote(content, quote)
        assert result.is_valid is True
