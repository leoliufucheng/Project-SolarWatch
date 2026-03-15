from __future__ import annotations

"""
SolarWatch Response Parser
============================
Parses LLM JSON responses and validates against Pydantic schema.

Supports:
  - Single-review mode: parse one JSON object
  - Batch mode: parse a JSON array of objects, one per review
"""
import json
import re
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.config.constants import ImpactSeverity, PrimaryCategory, UserPersona
from src.utils.logger import get_logger

logger = get_logger(__name__)


class LLMResponseSchema(BaseModel):
    """
    Pydantic model for validating LLM analysis output.

    Each field maps directly to a ProcessedReview column.
    Enum fields use the constants.py enums — Pydantic matches on .value.
    """
    review_index: int = Field(default=0, description="Index mapping back to input review")
    primary_category: PrimaryCategory
    user_persona: UserPersona
    impact_severity: ImpactSeverity
    is_sarcasm: bool = Field(..., description="True if irony/sarcasm detected")
    evidence_quote: str = Field(
        ..., min_length=5,
        description="VERBATIM substring from original review text"
    )
    sentiment_score: float = Field(
        ..., ge=-1.0, le=1.0,
        description="Sentiment score [-1.0, 1.0]"
    )
    root_cause_tag: Optional[str] = None

    model_config = ConfigDict(use_enum_values=False)


def _strip_markdown_fences(text: str) -> str:
    """
    Remove markdown code fences that LLMs sometimes add despite instructions.

    Handles patterns like:
      ```json\n{...}\n```
      ```\n{...}\n```
    """
    text = text.strip()
    pattern = r"^```(?:json)?\s*\n?(.*?)\n?```$"
    match = re.match(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text


def parse_llm_response(raw_response: str) -> Optional[LLMResponseSchema]:
    """
    Parse and validate a single-review LLM response.

    Returns:
      LLMResponseSchema if valid, None if parsing/validation fails.
    """
    try:
        cleaned = _strip_markdown_fences(raw_response)
        data = json.loads(cleaned)
        # Handle array response with single element
        if isinstance(data, list):
            data = data[0] if data else {}
        schema = LLMResponseSchema(**data)
        return schema

    except (json.JSONDecodeError, ValidationError, Exception) as e:
        logger.error(
            f"Parse error: {type(e).__name__}: {e}\n"
            f"Raw response (first 500 chars): {raw_response[:500]}"
        )
        return None


def parse_batch_response(
    raw_response: str,
    expected_count: int,
) -> Dict[int, Optional[LLMResponseSchema]]:
    """
    Parse a batch LLM response (JSON array) into indexed results.

    Returns:
        Dict mapping review_index → LLMResponseSchema (or None for failures).
        Missing indices are mapped to None.
    """
    results: Dict[int, Optional[LLMResponseSchema]] = {}

    try:
        cleaned = _strip_markdown_fences(raw_response)
        data = json.loads(cleaned)

        # Handle case where LLM returns a single object instead of array
        if isinstance(data, dict):
            data = [data]

        if not isinstance(data, list):
            logger.error(f"Batch response is not a list: {type(data)}")
            return {i: None for i in range(expected_count)}

        for item in data:
            try:
                schema = LLMResponseSchema(**item)
                results[schema.review_index] = schema
            except (ValidationError, Exception) as e:
                idx = item.get("review_index", -1) if isinstance(item, dict) else -1
                logger.warning(
                    f"Batch item {idx} validation failed: {e}"
                )
                if idx >= 0:
                    results[idx] = None

    except json.JSONDecodeError as e:
        logger.error(
            f"Batch JSON parse error: {e}\n"
            f"Raw response (first 500 chars): {raw_response[:500]}"
        )
        return {i: None for i in range(expected_count)}

    # Fill in missing indices
    for i in range(expected_count):
        if i not in results:
            results[i] = None

    return results
