"""Abstract base classes and mock implementations for studio providers."""
from __future__ import annotations

import io
import os
import wave
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Type, TypeVar

from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel

from src.core.models import Beat, Script, Source, Topic, VideoJob

T = TypeVar("T", bound=BaseModel)


class LLMUsage(BaseModel):
    """Token consumption and estimated cost."""
    provider: str
    model: str
    prompt_tokens: int = 0
    candidate_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0


class LLMProvider(ABC):
    """Interface for LLM text and structured JSON generation."""

    def __init__(self) -> None:
        self.last_usage: Optional[LLMUsage] = None

    @abstractmethod
    def generate_json(
        self,
        prompt: str,
        schema: Type[T],
        tier: str = "fast",
        system_instruction: Optional[str] = None,
    ) -> T:
        """Generate structured JSON conforming to the given Pydantic schema."""
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """Verify connectivity and credentials."""
        pass


class TTSProvider(ABC):
    """Interface for Text-to-Speech audio synthesis."""

    @abstractmethod
    def synthesize(
        self,
        text: str,
        output_path: str,
        voice: Optional[str] = None,
        language: str = "vi",
    ) -> str:
        """Synthesize text into speech file and return the saved path."""
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """Verify connectivity and credentials."""
        pass


class ImageProvider(ABC):
    """Interface for Image Generation."""

    @abstractmethod
    def generate_image(
        self,
        prompt: str,
        output_path: str,
        aspect_ratio: str = "9:16",
    ) -> str:
        """Generate an image from prompt and save to output_path."""
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """Verify connectivity and credentials."""
        pass


class PublisherProvider(ABC):
    """Interface for publishing videos."""

    @abstractmethod
    def publish(self, job: VideoJob) -> Dict[str, Any]:
        """Publish the rendered video to platform."""
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """Verify credentials and platform status."""
        pass


# =====================================================================
# MOCK IMPLEMENTATIONS (for local offline testing and CI/CD)
# =====================================================================


class MockLLMProvider(LLMProvider):
    """Mock LLM that generates valid synthetic Pydantic models."""

    def __init__(self, should_fail: bool = False) -> None:
        super().__init__()
        self.should_fail = should_fail

    def generate_json(
        self,
        prompt: str,
        schema: Type[T],
        tier: str = "fast",
        system_instruction: Optional[str] = None,
    ) -> T:
        if self.should_fail:
            raise RuntimeError("MockLLMProvider simulated failure")

        self.last_usage = LLMUsage(
            provider="mock",
            model=f"mock-{tier}",
            prompt_tokens=120,
            candidate_tokens=180,
            total_tokens=300,
            estimated_cost_usd=0.0001,
        )

        if issubclass(schema, Script):
            mock_script = Script(
                hook="Cảnh báo: Thủ đoạn Deepfake giả giọng người thân đang bùng nổ!",
                beats=[
                    Beat(
                        text="Kẻ gian thu thập mẫu giọng nạn nhân từ mạng xã hội để tạo giọng nhân tạo hoàn hảo.",
                        visual_hint="Đồ họa trừu tượng sóng âm thanh biến đổi thành mã nhị phân màu đỏ cảnh báo.",
                    ),
                    Beat(
                        text="Chúng gọi điện cho người thân trong tình huống khẩn cấp, yêu cầu chuyển tiền tức thời.",
                        visual_hint="Hoạt họa chiếc điện thoại rung chuông trong bóng tối, đồng hồ đếm ngược.",
                    ),
                    Beat(
                        text="Nhiều nạn nhân hoảng loạn chuyển khoản trước khi kịp gọi lại kiểm tra số gốc.",
                        visual_hint="Biểu tượng chuyển khoản ngân hàng cùng dấu chấm hỏi lớn.",
                    ),
                ],
                checklist=[
                    "Bình tĩnh dập máy và gọi lại số điện thoại cá nhân thông thường của người thân.",
                    "Hỏi một câu hỏi bí mật hoặc kỷ niệm chỉ hai người biết.",
                    "Tuyệt đối không chuyển tiền vào tài khoản người lạ đứng tên.",
                ],
                cta="Hãy chia sẻ video này để bảo vệ người thân và bấm theo dõi kênh Cảnh Báo Lừa Đảo!",
                sources=[
                    Source(
                        title="Cục An toàn thông tin - Bộ Thông tin và Truyền thông",
                        url="https://ais.gov.vn/canh-bao-deepfake-lua-dao",
                    )
                ],
                risk_flags=[],
            )
            return mock_script  # type: ignore

        if issubclass(schema, Topic):
            mock_topic = Topic(
                title="Lừa đảo Deepfake voice clone mạo danh chuyển tiền",
                summary="Kẻ lừa đảo sử dụng AI bắt chước giọng nói người thân để tống tiền.",
                scam_type="deepfake_voice_fraud",
                target_audience="Phụ huynh, người lớn tuổi",
                sources=[
                    Source(
                        title="Báo Tuổi Trẻ - Cảnh giác thủ đoạn lừa đảo tinh vi",
                        url="https://tuoitre.vn/canh-giac-lua-dao-ai",
                    )
                ],
            )
            return mock_topic  # type: ignore

        # ── Đợt 2: Schema của các agent mới ─────────────────────────────────
        schema_name = schema.__name__

        if schema_name == "ScoutOutput":
            from src.agents.trend_scout import ScoredTopic, ScoutOutput
            return ScoutOutput(topics=[
                ScoredTopic(
                    title="Lừa đảo Deepfake giả giọng người thân đòi tiền khẩn cấp",
                    summary="Kẻ gian clone giọng nói bằng AI rồi giả vờ người thân gọi xin tiền gấp.",
                    scam_type="deepfake",
                    target_audience="Người lớn tuổi, phụ huynh",
                    score=9.2,
                    sources=[Source(title="Cục An toàn thông tin", url="https://ais.gov.vn/mock")],
                )
            ])  # type: ignore

        if schema_name == "FactOutput":
            from src.agents.fact_checker import FactEvent, FactOutput
            return FactOutput(
                status="VERIFIED",
                reason="",
                facts=[
                    FactEvent(
                        event="Công an TP.HCM ghi nhận 47 vụ lừa đảo deepfake giọng nói trong Q3/2026.",
                        source_title="Báo VnExpress",
                        source_url="https://vnexpress.net/mock-fact",
                    ),
                    FactEvent(
                        event="Nạn nhân trung bình mất 85 triệu đồng mỗi vụ theo thống kê Bộ Công an.",
                        source_title="Cục An toàn thông tin",
                        source_url="https://ais.gov.vn/mock-fact",
                    ),
                    FactEvent(
                        event="Kẻ gian chỉ cần 3 giây mẫu giọng từ mạng xã hội để tạo bản clone.",
                        source_title="Báo Tuổi Trẻ",
                        source_url="https://tuoitre.vn/mock-fact",
                    ),
                ],
                verified_sources=[
                    Source(title="Báo VnExpress", url="https://vnexpress.net/mock-fact"),
                    Source(title="Cục An toàn thông tin", url="https://ais.gov.vn/mock-fact"),
                ],
            )  # type: ignore

        if schema_name == "WriterOutput":
            from src.agents.story_writer import WriterOutput
            return WriterOutput(
                hook="47 người mất hết tiền tiết kiệm chỉ vì một cuộc gọi — giọng người thân họ!",
                beats=[
                    Beat(
                        text="Kẻ gian thu thập 3 giây giọng nói từ video mạng xã hội, dùng AI clone hoàn hảo.",
                        visual_hint="Sóng âm thanh biến thành mã nhị phân đỏ trên nền tối.",
                    ),
                    Beat(
                        text="Chúng gọi điện: 'Con bị tai nạn, cần chuyển tiền gấp!' — chính xác giọng người thân bạn.",
                        visual_hint="Điện thoại rung trong bóng tối, đồng hồ đếm ngược màu đỏ.",
                    ),
                    Beat(
                        text="Twist: AI chỉ cần 3 giây mẫu — ai đăng video nói chuyện đều có thể là nạn nhân tiếp theo.",
                        visual_hint="Vòng tròn kết nối mạng xã hội thu nhỏ thành mục tiêu.",
                    ),
                ],
                checklist=[
                    "Gọi lại trực tiếp số điện thoại quen thuộc của người thân.",
                    "Hỏi câu hỏi bí mật chỉ hai người biết.",
                    "Tuyệt đối không chuyển tiền vào tài khoản người lạ.",
                ],
                cta="Gửi ngay video này cho bố mẹ để bảo vệ họ khỏi bẫy AI!",
                sources=[Source(title="Cục An toàn thông tin", url="https://ais.gov.vn/mock")],
                risk_flags=[],
            )  # type: ignore

        if schema_name == "ComplianceOutput":
            from src.agents.compliance_guard import ComplianceOutput
            return ComplianceOutput(passed=True, violations=[])  # type: ignore

        # Fallback to default model creation if fields allow
        try:
            return schema.model_validate({})
        except Exception:
            # Construct minimal dummy fields if needed
            data: Dict[str, Any] = {}
            for field_name, field_info in schema.model_fields.items():
                if field_info.is_required():
                    data[field_name] = f"mock_{field_name}"
            return schema.model_validate(data)

    def health_check(self) -> bool:
        return not self.should_fail


class MockTTSProvider(TTSProvider):
    """Mock TTS that generates a valid silent WAV file."""

    def __init__(self, should_fail: bool = False) -> None:
        self.should_fail = should_fail

    def synthesize(
        self,
        text: str,
        output_path: str,
        voice: Optional[str] = None,
        language: str = "vi",
    ) -> str:
        if self.should_fail:
            raise RuntimeError("MockTTSProvider simulated failure")

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Generate a minimal 1-second 16-bit 16kHz mono silent WAV file
        sample_rate = 16000
        duration_sec = 1
        num_frames = sample_rate * duration_sec
        with wave.open(str(path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(b"\x00\x00" * num_frames)

        return str(path)

    def health_check(self) -> bool:
        return not self.should_fail


class MockImageProvider(ImageProvider):
    """Mock ImageProvider that produces a valid vertical 9:16 PNG using Pillow."""

    def __init__(self, should_fail: bool = False) -> None:
        self.should_fail = should_fail

    def generate_image(
        self,
        prompt: str,
        output_path: str,
        aspect_ratio: str = "9:16",
    ) -> str:
        if self.should_fail:
            raise RuntimeError("MockImageProvider simulated failure")

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        # 9:16 aspect ratio: 540x960
        img = Image.new("RGB", (540, 960), color=(18, 24, 38))
        draw = ImageDraw.Draw(img)
        # Draw some abstract geometric frames
        draw.rectangle([20, 20, 520, 940], outline=(220, 38, 38), width=4)
        draw.text((40, 60), "[SCAM ALERT STUDIO]", fill=(255, 255, 255))
        draw.text((40, 100), "MOCK ABSTRACT VISUAL", fill=(234, 179, 8))
        # Draw shortened prompt info
        clean_prompt = prompt[:80] + ("..." if len(prompt) > 80 else "")
        draw.text((40, 160), f"Prompt: {clean_prompt}", fill=(156, 163, 175))

        img.save(str(path), format="PNG")
        return str(path)

    def health_check(self) -> bool:
        return not self.should_fail


class MockPublisherProvider(PublisherProvider):
    """Mock Publisher that simulates publishing to TikTok."""

    def __init__(self, should_fail: bool = False) -> None:
        self.should_fail = should_fail

    def publish(self, job: VideoJob) -> Dict[str, Any]:
        if self.should_fail:
            raise RuntimeError("MockPublisherProvider simulated failure")

        return {
            "published": True,
            "platform": "tiktok_mock",
            "post_id": f"mock_tt_{job.id}",
            "url": f"https://tiktok.com/@scam_alert_studio/video/{job.id}",
            "is_aigc": job.is_aigc,
        }

    def health_check(self) -> bool:
        return not self.should_fail
