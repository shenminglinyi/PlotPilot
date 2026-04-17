"""AutopilotDaemon 辅助逻辑测试"""
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from application.engine.dtos.word_control_dto import WordControlDTO
from application.engine.services.autopilot_daemon import AutopilotDaemon
from domain.novel.entities.novel import AutopilotStatus, Novel, NovelStage
from domain.novel.value_objects.novel_id import NovelId


def _build_novel(target_words_per_chapter: int = 3200) -> Novel:
    return Novel(
        id=NovelId("novel-1"),
        title="测试小说",
        author="作者",
        target_chapters=10,
        target_words_per_chapter=target_words_per_chapter,
        autopilot_status=AutopilotStatus.RUNNING,
        current_stage=NovelStage.WRITING,
    )


def _build_workflow(action: str) -> Mock:
    workflow = Mock()
    workflow.prepare_chapter_generation.return_value = {
        "context": "ctx",
        "context_tokens": 12,
        "storyline_context": "",
        "plot_tension": 5,
        "style_summary": "",
        "voice_anchors": "",
    }
    workflow.build_chapter_prompt.return_value = "prompt"
    workflow.post_process_generated_chapter = AsyncMock()
    workflow._apply_word_control = AsyncMock(
        return_value=(
            f"修正后正文-{action}",
            SimpleNamespace(action=action),
        )
    )
    workflow._serialize_word_control.return_value = WordControlDTO(
        target=3200,
        actual=3180 if action == "expand" else 3090,
        tolerance=0.15,
        delta=-20 if action == "expand" else -110,
        status="ok",
        within_tolerance=True,
        action=action,
        expansion_attempts=1 if action == "expand" else 0,
        trim_applied=action == "trim",
        fallback_used=False,
        min_allowed=2720,
        max_allowed=3680,
    )
    workflow.word_control_service = Mock()
    workflow.word_control_service.inject_length_requirements.side_effect = (
        lambda prompt, target: f"{prompt}|target={target}"
    )
    return workflow


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["expand", "trim"])
async def test_handle_writing_persists_word_control_metrics(action: str):
    chapter_repository = Mock()
    chapter_repository.get_by_novel_and_number.return_value = None
    metrics_repository = Mock()
    workflow = _build_workflow(action)

    daemon = AutopilotDaemon(
        novel_repository=Mock(),
        llm_service=Mock(),
        context_builder=None,
        background_task_service=Mock(),
        planning_service=Mock(),
        story_node_repo=Mock(),
        chapter_repository=chapter_repository,
        chapter_workflow=workflow,
        chapter_generation_metrics_repository=metrics_repository,
    )

    daemon._is_still_running = Mock(return_value=True)
    daemon._flush_novel = Mock()
    daemon._find_next_unwritten_chapter_async = AsyncMock(
        return_value=SimpleNamespace(
            id="chapter-node-1",
            number=1,
            title="第一章",
            outline="章节大纲",
            description="",
        )
    )
    daemon._get_existing_chapter_content = AsyncMock(return_value="")
    daemon._stream_llm_with_stop_watch = AsyncMock(return_value="原始正文")

    novel = _build_novel()

    await daemon._handle_writing(novel)

    workflow._apply_word_control.assert_awaited_once()
    workflow._serialize_word_control.assert_called_once()
    metrics_repository.upsert.assert_called_once()

    upsert_args = metrics_repository.upsert.call_args.args
    assert upsert_args[0] == "novel-1"
    assert upsert_args[1] == 1
    assert upsert_args[2]["generated_via"] == "autopilot"
    assert upsert_args[2]["action"] == action
    assert upsert_args[2]["within_tolerance"] is True
    assert novel.current_stage == NovelStage.AUDITING
    assert novel.current_auto_chapters == 1


def test_get_latest_completed_chapter_prefers_highest_number():
    """审计阶段应按真实章节号选择最近完成章节。"""
    chapters = [
        Mock(number=11, status=Mock(value="completed")),
        Mock(number=12, status=Mock(value="draft")),
        Mock(number=13, status=Mock(value="completed")),
    ]

    chapter = AutopilotDaemon._get_latest_completed_chapter(chapters)

    assert chapter.number == 13


def test_get_latest_completed_chapter_returns_none_when_no_completed():
    """没有完成章节时应返回 None。"""
    chapters = [
        Mock(number=11, status=Mock(value="draft")),
        Mock(number=12, status=Mock(value="reviewing")),
    ]

    chapter = AutopilotDaemon._get_latest_completed_chapter(chapters)

    assert chapter is None
