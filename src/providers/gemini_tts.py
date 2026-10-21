"""Gemini TTS Provider using official google-genai SDK."""
from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Optional

from google import genai

from src.core.config import Config
from src.providers.base import TTSProvider

logger = logging.getLogger(__name__)


class GeminiTTSProvider(TTSProvider):
    """Text-to-speech audio provider powered by Gemini 3.8 Flash TTS."""

    def __init__(self, config: Optional[Config] = None) -> None:
        self.config = config or Config.get()
        api_key = self.config.gemini_api_key
        if not api_key:
            logger.warning("GEMINI_API_KEY is not set. GeminiTTSProvider calls will fail unless configured.")
            self.client = None
        else:
            self.client = genai.Client(api_key=api_key)
        self.gemini_cfg = self.config.providers_cfg.get("gemini", {})
        self.tts_cfg = self.gemini_cfg.get("tts", {})

    def synthesize(
        self,
        text: str,
        output_path: str,
        voice: Optional[str] = None,
        language: str = "vi",
    ) -> str:
        """Convert text into speech audio file (WAV)."""
        if not self.client:
            raise ValueError("GEMINI_API_KEY is not set. Please configure GEMINI_API_KEY in .env.")
        model_name = self.tts_cfg.get("model", "gemini-3.8-flash-tts")
        selected_voice = voice or self.tts_cfg.get("voice", "Aoede")
        style = self.tts_cfg.get("style", "serious investigative and warning tone")

        # Prepare user input with speech_metadata annotation
        user_input = [
            {
                "type": "user_input",
                "content": [
                    {
                        "type": "text",
                        "text": text,
                        "annotations": [
                            {
                                "type": "speech_metadata",
                                "style": style,
                                # TODO: Thêm pitch/rate modifier khi API Gemini TTS hỗ trợ chính thức
                            }
                        ],
                    }
                ],
            }
        ]

        # Call Gemini TTS interaction
        interaction = self.client.interactions.create(
            model=model_name,
            input=user_input,
            response_format={"type": "audio"},
            generation_config={
                "speech_config": [
                    {"voice": selected_voice}
                ]
            },
        )

        output_audio = getattr(interaction, "output_audio", None)
        if not output_audio or not output_audio.data:
            raise RuntimeError("Gemini TTS did not return audio data")

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        audio_bytes = base64.b64decode(output_audio.data)
        with open(path, "wb") as f:
            f.write(audio_bytes)

        return str(path)

    def health_check(self) -> bool:
        """Verify TTS endpoint by synthesizing a minimal short word."""
        if not self.client:
            return False
        try:
            model_name = self.tts_cfg.get("model", "gemini-3.8-flash-tts")
            voice = self.tts_cfg.get("voice", "Aoede")
            interaction = self.client.interactions.create(
                model=model_name,
                input=[
                    {
                        "type": "user_input",
                        "content": [{"type": "text", "text": "Test"}],
                    }
                ],
                response_format={"type": "audio"},
                generation_config={"speech_config": [{"voice": voice}]},
            )
            output_audio = getattr(interaction, "output_audio", None)
            return bool(output_audio and output_audio.data)
        except Exception as e:
            logger.error(f"Gemini TTS health check failed: {e}")
            return False
