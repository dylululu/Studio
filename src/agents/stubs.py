"""Default stub agents for the orchestrator pipeline."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from src.core.models import Beat, JobStatus, Script, Source, VideoJob
from src.providers import (
    ImageProvider,
    LLMProvider,
    PublisherProvider,
    TTSProvider,
    get_image_provider,
    get_llm_provider,
    get_publisher_provider,
    get_tts_provider,
)

logger = logging.getLogger(__name__)


class FactCheckerStubAgent:
    """Agent validating sources and facts against official authorities."""

    def __init__(self, llm: Optional[LLMProvider] = None) -> None:
        self.llm = llm or get_llm_provider()

    def run(self, job: VideoJob) -> VideoJob:
        logger.info(f"FactChecker running for job {job.id}")
        # Validate that topic exists
        if not job.topic:
            raise ValueError("Job topic is missing")

        # In stub mode, ensure at least 1 verified source exists
        if not job.topic.sources:
            job.topic.sources.append(
                Source(
                    title="Cục An toàn thông tin - Bộ Thông tin & Truyền thông",
                    url="https://ais.gov.vn/canh-bao-lua-dao-moi-nhat",
                )
            )

        job.status = JobStatus.VERIFIED
        job.mark_updated()
        return job


class StoryWriterStubAgent:
    """Agent producing structured 30-60s script."""

    def __init__(self, llm: Optional[LLMProvider] = None) -> None:
        self.llm = llm or get_llm_provider()

    def run(self, job: VideoJob) -> VideoJob:
        logger.info(f"StoryWriter running for job {job.id}")
        if not job.topic or not job.topic.sources:
            raise ValueError("Cannot write script without verified topic and sources")

        prompt = f"Viết kịch bản video cảnh báo lừa đảo 30-60s về chủ đề: {job.topic.title}."
        script = self.llm.generate_json(prompt=prompt, schema=Script, tier="smart")

        # Ensure verified sources from topic are propagated if script had default ones
        if not script.sources and job.topic.sources:
            script.sources = job.topic.sources

        job.script = script
        job.status = JobStatus.SCRIPTED
        job.mark_updated()
        return job


class RenderStubAgent:
    """Agent generating TTS speech and abstract visual illustrations."""

    def __init__(
        self,
        tts: Optional[TTSProvider] = None,
        image_provider: Optional[ImageProvider] = None,
    ) -> None:
        self.tts = tts or get_tts_provider()
        self.image_provider = image_provider or get_image_provider()

    def run(self, job: VideoJob) -> VideoJob:
        logger.info(f"RenderAgent running for job {job.id}")
        if not job.script:
            raise ValueError("Script is missing before rendering")

        base_dir = Path("data") / "output" / job.id
        base_dir.mkdir(parents=True, exist_ok=True)

        # 1. Synthesize audio
        narration_text = f"{job.script.hook} {' '.join(b.text for b in job.script.beats)} {job.script.cta}"
        audio_path = str(base_dir / "narration.wav")
        saved_audio = self.tts.synthesize(text=narration_text, output_path=audio_path)
        job.paths["audio"] = saved_audio

        # 2. Generate abstract cover image
        image_prompt = (
            f"Abstract investigative graphic for scam: {job.topic.title if job.topic else 'Phishing Scam'}. "
            f"Visual hint: {job.script.beats[0].visual_hint if job.script.beats else 'Cyber warning alert'}"
        )
        img_path = str(base_dir / "scene_1.png")
        saved_img = self.image_provider.generate_image(prompt=image_prompt, output_path=img_path)
        job.paths["cover_image"] = saved_img
        job.paths["video_stub"] = str(base_dir / "final_video_stub.mp4")

        job.status = JobStatus.RENDERED
        job.mark_updated()
        return job


class QAStubAgent:
    """Agent checking compliance: sources ≥ 1, checklist ≥ 3, AI flag."""

    def run(self, job: VideoJob) -> VideoJob:
        logger.info(f"QAAgent running for job {job.id}")
        if not job.script:
            raise ValueError("Job script is missing for QA check")

        # Rule 1: At least 1 verified source
        if len(job.script.sources) < 1:
            raise ValueError("Compliance failed: Script must have at least 1 verified source")

        # Rule 2: At least 3 checklist items
        if len(job.script.checklist) < 3:
            raise ValueError("Compliance failed: Checklist must have at least 3 prevention items")

        # Rule 3: Must be flagged as AIGC
        if not job.is_aigc:
            raise ValueError("Compliance failed: Content must be flagged as AI-generated (is_aigc=true)")

        job.status = JobStatus.QA_PASSED
        job.mark_updated()
        return job


class PublisherStubAgent:
    """Agent publishing video to platform."""

    def __init__(self, publisher: Optional[PublisherProvider] = None) -> None:
        self.publisher = publisher or get_publisher_provider()

    def run(self, job: VideoJob) -> VideoJob:
        logger.info(f"Publisher running for job {job.id}")
        result = self.publisher.publish(job)
        job.paths["platform_url"] = result.get("url", "")
        job.status = JobStatus.PUBLISHED
        job.mark_updated()
        return job
