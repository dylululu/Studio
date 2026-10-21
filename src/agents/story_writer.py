"""Agent StoryWriter: kịch bản tiếng Việt 150–220 từ với variant A/B hook."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field

from src.core.models import Beat, JobStatus, Script, Source, VideoJob
from src.providers.base import LLMProvider, MockLLMProvider

logger = logging.getLogger(__name__)

LEARNED_FILE = Path("config/learned.yaml")


# ── I/O schemas ──────────────────────────────────────────────────────────────

class FactEvent(BaseModel):
    event: str
    source_title: str
    source_url: str


class WriterInput(BaseModel):
    title: str
    facts: List[FactEvent] = Field(default_factory=list)
    verified_sources: List[Source] = Field(default_factory=list)
    variant: str = "A"
    learned: dict = Field(default_factory=dict)


class WriterOutput(BaseModel):
    hook: str
    beats: List[Beat]
    checklist: List[str] = Field(min_length=3)
    cta: str
    sources: List[Source]
    risk_flags: List[str] = Field(default_factory=list)


# ── Agent ─────────────────────────────────────────────────────────────────────

class StoryWriterAgent:
    """Tier: smart. Viết kịch bản 150–220 từ với variant A/B hook.
    Đọc config/learned.yaml nếu tồn tại để điều chỉnh phong cách.
    """

    PROMPT_FILE = Path("prompts/story_writer.md")

    def __init__(
        self,
        llm: Optional[LLMProvider] = None,
        variant: str = "A",
    ) -> None:
        self.llm = llm or MockLLMProvider()
        self.variant = variant

    def _load_prompt(self) -> str:
        if self.PROMPT_FILE.exists():
            return self.PROMPT_FILE.read_text(encoding="utf-8")
        return "Viết kịch bản cảnh báo lừa đảo."

    def _load_learned(self) -> dict:
        if not LEARNED_FILE.exists():
            return {}
        try:
            import yaml
            with open(LEARNED_FILE, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception:
            return {}

    def _extract_facts(self, job: VideoJob) -> tuple[List[FactEvent], List[Source]]:
        """Lấy facts từ job.paths['_facts_json'] (được FactChecker ghi lại)."""
        facts_json = job.paths.get("_facts_json", "")
        if facts_json:
            try:
                data = json.loads(facts_json)
                facts = [FactEvent(**f) for f in data.get("facts", [])]
                sources = [Source(**s) for s in data.get("verified_sources", [])]
                return facts, sources
            except Exception as e:
                logger.warning(f"Không parse được _facts_json: {e}")
        # Fallback: dùng sources từ topic
        sources = job.topic.sources if job.topic else []
        return [], sources

    def _build_prompt(self, writer_input: WriterInput) -> str:
        tpl = self._load_prompt()
        return (
            tpl.strip()
            + "\n\n## Input\n```json\n"
            + writer_input.model_dump_json(indent=2)
            + "\n```"
        )

    def run(self, job: VideoJob) -> VideoJob:
        """Tạo Script từ topic đã VERIFIED; hỗ trợ variant A/B."""
        if not job.topic:
            raise ValueError("StoryWriter: job.topic is missing")
        if not job.topic.sources:
            raise ValueError("StoryWriter: không có nguồn đã xác minh")

        facts, verified_sources = self._extract_facts(job)
        learned = self._load_learned()

        writer_input = WriterInput(
            title=job.topic.title,
            facts=facts,
            verified_sources=verified_sources or job.topic.sources,
            variant=self.variant,
            learned=learned,
        )

        result: WriterOutput = self.llm.generate_json(
            prompt=self._build_prompt(writer_input),
            schema=WriterOutput,
            tier="smart",
        )

        job.script = Script(
            hook=result.hook,
            beats=result.beats,
            checklist=result.checklist,
            cta=result.cta,
            sources=result.sources or verified_sources,
            risk_flags=result.risk_flags,
        )
        job.set_status(JobStatus.SCRIPTED)
        return job
