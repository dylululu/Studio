"""Tests for domain models."""
import pytest
from pydantic import ValidationError

from src.core.models import Beat, JobStatus, Script, Source, Topic, VideoJob


def test_source_validation():
    # Valid sources
    s = Source(title="Báo Tuổi Trẻ", url="https://tuoitre.vn/canh-bao-lua-dao")
    assert s.url == "https://tuoitre.vn/canh-bao-lua-dao"

    # Invalid URL scheme
    with pytest.raises(ValidationError):
        Source(title="Nguồn lỗi", url="ftp://invalid.com")


def test_script_validation():
    # Valid script
    script = Script(
        hook="Cảnh báo cuộc gọi lừa đảo!",
        beats=[Beat(text="Kẻ gian giả danh công an", visual_hint="Cảnh sát trừu tượng")],
        checklist=["Bình tĩnh", "Không chuyển tiền", "Báo công an"],
        cta="Hãy theo dõi kênh",
        sources=[Source(title="Bộ Công An", url="https://bocongan.gov.vn")],
    )
    assert len(script.checklist) == 3
    assert len(script.sources) >= 1

    # Checklist must have at least 3 items
    with pytest.raises(ValidationError):
        Script(
            hook="Cảnh báo!",
            beats=[Beat(text="Test", visual_hint="Test")],
            checklist=["Chỉ 1 ý"],
            cta="CTA",
            sources=[Source(title="Nguồn", url="https://example.com")],
        )

    # Sources must have at least 1 item
    with pytest.raises(ValidationError):
        Script(
            hook="Cảnh báo!",
            beats=[Beat(text="Test", visual_hint="Test")],
            checklist=["Ý 1", "Ý 2", "Ý 3"],
            cta="CTA",
            sources=[],
        )


def test_video_job_lifecycle():
    topic = Topic(title="Giả mạo nhân viên điện lực")
    job = VideoJob(topic=topic)
    assert job.status == JobStatus.SCOUTED
    assert job.is_aigc is True

    job.set_status(JobStatus.VERIFIED)
    assert job.status == JobStatus.VERIFIED
    assert "updated_at" in job.timestamps
