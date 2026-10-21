"""Agent TrendScout: đọc config/sources.yaml, lọc bài, chấm điểm chủ đề, trả top-N."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

import yaml

from src.core.models import Source, Topic
from src.providers.base import LLMProvider, MockLLMProvider

logger = logging.getLogger(__name__)


# ── I/O schemas (nhỏ gọn, chỉ truyền dữ liệu cần thiết) ─────────────────────

class Headline(BaseModel):
    title: str
    url: str
    source: str
    published: str = ""


class ScoutInput(BaseModel):
    headlines: List[Headline]
    seen_topic_titles: List[str] = Field(default_factory=list)
    top_n: int = 5


class ScoredTopic(BaseModel):
    title: str
    summary: str
    scam_type: str = "other"
    target_audience: str = "general"
    score: float = 0.0
    sources: List[Source] = Field(default_factory=list)


class ScoutOutput(BaseModel):
    topics: List[ScoredTopic] = Field(default_factory=list)


# ── Agent ─────────────────────────────────────────────────────────────────────

class TrendScoutAgent:
    """Tier: fast. Đọc config/sources.yaml, gọi LLM chấm điểm, trả top-N Topic."""

    PROMPT_FILE = Path("prompts/scout.md")
    SOURCES_FILE = Path("config/sources.yaml")

    def __init__(
        self,
        llm: Optional[LLMProvider] = None,
        sources_path: Optional[Path] = None,
        db_seen_titles: Optional[List[str]] = None,
    ) -> None:
        self.llm = llm or MockLLMProvider()
        self.sources_path = sources_path or self.SOURCES_FILE
        self.db_seen_titles: List[str] = db_seen_titles or []

    def _load_sources_cfg(self) -> Dict[str, Any]:
        if not self.sources_path.exists():
            logger.warning(f"sources.yaml not found at {self.sources_path}")
            return {}
        with open(self.sources_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _load_prompt(self) -> str:
        if self.PROMPT_FILE.exists():
            return self.PROMPT_FILE.read_text(encoding="utf-8")
        return "Chấm điểm và lọc chủ đề lừa đảo từ danh sách headlines."

    def _build_mock_headlines(self, sources_cfg: Dict[str, Any]) -> List[Headline]:
        """Tạo headlines giả khi chạy offline / mock (không fetch thực tế)."""
        sources = sources_cfg.get("sources", [])
        keywords = sources_cfg.get("keywords", ["lừa đảo"])
        headlines = []
        for s in sources[:3]:
            kw = keywords[0] if keywords else "lừa đảo"
            headlines.append(Headline(
                title=f"[Mock] Cảnh báo {kw} mới từ {s.get('name', 'Nguồn')}",
                url=s.get("url", "https://example.com"),
                source=s.get("name", "Nguồn"),
                published="2026-10-21T07:00:00Z",
            ))
        return headlines

    def run(self, top_n: int = 5, extra_headlines: Optional[List[Headline]] = None) -> List[Topic]:
        """Trả danh sách Topic đã chấm điểm, top_n chủ đề tốt nhất."""
        sources_cfg = self._load_sources_cfg()
        seen = list(self.db_seen_titles) + sources_cfg.get("seen_topics", [])

        headlines = extra_headlines or self._build_mock_headlines(sources_cfg)

        prompt_tpl = self._load_prompt()
        scout_input = ScoutInput(
            headlines=headlines,
            seen_topic_titles=seen,
            top_n=top_n,
        )

        prompt = (
            prompt_tpl.strip()
            + "\n\n## Input\n```json\n"
            + scout_input.model_dump_json(indent=2)
            + "\n```"
        )

        result: ScoutOutput = self.llm.generate_json(
            prompt=prompt,
            schema=ScoutOutput,
            tier="fast",
        )

        topics: List[Topic] = []
        for st in result.topics:
            topics.append(Topic(
                title=st.title,
                summary=st.summary,
                scam_type=st.scam_type,
                target_audience=st.target_audience,
                sources=st.sources,
            ))
        return topics
