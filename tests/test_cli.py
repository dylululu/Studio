"""Tests for Typer CLI commands."""
from typer.testing import CliRunner
import pytest
from src.cli import app

runner = CliRunner()


def test_cli_doctor():
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "Kết quả kiểm tra hệ thống" in result.output
    assert "GEMINI_API_KEY" in result.output
    # Must NOT expose any key
    assert "sk-" not in result.output


def test_cli_run_and_status_and_approval_flow():
    # 1. Run a topic
    run_res = runner.invoke(app, ["run", "--topic", "Thủ đoạn giả mạo mã QR ngân hàng"])
    assert run_res.exit_code == 0
    assert "Job ID:" in run_res.output
    assert "SCRIPTED" in run_res.output

    # Extract job ID
    job_id = None
    for line in run_res.output.splitlines():
        if "Job ID:" in line:
            job_id = line.split("Job ID:")[-1].strip()
            break
    assert job_id is not None

    # 2. Status for specific job
    status_res = runner.invoke(app, ["status", job_id])
    assert status_res.exit_code == 0
    assert job_id in status_res.output
    assert "SCRIPTED" in status_res.output

    # 3. Status list
    list_res = runner.invoke(app, ["status"])
    assert list_res.exit_code == 0
    assert job_id in list_res.output

    # 4. Approve script -> moves to PENDING_REVIEW
    appr_res1 = runner.invoke(app, ["approve", job_id, "--notes", "Duyệt kịch bản"])
    assert appr_res1.exit_code == 0
    assert "PENDING_REVIEW" in appr_res1.output

    # 5. Approve final review -> moves to PUBLISHED
    appr_res2 = runner.invoke(app, ["approve", job_id])
    assert appr_res2.exit_code == 0
    assert "PUBLISHED" in appr_res2.output


def test_cli_reject():
    run_res = runner.invoke(app, ["run", "--topic", "Chủ đề cần huỷ"])
    assert run_res.exit_code == 0
    job_id = None
    for line in run_res.output.splitlines():
        if "Job ID:" in line:
            job_id = line.split("Job ID:")[-1].strip()
            break

    rej_res = runner.invoke(app, ["reject", job_id, "--reason", "Nội dung trùng lặp"])
    assert rej_res.exit_code == 0
    assert "REJECTED" in rej_res.output
