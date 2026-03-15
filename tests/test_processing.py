from __future__ import annotations

"""
SolarWatch Response Parser Tests
===================================
Tests for LLM response parsing and Pydantic validation.

Coverage:
  - Valid JSON parsing
  - Enum validation (PrimaryCategory, UserPersona, ImpactSeverity)
  - Range validation (sentiment_score)
  - Malformed JSON handling
  - Markdown fence stripping
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.processing.response_parser import LLMResponseSchema, parse_llm_response, _strip_markdown_fences
from src.config.constants import PrimaryCategory, UserPersona, ImpactSeverity


# ─── Valid Parsing ────────────────────────────────────────


class TestValidParsing:
    """Tests for successful parsing of valid LLM responses."""

    def test_valid_complete_response(self):
        """Should parse a complete, valid JSON response."""
        response = '''{
            "primary_category": "Commissioning",
            "user_persona": "Installer",
            "impact_severity": "Critical",
            "is_sarcasm": false,
            "evidence_quote": "Die App stürzt beim Konfigurieren ab",
            "sentiment_score": -0.8,
            "root_cause_tag": "WiFi Handshake Timeout"
        }'''
        result = parse_llm_response(response)
        assert result is not None
        assert result.primary_category == PrimaryCategory.COMMISSIONING
        assert result.user_persona == UserPersona.INSTALLER
        assert result.impact_severity == ImpactSeverity.CRITICAL
        assert result.is_sarcasm is False
        assert result.sentiment_score == -0.8
        assert result.root_cause_tag == "WiFi Handshake Timeout"

    def test_valid_with_null_root_cause(self):
        """root_cause_tag can be null."""
        response = '''{
            "primary_category": "DevOps",
            "user_persona": "Homeowner",
            "impact_severity": "Minor",
            "is_sarcasm": false,
            "evidence_quote": "Die App ist etwas langsam",
            "sentiment_score": -0.2,
            "root_cause_tag": null
        }'''
        result = parse_llm_response(response)
        assert result is not None
        assert result.root_cause_tag is None

    def test_oandm_category(self):
        """Should correctly parse O&M category."""
        response = '''{
            "primary_category": "O&M",
            "user_persona": "Installer",
            "impact_severity": "Major",
            "is_sarcasm": false,
            "evidence_quote": "Monitoring zeigt falsche Werte",
            "sentiment_score": -0.6,
            "root_cause_tag": "Data Sync Error"
        }'''
        result = parse_llm_response(response)
        assert result is not None
        assert result.primary_category == PrimaryCategory.O_AND_M


# ─── Markdown Fence Stripping ─────────────────────────────


class TestMarkdownStripping:
    """Tests for removing markdown code fences."""

    def test_strips_json_fences(self):
        """Should strip ```json ... ``` wrapping."""
        text = '```json\n{"key": "value"}\n```'
        assert _strip_markdown_fences(text) == '{"key": "value"}'

    def test_strips_plain_fences(self):
        """Should strip plain ``` ... ``` wrapping."""
        text = '```\n{"key": "value"}\n```'
        assert _strip_markdown_fences(text) == '{"key": "value"}'

    def test_no_fences_unchanged(self):
        """Text without fences should be unchanged."""
        text = '{"key": "value"}'
        assert _strip_markdown_fences(text) == '{"key": "value"}'

    def test_parse_with_fences(self):
        """Full parse should work even with markdown fences."""
        response = '```json\n{"primary_category":"DevOps","user_persona":"Homeowner","impact_severity":"Minor","is_sarcasm":false,"evidence_quote":"App is slow","sentiment_score":-0.1,"root_cause_tag":null}\n```'
        result = parse_llm_response(response)
        assert result is not None
        assert result.primary_category == PrimaryCategory.DEVOPS


# ─── Validation Failures ──────────────────────────────────


class TestValidationFailures:
    """Tests for cases that should fail Pydantic validation."""

    def test_invalid_category(self):
        """Unknown category should fail."""
        response = '''{
            "primary_category": "InvalidCategory",
            "user_persona": "Installer",
            "impact_severity": "Critical",
            "is_sarcasm": false,
            "evidence_quote": "some quote here",
            "sentiment_score": -0.5,
            "root_cause_tag": null
        }'''
        result = parse_llm_response(response)
        assert result is None

    def test_sentiment_out_of_range(self):
        """sentiment_score > 1.0 should fail."""
        response = '''{
            "primary_category": "DevOps",
            "user_persona": "Homeowner",
            "impact_severity": "Minor",
            "is_sarcasm": false,
            "evidence_quote": "some quote here",
            "sentiment_score": 1.5,
            "root_cause_tag": null
        }'''
        result = parse_llm_response(response)
        assert result is None

    def test_short_evidence_quote(self):
        """evidence_quote < 5 chars should fail."""
        response = '''{
            "primary_category": "DevOps",
            "user_persona": "Homeowner",
            "impact_severity": "Minor",
            "is_sarcasm": false,
            "evidence_quote": "ab",
            "sentiment_score": -0.1,
            "root_cause_tag": null
        }'''
        result = parse_llm_response(response)
        assert result is None

    def test_malformed_json(self):
        """Completely broken JSON should return None."""
        result = parse_llm_response("This is not JSON at all")
        assert result is None

    def test_empty_response(self):
        """Empty string should return None."""
        result = parse_llm_response("")
        assert result is None
