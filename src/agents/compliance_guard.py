"""Agent ComplianceGuard: kiểm tra Script theo 6 quy tắc nội dung, tối đa 2 vòng sửa."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field

from src.core.models import JobStatus, Script, VideoJob
from src.providers.base import LLMProvider, MockLLMProvider

logger = logging.getLogger(__name__)

MAX_REVISION_ROUNDS = 2


# ── I/O schemas ──────────────────────────────────────────────────────────────

class ComplianceInput(BaseModel):
    hook: str
    beats: List[dict] = Field(default_factory=list)
    checklist: List[str] = Field(default_factory=list)
    cta: str
    sources: List[dict] = Field(default_factory=list)
    risk_flags: List[str] = Field(default_factory=list)


class Violation(BaseModel):
    rule: str
    detail: str


class ComplianceOutput(BaseModel):
    passed: bool = True
    violations: List[Violation] = Field(default_factory=list)


# ── Agent ─────────────────────────────────────────────────────────────────────

class ComplianceGuardAgent:
    """Tier: smart. Kiểm tra 6 quy tắc nội dung.
    Nếu Script vi phạm, gọi StoryWriter sửa tối đa 2 vòng; vẫn lỗi → REJECTED.
    """

    PROMPT_FILE = Path("prompts/compliance.md")

    def __init__(
        self,
        llm: Optional[LLMProvider] = None,
        writer_agent=None,
    ) -> None:
        self.llm = llm or MockLLMProvider()
        self.writer_agent = writer_agent  # Optional: inject StoryWriterAgent cho vòng sửa

    def _load_prompt(self) -> str:
        if self.PROMPT_FILE.exists():
            return self.PROMPT_FILE.read_text(encoding="utf-8")
        return "Kiểm tra tuân thủ nội dung."

    def _build_input(self, script: Script) -> ComplianceInput:
        return ComplianceInput(
            hook=script.hook,
            beats=[b.model_dump() for b in script.beats],
            checklist=script.checklist,
            cta=script.cta,
            sources=[s.model_dump() for s in script.sources],
            risk_flags=script.risk_flags,
        )

    def _check(self, script: Script) -> ComplianceOutput:
        ci = self._build_input(script)
        prompt = (
            self._load_prompt().strip()
            + "\n\n## Input\n```json\n"
            + ci.model_dump_json(indent=2)
            + "\n```"
        )
        return self.llm.generate_json(
            prompt=prompt,
            schema=ComplianceOutput,
            tier="smart",
        )

    def run(self, job: VideoJob) -> VideoJob:
        """Kiểm tra và (nếu có writer_agent) thử sửa tối đa 2 vòng."""
        if not job.script:
            raise ValueError("ComplianceGuard: job.script is missing")

        for attempt in range(MAX_REVISION_ROUNDS + 1):
            result = self._check(job.script)

            if result.passed:
                job.set_status(JobStatus.QA_PASSED)
                logger.info(f"ComplianceGuard PASSED (attempt {attempt + 1})")
                return job

            violation_summary = "; ".join(
                f"{v.rule}: {v.detail}" for v in result.violations
            )
            logger.warning(
                f"ComplianceGuard vi phạm (attempt {attempt + 1}): {violation_summary}"
            )

            # Gắn risk_flags để writer biết cần sửa gì
            job.script.risk_flags = [f"{v.rule}: {v.detail}" for v in result.violations]

            if attempt < MAX_REVISION_ROUNDS and self.writer_agent:
                logger.info(f"Yêu cầu StoryWriter sửa lần {attempt + 1}...")
                job = self.writer_agent.run(job)
                if job.status == JobStatus.FAILED:
                    return job
            else:
                # Hết vòng hoặc không có writer → REJECTED
                job.set_status(
                    JobStatus.REJECTED,
                    note=f"ComplianceGuard REJECTED sau {attempt + 1} lần: {violation_summary}",
                )
                job.error_message = violation_summary
                return job

        # Không bao giờ đến đây, nhưng an toàn
        job.set_status(JobStatus.REJECTED, note="ComplianceGuard: vượt quá số lần sửa cho phép")
        return job
