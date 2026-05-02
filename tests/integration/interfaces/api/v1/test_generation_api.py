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
    workflow.precheck_coc_cognition_boundary = Mock(return_value={
        "checked": True,
        "allow_generate": True,
        "risk_level": "none",
        "blocking_issues": [],
        "warnings": [],
        "matched_tokens": [],
        "chapter_number": 1,
    })
    workflow.rewrite_outline_for_coc_boundary = Mock(return_value={
        "original_outline": "原始大纲",
        "rewritten_outline": "改写后大纲",
        "changed": True,
        "rewrite_mode": "conservative",
        "rewrite_style": "generic",
        "applied_rules": ["替换敏感片段：ledger_owner"],
        "precheck_before": {
            "checked": True,
            "allow_generate": False,
            "risk_level": "block",
            "blocking_issues": ["命中 author_only 线索键：ledger_owner"],
            "warnings": [],
            "matched_tokens": ["ledger_owner"],
            "chapter_number": 1,
        },
        "precheck_after": {
            "checked": True,
            "allow_generate": True,
            "risk_level": "none",
            "blocking_issues": [],
            "warnings": [],
            "matched_tokens": [],
            "chapter_number": 1,
        },
    })
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
    test_app.dependency_overrides[generation.get_analysis_workflow] = lambda: mock_workflow
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

    def test_generate_chapter_stream_blocked_by_coc_precheck(self, client, mock_workflow):
        mock_workflow.precheck_coc_cognition_boundary.return_value = {
            "checked": True,
            "allow_generate": False,
            "risk_level": "block",
            "blocking_issues": ["命中 author_only 线索键：clue-zhou-origin"],
            "warnings": [],
            "matched_tokens": ["clue-zhou-origin"],
            "chapter_number": 1,
        }

        response = client.post(
            "/api/v1/novels/novel-1/generate-chapter-stream",
            json={
                "chapter_number": 1,
                "outline": "主角直接确认 clue-zhou-origin 的真相。",
            },
        )
        assert response.status_code == 200
        assert '"type": "error"' in response.text
        assert "CoC 认知边界阻断" in response.text

    def test_coc_cognition_precheck_endpoint(self, client, mock_workflow):
        mock_workflow.precheck_coc_cognition_boundary.return_value = {
            "checked": True,
            "allow_generate": False,
            "risk_level": "block",
            "blocking_issues": ["命中 author_only 线索键：ledger_owner"],
            "warnings": [],
            "matched_tokens": ["ledger_owner"],
            "chapter_number": 6,
        }

        response = client.post(
            "/api/v1/novels/novel-1/chapters/6/coc-cognition-precheck",
            json={"outline": "主角确认 ledger_owner 的真实身份。"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["checked"] is True
        assert data["allow_generate"] is False
        assert data["risk_level"] == "block"
        assert len(data["blocking_issues"]) == 1

    def test_coc_cognition_rewrite_outline_endpoint(self, client):
        response = client.post(
            "/api/v1/novels/novel-1/chapters/6/coc-cognition-rewrite-outline",
            json={"outline": "主角确认 ledger_owner 的真实身份。", "rewrite_mode": "aggressive"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["changed"] is True
        assert data["rewritten_outline"] == "改写后大纲"
        assert data["rewrite_mode"] == "conservative"
        assert data["rewrite_style"] == "generic"
        assert data["precheck_before"]["risk_level"] == "block"

    def test_coc_cognition_rewrite_outline_passes_mode_to_workflow(self, client, mock_workflow):
        response = client.post(
            "/api/v1/novels/novel-1/chapters/8/coc-cognition-rewrite-outline",
            json={"outline": "测试大纲", "rewrite_mode": "aggressive", "rewrite_style": "coc"},
        )
        assert response.status_code == 200
        mock_workflow.rewrite_outline_for_coc_boundary.assert_called_once()
        kwargs = mock_workflow.rewrite_outline_for_coc_boundary.call_args.kwargs
        assert kwargs["rewrite_mode"] == "aggressive"
        assert kwargs["rewrite_style"] == "coc"

    def test_generate_chapter_stream_can_enable_anti_compression_directive(
        self, client, mock_workflow
    ):
        """开启避免压缩表达时，后端应把慢写约束注入实际生成大纲。"""
        captured = {}

        async def stream_with_capture(*args, **kwargs):
            captured.update(kwargs)
            yield {"type": "done", "content": "", "consistency_report": {}, "token_count": 0}

        mock_workflow.generate_chapter_stream = stream_with_capture

        response = client.post(
            "/api/v1/novels/novel-1/generate-chapter-stream",
            json={
                "chapter_number": 1,
                "outline": "主角和同伴讨论下一步行动。",
                "avoid_compressed_expression": True,
            },
        )

        assert response.status_code == 200
        assert "主角和同伴讨论下一步行动。" in captured["outline"]
        assert "避免 AI 压缩表达" in captured["outline"]
        assert "不要用一句概括跳过" in captured["outline"]

    def test_strategy_preview_returns_chapter_contract_and_showing_scene_fields(self, client, mock_workflow):
        async def strategy_with_showing_fields(*args, **kwargs):
            return {
                "chapter_contract": {
                    "chapter_question": "灰卡为什么能刷开门禁？",
                    "protagonist_want": "白雨翔要确认写卡器来源。",
                    "opposition": "许照只给半份证据。",
                    "reader_expectation": "看到两人互相试探。",
                    "required_information_change": "签收记录暴露伪造痕迹。",
                    "required_relationship_change": "两人形成有限合作。",
                    "ending_question": "谁借用了审计流程？",
                    "show_dont_tell_rules": ["不能直写怀疑，只写扣住证物。"],
                },
                "dramatic_task": {
                    "goal": "确认写卡器来源",
                    "obstacle": "许照保留证据",
                    "reader_expectation": "看到试探",
                    "ending_hook": "审计流程异常",
                },
                "scene_plan": [
                    {
                        "label": "核对签收单",
                        "task": "确认签名真伪",
                        "resistance": "许照不交原件",
                        "info_shift": "签名疑点出现",
                        "relationship_shift": "有限合作",
                        "anchor": "证物袋",
                        "visible_action": "白雨翔按住证物袋封口。",
                        "subtext_dialogue": "表面问流程，实际逼许照露底。",
                        "unspoken_emotion": "怀疑不能直说。",
                        "object_or_clue_change": "灰卡变成伪造链条证据。",
                        "hook": "审计流程异常",
                        "target_words": 800,
                    }
                ],
                "writing_focus": ["少解释，多展示。"],
            }

        mock_workflow.generate_chapter_strategy = strategy_with_showing_fields
        response = client.post(
            "/api/v1/novels/novel-1/chapters/2/strategy-preview",
            json={"outline": "白雨翔追查灰卡。"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["chapter_contract"]["chapter_question"].startswith("灰卡")
        assert data["scene_plan"][0]["visible_action"].startswith("白雨翔")

    def test_editorial_review_returns_showing_score(self, client, mock_workflow):
        async def editorial_with_showing(*args, **kwargs):
            return {
                "summary": "对白有张力，但解释略多。",
                "scores": {
                    "opening": 88,
                    "conflict": 90,
                    "character": 86,
                    "dialogue": 84,
                    "hook": 92,
                    "pacing": 87,
                    "showing": 79,
                },
                "strengths": ["证物动作具体。"],
                "problems": ["部分情绪仍被直接命名。"],
                "actions": ["把解释改成动作。"],
                "verdict": "可优化后使用",
            }

        mock_workflow.review_generated_chapter_editorially = editorial_with_showing
        response = client.post(
            "/api/v1/novels/novel-1/chapters/2/editorial-review",
            json={"outline": "白雨翔追查灰卡。", "content": "白雨翔按住证物袋。"},
        )

        assert response.status_code == 200
        assert response.json()["scores"]["showing"] == 79

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
