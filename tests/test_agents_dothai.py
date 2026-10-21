"""Tests cho 4 agent Đợt 2: TrendScout, FactChecker, StoryWriter, ComplianceGuard."""
import json
import os
import pytest

os.environ["STUDIO_ENV"] = "test"

from src.providers.base import MockLLMProvider
from src.core.models import Beat, JobStatus, Script, Source, Topic, VideoJob


# ═══════════════════════════════════════════════════════════════════
# TrendScout
# ═══════════════════════════════════════════════════════════════════

class TestTrendScoutAgent:
    def test_run_returns_topics(self):
        from src.agents.trend_scout import TrendScoutAgent
        agent = TrendScoutAgent(llm=MockLLMProvider())
        topics = agent.run(top_n=3)
        assert isinstance(topics, list)
        assert len(topics) >= 1
        assert topics[0].title

    def test_run_respects_top_n(self):
        """MockLLM trả 1 topic → kết quả ≤ top_n."""
        from src.agents.trend_scout import TrendScoutAgent
        agent = TrendScoutAgent(llm=MockLLMProvider())
        topics = agent.run(top_n=5)
        assert len(topics) <= 5

    def test_extra_headlines_accepted(self):
        from src.agents.trend_scout import TrendScoutAgent, Headline
        agent = TrendScoutAgent(llm=MockLLMProvider())
        custom = [Headline(title="Test lừa đảo", url="https://example.com", source="Test")]
        topics = agent.run(extra_headlines=custom)
        assert isinstance(topics, list)

    def test_sources_yaml_missing_uses_mock_headlines(self, tmp_path):
        from src.agents.trend_scout import TrendScoutAgent
        agent = TrendScoutAgent(
            llm=MockLLMProvider(),
            sources_path=tmp_path / "nonexistent.yaml",
        )
        topics = agent.run()
        assert isinstance(topics, list)


# ═══════════════════════════════════════════════════════════════════
# FactChecker
# ═══════════════════════════════════════════════════════════════════

class TestFactCheckerAgent:
    def _make_job(self, has_sources: bool = True) -> VideoJob:
        sources = [Source(title="Mock Source", url="https://mock.example.com")] if has_sources else []
        return VideoJob(
            status=JobStatus.SCOUTED,
            topic=Topic(
                title="Lừa đảo Deepfake giọng nói",
                summary="Kẻ gian clone giọng để tống tiền.",
                sources=sources,
            ),
        )

    def test_verified_happy_path(self):
        from src.agents.fact_checker import FactCheckerAgent
        agent = FactCheckerAgent(llm=MockLLMProvider(), check_urls=False)
        job = agent.run(self._make_job())
        assert job.status == JobStatus.VERIFIED
        assert job.topic.sources

    def test_rejected_when_llm_returns_rejected(self):
        """Mock LLM trả REJECTED."""
        from src.agents.fact_checker import FactCheckerAgent, FactOutput

        class RejectLLM(MockLLMProvider):
            def generate_json(self, prompt, schema, tier="fast", system_instruction=None):
                if schema.__name__ == "FactOutput":
                    return FactOutput(status="REJECTED", reason="Không tìm thấy nguồn tin cậy.")
                return super().generate_json(prompt, schema, tier, system_instruction)

        agent = FactCheckerAgent(llm=RejectLLM(), check_urls=False)
        job = agent.run(self._make_job())
        assert job.status == JobStatus.REJECTED
        assert "Không tìm thấy" in job.error_message

    def test_missing_topic_raises(self):
        from src.agents.fact_checker import FactCheckerAgent
        agent = FactCheckerAgent(llm=MockLLMProvider(), check_urls=False)
        with pytest.raises(ValueError, match="missing"):
            agent.run(VideoJob())

    def test_facts_stored_in_paths(self):
        from src.agents.fact_checker import FactCheckerAgent
        agent = FactCheckerAgent(llm=MockLLMProvider(), check_urls=False)
        job = agent.run(self._make_job())
        assert "_facts_json" in job.paths
        data = json.loads(job.paths["_facts_json"])
        assert "facts" in data


# ═══════════════════════════════════════════════════════════════════
# StoryWriter
# ═══════════════════════════════════════════════════════════════════

class TestStoryWriterAgent:
    def _make_verified_job(self) -> VideoJob:
        from src.agents.fact_checker import FactCheckerAgent
        job = VideoJob(
            status=JobStatus.SCOUTED,
            topic=Topic(
                title="Lừa đảo Deepfake giọng nói",
                summary="Clone giọng rồi tống tiền.",
                sources=[Source(title="AIS", url="https://ais.gov.vn/mock")],
            ),
        )
        agent = FactCheckerAgent(llm=MockLLMProvider(), check_urls=False)
        return agent.run(job)

    def test_creates_script_variant_a(self):
        from src.agents.story_writer import StoryWriterAgent
        job = self._make_verified_job()
        agent = StoryWriterAgent(llm=MockLLMProvider(), variant="A")
        job = agent.run(job)
        assert job.status == JobStatus.SCRIPTED
        assert job.script is not None
        assert job.script.hook
        assert len(job.script.beats) >= 1
        assert len(job.script.checklist) >= 3
        assert job.script.cta

    def test_creates_script_variant_b(self):
        from src.agents.story_writer import StoryWriterAgent
        job = self._make_verified_job()
        agent = StoryWriterAgent(llm=MockLLMProvider(), variant="B")
        job = agent.run(job)
        assert job.status == JobStatus.SCRIPTED

    def test_raises_without_topic(self):
        from src.agents.story_writer import StoryWriterAgent
        agent = StoryWriterAgent(llm=MockLLMProvider())
        with pytest.raises(ValueError, match="missing"):
            agent.run(VideoJob())

    def test_raises_without_sources(self):
        from src.agents.story_writer import StoryWriterAgent
        job = VideoJob(
            status=JobStatus.VERIFIED,
            topic=Topic(title="Test", sources=[]),
        )
        agent = StoryWriterAgent(llm=MockLLMProvider())
        with pytest.raises(ValueError, match="nguồn"):
            agent.run(job)


# ═══════════════════════════════════════════════════════════════════
# ComplianceGuard
# ═══════════════════════════════════════════════════════════════════

class TestComplianceGuardAgent:
    def _make_scripted_job(self) -> VideoJob:
        """Job đã có script hợp lệ."""
        from src.agents.fact_checker import FactCheckerAgent
        from src.agents.story_writer import StoryWriterAgent

        llm = MockLLMProvider()
        job = VideoJob(
            status=JobStatus.SCOUTED,
            topic=Topic(
                title="Lừa đảo Deepfake",
                summary="Clone giọng.",
                sources=[Source(title="AIS", url="https://ais.gov.vn/mock")],
            ),
        )
        job = FactCheckerAgent(llm=llm, check_urls=False).run(job)
        job = StoryWriterAgent(llm=llm).run(job)
        return job

    def test_passes_valid_script(self):
        from src.agents.compliance_guard import ComplianceGuardAgent
        job = self._make_scripted_job()
        agent = ComplianceGuardAgent(llm=MockLLMProvider())
        job = agent.run(job)
        assert job.status == JobStatus.QA_PASSED

    def test_rejected_after_max_revisions(self):
        """Mock ComplianceOutput luôn vi phạm → REJECTED sau 2 vòng."""
        from src.agents.compliance_guard import ComplianceGuardAgent, ComplianceOutput, Violation

        class AlwaysFailLLM(MockLLMProvider):
            def generate_json(self, prompt, schema, tier="fast", system_instruction=None):
                if schema.__name__ == "ComplianceOutput":
                    return ComplianceOutput(
                        passed=False,
                        violations=[Violation(rule="no_how_to", detail="Có hướng dẫn lừa đảo.")],
                    )
                return super().generate_json(prompt, schema, tier, system_instruction)

        job = self._make_scripted_job()
        # Writer cũng dùng Mock nên sửa vẫn giữ nguyên vi phạm
        agent = ComplianceGuardAgent(llm=AlwaysFailLLM(), writer_agent=None)
        job = agent.run(job)
        assert job.status == JobStatus.REJECTED
        assert job.error_message

    def test_raises_without_script(self):
        from src.agents.compliance_guard import ComplianceGuardAgent
        agent = ComplianceGuardAgent(llm=MockLLMProvider())
        with pytest.raises(ValueError, match="missing"):
            agent.run(VideoJob())

    def test_revision_loop_with_writer(self):
        """Sau 1 lần fail, writer sửa, lần 2 pass → QA_PASSED."""
        from src.agents.compliance_guard import ComplianceGuardAgent, ComplianceOutput, Violation

        call_count = {"n": 0}

        class OneFailLLM(MockLLMProvider):
            def generate_json(self, prompt, schema, tier="fast", system_instruction=None):
                if schema.__name__ == "ComplianceOutput":
                    call_count["n"] += 1
                    if call_count["n"] == 1:
                        return ComplianceOutput(
                            passed=False,
                            violations=[Violation(rule="no_victim_info", detail="Có tên nạn nhân.")],
                        )
                    return ComplianceOutput(passed=True, violations=[])
                return super().generate_json(prompt, schema, tier, system_instruction)

        from src.agents.story_writer import StoryWriterAgent
        job = self._make_scripted_job()
        writer = StoryWriterAgent(llm=MockLLMProvider())
        agent = ComplianceGuardAgent(llm=OneFailLLM(), writer_agent=writer)
        job = agent.run(job)
        assert job.status == JobStatus.QA_PASSED
        assert call_count["n"] == 2


# ═══════════════════════════════════════════════════════════════════
# Integration: Full pipeline Scout→Fact→Story→Compliance
# ═══════════════════════════════════════════════════════════════════

class TestFullPipeline:
    def test_full_script_pipeline_mock(self):
        """Chạy toàn bộ pipeline Đợt 2 với MockLLM, không cần mạng."""
        from src.agents.trend_scout import TrendScoutAgent
        from src.agents.fact_checker import FactCheckerAgent
        from src.agents.story_writer import StoryWriterAgent
        from src.agents.compliance_guard import ComplianceGuardAgent

        llm = MockLLMProvider()

        # 1. Scout
        scout = TrendScoutAgent(llm=llm)
        topics = scout.run(top_n=1)
        assert topics

        # 2. FactChecker
        job = VideoJob(status=JobStatus.SCOUTED, topic=topics[0])
        job = FactCheckerAgent(llm=llm, check_urls=False).run(job)
        assert job.status == JobStatus.VERIFIED

        # 3. StoryWriter
        job = StoryWriterAgent(llm=llm, variant="A").run(job)
        assert job.status == JobStatus.SCRIPTED
        assert job.script

        # 4. ComplianceGuard
        job = ComplianceGuardAgent(llm=llm).run(job)
        assert job.status == JobStatus.QA_PASSED
        assert job.script.sources
