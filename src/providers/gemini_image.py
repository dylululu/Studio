"""Gemini Image Generation Provider using official google-genai SDK."""
from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Optional

from google import genai

from src.core.config import Config
from src.providers.base import ImageProvider

logger = logging.getLogger(__name__)


class GeminiImageProvider(ImageProvider):
    """Image generation provider using Gemini Nano Banana 2.1."""

    def __init__(self, config: Optional[Config] = None) -> None:
        self.config = config or Config.get()
        api_key = self.config.gemini_api_key
        if not api_key:
            logger.warning("GEMINI_API_KEY is not set. GeminiImageProvider calls will fail unless configured.")
            self.client = None
        else:
            self.client = genai.Client(api_key=api_key)
        self.gemini_cfg = self.config.providers_cfg.get("gemini", {})
        self.img_cfg = self.gemini_cfg.get("image", {})

    def generate_image(
        self,
        prompt: str,
        output_path: str,
        aspect_ratio: str = "9:16",
    ) -> str:
        """Generate an abstract visual illustration adhering to anti-scam safety rules."""
        if not self.client:
            raise ValueError("GEMINI_API_KEY is not set. Please configure GEMINI_API_KEY in .env.")
        model_name = self.img_cfg.get("model", "gemini-nano-banana-2.1")
        style_prompt = self.img_cfg.get(
            "style_prompt",
            "Phong cách đồ họa minh họa trừu tượng, gam màu tối bí ẩn, không vẽ mặt người thật cụ thể, tỷ lệ khung hình 9:16 dọc",
        )

        full_prompt = (
            f"{prompt}. "
            f"Visual style: {style_prompt}. "
            f"Aspect ratio: {aspect_ratio}. "
            f"CRITICAL SAFETY RULE: Do NOT depict real individuals or photorealistic human faces. Use stylized 3D graphics or abstract iconography."
        )

        interaction = self.client.interactions.create(
            model=model_name,
            input=full_prompt,
            # TODO: Cập nhật image_generation_config khi SDK chính thức chuẩn hóa tham số aspect_ratio riêng
        )

        output_image = getattr(interaction, "output_image", None)
        if not output_image or not output_image.data:
            raise RuntimeError("Gemini Image generation did not return image data")

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        img_bytes = base64.b64decode(output_image.data)
        with open(path, "wb") as f:
            f.write(img_bytes)

        return str(path)

    def health_check(self) -> bool:
        """Verify image generation endpoint with a small ping prompt."""
        if not self.client:
            self.last_error = "GEMINI_API_KEY chưa được thiết lập"
            return False
        try:
            model_name = self.img_cfg.get("model", "gemini-nano-banana-2.1")
            # 1. Verify API key and model existence
            self.client.models.get(model=f"models/{model_name}")
            # 2. Test generation request
            self.client.models.generate_content(
                model=model_name,
                contents="Minimal test prompt: abstract blue circle",
            )
            return True
        except Exception as e:
            err_str = str(e)
            logger.warning(f"Gemini Image health check failed: {err_str}")
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                self.last_error = "429 Quota Exceeded (Free Tier: Cần kích hoạt billing để dùng model ảnh)"
            else:
                self.last_error = err_str[:120]
            return False
