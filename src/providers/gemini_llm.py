"""Gemini LLM Provider using official google-genai SDK."""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional, Type, TypeVar
from pydantic import BaseModel, ValidationError

from google import genai
from google.genai import types
from google.genai.errors import APIError

from src.core.config import Config
from src.providers.base import LLMProvider, LLMUsage

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class GeminiLLMProvider(LLMProvider):
    """LLM provider backed by Gemini API with structured JSON output and usage tracking."""

    def __init__(self, config: Optional[Config] = None) -> None:
        super().__init__()
        self.config = config or Config.get()
        api_key = self.config.gemini_api_key
        if not api_key:
            logger.warning("GEMINI_API_KEY is not set. GeminiLLMProvider calls will fail unless configured.")
            self.client = None
        else:
            self.client = genai.Client(api_key=api_key)
        self.gemini_cfg = self.config.providers_cfg.get("gemini", {})
        self.models_cfg = self.gemini_cfg.get("models", {})
        self.pricing_cfg = self.gemini_cfg.get("pricing", {})

    def _resolve_model(self, tier: str) -> str:
        """Resolve model name by tier from config/providers.yaml."""
        if tier == "smart":
            return self.models_cfg.get("smart", "gemini-3.5-flash-lite")
        # default fast
        return self.models_cfg.get("fast", "gemini-3.5-flash-lite")

    def _calculate_cost(self, model: str, prompt_tokens: int, candidate_tokens: int) -> float:
        """Estimate cost in USD from token counts and config pricing."""
        pricing = self.pricing_cfg.get(model, {})
        prompt_rate = pricing.get("prompt_per_1m", 0.15) / 1_000_000.0
        candidate_rate = pricing.get("candidate_per_1m", 0.60) / 1_000_000.0
        return round(prompt_tokens * prompt_rate + candidate_tokens * candidate_rate, 6)

    def generate_json(
        self,
        prompt: str,
        schema: Type[T],
        tier: str = "fast",
        system_instruction: Optional[str] = None,
    ) -> T:
        """Generate structured JSON adhering to Pydantic schema with 1 retry on parse error."""
        if not self.client:
            raise ValueError("GEMINI_API_KEY is not set. Please set GEMINI_API_KEY in .env.")

        model_name = self._resolve_model(tier)

        gen_config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
            system_instruction=system_instruction,
        )

        last_error: Optional[Exception] = None
        current_prompt = prompt

        for attempt in range(2):
            try:
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=current_prompt,
                    config=gen_config,
                )
                raw_text = response.text or ""

                # Extract token usage if provided
                usage = getattr(response, "usage_metadata", None)
                p_tokens = getattr(usage, "prompt_token_count", 0) or 0
                c_tokens = getattr(usage, "candidates_token_count", 0) or 0
                t_tokens = getattr(usage, "total_token_count", 0) or (p_tokens + c_tokens)

                self.last_usage = LLMUsage(
                    provider="gemini",
                    model=model_name,
                    prompt_tokens=p_tokens,
                    candidate_tokens=c_tokens,
                    total_tokens=t_tokens,
                    estimated_cost_usd=self._calculate_cost(model_name, p_tokens, c_tokens),
                )

                # Validate against schema
                validated = schema.model_validate_json(raw_text)
                return validated

            except (ValidationError, json.JSONDecodeError) as e:
                last_error = e
                logger.warning(f"Schema validation failed on attempt {attempt + 1}: {e}. Retrying once...")
                current_prompt = (
                    f"{prompt}\n\n"
                    f"IMPORTANT: Your previous output failed schema validation with error: {str(e)}.\n"
                    f"Please output strictly valid JSON conforming exactly to the required schema."
                )
            except Exception as e:
                raise e

        if last_error:
            raise last_error
        raise RuntimeError("Failed to generate valid structured JSON from Gemini LLM")

    def health_check(self) -> bool:
        """Ping Gemini API with a minimal generation to verify API key and model availability."""
        if not self.client:
            return False
        try:
            model_name = self._resolve_model("fast")
            response = self.client.models.generate_content(
                model=model_name,
                contents="Health check test. Reply with 'OK'.",
            )
            return bool(response and response.text)
        except Exception as e:
            logger.error(f"Gemini LLM health check failed: {e}")
            return False

