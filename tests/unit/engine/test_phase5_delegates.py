"""Phase 5/6 runtime delegates 测试"""
from unittest.mock import AsyncMock, MagicMock, patch
from types import SimpleNamespace

import pytest

from engine.runtime.act_planning_delegate import run_act_planning
from engine.runtime.macro_planning_delegate import run_macro_planning
from engine.runtime.novel_lifecycle import process_novel
from engine.runtime.writing_delegate import run_writing


@pytest.mark.asyncio
async def test_process_novel_routes_macro_planning():
    from domain.novel.entities.novel import AutopilotStatus, NovelStage

    host = MagicMock()
    host._is_still_running.return_value = True
    host.circuit_breaker = None
    novel = MagicMock()
    novel.novel_id.value = "n-1"
    novel.current_stage = NovelStage.MACRO_PLANNING
    novel.autopilot_status = AutopilotStatus.RUNNING

    with patch(
        "engine.runtime.novel_lifecycle.run_macro_planning",
        new_callable=AsyncMock,
    ) as mock_macro:
        await process_novel(host, novel)
        mock_macro.assert_awaited_once_with(host, novel)


@pytest.mark.asyncio
async def test_process_novel_treats_legacy_planning_as_macro_planning():
    from domain.novel.entities.novel import AutopilotStatus, NovelStage

    host = MagicMock()
    host._is_still_running.return_value = True
    host.circuit_breaker = None
    novel = MagicMock()
    novel.novel_id.value = "n-1"
    novel.current_stage = NovelStage.PLANNING
    novel.autopilot_status = AutopilotStatus.RUNNING

    with patch(
        "engine.runtime.novel_lifecycle.run_macro_planning",
        new_callable=AsyncMock,
    ) as mock_macro:
        await process_novel(host, novel)
        assert novel.current_stage == NovelStage.MACRO_PLANNING
        host._save_novel_state.assert_called()
        mock_macro.assert_awaited_once_with(host, novel)


@pytest.mark.asyncio
async def test_run_macro_planning_stops_when_not_running():
    host = MagicMock()
    host._is_still_running.return_value = False
    novel = MagicMock()

    await run_macro_planning(host, novel)

    host.planning_service.generate_macro_plan.assert_not_called()


@pytest.mark.asyncio
async def test_run_macro_planning_pauses_for_ai_invocation(monkeypatch):
    from domain.novel.entities.novel import NovelStage

    host = MagicMock()
    host._is_still_running.return_value = True
    host.planning_service.generate_macro_plan = AsyncMock()
    novel = MagicMock()
    novel.novel_id.value = "n-1"
    novel.target_chapters = 12
    novel.auto_approve_mode = False

    monkeypatch.setattr(
        "engine.runtime.macro_planning_delegate._read_shared_state",
        lambda _novel_id: {},
    )
    monkeypatch.setattr(
        "engine.runtime.macro_planning_delegate._request_macro_invocation",
        AsyncMock(
            return_value=SimpleNamespace(
                status="awaiting_pre_call_review",
                session_id="session-1",
                operation="autopilot.macro.plan",
                node_key="planning-quick-macro",
                autopilot_pause_reason="awaiting_ai_review",
                payload={
                    "session": SimpleNamespace(policy=SimpleNamespace(value="AUTOPILOT_PAUSE")),
                },
            )
        ),
    )

    await run_macro_planning(host, novel)

    host.planning_service.generate_macro_plan.assert_not_called()
    assert novel.current_stage == NovelStage.PAUSED_FOR_REVIEW
    host._update_shared_state.assert_any_call(
        "n-1",
        active_invocation_session_id="session-1",
        active_invocation_operation="autopilot.macro.plan",
        active_invocation_node_key="planning-quick-macro",
        active_invocation_status="awaiting_pre_call_review",
        active_invocation_policy="AUTOPILOT_PAUSE",
        has_active_invocation=True,
        requires_ai_review=True,
        autopilot_pause_reason="awaiting_ai_review",
        macro_structure_ready=False,
        writing_substep="macro_planning",
        writing_substep_label="宏观规划 · AI 请求面板",
    )


@pytest.mark.asyncio
async def test_run_act_planning_stops_when_not_running():
    host = MagicMock()
    host._is_still_running.return_value = False
    novel = MagicMock()

    await run_act_planning(host, novel)

    host.story_node_repo.get_by_novel.assert_not_called()


@pytest.mark.asyncio
async def test_run_act_planning_pauses_for_ai_invocation(monkeypatch):
    from domain.novel.entities.novel import NovelStage

    host = MagicMock()
    host._is_still_running.return_value = True
    host.planning_service.plan_act_chapters = AsyncMock()
    host.story_node_repo.get_children_sync.return_value = []

    target_act = MagicMock()
    target_act.id = "act-1"
    target_act.number = 1
    target_act.node_type.value = "act"
    target_act.suggested_chapter_count = 5
    target_act.title = "第一幕"
    target_act.description = "开端"

    host.story_node_repo.get_by_novel = AsyncMock(return_value=[target_act])

    novel = MagicMock()
    novel.novel_id.value = "n-1"
    novel.target_chapters = 12
    novel.current_act = 0
    novel.auto_approve_mode = False

    monkeypatch.setattr(
        "engine.runtime.act_planning_delegate._read_shared_state",
        lambda _novel_id: {},
    )
    monkeypatch.setattr(
        "engine.runtime.act_planning_delegate._request_act_invocation",
        AsyncMock(
            return_value=SimpleNamespace(
                status="awaiting_pre_call_review",
                session_id="session-1",
                operation="autopilot.act.plan",
                node_key="planning-act",
                autopilot_pause_reason="awaiting_ai_review",
                payload={
                    "session": SimpleNamespace(policy=SimpleNamespace(value="AUTOPILOT_PAUSE")),
                },
            )
        ),
    )

    await run_act_planning(host, novel)

    host.planning_service.plan_act_chapters.assert_not_called()
    assert novel.current_stage == NovelStage.PAUSED_FOR_REVIEW
    host._update_shared_state.assert_any_call(
        "n-1",
        active_invocation_session_id="session-1",
        active_invocation_operation="autopilot.act.plan",
        active_invocation_node_key="planning-act",
        active_invocation_status="awaiting_pre_call_review",
        active_invocation_policy="AUTOPILOT_PAUSE",
        has_active_invocation=True,
        requires_ai_review=True,
        autopilot_pause_reason="awaiting_ai_review",
    )


@pytest.mark.asyncio
async def test_run_writing_routes_to_story_pipeline_when_enabled():
    host = MagicMock()
    host.use_story_pipeline_for_writing = True
    novel = MagicMock()

    with patch(
        "engine.runtime.writing_delegate.run_story_pipeline_writing",
        new_callable=AsyncMock,
    ) as mock_pipeline, patch(
        "engine.runtime.legacy_writing_delegate.run_legacy_writing",
        new_callable=AsyncMock,
    ) as mock_legacy:
        await run_writing(host, novel)
        mock_pipeline.assert_awaited_once_with(host, novel)
        mock_legacy.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_writing_routes_to_legacy_when_pipeline_off():
    host = MagicMock()
    host.use_story_pipeline_for_writing = False
    novel = MagicMock()

    with patch(
        "engine.runtime.writing_delegate.run_story_pipeline_writing",
        new_callable=AsyncMock,
    ) as mock_pipeline, patch(
        "engine.runtime.legacy_writing_delegate.run_legacy_writing",
        new_callable=AsyncMock,
    ) as mock_legacy:
        await run_writing(host, novel)
        mock_legacy.assert_awaited_once_with(host, novel)
        mock_pipeline.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_novel_routes_writing_via_run_writing():
    from domain.novel.entities.novel import AutopilotStatus, NovelStage

    host = MagicMock()
    host._is_still_running.return_value = True
    host.circuit_breaker = None
    novel = MagicMock()
    novel.novel_id.value = "n-1"
    novel.current_stage = NovelStage.WRITING
    novel.autopilot_status = AutopilotStatus.RUNNING

    with patch(
        "engine.runtime.writing_delegate.run_writing",
        new_callable=AsyncMock,
    ) as mock_writing:
        await process_novel(host, novel)
        mock_writing.assert_awaited_once_with(host, novel)


@pytest.mark.asyncio
async def test_process_novel_records_last_error_summary_on_failure():
    from domain.novel.entities.novel import AutopilotStatus, NovelStage

    host = MagicMock()
    host._is_still_running.return_value = True
    host.circuit_breaker = MagicMock()
    novel = MagicMock()
    novel.novel_id.value = "n-1"
    novel.current_stage = NovelStage.MACRO_PLANNING
    novel.autopilot_status = AutopilotStatus.RUNNING
    novel.consecutive_error_count = 0

    with patch(
        "engine.runtime.novel_lifecycle.run_macro_planning",
        new_callable=AsyncMock,
        side_effect=RuntimeError("Error code: 500 - api_error upstream"),
    ):
        await process_novel(host, novel)

    assert "Error code: 500 - api_error upstream" in novel.last_error_summary
    assert novel.consecutive_error_count == 1
    host._save_novel_state.assert_called()


@pytest.mark.asyncio
async def test_process_novel_marks_error_after_three_failures():
    from domain.novel.entities.novel import AutopilotStatus, NovelStage

    host = MagicMock()
    host._is_still_running.return_value = True
    host.circuit_breaker = MagicMock()
    novel = MagicMock()
    novel.novel_id.value = "n-1"
    novel.current_stage = NovelStage.MACRO_PLANNING
    novel.autopilot_status = AutopilotStatus.RUNNING
    novel.consecutive_error_count = 2

    with patch(
        "engine.runtime.novel_lifecycle.run_macro_planning",
        new_callable=AsyncMock,
        side_effect=RuntimeError("boom"),
    ):
        # 非风控错误:不走自修复,直接累计

        await process_novel(host, novel)

    assert novel.consecutive_error_count == 3
    assert novel.autopilot_status == AutopilotStatus.ERROR


@pytest.mark.asyncio
async def test_process_novel_clears_last_error_summary_on_success():
    from domain.novel.entities.novel import AutopilotStatus, NovelStage

    host = MagicMock()
    host._is_still_running.return_value = True
    host.circuit_breaker = MagicMock()
    novel = MagicMock()
    novel.novel_id.value = "n-1"
    novel.current_stage = NovelStage.WRITING
    novel.autopilot_status = AutopilotStatus.RUNNING
    novel.consecutive_error_count = 5
    novel.last_error_summary = "RuntimeError: stale"

    with patch(
        "engine.runtime.writing_delegate.run_writing",
        new_callable=AsyncMock,
    ):
        await process_novel(host, novel)

    assert novel.consecutive_error_count == 0
    assert novel.last_error_summary == ""
    host.circuit_breaker.record_success.assert_called_once()


def test_summarize_error_collapses_whitespace_and_truncates():
    from engine.runtime.novel_lifecycle import _summarize_error

    err = RuntimeError("Error code: 500 -\n{'type': 'api_error',\n 'message': 'input new_sensitive'}")
    summary = _summarize_error(err)
    assert "\n" not in summary
    assert summary.startswith("RuntimeError: ")
    assert "input new_sensitive" in summary
    assert len(_summarize_error(ValueError("x" * 2000))) == 500


@pytest.mark.asyncio
async def test_process_novel_auto_heals_content_filter_error():
    """1026 类错误触发自修复:成功后清零计数,不挂起"""
    from domain.novel.entities.novel import AutopilotStatus, NovelStage

    host = MagicMock()
    host._is_still_running.return_value = True
    host.circuit_breaker = MagicMock()
    host._latest_completed_chapter_number.return_value = 222
    host.chapter_repository.get_by_novel_and_number.return_value = SimpleNamespace(content="触发内容")
    host.llm_service.generate = AsyncMock(return_value=SimpleNamespace(content="改写后内容"))

    novel = MagicMock()
    novel.novel_id.value = "n-1"
    novel.current_stage = NovelStage.MACRO_PLANNING
    novel.autopilot_status = AutopilotStatus.RUNNING
    novel.consecutive_error_count = 0

    with patch(
        "engine.runtime.novel_lifecycle.run_macro_planning",
        new_callable=AsyncMock,
        side_effect=RuntimeError("Error code: 500 - input new_sensitive (1026)"),
    ):
        await process_novel(host, novel)

    assert novel.consecutive_error_count == 0
    assert novel.autopilot_status == AutopilotStatus.RUNNING
    host.chapter_repository.save.assert_called_once()


@pytest.mark.asyncio
async def test_process_novel_counts_failure_when_heal_fails():
    """自修复失败:照常累计失败并把原因写进 last_error_summary"""
    from domain.novel.entities.novel import AutopilotStatus, NovelStage

    host = MagicMock()
    host._is_still_running.return_value = True
    host.circuit_breaker = MagicMock()
    host._latest_completed_chapter_number.return_value = None  # 无法定位章节 → 修复失败

    novel = MagicMock()
    novel.novel_id.value = "n-1"
    novel.current_stage = NovelStage.MACRO_PLANNING
    novel.autopilot_status = AutopilotStatus.RUNNING
    novel.consecutive_error_count = 0

    with patch(
        "engine.runtime.novel_lifecycle.run_macro_planning",
        new_callable=AsyncMock,
        side_effect=RuntimeError("Error code: 500 - input new_sensitive (1026)"),
    ):
        await process_novel(host, novel)

    assert novel.consecutive_error_count == 1
    assert "自动修复未成功" in novel.last_error_summary


@pytest.mark.asyncio
async def test_process_novel_resumes_completed_book_after_target_raise():
    """已完成的书在目标章节数上调后,下一轮自动回到写作"""
    from domain.novel.entities.novel import AutopilotStatus, NovelStage

    host = MagicMock()
    host._is_still_running.return_value = True
    host.circuit_breaker = None
    host._count_completed_chapters.return_value = 300
    novel = MagicMock()
    novel.novel_id.value = "n-1"
    novel.current_stage = NovelStage.COMPLETED
    novel.autopilot_status = AutopilotStatus.RUNNING
    novel.target_chapters = 303

    await process_novel(host, novel)

    assert novel.current_stage == NovelStage.WRITING
    host._save_novel_state.assert_called()


@pytest.mark.asyncio
async def test_process_novel_keeps_completed_book_when_target_met():
    """完成数已达目标:保持 completed,不误触发续写"""
    from domain.novel.entities.novel import AutopilotStatus, NovelStage

    host = MagicMock()
    host._is_still_running.return_value = True
    host.circuit_breaker = None
    host._count_completed_chapters.return_value = 303
    novel = MagicMock()
    novel.novel_id.value = "n-1"
    novel.current_stage = NovelStage.COMPLETED
    novel.autopilot_status = AutopilotStatus.RUNNING
    novel.target_chapters = 303

    await process_novel(host, novel)

    assert novel.current_stage == NovelStage.COMPLETED
    host._save_novel_state.assert_not_called()
