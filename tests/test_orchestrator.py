"""Tests for pipeline orchestrator with mock providers and stub agents."""
import pytest
from src.core.db import Database
from src.core.models import JobStatus, Topic, VideoJob
from src.core.orchestrator import AgentRegistry, Orchestrator


@pytest.fixture
def clean_orchestrator(tmp_path):
    db_file = tmp_path / "test_orch.db"
    db = Database(db_file)
    registry = AgentRegistry()
    # backoff 0 for fast tests
    orch = Orchestrator(db=db, registry=registry, max_retries=2, backoff_seconds=0.0)
    return orch


def test_orchestrator_end_to_end_flow(clean_orchestrator):
    orch = clean_orchestrator
    topic = Topic(title="Lừa đảo Deepfake chuyển tiền khẩn cấp")
    job = VideoJob(status=JobStatus.SCOUTED, topic=topic)

    # Stage 1: Run to Gate 1 (Text Approval Gate)
    job = orch.run_job(job)
    assert job.status == JobStatus.SCRIPTED
    assert job.script is not None
    assert len(job.script.checklist) >= 3
    assert len(job.script.sources) >= 1

    # Stage 2: Approve Gate 1 (Script Approval) -> runs to Gate 2 (Pending Review)
    job = orch.approve_job(job.id, notes="Kịch bản tốt, đã duyệt")
    assert job.status == JobStatus.PENDING_REVIEW
    assert "audio" in job.paths
    assert "cover_image" in job.paths

    # Stage 3: Approve Gate 2 (Final Video Publish Approval) -> Published
    job = orch.approve_job(job.id, notes="Video đạt chuẩn, duyệt xuất bản")
    assert job.status == JobStatus.PUBLISHED
    assert job.paths.get("platform_url") != ""


def test_orchestrator_reject_at_gate(clean_orchestrator):
    orch = clean_orchestrator
    job = VideoJob(status=JobStatus.SCOUTED, topic=Topic(title="Vụ việc nghi vấn"))
    job = orch.run_job(job)
    assert job.status == JobStatus.SCRIPTED

    # Reviewer rejects
    rejected = orch.reject_job(job.id, reason="Nguồn tin chưa đủ căn cứ xác thực")
    assert rejected.status == JobStatus.REJECTED
    assert "chưa đủ căn cứ" in rejected.error_message


def test_orchestrator_retry_and_failure(clean_orchestrator):
    orch = clean_orchestrator

    # Register an agent that always throws an error
    attempts = 0

    def failing_agent(job: VideoJob) -> VideoJob:
        nonlocal attempts
        attempts += 1
        raise RuntimeError("External network connection timeout")

    orch.registry.register("fact_checker", failing_agent)

    job = VideoJob(status=JobStatus.SCOUTED, topic=Topic(title="Test retry"))
    job = orch.run_job(job)

    # Max retries = 2 -> 1 initial attempt + 2 retries = 3 attempts total
    assert attempts == 3
    assert job.status == JobStatus.FAILED
    assert "timeout" in job.error_message

    # Verify db logs
    steps = orch.db.get_job_steps(job.id)
    assert any(s["status"] == "FAILED" for s in steps)


def test_orchestrator_transient_error_recovery(clean_orchestrator):
    orch = clean_orchestrator

    # Agent that fails once then succeeds
    attempts = 0

    class FlakyAgent:
        def run(self, job: VideoJob) -> VideoJob:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise ConnectionError("Temporary connection glitch")
            job.status = JobStatus.VERIFIED
            from src.core.models import Source
            if not job.topic.sources:
                job.topic.sources.append(Source(title="Nguồn tin tức", url="https://tuoitre.vn/test"))
            return job

    orch.registry.register("fact_checker", FlakyAgent())

    job = VideoJob(status=JobStatus.SCOUTED, topic=Topic(title="Flaky test"))
    job = orch.run_job(job)

    assert attempts == 2
    # It should have recovered and continued to SCRIPTED
    assert job.status == JobStatus.SCRIPTED
