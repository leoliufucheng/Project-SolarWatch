"""SolarWatch Processing Package — Cognitive Analysis Pipeline."""
from src.processing.hallucination_guard import ValidationResult, validate_evidence_quote
from src.processing.processor import CognitiveProcessor, ProcessingStats
from src.processing.prompt_templates import SYSTEM_PROMPT, build_user_prompt
from src.processing.response_parser import LLMResponseSchema, parse_llm_response

__all__ = [
    "CognitiveProcessor",
    "ProcessingStats",
    "SYSTEM_PROMPT",
    "build_user_prompt",
    "LLMResponseSchema",
    "parse_llm_response",
    "ValidationResult",
    "validate_evidence_quote",
]
