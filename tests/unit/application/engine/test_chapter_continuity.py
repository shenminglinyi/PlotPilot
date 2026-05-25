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
