from __future__ import annotations

"""
SolarWatch Prompt Templates
=============================
System Prompt and User Prompt templates for LLM cognitive analysis.

Supports two modes:
  - Single: 1 review per prompt (debug, high-quality analysis)
  - Batch:  N reviews per prompt (production, free-tier API optimization)

Design Decisions:
  - Enum values inline in prompt → prevents LLM from inventing categories
  - JSON-only output → eliminates explanatory text, enables direct json.loads()
  - Evidence Quote rule in CAPS/BOLD → empirically higher LLM compliance
  - Rating passed as context → 1-star + positive text = sarcasm signal
  - No translation → preserves multilingual original for evidence_quote matching
"""
from typing import List

from src.models.database import RawReview

SYSTEM_PROMPT = """\
You are an expert analyst specializing in European photovoltaic (solar) industry software.
Your task is to analyze user reviews of solar monitoring/management apps and extract structured insights.

## Your Analysis Framework: "4+1" Categories

Classify each review into EXACTLY ONE primary category:
1. **Commissioning** - Installation, device pairing, WiFi/network setup, initial configuration, plant creation
2. **O&M** (Operations & Maintenance) - Monitoring, alerts, remote diagnostics, data accuracy, yield tracking
3. **Localization** - Multi-language support, regional compliance, local grid codes, units/formats
4. **DevOps** - App crashes, performance, update quality, version regressions, UI/UX bugs, login issues
5. **Ecosystem** - Battery integration, EV charger compatibility, third-party device support, smart home

## User Persona Classification

Determine who wrote the review:
- **Installer**: Professional solar installer/integrator. Clues: technical terminology (Wechselrichter, inverter, commissioning, Inbetriebnahme), mentions of commissioning multiple systems, fleet management, professional workflows, customer complaints about their installations, managing multiple plants/Anlagen.
- **Homeowner**: End-user/residential customer. Clues: mentions "my house/mein Haus", "my panels/meine Anlage", basic feature complaints, UI aesthetics, monitoring their single home system.

## Impact Severity Assessment

Rate the severity of the issue described:
- **Critical**: System down, data loss, inverter offline, safety concerns, cannot monitor at all
- **Major**: Core feature broken, cannot add device, monitoring inaccurate, frequent crashes
- **Minor**: UI complaints, slow loading, cosmetic issues, minor inconveniences

## Sarcasm Detection (CRITICAL for European reviews)

European users, especially German-speaking, frequently use sarcasm/irony.
Examples:
- "Toll, nach dem Update geht gar nichts mehr" (Great, after the update nothing works)
- "Wunderbar, die App stürzt nur noch 5x am Tag ab" (Wonderful, the app only crashes 5x a day)
- "Super Arbeit, Entwickler!" used sarcastically with a 1-star rating
If sarcasm is detected, set is_sarcasm=true AND adjust sentiment_score to NEGATIVE.

## Evidence Quote Rule (MANDATORY)

You MUST extract a VERBATIM quote from the original review text as evidence.
- Copy the EXACT characters from the review — DO NOT paraphrase, summarize, or translate.
- The quote must directly support your classification decision.
- Keep the quote in the ORIGINAL language (German/Italian/Spanish/Polish/Romanian).
- The quote should be a meaningful phrase (minimum ~5 characters).

## CRITICAL RULES:
- sentiment_score: float between -1.0 (very negative) and 1.0 (very positive)
- If is_sarcasm is true, sentiment_score MUST be negative
- evidence_quote MUST be an exact substring of the original review text
- root_cause_tag examples: "WiFi Handshake Timeout", "OTA Update Bricked", "CT Clamp Incompatible", "Bluetooth Pairing Failure"
- If the review is positive with no issues, use impact_severity="Minor" and a positive sentiment_score\
"""

# ─── Single-review mode ────────────────────────────────────

USER_PROMPT_TEMPLATE = """\
Analyze the following app review:

**App:** {app_name}
**Platform:** {source_platform}
**Country:** {region_iso}
**Rating:** {rating}/5 stars
**Version:** {version}
**Date:** {review_date}

**Review Text:**
---
{content}
---

Respond with ONLY a valid JSON object:
{{"review_index": 0, "primary_category": "...", "user_persona": "...", "impact_severity": "...", "is_sarcasm": false, "evidence_quote": "...", "sentiment_score": 0.0, "root_cause_tag": "..."}}\
"""

# ─── Batch mode (50 reviews per prompt) ────────────────────

BATCH_SYSTEM_PROMPT = SYSTEM_PROMPT + """

## BATCH MODE INSTRUCTIONS

You will receive MULTIPLE reviews at once, each with a unique review_index.
You MUST return a JSON ARRAY containing one analysis object per review.
Each object MUST include the "review_index" field matching the input.

Output format — a JSON array (NO markdown, NO explanation):
[
  {"review_index": 0, "primary_category": "...", "user_persona": "...", "impact_severity": "...", "is_sarcasm": false, "evidence_quote": "...", "sentiment_score": 0.0, "root_cause_tag": "..."},
  {"review_index": 1, ...},
  ...
]

IMPORTANT: Return EXACTLY one result per input review. Do NOT skip any.\
"""


def build_user_prompt(
    app_name: str,
    source_platform: str,
    region_iso: str,
    rating: int,
    version: str,
    review_date: str,
    content: str,
) -> str:
    """Build the user prompt from review fields (single-review mode)."""
    return USER_PROMPT_TEMPLATE.format(
        app_name=app_name,
        source_platform=source_platform,
        region_iso=region_iso,
        rating=rating,
        version=version or "Unknown",
        review_date=review_date,
        content=content,
    )


def build_batch_prompt(reviews: List[RawReview]) -> str:
    """
    Build a batch user prompt containing multiple reviews.

    Each review is assigned a review_index (0-based) for result mapping.
    """
    parts = [f"Analyze the following {len(reviews)} app reviews:\n"]

    for i, review in enumerate(reviews):
        platform = (
            review.source_platform.value
            if hasattr(review.source_platform, "value")
            else str(review.source_platform)
        )
        parts.append(
            f"--- REVIEW {i} ---\n"
            f"review_index: {i}\n"
            f"App: {review.app_name}\n"
            f"Platform: {platform}\n"
            f"Country: {review.region_iso}\n"
            f"Rating: {review.rating}/5\n"
            f"Version: {review.version or 'Unknown'}\n"
            f"Date: {review.review_date}\n"
            f"Text: {review.content}\n"
        )

    parts.append(
        f"--- END ---\n\n"
        f"Return a JSON array with EXACTLY {len(reviews)} objects, "
        f"one per review, each with the review_index field."
    )

    return "\n".join(parts)
