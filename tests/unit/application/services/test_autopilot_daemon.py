from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from application.engine.services.autopilot_daemon import AutopilotDaemon
from domain.novel.entities.novel import AutopilotStatus, NovelStage
from domain.novel.value_objects.novel_id import NovelId


@pytest.mark.asyncio
async def test_handle_auditing_uses_current_auto_chapters_for_lookup(monkeypatch):
    chapter = Mock()
    chapter.id = "chapter-12"
    chapter.content = "本章内容"
    chapter.status = SimpleNamespace(value="completed")
    chapter.update_tension_score = Mock()

    chapter_repository = Mock()
    chapter_repository.get_by_novel_and_number.return_value = chapter
    chapter_repository.list_by_novel.return_value = [chapter]

    daemon = AutopilotDaemon(
        novel_repository=Mock(),
        llm_service=None,
        context_builder=None,
        background_task_service=Mock(),
        planning_service=Mock(),
        story_node_repo=None,
        chapter_repository=chapter_repository,
    )

    monkeypatch.setattr(daemon, "_is_still_running", lambda novel: True)
    monkeypatch.setattr(
        daemon,
        "_legacy_auditing_tasks_and_voice",
        lambda *args, **kwargs: {
            "drift_alert": False,
            "similarity_score": 0.93,
            "narrative_sync_ok": True,
        },
    )
    daemon._score_tension = AsyncMock(return_value=7)
    daemon._auto_trigger_macro_diagnosis = AsyncMock()
    daemon._maybe_generate_summaries = AsyncMock()

    novel = SimpleNamespace(
        novel_id=NovelId("novel-1"),
        current_act=2,
        current_chapter_in_act=1,
        current_auto_chapters=12,
        current_stage=NovelStage.AUDITING,
        autopilot_status=AutopilotStatus.RUNNING,
        target_chapters=99,
    )

    await daemon._handle_auditing(novel)

    chapter_repository.get_by_novel_and_number.assert_called_once()
    lookup_novel_id, lookup_chapter_number = chapter_repository.get_by_novel_and_number.call_args.args
    assert lookup_novel_id.value == "novel-1"
    assert lookup_chapter_number == 12
    assert novel.last_audit_chapter_number == 12
    chapter.update_tension_score.assert_called_once_with(70)
    chapter_repository.save.assert_called_once_with(chapter)
