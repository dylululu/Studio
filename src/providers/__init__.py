"""Provider factory and registry for Scam-Alert Studio."""
from __future__ import annotations

from src.core.config import Config
from src.providers.base import (
    ImageProvider,
    LLMProvider,
    MockImageProvider,
    MockLLMProvider,
    MockPublisherProvider,
    MockTTSProvider,
    PublisherProvider,
    TTSProvider,
)
from src.providers.gemini_image import GeminiImageProvider
from src.providers.gemini_llm import GeminiLLMProvider
from src.providers.gemini_tts import GeminiTTSProvider
from src.providers.pillow_graphics import PillowGraphicsProvider


def get_llm_provider(config: Config | None = None) -> LLMProvider:
    cfg = config or Config.get()
    if cfg.active_provider == "gemini":
        return GeminiLLMProvider(cfg)
    return MockLLMProvider()


def get_tts_provider(config: Config | None = None) -> TTSProvider:
    cfg = config or Config.get()
    if cfg.active_provider == "gemini":
        return GeminiTTSProvider(cfg)
    return MockTTSProvider()


def get_image_provider(config: Config | None = None) -> ImageProvider:
    cfg = config or Config.get()
    choice = cfg.active_image_provider
    if choice == "gemini":
        return GeminiImageProvider(cfg)
    elif choice == "mock":
        return MockImageProvider()
    # Default is pillow_graphics (free, high-res 1080x1920)
    return PillowGraphicsProvider()


def get_publisher_provider(config: Config | None = None) -> PublisherProvider:
    # Publisher currently defaults to mock for phase 1
    return MockPublisherProvider()


__all__ = [
    "LLMProvider",
    "TTSProvider",
    "ImageProvider",
    "PublisherProvider",
    "MockLLMProvider",
    "MockTTSProvider",
    "MockImageProvider",
    "MockPublisherProvider",
    "GeminiLLMProvider",
    "GeminiTTSProvider",
    "GeminiImageProvider",
    "PillowGraphicsProvider",
    "get_llm_provider",
    "get_tts_provider",
    "get_image_provider",
    "get_publisher_provider",
]
