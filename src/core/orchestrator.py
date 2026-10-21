"""Orchestrator for managing the multi-agent anti-scam video pipeline."""
from __future__ import annotations

import logging
import time
import traceback
from typing import Any, Callable, Dict, Optional

from src.agents.stubs import (
    FactCheckerStubAgent,
    PublisherStubAgent,
    QAStubAgent,
    RenderStubAgent,
    StoryWriterStubAgent,
)
from src.core.config import Config
from src.core.db import Database
from src.core.models import JobStatus, VideoJob
from src.providers import get_llm_provider

logger = logging.getLogger(__name__)


class AgentRegistry:
    """Registry mapping pipeline step names to agent instances or callables."""

    def __init__(self) -> None:
        self._agents: Dict[str, Any] = {}

    def register(self, step_name: str, agent: Any) -> None:
        self._agents[step_name] = agent

    def get(self, step_name: str) -> Any:
        if step_name not in self._agents:
            raise KeyError(f"No agent registered for step '{step_name}'")
        return self._agents[step_name]

    def has(self, step_name: str) -> bool:
        return step_name in self._agents


class Orchestrator:
    """Executes VideoJob lifecycle across agents with retries, backoff, and manual gates."""

    def __init__(
        self,
        db: Optional[Database] = None,
        registry: Optional[AgentRegistry] = None,
        config: Optional[Config] = None,
        max_retries: Optional[int] = None,
        backoff_seconds: Optional[float] = None,
    ) -> None:
        self.config = config or Config.get()
        self.db = db or Database(self.config.db_path)
        self.registry = registry or AgentRegistry()

        orch_cfg = self.config.default_cfg.get("orchestrator", {})
        self.max_retries = (
            max_retries
            if max_retries is not None
            else orch_cfg.get("max_retries", 2)
        )
        self.backoff_seconds = (
            backoff_seconds
            if backoff_seconds is not None
            else orch_cfg.get("retry_backoff_seconds", 0.5)
        )

        self._register_default_agents()

    def _register_default_agents(self) -> None:
        """Register default stub agents if not already present."""
        if not self.registry.has("fact_checker"):
            self.registry.register("fact_checker", FactCheckerStubAgent())
        if not self.registry.has("story_writer"):
            self.registry.register("story_writer", StoryWriterStubAgent())
        if not self.registry.has("renderer"):
            self.registry.register("renderer", RenderStubAgent())
        if not self.registry.has("qa_compliance"):
            self.registry.register("qa_compliance", QAStubAgent())
        if not self.registry.has("publisher"):
            self.registry.register("publisher", PublisherStubAgent())

    def _execute_agent_with_retry(
        self,
        step_name: str,
        job: VideoJob,
    ) -> VideoJob:
        """Execute an agent with exponential backoff on retry (max 2 retries)."""
        agent = self.registry.get(step_name)
        input_snapshot = job.model_dump()

        last_exception: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                if hasattr(agent, "run"):
                    result_job = agent.run(job)
                elif callable(agent):
                    result_job = agent(job)
                else:
                    raise TypeError(f"Agent for step '{step_name}' is not callable and has no run() method")

                # Step completed successfully
                self.db.log_step(
                    job_id=job.id,
                    step_name=step_name,
                    status="COMPLETED",
                    input_payload=input_snapshot,
                    output_payload=result_job.model_dump(),
                )

                # Check and record LLM usage if available on agent
                llm = getattr(agent, "llm", None)
                if llm and getattr(llm, "last_usage", None):
                    u = llm.last_usage
                    self.db.record_usage(
                        job_id=job.id,
                        step_name=step_name,
                        provider=u.provider,
                        model=u.model,
                        prompt_tokens=u.prompt_tokens,
                        candidate_tokens=u.candidate_tokens,
                        total_tokens=u.total_tokens,
                        estimated_cost_usd=u.estimated_cost_usd,
                    )

                return result_job

            except Exception as e:
                last_exception = e
                tb = traceback.format_exc()
                self.db.log_error(
                    job_id=job.id,
                    step_name=step_name,
                    error_message=str(e),
                    traceback_str=tb,
                )
                logger.warning(
                    f"Step '{step_name}' failed attempt {attempt + 1}/{self.max_retries + 1}: {e}"
                )

                if attempt < self.max_retries:
                    sleep_time = self.backoff_seconds * (2 ** attempt)
                    if sleep_time > 0:
                        time.sleep(sleep_time)

        # Retries exhausted
        self.db.log_step(
            job_id=job.id,
            step_name=step_name,
            status="FAILED",
            input_payload=input_snapshot,
            output_payload={"error": str(last_exception)},
        )
        job.set_status(JobStatus.FAILED, note=f"Failed at step '{step_name}': {str(last_exception)}")
        job.error_message = str(last_exception)
        return job

    def run_job(self, job: VideoJob) -> VideoJob:
        """Run job through pipeline stages until completion, failure, or a manual gate."""
        self.db.save_job(job)

        while True:
            # 1. SCOUTED -> VERIFIED
            if job.status == JobStatus.SCOUTED:
                job = self._execute_agent_with_retry("fact_checker", job)
                self.db.save_job(job)
                if job.status == JobStatus.FAILED:
                    break

            # 2. VERIFIED -> SCRIPTED
            elif job.status == JobStatus.VERIFIED:
                job = self._execute_agent_with_retry("story_writer", job)
                self.db.save_job(job)
                if job.status == JobStatus.FAILED:
                    break

            # 3. SCRIPTED: Manual gate 1 (Text Approval Gate)
            elif job.status == JobStatus.SCRIPTED:
                logger.info(f"Job {job.id} halted at TEXT APPROVAL GATE (Status: SCRIPTED). Awaiting manual approval.")
                break

            # 4. TEXT_APPROVED -> RENDERED
            elif job.status == JobStatus.TEXT_APPROVED:
                job = self._execute_agent_with_retry("renderer", job)
                self.db.save_job(job)
                if job.status == JobStatus.FAILED:
                    break

            # 5. RENDERED -> QA_PASSED
            elif job.status == JobStatus.RENDERED:
                job = self._execute_agent_with_retry("qa_compliance", job)
                self.db.save_job(job)
                if job.status == JobStatus.FAILED:
                    break

            # 6. QA_PASSED -> PENDING_REVIEW
            elif job.status == JobStatus.QA_PASSED:
                job.set_status(JobStatus.PENDING_REVIEW)
                self.db.save_job(job)
                logger.info(f"Job {job.id} halted at FINAL REVIEW GATE (Status: PENDING_REVIEW). Awaiting publish approval.")
                break

            # 7. PENDING_REVIEW: Manual gate 2 (Final Video Review Gate)
            elif job.status == JobStatus.PENDING_REVIEW:
                logger.info(f"Job {job.id} is waiting for final publish approval.")
                break

            # Terminal states
            elif job.status in (JobStatus.PUBLISHED, JobStatus.REJECTED, JobStatus.FAILED):
                break

            else:
                logger.error(f"Unknown or unhandled job status: {job.status}")
                break

        return job

    def approve_job(self, job_id: str, notes: Optional[str] = None) -> VideoJob:
        """Approve job at manual gates (SCRIPTED -> TEXT_APPROVED, PENDING_REVIEW -> PUBLISHED)."""
        job = self.db.get_job(job_id)
        if not job:
            raise ValueError(f"Job with id '{job_id}' not found")

        if job.status == JobStatus.SCRIPTED:
            logger.info(f"Approving script for job {job_id}")
            job.set_status(JobStatus.TEXT_APPROVED, note=notes or "Script approved by reviewer")
            self.db.save_job(job)
            return self.run_job(job)

        elif job.status == JobStatus.PENDING_REVIEW:
            logger.info(f"Approving final video for job {job_id}")
            # Run publisher step
            job = self._execute_agent_with_retry("publisher", job)
            self.db.save_job(job)
            return job

        else:
            raise ValueError(
                f"Job {job_id} is in status '{job.status.value}', which cannot be approved. "
                f"Approval is only valid for SCRIPTED or PENDING_REVIEW."
            )

    def reject_job(self, job_id: str, reason: str = "Rejected by reviewer") -> VideoJob:
        """Reject job and halt pipeline."""
        job = self.db.get_job(job_id)
        if not job:
            raise ValueError(f"Job with id '{job_id}' not found")

        job.set_status(JobStatus.REJECTED, note=reason)
        job.error_message = reason
        self.db.save_job(job)
        logger.info(f"Job {job_id} rejected. Reason: {reason}")
        return job
