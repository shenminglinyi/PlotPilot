"""API 端点测试 - 生成工作流"""
import pytest
from unittest.mock import Mock, AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from interfaces.api.v1.engine.generation import router
from application.workflows.auto_novel_generation_workflow import AutoNovelGenerationWorkflow
from application.engine.services.hosted_write_service import HostedWriteService
from domain.novel.services.storyline_manager import StorylineManager
from domain.novel.repositories.plot_arc_repository import PlotArcRepository
from domain.novel.entities.storyline import Storyline
from domain.novel.value_objects.novel_id import NovelId
from domain.novel.value_objects.storyline_type import StorylineType
from domain.novel.value_objects.storyline_status import StorylineStatus
from domain.novel.entities.plot_arc import PlotArc
from domain.novel.value_objects.plot_point import PlotPoint, PlotPointType
from domain.novel.value_objects.tension_level import TensionLevel


async def _mock_generate_chapter_stream(*args, **kwargs):
    yield {"type": "phase", "phase": "planning"}
    yield {"type": "chunk", "text": "x"}
    yield {
        "type": "done",
        "content": "Generated chapter content",
        "consistency_report": {"issues": [], "warnings": [], "suggestions": []},
        "token_count": 8750,
    }


async def _mock_hosted_stream(*args, **kwargs):
    yield {
        "type": "session",
        "novel_id": "novel-1",
        "from_chapter": 1,
        "to_chapter": 1,
        "total": 1,
    }
    yield {"type": "session_done", "novel_id": "novel-1"}


@pytest.fixture
def mock_workflow():
    """Mock AutoNovelGenerationWorkflow"""
    workflow = Mock(spec=AutoNovelGenerationWorkflow)
    workflow.generate_chapter_stream = _mock_generate_chapter_stream
    return workflow


@pytest.fixture
def mock_storyline_manager():
    """Mock StorylineManager"""
    manager = Mock(spec=StorylineManager)
    manager.repository = Mock()
    manager.repository.get_by_novel_id.return_value = [
        Storyline(
            id="storyline-1",
            novel_id=NovelId("novel-1"),
            storyline_type=StorylineType.MAIN_PLOT,
            status=StorylineStatus.ACTIVE,
            estimated_chapter_start=1,
            estimated_chapter_end=10
        )
    ]
    manager.create_storyline.return_value = Storyline(
        id="storyline-2",
        novel_id=NovelId("novel-1"),
        storyline_type=StorylineType.ROMANCE,
        status=StorylineStatus.ACTIVE,
        estimated_chapter_start=5,
        estimated_chapter_end=15
    )
    return manager


@pytest.fixture
def mock_plot_arc_repository():
    """Mock PlotArcRepository"""
    repo = Mock(spec=PlotArcRepository)
    plot_arc = PlotArc(id="arc-1", novel_id=NovelId("novel-1"))
    plot_arc.add_plot_point(PlotPoint(
        chapter_number=1,
        point_type=PlotPointType.OPENING,
        description="Opening",
        tension=TensionLevel.LOW
    ))
    plot_arc.add_plot_point(PlotPoint(
        chapter_number=50,
        point_type=PlotPointType.CLIMAX,
        description="Climax",
        tension=TensionLevel.PEAK
    ))
    repo.get_by_novel_id.return_value = plot_arc
    repo.save.return_value = None
    return repo


@pytest.fixture
def mock_hosted_service():
    svc = Mock(spec=HostedWriteService)
    svc.stream_hosted_write = _mock_hosted_stream
    return svc


@pytest.fixture
def app(mock_workflow, mock_storyline_manager, mock_plot_arc_repository, mock_hosted_service):
    """创建测试应用"""
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/v1")

    # Override dependencies
    from interfaces.api.v1.engine import generation
    test_app.dependency_overrides[generation.get_auto_workflow] = lambda: mock_workflow
    test_app.dependency_overrides[generation.get_hosted_write_service] = lambda: mock_hosted_service
    test_app.dependency_overrides[generation.get_storyline_manager] = lambda: mock_storyline_manager
    test_app.dependency_overrides[generation.get_plot_arc_repository] = lambda: mock_plot_arc_repository

    return test_app


@pytest.fixture
def client(app):
    """创建测试客户端"""
    return TestClient(app)


class TestGenerateChapterEndpoint:
    """测试章节生成端点（仅流式）"""

    def test_generate_chapter_stream_invalid_body(self, client):
        """流式端点：无效章节号"""
        response = client.post(
            "/api/v1/novels/novel-1/generate-chapter-stream",
            json={
                "chapter_number": 0,
                "outline": "x",
            },
        )
        assert response.status_code == 422

    def test_generate_chapter_stream_empty_outline(self, client):
        """流式端点：空大纲"""
        response = client.post(
            "/api/v1/novels/novel-1/generate-chapter-stream",
            json={
                "chapter_number": 1,
                "outline": "",
            },
        )
        assert response.status_code == 422

    def test_generate_chapter_stream_sse(self, client):
        """流式端点返回 SSE"""
        response = client.post(
            "/api/v1/novels/novel-1/generate-chapter-stream",
            json={
                "chapter_number": 1,
                "outline": "Chapter outline",
            },
        )
        assert response.status_code == 200
        assert "event-stream" in response.headers.get("content-type", "")
        body = response.text
        assert "data:" in body
        assert '"type": "done"' in body or '"done"' in body

    def test_generate_chapter_stream_approval_required(self, client, monkeypatch):
        """FULL_INTERACTIVE 策略先返回 AI Invocation 审阅会话"""
        from interfaces.api.v1.engine import generation

        async def fake_create_pre_call_review_invocation(**kwargs):
            return {
                "session": {
                    "id": "session-1",
                    "status": "awaiting_pre_call_review",
                },
                "next_action": "pre_call_review_required",
            }

        monkeypatch.setattr(
            generation,
            "_create_pre_call_review_invocation",
            fake_create_pre_call_review_invocation,
        )

        response = client.post(
            "/api/v1/novels/novel-1/generate-chapter-stream",
            json={
                "chapter_number": 1,
                "outline": "Chapter outline",
                "invocation_policy": "FULL_INTERACTIVE",
            },
        )

        assert response.status_code == 200
        assert "event-stream" in response.headers.get("content-type", "")
        assert '"type": "approval_required"' in response.text
        assert '"session_id": "session-1"' in response.text

    def test_hosted_write_stream_sse(self, client):
        """托管连写 SSE"""
        response = client.post(
            "/api/v1/novels/novel-1/hosted-write-stream",
            json={
                "from_chapter": 1,
                "to_chapter": 1,
                "auto_save": False,
                "auto_outline": True,
            },
        )
        assert response.status_code == 200
        assert "event-stream" in response.headers.get("content-type", "")
        assert "session" in response.text


class TestStorylineEndpoints:
    """测试故事线端点"""

    def test_get_storylines(self, client, mock_storyline_manager):
        """测试获取故事线列表"""
        response = client.get("/api/v1/novels/novel-1/storylines")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["storyline_type"] == "main_plot"

    def test_create_storyline(self, client, mock_storyline_manager):
        """测试创建故事线"""
        response = client.post(
            "/api/v1/novels/novel-1/storylines",
            json={
                "storyline_type": "romance",
                "estimated_chapter_start": 5,
                "estimated_chapter_end": 15
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert data["storyline_type"] == "romance"
        assert data["estimated_chapter_start"] == 5


class TestPlotArcEndpoints:
    """测试情节弧端点"""

    def test_get_plot_arc(self, client, mock_plot_arc_repository):
        """测试获取情节弧"""
        response = client.get("/api/v1/novels/novel-1/plot-arc")

        assert response.status_code == 200
        data = response.json()
        assert "key_points" in data
        assert len(data["key_points"]) == 2

    def test_create_plot_arc(self, client, mock_plot_arc_repository):
        """测试创建/更新情节弧"""
        response = client.post(
            "/api/v1/novels/novel-1/plot-arc",
            json={
                "key_points": [
                    {
                        "chapter_number": 1,
                        "tension": 1,
                        "description": "Opening",
                        "point_type": "opening"
                    },
                    {
                        "chapter_number": 100,
                        "tension": 4,
                        "description": "Climax",
                        "point_type": "climax"
                    }
                ]
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert "key_points" in data

