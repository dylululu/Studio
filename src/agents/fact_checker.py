"""Agent FactChecker: xác minh Topic, trích sự kiện + URL, kiểm tra URL bằng httpx."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field

import httpx

from src.core.models import JobStatus, Source, VideoJob
from src.providers.base import LLMProvider, MockLLMProvider

logger = logging.getLogger(__name__)


# ── I/O schemas ──────────────────────────────────────────────────────────────

class FactInput(BaseModel):
    title: str
    summary: str
    sources: List[Source] = Field(default_factory=list)


class FactEvent(BaseModel):
    event: str
    source_title: str
    source_url: str


class FactOutput(BaseModel):
    status: str = "VERIFIED"          # VERIFIED | REJECTED
    reason: str = ""
    facts: List[FactEvent] = Field(default_factory=list)
    verified_sources: List[Source] = Field(default_factory=list)


# ── URL reachability check ────────────────────────────────────────────────────

def _url_reachable(url: str, timeout: float = 5.0) -> bool:
    """HEAD request để kiểm tra URL còn truy cập được. Trả False nếu lỗi."""
    try:
        resp = httpx.head(url, timeout=timeout, follow_redirects=True)
        return resp.status_code < 400
    except Exception:
        return False


# ── Agent ─────────────────────────────────────────────────────────────────────

class FactCheckerAgent:
    """Tier: smart + grounding Google Search (nếu provider hỗ trợ).
    Xác minh Topic, kiểm tra URL, trích 3–5 sự kiện then chốt.
    """

    PROMPT_FILE = Path("prompts/fact_checker.md")

    def __init__(
        self,
        llm: Optional[LLMProvider] = None,
        check_urls: bool = True,
    ) -> None:
        self.llm = llm or MockLLMProvider()
        self.check_urls = check_urls

    def _load_prompt(self) -> str:
        if self.PROMPT_FILE.exists():
            return self.PROMPT_FILE.read_text(encoding="utf-8")
        return "Xác minh sự kiện và nguồn tin."

    def _build_prompt(self, fact_input: FactInput) -> str:
        tpl = self._load_prompt()
        return (
            tpl.strip()
            + "\n\n## Input\n```json\n"
            + fact_input.model_dump_json(indent=2)
            + "\n```"
        )

    def _filter_reachable_sources(self, sources: List[Source]) -> List[Source]:
        """Giữ lại các URL HEAD 2xx/3xx; mock URL luôn pass."""
        if not self.check_urls:
            return sources
        reachable = []
        for s in sources:
            if "mock" in s.url or "example.com" in s.url:
                reachable.append(s)   # mock/fixture URL không fetch thực
            elif _url_reachable(s.url):
                reachable.append(s)
            else:
                logger.warning(f"URL không khả dụng (bỏ qua): {s.url}")
        return reachable

    def run(self, job: VideoJob) -> VideoJob:
        """Xác minh job.topic; cập nhật status VERIFIED hoặc REJECTED."""
        if not job.topic:
            raise ValueError("FactChecker: job.topic is missing")

        fact_input = FactInput(
            title=job.topic.title,
            summary=job.topic.summary,
            sources=job.topic.sources,
        )

        result: FactOutput = self.llm.generate_json(
            prompt=self._build_prompt(fact_input),
            schema=FactOutput,
            tier="smart",
        )

        if result.status == "REJECTED":
            job.set_status(JobStatus.REJECTED, note=f"FactChecker REJECTED: {result.reason}")
            job.error_message = result.reason
            return job

        # Lọc URL còn khả dụng
        live_sources = self._filter_reachable_sources(result.verified_sources)
        if not live_sources:
            job.set_status(
                JobStatus.REJECTED,
                note="FactChecker REJECTED: Không có nguồn URL nào còn khả dụng."
            )
            job.error_message = "Không có nguồn URL còn khả dụng."
            return job

        # Lưu facts và verified sources vào topic
        job.topic.sources = live_sources
        # Gán facts vào job metadata (dùng trong StoryWriter)
        job.paths["_facts_json"] = result.model_dump_json()

        job.set_status(JobStatus.VERIFIED)
        return job
