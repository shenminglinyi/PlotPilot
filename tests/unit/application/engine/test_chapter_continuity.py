import asyncio

import pytest

from application.engine.services.chapter_aftermath_pipeline import ChapterAftermathPipeline
from application.engine.services.chapter_bridge_service import (
    ChapterContinuityPolicy,
    ContinuityCheckResult,
)


def test_continuity_policy_separates_warning_from_auto_fix():
    policy = ChapterContinuityPolicy(warn_threshold=0.6, auto_fix_threshold=0.4)

    assert policy.needs_attention(0.59) is True
    assert policy.should_auto_fix(0.59) is False
    assert policy.should_auto_fix(0.39) is True


def test_bridge_service_uses_policy_for_opening_fix():
    from application.engine.services.chapter_bridge_service import ChapterBridgeService

    service = ChapterBridgeService(
        policy=ChapterContinuityPolicy(warn_threshold=0.6, auto_fix_threshold=0.45)
    )

    assert service.should_auto_fix_opening(ContinuityCheckResult(score=0.46)) is False
    assert service.should_auto_fix_opening(ContinuityCheckResult(score=0.44)) is True


@pytest.mark.asyncio
async def test_aftermath_extracts_bridge_through_unified_port(monkeypatch):
    calls = []

    class FakeBridgeService:
        def __init__(self, llm_service=None, db_path=None):
            self.llm_service = llm_service
            self.db_path = db_path

        async def extract_bridge(self, novel_id, chapter_number, content):
            calls.append((novel_id, chapter_number, content, self.llm_service, self.db_path))

    monkeypatch.setattr(
        "application.engine.services.chapter_bridge_service.ChapterBridgeService",
        FakeBridgeService,
    )
    monkeypatch.setattr("application.paths.get_db_path", lambda: "continuity.db")

    pipeline = ChapterAftermathPipeline(
        knowledge_service=None,
        chapter_indexing_service=None,
        llm_service=object(),
    )

    await pipeline._extract_chapter_bridge("novel-1", 7, "正文内容")

    assert len(calls) == 1
    assert calls[0][0:3] == ("novel-1", 7, "正文内容")
    assert calls[0][4] == "continuity.db"


@pytest.mark.asyncio
async def test_aftermath_defers_auxiliary_stages(monkeypatch):
    started = []
    release = asyncio.Event()

    async def fake_bridge(self, novel_id, chapter_number, content):
        return None

    async def fake_sync(*args, **kwargs):
        return {
            "vector_stored": True,
            "foreshadow_stored": True,
            "triples_extracted": True,
            "causal_edges_stored": False,
            "character_mutations_stored": False,
            "debt_updated": False,
            "tension_composite": 61.0,
        }

    async def fake_auxiliary(self, novel_id, chapter_number, content, evidence):
        started.append((novel_id, chapter_number, evidence["tension_composite"]))
        await release.wait()

    monkeypatch.setattr(ChapterAftermathPipeline, "_extract_chapter_bridge", fake_bridge)
    monkeypatch.setattr(
        "application.world.services.chapter_narrative_sync.sync_chapter_narrative_after_save",
        fake_sync,
    )
    monkeypatch.setattr(ChapterAftermathPipeline, "_run_auxiliary_stages", fake_auxiliary)

    pipeline = ChapterAftermathPipeline(
        knowledge_service=None,
        chapter_indexing_service=None,
        llm_service=object(),
    )

    result = await pipeline.run_after_chapter_saved("novel-1", 7, "正文内容")

    assert result["tension_composite"] == 61.0
    assert result["auxiliary_deferred"] is True
    await asyncio.sleep(0)
    assert started == [("novel-1", 7, 61.0)]

    release.set()
    await pipeline.drain_auxiliary_stages()


@pytest.mark.asyncio
async def test_aftermath_reuses_precomputed_voice_result(monkeypatch):
    async def fake_bridge(self, novel_id, chapter_number, content):
        return None

    async def fake_sync(*args, **kwargs):
        return {"tension_composite": 68.0}

    async def fake_auxiliary(self, novel_id, chapter_number, content, evidence):
        return None

    class VoiceShouldNotRun:
        use_llm_mode = False

        def score_chapter(self, **kwargs):
            raise AssertionError("voice score should be reused")

    monkeypatch.setattr(ChapterAftermathPipeline, "_extract_chapter_bridge", fake_bridge)
    monkeypatch.setattr(
        "application.world.services.chapter_narrative_sync.sync_chapter_narrative_after_save",
        fake_sync,
    )
    monkeypatch.setattr(ChapterAftermathPipeline, "_run_auxiliary_stages", fake_auxiliary)

    pipeline = ChapterAftermathPipeline(
        knowledge_service=None,
        chapter_indexing_service=None,
        llm_service=object(),
        voice_drift_service=VoiceShouldNotRun(),
    )

    result = await pipeline.run_after_chapter_saved(
        "novel-1",
        8,
        "正文内容",
        voice_result={"similarity_score": 0.91, "drift_alert": False, "mode": "llm"},
    )

    assert result["similarity_score"] == 0.91
    assert result["drift_alert"] is False
    assert result["voice_mode"] == "llm"
    assert result["voice_reused"] is True
    await pipeline.drain_auxiliary_stages()
