"""Tests for studio providers (Mock & Gemini adapters)."""
import os
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from PIL import Image

from src.core.models import Script, Topic, VideoJob
from src.providers.base import (
    MockImageProvider,
    MockLLMProvider,
    MockPublisherProvider,
    MockTTSProvider,
)
from src.providers.gemini_llm import GeminiLLMProvider
from src.providers.gemini_tts import GeminiTTSProvider
from src.providers.gemini_image import GeminiImageProvider


def test_mock_llm_provider():
    llm = MockLLMProvider()
    assert llm.health_check() is True

    # Generate Script
    script = llm.generate_json("Tạo kịch bản", Script, tier="smart")
    assert isinstance(script, Script)
    assert len(script.checklist) >= 3
    assert len(script.sources) >= 1
    assert llm.last_usage is not None
    assert llm.last_usage.total_tokens > 0

    # Generate Topic
    topic = llm.generate_json("Tìm chủ đề", Topic, tier="fast")
    assert isinstance(topic, Topic)
    assert topic.title != ""


def test_mock_tts_provider(tmp_path):
    tts = MockTTSProvider()
    assert tts.health_check() is True

    out_file = tmp_path / "test_audio.wav"
    result_path = tts.synthesize("Xin chào khán giả", str(out_file))
    assert Path(result_path).exists()
    assert Path(result_path).stat().st_size > 0


def test_mock_image_provider(tmp_path):
    img_prov = MockImageProvider()
    assert img_prov.health_check() is True

    out_file = tmp_path / "test_img.png"
    result_path = img_prov.generate_image("Abstract scene", str(out_file), aspect_ratio="9:16")
    assert Path(result_path).exists()

    with Image.open(result_path) as im:
        assert im.size == (540, 960)  # 9:16 vertical ratio


def test_pillow_graphics_provider(tmp_path):
    from src.providers.pillow_graphics import PillowGraphicsProvider
    provider = PillowGraphicsProvider()
    assert provider.health_check() is True

    out_file = tmp_path / "test_pillow.png"
    result_path = provider.generate_image("Thủ đoạn giả mạo công an qua video call", str(out_file))
    assert Path(result_path).exists()

    with Image.open(result_path) as im:
        assert im.size == (1080, 1920)  # Standard 1080x1920 TikTok vertical canvas


def test_mock_publisher_provider():
    pub = MockPublisherProvider()
    assert pub.health_check() is True

    job = VideoJob(id="job_unit_test")
    res = pub.publish(job)
    assert res["published"] is True
    assert "mock_tt_job_unit_test" in res["post_id"]


def test_gemini_llm_retry_on_invalid_json():
    # Test that GeminiLLMProvider retries once on parse failure
    provider = GeminiLLMProvider()
    provider.client = MagicMock()

    # Create mock interaction with invalid json on first call, valid on second
    mock_bad_resp = MagicMock()
    mock_bad_resp.output_text = "This is not json"
    mock_bad_resp.usage = MagicMock(prompt_tokens=10, candidate_tokens=20, total_tokens=30)

    valid_script = MockLLMProvider().generate_json("test", Script).model_dump_json()
    mock_good_resp = MagicMock()
    mock_good_resp.output_text = valid_script
    mock_good_resp.usage = MagicMock(prompt_tokens=10, candidate_tokens=50, total_tokens=60)

    provider.client.interactions.create.side_effect = [mock_bad_resp, mock_good_resp]
    res = provider.generate_json("Prompt", Script)
    assert isinstance(res, Script)
    assert provider.client.interactions.create.call_count == 2
    assert provider.last_usage is not None
    assert provider.last_usage.total_tokens == 60
