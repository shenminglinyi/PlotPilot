"""Phase 5/6 runtime delegates 测试"""
from unittest.mock import AsyncMock, MagicMock, patch

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
async def test_run_act_planning_stops_when_not_running():
    host = MagicMock()
    host._is_still_running.return_value = False
    novel = MagicMock()

    await run_act_planning(host, novel)

    host.story_node_repo.get_by_novel.assert_not_called()


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
