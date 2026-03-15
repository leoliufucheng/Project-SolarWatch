from __future__ import annotations

"""
SolarWatch LLM Client
========================
Unified LLM API client supporting Gemini and OpenAI providers.

Features:
  - Dual provider support (google-genai / openai SDK)
  - Structured JSON output via API-level response format
  - Synchronous API calls (for free-tier rate-limit-friendly batch mode)
  - Model version tracking for reproducibility
"""
import os
import time
from pathlib import Path
from typing import Optional

# Auto-load .env file from project root (if python-dotenv is available)
# NOTE: override=False ensures system env vars take precedence over .env
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    if _env_path.exists():
        load_dotenv(_env_path, override=False)
except ImportError:
    pass  # dotenv not installed; fall back to manual env vars

from src.config.settings import load_settings
from src.utils.logger import get_logger

logger = get_logger(__name__)


class LLMClientError(Exception):
    """Base exception for LLM client errors."""
    pass


class RateLimitError(LLMClientError):
    """Raised on 429 / rate limit responses (transient, worth retrying)."""
    pass


class QuotaExhaustedError(LLMClientError):
    """Raised when daily quota is exhausted (limit: 0). No point retrying."""
    pass


class LLMClient:
    """
    Unified LLM API client.

    Reads provider/model/temperature from settings.yaml.
    Exposes a synchronous method: analyze(system_prompt, user_prompt) → str.
    """

    def __init__(self):
        self._settings = load_settings()
        self._llm_config = self._settings.llm
        self._provider = self._llm_config.provider
        self._model = self._llm_config.model
        self._temperature = self._llm_config.temperature
        self._max_retries = self._llm_config.max_retries
        self._client = None

        logger.info(
            f"LLM Client initialized: provider={self._provider}, "
            f"model={self._model}, temp={self._temperature}"
        )

    @property
    def model_version(self) -> str:
        """Return the model identifier for reproducibility tracking."""
        return f"{self._provider}/{self._model}"

    def _get_client(self):
        """Lazy-initialize the provider SDK client."""
        if self._client is not None:
            return self._client

        if self._provider == "gemini":
            from google import genai
            api_key = os.environ.get("GEMINI_API_KEY")
            if not api_key:
                raise LLMClientError(
                    "GEMINI_API_KEY environment variable not set. "
                    "Set it with: export GEMINI_API_KEY='your-key'"
                )
            self._client = genai.Client(api_key=api_key)

        elif self._provider == "openai":
            from openai import OpenAI
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                raise LLMClientError(
                    "OPENAI_API_KEY environment variable not set. "
                    "Set it with: export OPENAI_API_KEY='your-key'"
                )
            self._client = OpenAI(api_key=api_key)

        else:
            raise LLMClientError(f"Unknown LLM provider: {self._provider}")

        return self._client

    def analyze(self, system_prompt: str, user_prompt: str) -> str:
        """
        Send prompts to the LLM and return the raw response text (SYNCHRONOUS).

        Rate limit handling:
          - On 429: sleep 60s, then retry (up to max_retries)
          - On other errors: sleep 10s, then retry

        Args:
            system_prompt: System-level instructions (analyst role, rules).
            user_prompt: Per-review or batch formatted prompt.

        Returns:
            Raw LLM response string (expected to be JSON).

        Raises:
            LLMClientError: On unrecoverable errors after retries exhausted.
        """
        last_error: Optional[Exception] = None

        for attempt in range(1, self._max_retries + 1):
            try:
                if self._provider == "gemini":
                    return self._call_gemini(system_prompt, user_prompt)
                elif self._provider == "openai":
                    return self._call_openai(system_prompt, user_prompt)
                else:
                    raise LLMClientError(f"Unknown provider: {self._provider}")

            except QuotaExhaustedError:
                raise  # Don't retry — daily quota is gone

            except RateLimitError as e:
                last_error = e
                cooldown = 60  # Fixed 60s cooldown for rate limits
                logger.warning(
                    f"⏳ Rate limit hit (attempt {attempt}/{self._max_retries}), "
                    f"cooling down for {cooldown}s..."
                )
                time.sleep(cooldown)

            except LLMClientError:
                raise  # Don't retry config errors

            except Exception as e:
                last_error = e
                backoff = 10
                logger.warning(
                    f"LLM error (attempt {attempt}/{self._max_retries}): {e}. "
                    f"Retrying in {backoff}s..."
                )
                time.sleep(backoff)

        raise LLMClientError(
            f"LLM retries exhausted after {self._max_retries} attempts. "
            f"Last error: {last_error}"
        )

    def _call_gemini(self, system_prompt: str, user_prompt: str) -> str:
        """Call Gemini API via google-genai SDK (synchronous)."""
        from google.genai import types

        client = self._get_client()

        try:
            response = client.models.generate_content(
                model=self._model,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=self._temperature,
                    response_mime_type="application/json",
                ),
            )
            text = response.text
            if not text:
                raise LLMClientError("Gemini returned empty response")
            return text

        except Exception as e:
            error_str = str(e).lower()
            if "429" in error_str or "resource_exhausted" in error_str:
                # Distinguish daily quota exhaustion from transient RPM limit
                if "limit: 0" in error_str or "quota exceeded" in error_str:
                    raise QuotaExhaustedError(
                        f"🚨 Daily quota exhausted: {e}"
                    ) from e
                raise RateLimitError(f"Gemini rate limit: {e}") from e
            raise

    def _call_openai(self, system_prompt: str, user_prompt: str) -> str:
        """Call OpenAI API via openai SDK (synchronous)."""
        client = self._get_client()

        try:
            response = client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=self._temperature,
                response_format={"type": "json_object"},
            )
            text = response.choices[0].message.content
            if not text:
                raise LLMClientError("OpenAI returned empty response")
            return text

        except Exception as e:
            error_str = str(e).lower()
            if "429" in error_str or "rate" in error_str:
                raise RateLimitError(f"OpenAI rate limit: {e}") from e
            raise
