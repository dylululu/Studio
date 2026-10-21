"""Pillow Graphics Provider for high-resolution 1080x1920 vertical video visuals."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import yaml
from PIL import Image, ImageDraw, ImageFont

from src.core.config import Config
from src.providers.base import ImageProvider

logger = logging.getLogger(__name__)


def _draw_vertical_gradient(
    draw: ImageDraw.ImageDraw,
    width: int,
    height: int,
    start_color: Tuple[int, int, int],
    end_color: Tuple[int, int, int],
) -> None:
    """Draw a smooth vertical color gradient."""
    for y in range(height):
        factor = y / height
        r = int(start_color[0] + (end_color[0] - start_color[0]) * factor)
        g = int(start_color[1] + (end_color[1] - start_color[1]) * factor)
        b = int(start_color[2] + (end_color[2] - start_color[2]) * factor)
        draw.line([(0, y), (width, y)], fill=(r, g, b))


def _wrap_text(text: str, max_chars_per_line: int = 38) -> list[str]:
    """Simple greedy word-wrap for title and hint text."""
    words = text.split()
    lines = []
    current_line = []
    current_len = 0

    for word in words:
        if current_len + len(word) + 1 <= max_chars_per_line:
            current_line.append(word)
            current_len += len(word) + 1
        else:
            if current_line:
                lines.append(" ".join(current_line))
            current_line = [word]
            current_len = len(word)

    if current_line:
        lines.append(" ".join(current_line))
    return lines or [text]


class PillowGraphicsProvider(ImageProvider):
    """Generates 1080x1920 vertical graphics using Pillow according to config/style.yaml."""

    def __init__(self, style_path: str | Path = "config/style.yaml") -> None:
        self.style_path = Path(style_path)
        self.style = self._load_style()

    def _load_style(self) -> Dict[str, Any]:
        if self.style_path.exists():
            with open(self.style_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        return {}

    def generate_image(
        self,
        prompt: str,
        output_path: str,
        aspect_ratio: str = "9:16",
    ) -> str:
        """Create a 1080x1920 abstract visual frame for the TikTok video."""
        canvas_cfg = self.style.get("canvas", {})
        width = canvas_cfg.get("width", 1080)
        height = canvas_cfg.get("height", 1920)

        colors = self.style.get("colors", {})
        bg_start = tuple(colors.get("background_start", [11, 19, 43]))
        bg_end = tuple(colors.get("background_end", [28, 15, 26]))
        card_border = tuple(colors.get("card_border", [239, 68, 68]))
        accent_warn = tuple(colors.get("accent_warning", [245, 158, 11]))
        accent_cyan = tuple(colors.get("accent_cyan", [6, 182, 212]))
        chat_bg = tuple(colors.get("chat_bubble", [30, 41, 59]))

        # 1. Base image with gradient
        img = Image.new("RGB", (width, height))
        draw = ImageDraw.Draw(img)
        _draw_vertical_gradient(draw, width, height, bg_start, bg_end)

        # 2. Subtle background tech grid lines
        for y in range(0, height, 120):
            draw.line([(0, y), (width, y)], fill=(255, 255, 255, 10), width=1)
        for x in range(0, width, 120):
            draw.line([(x, 0), (x, height)], fill=(255, 255, 255, 10), width=1)

        # 3. Outer Warning Border
        draw.rounded_rectangle([30, 30, width - 30, height - 30], radius=24, outline=card_border, width=4)

        # 4. Top Badge Banner
        badge_text = self.style.get("badge", {}).get("text", "● CẢNH BÁO LỪA ĐẢO CÔNG NGHỆ CAO")
        draw.rounded_rectangle([80, 100, width - 80, 190], radius=16, fill=(220, 38, 38))
        draw.text((120, 130), badge_text, fill=(255, 255, 255))

        # 5. Shield Alert Icon / Graphic Placeholder
        center_x = width // 2
        shield_top = 260
        draw.polygon(
            [
                (center_x, shield_top),
                (center_x + 90, shield_top + 40),
                (center_x + 60, shield_top + 160),
                (center_x, shield_top + 210),
                (center_x - 60, shield_top + 160),
                (center_x - 90, shield_top + 40),
            ],
            outline=accent_warn,
            fill=(30, 41, 59),
        )
        draw.text((center_x - 12, shield_top + 70), "!", fill=accent_warn)

        # 6. Main Scenario / Title Card
        draw.rounded_rectangle([80, 530, width - 80, 880], radius=20, fill=(15, 23, 42), outline=accent_cyan, width=3)
        draw.text((120, 560), "[ HỒ SƠ ĐIỀU TRA ]", fill=accent_cyan)

        # Clean prompt text
        clean_prompt = prompt.replace("Abstract investigative graphic for scam:", "").strip()
        wrapped_title = _wrap_text(clean_prompt, max_chars_per_line=32)
        y_offset = 620
        for line in wrapped_title[:6]:
            draw.text((120, y_offset), line, fill=(255, 255, 255))
            y_offset += 40

        # 7. Mock Scam SMS / Message Frame (Khung tin nhắn đơn giản, không mặt người)
        draw.rounded_rectangle([80, 930, width - 80, 1420], radius=20, fill=chat_bg, outline=(71, 85, 105), width=2)
        draw.text((120, 960), "💬 TIN NHẮN / CUỘC GỌI NGHI VẤN:", fill=accent_warn)

        # Message bubble 1
        draw.rounded_rectangle([120, 1020, width - 120, 1160], radius=16, fill=(15, 23, 42))
        draw.text((150, 1045), "Kẻ gian (Giả mạo):", fill=(239, 68, 68))
        draw.text((150, 1085), '"Tài khoản của bạn sắp bị khóa. Nhấp link để xác thực ngay!"', fill=(226, 232, 240))

        # Warning advice bubble 2
        draw.rounded_rectangle([120, 1200, width - 120, 1370], radius=16, fill=(17, 24, 39), outline=accent_warn, width=2)
        draw.text((150, 1225), "⚠️ DẤU HIỆU NHẬN BIẾT:", fill=accent_warn)
        draw.text((150, 1265), "• Giục giã, đe dọa, tạo áp lực thời gian khẩn cấp", fill=(203, 213, 225))
        draw.text((150, 1305), "• Yêu cầu cung cấp mã OTP hoặc click vào link lạ", fill=(203, 213, 225))

        # 8. Bottom Action Box
        draw.rounded_rectangle([80, 1470, width - 80, 1680], radius=20, fill=(22, 101, 52), outline=(34, 197, 94), width=3)
        draw.text((120, 1505), "🛡️ BIỆN PHÁP BẢO VỆ NGAY:", fill=(255, 255, 255))
        draw.text((120, 1555), "1. Tuyệt đối KHÔNG click vào link trong tin nhắn", fill=(240, 253, 244))
        draw.text((120, 1595), "2. Liên hệ trực tiếp cơ quan ban ngành qua hotline chính thống", fill=(240, 253, 244))

        # 9. Footer Hashtags
        footer_text = self.style.get("footer", {}).get("hashtag", "#CanhBaoLuaDao #AntiScamStudio #AI_Content")
        draw.text((center_x - 220, 1750), footer_text, fill=(148, 163, 184))

        # Save to output path
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(path), format="PNG")
        logger.info(f"Generated 1080x1920 graphic at {path}")
        return str(path)

    def health_check(self) -> bool:
        """Pillow is a local dependency, health check always succeeds."""
        return True
