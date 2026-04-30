import pytest
from fastapi import HTTPException
from types import SimpleNamespace

from application.engine.services.autopilot_runtime_state import set_autopilot_runtime_state
from interfaces.api.v1.engine.autopilot_routes import (
    StartRequest,
    _chapter_has_content,
    start_autopilot,
)


@pytest.fixture(autouse=True)
def reset_autopilot_runtime_state():
    yield
    set_autopilot_runtime_state(
        running=False,
        disabled=False,
        reason="守护进程尚未初始化",
    )


@pytest.mark.asyncio
async def test_start_autopilot_rejects_when_daemon_disabled():
    set_autopilot_runtime_state(
        running=False,
        disabled=True,
        reason="DISABLE_AUTO_DAEMON=1，自动驾驶守护进程未启动",
    )

    with pytest.raises(HTTPException) as exc:
        await start_autopilot("novel-1", StartRequest(max_auto_chapters=3))

    assert exc.value.status_code == 503
    assert "DISABLE_AUTO_DAEMON" in exc.value.detail


@pytest.mark.asyncio
async def test_start_autopilot_rejects_when_daemon_not_running():
    set_autopilot_runtime_state(
        running=False,
        disabled=False,
        reason="守护进程已停止",
    )

    with pytest.raises(HTTPException) as exc:
        await start_autopilot("novel-1", StartRequest(max_auto_chapters=3))

    assert exc.value.status_code == 503
    assert exc.value.detail == "守护进程已停止"


def test_chapter_has_content_ignores_empty_planning_drafts():
    empty = SimpleNamespace(word_count=0, content="")
    with_content = SimpleNamespace(word_count=0, content="已经写出的正文")

    assert _chapter_has_content(empty) is False
    assert _chapter_has_content(with_content) is True
