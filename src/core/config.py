"""Configuration loader for Scam-Alert Studio."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict
import yaml
from dotenv import load_dotenv

# Load .env file automatically
load_dotenv()


def load_yaml(file_path: str | Path) -> Dict[str, Any]:
    path = Path(file_path)
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class Config:
    """Singleton-like configuration access."""

    _instance = None

    def __init__(self, root_dir: str | Path = ".") -> None:
        self.root_dir = Path(root_dir)
        self.default_cfg = load_yaml(self.root_dir / "config" / "default.yaml")
        self.providers_cfg = load_yaml(self.root_dir / "config" / "providers.yaml")

    @classmethod
    def get(cls) -> "Config":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def gemini_api_key(self) -> str:
        return os.environ.get("GEMINI_API_KEY", "")

    @property
    def active_provider(self) -> str:
        import sys
        if "pytest" in sys.modules or os.environ.get("STUDIO_ENV") == "test":
            return "mock"
        return self.providers_cfg.get("active_provider", "mock")

    @property
    def active_image_provider(self) -> str:
        import sys
        if "pytest" in sys.modules or os.environ.get("STUDIO_ENV") == "test":
            return "mock"
        return self.providers_cfg.get("active_image_provider", "pillow_graphics")

    @property
    def db_path(self) -> str:
        return self.default_cfg.get("storage", {}).get("db_path", "data/studio.db")
