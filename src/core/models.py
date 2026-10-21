"""Domain models for Scam-Alert Studio pipeline."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


class JobStatus(str, Enum):
    """Lifecycle statuses for a VideoJob."""
    SCOUTED = "SCOUTED"
    VERIFIED = "VERIFIED"
    SCRIPTED = "SCRIPTED"
    TEXT_APPROVED = "TEXT_APPROVED"
    RENDERED = "RENDERED"
    QA_PASSED = "QA_PASSED"
    PENDING_REVIEW = "PENDING_REVIEW"
    PUBLISHED = "PUBLISHED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class Source(BaseModel):
    """Verified news or authority source for scam investigation."""
    title: str = Field(..., description="Tên cơ quan, tổ chức báo chí hoặc tiêu đề bài viết")
    url: str = Field(..., description="Đường dẫn kiểm chứng trực tiếp")

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v = v.strip()
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("Source URL must start with http:// or https://")
        return v


class Beat(BaseModel):
    """Story beat / narration segment for short-form video (30-60s)."""
    text: str = Field(..., description="Nội dung lời đọc giọng kể điều tra")
    visual_hint: str = Field(..., description="Gợi ý hình ảnh minh họa trừu tượng/đồ họa")


class Script(BaseModel):
    """Script structure complying with anti-scam studio guidelines."""
    hook: str = Field(..., description="Câu mở đầu gây chú ý 3-5s đầu")
    beats: List[Beat] = Field(..., min_length=1, description="Các phân cảnh kể chuyện")
    checklist: List[str] = Field(
        ...,
        min_length=3,
        description="Checklist ≥3 dấu hiệu nhận biết hoặc biện pháp phòng tránh",
    )
    cta: str = Field(..., description="Lời kêu gọi hành động bảo vệ bản thân / tố giác")
    sources: List[Source] = Field(
        ...,
        min_length=1,
        description="Bắt buộc có ≥1 nguồn kiểm chứng theo quy định",
    )
    risk_flags: List[str] = Field(
        default_factory=list,
        description="Cảnh báo rủi ro nội dung nếu phát hiện yếu tố nhạy cảm",
    )


class Topic(BaseModel):
    """Scam topic identified for video production."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    title: str = Field(..., description="Tiêu đề vụ việc lừa đảo")
    summary: str = Field(default="", description="Tóm tắt thủ đoạn lừa đảo")
    scam_type: str = Field(default="deepfake_fraud", description="Phân loại hình thức lừa đảo")
    target_audience: str = Field(default="general", description="Đối tượng dễ bị nhắm tới")
    sources: List[Source] = Field(default_factory=list, description="Nguồn tin tức ban đầu")


def current_iso_time() -> str:
    return datetime.now(timezone.utc).isoformat()


class VideoJob(BaseModel):
    """Main unit of work processed by orchestrator across agents."""
    id: str = Field(default_factory=lambda: f"job_{uuid.uuid4().hex[:10]}")
    status: JobStatus = Field(default=JobStatus.SCOUTED)
    topic: Optional[Topic] = None
    script: Optional[Script] = None
    paths: Dict[str, str] = Field(default_factory=dict)
    timestamps: Dict[str, str] = Field(default_factory=lambda: {"created_at": current_iso_time()})
    is_aigc: bool = Field(default=True, description="Đánh dấu nội dung AI theo quy định TikTok")
    error_message: Optional[str] = None
    approval_notes: Optional[str] = None

    def mark_updated(self) -> None:
        self.timestamps["updated_at"] = current_iso_time()

    def set_status(self, new_status: JobStatus, note: Optional[str] = None) -> None:
        self.status = new_status
        self.mark_updated()
        if note:
            self.approval_notes = note
