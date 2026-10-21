"""Tests for SQLite database persistence."""
import pytest
from src.core.db import Database
from src.core.models import JobStatus, Topic, VideoJob


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_studio.db"
    return Database(db_file)


def test_save_and_get_job(temp_db):
    job = VideoJob(topic=Topic(title="Lừa đảo app vay tiền lãi suất cắt cổ"))
    temp_db.save_job(job)

    fetched = temp_db.get_job(job.id)
    assert fetched is not None
    assert fetched.id == job.id
    assert fetched.topic.title == "Lừa đảo app vay tiền lãi suất cắt cổ"
    assert fetched.status == JobStatus.SCOUTED


def test_list_jobs_and_filter(temp_db):
    j1 = VideoJob(status=JobStatus.SCOUTED, topic=Topic(title="Job 1"))
    j2 = VideoJob(status=JobStatus.SCRIPTED, topic=Topic(title="Job 2"))
    temp_db.save_job(j1)
    temp_db.save_job(j2)

    all_jobs = temp_db.list_jobs()
    assert len(all_jobs) == 2

    scripted_jobs = temp_db.list_jobs(status=JobStatus.SCRIPTED)
    assert len(scripted_jobs) == 1
    assert scripted_jobs[0].id == j2.id


def test_step_and_error_logging(temp_db):
    job = VideoJob(topic=Topic(title="Test logging"))
    temp_db.save_job(job)

    temp_db.log_step(
        job_id=job.id,
        step_name="fact_checker",
        status="COMPLETED",
        input_payload={"topic": "Test"},
        output_payload={"status": "VERIFIED"},
    )
    steps = temp_db.get_job_steps(job.id)
    assert len(steps) == 1
    assert steps[0]["step_name"] == "fact_checker"
    assert steps[0]["status"] == "COMPLETED"

    temp_db.log_error(
        job_id=job.id,
        step_name="renderer",
        error_message="Simulation failure",
        traceback_str="Traceback...",
    )
    with temp_db._get_connection() as conn:
        row = conn.execute("SELECT * FROM error_logs WHERE job_id = ?", (job.id,)).fetchone()
        assert row is not None
        assert row["error_message"] == "Simulation failure"


def test_usage_tracking(temp_db):
    temp_db.record_usage(
        job_id="job_test",
        step_name="story_writer",
        provider="gemini",
        model="gemini-3.8-flash",
        prompt_tokens=500,
        candidate_tokens=1000,
        total_tokens=1500,
        estimated_cost_usd=0.000675,
    )
    usages = temp_db.get_job_usage("job_test")
    assert len(usages) == 1
    assert usages[0]["total_tokens"] == 1500

    totals = temp_db.get_total_usage()
    assert totals["total_requests"] == 1
    assert totals["total_tokens"] == 1500
    assert totals["total_cost_usd"] > 0
