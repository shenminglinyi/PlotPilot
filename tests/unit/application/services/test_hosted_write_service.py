"""HostedWriteService 单元测试"""
import pytest
from unittest.mock import AsyncMock, Mock

from application.engine.services.hosted_write_service import HostedWriteService
from application.workflows.auto_novel_generation_workflow import AutoNovelGenerationWorkflow
from application.core.services.chapter_service import ChapterService


@pytest.fixture
def mock_workflow():
    wf = Mock(spec=AutoNovelGenerationWorkflow)

    async def stream(*a, **k):
        yield {
            "type": "done",
            "content": "body",
            "consistency_report": {"issues": [], "warnings": [], "suggestions": []},
            "token_count": 10,
        }

    wf.generate_chapter_stream = stream
    wf.suggest_outline = AsyncMock(return_value="大纲要点")
    return wf


@pytest.fixture
def mock_chapter_service():
    svc = Mock(spec=ChapterService)
    svc.get_chapter_by_novel_and_number.return_value = None
    svc.update_chapter_by_novel_and_number = Mock()
    return svc


@pytest.mark.asyncio
async def test_hosted_streams_events_and_saves(mock_workflow, mock_chapter_service):
    svc = HostedWriteService(mock_workflow, mock_chapter_service)
    events = []
    async for e in svc.stream_hosted_write(
        "novel-1", 1, 1, auto_save=True, auto_outline=True
    ):
        events.append(e)
    types = [x["type"] for x in events]
    assert "session" in types
    assert "outline" in types
    assert "saved" in types
    mock_chapter_service.update_chapter_by_novel_and_number.assert_called_once()


@pytest.mark.asyncio
async def test_suggest_outline_uses_llm(mock_workflow, mock_chapter_service):
    mock_workflow.suggest_outline = AsyncMock(return_value="auto")
    svc = HostedWriteService(mock_workflow, mock_chapter_service)
    events = []
    async for e in svc.stream_hosted_write(
        "novel-1", 2, 2, auto_save=False, auto_outline=True
    ):
        events.append(e)
    outline_ev = next(x for x in events if x["type"] == "outline")
    assert outline_ev["text"] == "auto"
