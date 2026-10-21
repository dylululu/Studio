"""Gemini LLM Provider using official google-genai SDK."""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional, Type, TypeVar
from pydantic import BaseModel, ValidationError

from google import genai
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
            return self.models_cfg.get("smart", "gemini-3.8-flash")
        # default fast
        return self.models_cfg.get("fast", "gemini-3.8-flash")

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
        schema_json = schema.model_json_schema()

        call_params: Dict[str, Any] = {
            "model": model_name,
            "input": prompt,
            "response_format": {
                "type": "text",
                "mime_type": "application/json",
                "schema": schema_json,
            },
        }
        if system_instruction:
            # Interaction API accepts interaction-scoped system_instruction
            call_params["system_instruction"] = system_instruction

        last_error: Optional[Exception] = None

        # Up to 2 attempts: attempt 1 + 1 retry on validation failure
        for attempt in range(2):
            try:
                interaction = self.client.interactions.create(**call_params)
                raw_text = interaction.output_text or ""

                # Extract token usage if provided
                usage = getattr(interaction, "usage", None)
                p_tokens = getattr(usage, "prompt_tokens", 0) or getattr(usage, "input_tokens", 0) or 0
                c_tokens = getattr(usage, "candidate_tokens", 0) or getattr(usage, "output_tokens", 0) or 0
                t_tokens = getattr(usage, "total_tokens", 0) or (p_tokens + c_tokens)

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
                # Augment prompt for retry with error guidance
                call_params["input"] = (
                    f"{prompt}\n\n"
                    f"IMPORTANT: Your previous output failed schema validation with error: {str(e)}.\n"
                    f"Please output strictly valid JSON conforming exactly to the required schema."
                )
            except Exception as e:
                # API error or unexpected network issue
                raise e

        if last_error:
            raise last_error
        raise RuntimeError("Failed to generate valid structured JSON from Gemini LLM")

    def health_check(self) -> bool:
        """Ping Gemini API with a minimal interaction to verify API key and model availability."""
        if not self.client:
            return False
        try:
            model_name = self._resolve_model("fast")
            interaction = self.client.interactions.create(
                model=model_name,
                input="Health check test. Reply with 'OK'.",
            )
            return bool(interaction and interaction.output_text)
        except Exception as e:
            logger.error(f"Gemini LLM health check failed: {e}")
            return False
