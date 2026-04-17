"""AutoNovelGenerationWorkflow 单元测试"""
import pytest
from unittest.mock import Mock, AsyncMock
from application.workflows.auto_novel_generation_workflow import AutoNovelGenerationWorkflow
from application.engine.dtos.generation_result import GenerationResult
from application.engine.dtos.scene_director_dto import SceneDirectorAnalysis
from application.engine.services.context_builder import ContextBuilder
from domain.novel.services.consistency_checker import ConsistencyChecker
from domain.novel.services.storyline_manager import StorylineManager
from domain.novel.repositories.plot_arc_repository import PlotArcRepository
from domain.novel.value_objects.consistency_report import ConsistencyReport, Issue, IssueType, Severity
from domain.novel.value_objects.chapter_state import ChapterState
from domain.ai.services.llm_service import LLMService, GenerationResult as LLMResult
from domain.ai.value_objects.token_usage import TokenUsage


@pytest.fixture
def mock_context_builder():
    """Mock ContextBuilder"""
    builder = Mock(spec=ContextBuilder)
    builder.build_structured_context.return_value = {
        "layer1_text": "Layer 1 context",
        "layer2_text": "Layer 2 context",
        "layer3_text": "Layer 3 context",
        "token_usage": {
            "layer1": 1250,
            "layer2": 5500,
            "layer3": 2500,
            "total": 9250
        }
    }
    # 不再需要 estimate_tokens 方法
    return builder


@pytest.fixture
def mock_consistency_checker():
    """Mock ConsistencyChecker"""
    checker = Mock(spec=ConsistencyChecker)
    checker.check_all = Mock(return_value=ConsistencyReport(
        issues=[],
        warnings=[],
        suggestions=[]
    ))
    return checker


@pytest.fixture
def mock_storyline_manager():
    """Mock StorylineManager"""
    manager = Mock(spec=StorylineManager)
    manager.repository = Mock()
    manager.repository.get_by_novel_id.return_value = []
    manager.get_storyline_context.return_value = "Main storyline context"
    return manager


@pytest.fixture
def mock_plot_arc_repository():
    """Mock PlotArcRepository"""
    repo = Mock(spec=PlotArcRepository)
    return repo


async def _mock_stream_generate(*args, **kwargs):
    yield "Generated chapter content"


@pytest.fixture
def mock_llm_service():
    """Mock LLMService"""
    service = Mock(spec=LLMService)
    service.generate = AsyncMock(return_value=LLMResult(
        content="Generated chapter content",
        token_usage=TokenUsage(input_tokens=500, output_tokens=500)
    ))
    service.stream_generate = _mock_stream_generate
    return service


@pytest.fixture
def workflow(
    mock_context_builder,
    mock_consistency_checker,
    mock_storyline_manager,
    mock_plot_arc_repository,
    mock_llm_service
):
    """创建 AutoNovelGenerationWorkflow 实例"""
    return AutoNovelGenerationWorkflow(
        context_builder=mock_context_builder,
        consistency_checker=mock_consistency_checker,
        storyline_manager=mock_storyline_manager,
        plot_arc_repository=mock_plot_arc_repository,
        llm_service=mock_llm_service
    )


class TestGenerateChapter:
    """测试 generate_chapter 方法"""

    @pytest.mark.asyncio
    async def test_generate_chapter_success(self, workflow, mock_context_builder, mock_llm_service):
        """测试成功生成章节"""
        result = await workflow.generate_chapter(
            novel_id="novel-1",
            chapter_number=1,
            outline="Chapter 1 outline"
        )

        # 验证返回结果
        assert isinstance(result, GenerationResult)
        assert result.content == "Generated chapter content"
        assert result.token_count == 9250
        assert "Layer 1 context" in result.context_used
        assert isinstance(result.consistency_report, ConsistencyReport)

        # 验证调用顺序
        mock_context_builder.build_structured_context.assert_called_once_with(
            novel_id="novel-1",
            chapter_number=1,
            outline="Chapter 1 outline",
            max_tokens=35000,
            scene_director=None
        )
        # 验证 LLM 被调用：至少一次用于生成章节，可能还有一次用于状态提取
        assert mock_llm_service.generate.call_count >= 1

    @pytest.mark.asyncio
    async def test_generate_chapter_with_scene_director(self, workflow, mock_context_builder, mock_llm_service):
        """测试使用 scene_director 参数生成章节"""
        scene_director = SceneDirectorAnalysis(
            characters=["Alice", "Bob"],
            locations=["Room A"],
            action_types=["dialogue", "action"],
            trigger_keywords=["conflict"],
            emotional_state="tense",
            pov="Alice"
        )

        result = await workflow.generate_chapter(
            novel_id="novel-1",
            chapter_number=1,
            outline="Chapter 1 outline",
            scene_director=scene_director
        )

        # 验证返回结果
        assert isinstance(result, GenerationResult)
        assert result.content == "Generated chapter content"

        # 验证 build_structured_context 被调用时传入了 scene_director
        mock_context_builder.build_structured_context.assert_called_once_with(
            novel_id="novel-1",
            chapter_number=1,
            outline="Chapter 1 outline",
            max_tokens=35000,
            scene_director=scene_director
        )

    @pytest.mark.asyncio
    async def test_generate_chapter_invalid_chapter_number(self, workflow):
        """测试无效的章节号"""
        with pytest.raises(ValueError, match="chapter_number must be positive"):
            await workflow.generate_chapter(
                novel_id="novel-1",
                chapter_number=0,
                outline="Chapter outline"
            )

    @pytest.mark.asyncio
    async def test_generate_chapter_empty_outline(self, workflow):
        """测试空大纲"""
        with pytest.raises(ValueError, match="outline cannot be empty"):
            await workflow.generate_chapter(
                novel_id="novel-1",
                chapter_number=1,
                outline=""
            )


class TestGenerateChapterWithReview:
    """测试 generate_chapter_with_review 方法"""

    @pytest.mark.asyncio
    async def test_generate_with_review_success(self, workflow):
        """测试带审查的生成成功"""
        content, report = await workflow.generate_chapter_with_review(
            novel_id="novel-1",
            chapter_number=1,
            outline="Chapter 1 outline"
        )

        assert content == "Generated chapter content"
        assert isinstance(report, ConsistencyReport)
        assert not report.has_critical_issues()


class TestSuggestOutline:
    """测试 suggest_outline"""

    @pytest.mark.asyncio
    async def test_suggest_outline_returns_llm_text(self, workflow, mock_context_builder, mock_llm_service):
        mock_context_builder.build_context = Mock(return_value="Mock context")
        mock_llm_service.generate = AsyncMock(
            return_value=LLMResult(
                content="1. 开场\n2. 转折",
                token_usage=TokenUsage(input_tokens=10, output_tokens=20),
            )
        )
        text = await workflow.suggest_outline("novel-1", 3)
        assert "开场" in text
        mock_llm_service.generate.assert_called_once()


class TestGenerateChapterStream:
    """测试 generate_chapter_stream 流式事件"""

    @pytest.mark.asyncio
    async def test_stream_emits_phases_chunk_and_done(self, workflow):
        events = []
        async for e in workflow.generate_chapter_stream("novel-1", 1, "Chapter outline"):
            events.append(e)
        types = [x["type"] for x in events]
        assert "phase" in types
        assert "chunk" in types
        assert events[-1]["type"] == "done"
        assert events[-1]["content"] == "Generated chapter content"
        assert events[-1]["token_count"] == 9250


class TestExtractChapterState:
    """测试 _extract_chapter_state 方法"""

    @pytest.mark.asyncio
    async def test_extract_chapter_state_from_content(self, workflow):
        """测试从内容中提取章节状态"""
        content = "Chapter content with character actions"

        state = await workflow._extract_chapter_state(content, chapter_number=1)

        assert isinstance(state, ChapterState)
        # 基本实现应该返回空列表
        assert isinstance(state.new_characters, list)
        assert isinstance(state.character_actions, list)
        assert isinstance(state.relationship_changes, list)


class TestBuildPrompt:
    """测试 _build_prompt 方法"""

    def test_build_prompt_with_context(self, workflow):
        """测试构建提示词"""
        prompt = workflow._build_prompt(
            context="Full context",
            outline="Chapter outline"
        )

        assert "Full context" in prompt.system
        assert "Chapter outline" in prompt.user

    def test_build_prompt_includes_storyline_and_tension(self, workflow):
        """故事线与情节张力应进入 system，供模型遵守"""
        prompt = workflow._build_prompt(
            context="CTX",
            outline="OL",
            storyline_context="主线：本章需触及 X",
            plot_tension="Expected tension: HIGH",
        )
        assert "主线" in prompt.system
        assert "HIGH" in prompt.system
        assert "CTX" in prompt.system

class TestConflictDetectionIntegration:
    """测试冲突检测集成"""

    @pytest.mark.asyncio
    async def test_generate_chapter_includes_ghost_annotations(
        self,
        mock_context_builder,
        mock_consistency_checker,
        mock_storyline_manager,
        mock_plot_arc_repository,
        mock_llm_service
    ):
        """测试生成章节时包含幽灵批注"""
        from application.services.conflict_detection_service import ConflictDetectionService
        from application.dtos.ghost_annotation import GhostAnnotation
        from domain.bible.repositories.bible_repository import BibleRepository
        from domain.bible.entities.bible import Bible
        from domain.bible.entities.character import Character
        from domain.novel.value_objects.novel_id import NovelId

        # Mock ConflictDetectionService
        mock_conflict_service = Mock(spec=ConflictDetectionService)
        mock_conflict_service.detect.return_value = [
            GhostAnnotation(
                type="setting_conflict",
                severity="warning",
                message="设定库中李明为 [水系]，此处使用了 [火系]",
                entity_id="char-001",
                entity_name="李明",
                expected="水系",
                actual="火系"
            )
        ]

        # Mock BibleRepository
        mock_bible_repo = Mock(spec=BibleRepository)
        mock_bible = Mock(spec=Bible)
        mock_bible.characters = [
            Mock(spec=Character, id="char-001", name="李明", description="水系法师", attributes={})
        ]
        mock_bible.locations = []
        mock_bible_repo.get_by_novel_id.return_value = mock_bible

        # 创建带冲突检测的工作流
        workflow = AutoNovelGenerationWorkflow(
            context_builder=mock_context_builder,
            consistency_checker=mock_consistency_checker,
            storyline_manager=mock_storyline_manager,
            plot_arc_repository=mock_plot_arc_repository,
            llm_service=mock_llm_service,
            conflict_detection_service=mock_conflict_service,
            bible_repository=mock_bible_repo
        )

        result = await workflow.generate_chapter(
            novel_id="novel-1",
            chapter_number=1,
            outline="李明释放火球术攻击敌人"
        )

        # 验证返回结果包含批注
        assert isinstance(result, GenerationResult)
        assert len(result.ghost_annotations) == 1
        assert result.ghost_annotations[0].type == "setting_conflict"
        assert result.ghost_annotations[0].severity == "warning"
        assert "李明" in result.ghost_annotations[0].message
        assert "水系" in result.ghost_annotations[0].message
        assert "火系" in result.ghost_annotations[0].message

        # 验证冲突检测服务被调用
        mock_conflict_service.detect.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_chapter_no_annotations_when_no_conflicts(
        self,
        mock_context_builder,
        mock_consistency_checker,
        mock_storyline_manager,
        mock_plot_arc_repository,
        mock_llm_service
    ):
        """测试无冲突时返回空批注列表"""
        from application.services.conflict_detection_service import ConflictDetectionService

        # Mock ConflictDetectionService 返回空列表
        mock_conflict_service = Mock(spec=ConflictDetectionService)
        mock_conflict_service.detect.return_value = []

        workflow = AutoNovelGenerationWorkflow(
            context_builder=mock_context_builder,
            consistency_checker=mock_consistency_checker,
            storyline_manager=mock_storyline_manager,
            plot_arc_repository=mock_plot_arc_repository,
            llm_service=mock_llm_service,
            conflict_detection_service=mock_conflict_service
        )

        result = await workflow.generate_chapter(
            novel_id="novel-1",
            chapter_number=1,
            outline="李明与王总对话"
        )

        # 验证返回空批注列表
        assert isinstance(result, GenerationResult)
        assert len(result.ghost_annotations) == 0

    @pytest.mark.asyncio
    async def test_generate_chapter_without_conflict_service(
        self,
        workflow
    ):
        """测试没有冲突检测服务时不报错"""
        # workflow fixture 默认没有 conflict_detection_service
        result = await workflow.generate_chapter(
            novel_id="novel-1",
            chapter_number=1,
            outline="Chapter outline"
        )

        # 验证不报错，返回空批注列表
        assert isinstance(result, GenerationResult)
        assert len(result.ghost_annotations) == 0

    @pytest.mark.asyncio
    async def test_generate_chapter_stream_includes_ghost_annotations(
        self,
        mock_context_builder,
        mock_consistency_checker,
        mock_storyline_manager,
        mock_plot_arc_repository,
        mock_llm_service
    ):
        """测试流式生成时包含幽灵批注"""
        from application.services.conflict_detection_service import ConflictDetectionService
        from application.dtos.ghost_annotation import GhostAnnotation

        # Mock ConflictDetectionService
        mock_conflict_service = Mock(spec=ConflictDetectionService)
        mock_conflict_service.detect.return_value = [
            GhostAnnotation(
                type="setting_conflict",
                severity="warning",
                message="测试批注",
                entity_id="char-001",
                entity_name="测试角色"
            )
        ]

        workflow = AutoNovelGenerationWorkflow(
            context_builder=mock_context_builder,
            consistency_checker=mock_consistency_checker,
            storyline_manager=mock_storyline_manager,
            plot_arc_repository=mock_plot_arc_repository,
            llm_service=mock_llm_service,
            conflict_detection_service=mock_conflict_service
        )

        events = []
        async for event in workflow.generate_chapter_stream(
            novel_id="novel-1",
            chapter_number=1,
            outline="测试大纲"
        ):
            events.append(event)

        # 验证最后的 done 事件包含批注
        done_event = events[-1]
        assert done_event["type"] == "done"
        assert "ghost_annotations" in done_event
        assert len(done_event["ghost_annotations"]) == 1
        assert done_event["ghost_annotations"][0]["type"] == "setting_conflict"
        assert done_event["ghost_annotations"][0]["message"] == "测试批注"


class TestStyleIntegration:
    """测试风格指纹和俗套扫描集成"""

    @pytest.mark.asyncio
    async def test_generate_chapter_includes_style_warnings(
        self,
        mock_context_builder,
        mock_consistency_checker,
        mock_storyline_manager,
        mock_plot_arc_repository,
        mock_llm_service
    ):
        """测试生成章节时包含风格警告"""
        from application.services.cliche_scanner import ClicheScanner, ClicheHit

        # Mock ClicheScanner
        mock_scanner = Mock(spec=ClicheScanner)
        mock_scanner.scan_cliches.return_value = [
            ClicheHit(
                pattern="熊熊系列",
                text="熊熊烈火",
                start=10,
                end=14,
                severity="warning"
            ),
            ClicheHit(
                pattern="眼神闪过系列",
                text="眼中闪过一丝",
                start=50,
                end=57,
                severity="warning"
            )
        ]

        # 创建带俗套扫描的工作流
        workflow = AutoNovelGenerationWorkflow(
            context_builder=mock_context_builder,
            consistency_checker=mock_consistency_checker,
            storyline_manager=mock_storyline_manager,
            plot_arc_repository=mock_plot_arc_repository,
            llm_service=mock_llm_service,
            cliche_scanner=mock_scanner
        )

        result = await workflow.generate_chapter(
            novel_id="novel-1",
            chapter_number=1,
            outline="测试大纲"
        )

        # 验证返回结果包含风格警告
        assert isinstance(result, GenerationResult)
        assert len(result.style_warnings) == 2
        assert result.style_warnings[0].pattern == "熊熊系列"
        assert result.style_warnings[0].text == "熊熊烈火"
        assert result.style_warnings[1].pattern == "眼神闪过系列"

        # 验证扫描器被调用
        mock_scanner.scan_cliches.assert_called_once_with("Generated chapter content")

    @pytest.mark.asyncio
    async def test_generate_chapter_injects_fingerprint_summary(
        self,
        mock_context_builder,
        mock_consistency_checker,
        mock_storyline_manager,
        mock_plot_arc_repository,
        mock_llm_service
    ):
        """测试生成章节时注入风格指纹摘要"""
        from application.services.voice_fingerprint_service import VoiceFingerprintService
        from domain.novel.repositories.voice_fingerprint_repository import VoiceFingerprintRepository

        # Mock VoiceFingerprintService
        mock_fingerprint_repo = Mock(spec=VoiceFingerprintRepository)
        mock_fingerprint_repo.get_by_novel.return_value = {
            "metrics": {
                "adjective_density": 0.052,
                "avg_sentence_length": 18.5,
                "sentence_count": 100
            },
            "sample_count": 10
        }

        mock_fingerprint_service = Mock(spec=VoiceFingerprintService)
        mock_fingerprint_service.fingerprint_repo = mock_fingerprint_repo

        # 创建带风格指纹的工作流
        workflow = AutoNovelGenerationWorkflow(
            context_builder=mock_context_builder,
            consistency_checker=mock_consistency_checker,
            storyline_manager=mock_storyline_manager,
            plot_arc_repository=mock_plot_arc_repository,
            llm_service=mock_llm_service,
            voice_fingerprint_service=mock_fingerprint_service
        )

        result = await workflow.generate_chapter(
            novel_id="novel-1",
            chapter_number=1,
            outline="测试大纲"
        )

        # 验证 LLM 被调用
        assert mock_llm_service.generate.called

        # 获取传递给 LLM 的 prompt
        call_args = mock_llm_service.generate.call_args
        prompt = call_args[0][0]

        # 验证 prompt 包含风格指纹摘要
        assert "形容词密度" in prompt.system or "平均句长" in prompt.system

        # 验证指纹仓储被调用
        mock_fingerprint_repo.get_by_novel.assert_called_once_with("novel-1", pov_character_id=None)

    @pytest.mark.asyncio
    async def test_generate_chapter_without_style_services(
        self,
        workflow
    ):
        """测试没有风格服务时不报错"""
        # workflow fixture 默认没有 voice_fingerprint_service 和 cliche_scanner
        result = await workflow.generate_chapter(
            novel_id="novel-1",
            chapter_number=1,
            outline="测试大纲"
        )

        # 验证不报错，返回空风格警告列表
        assert isinstance(result, GenerationResult)
        assert len(result.style_warnings) == 0

    @pytest.mark.asyncio
    async def test_generate_chapter_stream_includes_style_warnings(
        self,
        mock_context_builder,
        mock_consistency_checker,
        mock_storyline_manager,
        mock_plot_arc_repository,
        mock_llm_service
    ):
        """测试流式生成时包含风格警告"""
        from application.services.cliche_scanner import ClicheScanner, ClicheHit

        # Mock ClicheScanner
        mock_scanner = Mock(spec=ClicheScanner)
        mock_scanner.scan_cliches.return_value = [
            ClicheHit(
                pattern="熊熊系列",
                text="熊熊烈火",
                start=10,
                end=14,
                severity="warning"
            )
        ]

        workflow = AutoNovelGenerationWorkflow(
            context_builder=mock_context_builder,
            consistency_checker=mock_consistency_checker,
            storyline_manager=mock_storyline_manager,
            plot_arc_repository=mock_plot_arc_repository,
            llm_service=mock_llm_service,
            cliche_scanner=mock_scanner
        )

        events = []
        async for event in workflow.generate_chapter_stream(
            novel_id="novel-1",
            chapter_number=1,
            outline="测试大纲"
        ):
            events.append(event)

        # 验证最后的 done 事件包含风格警告
        done_event = events[-1]
        assert done_event["type"] == "done"
        assert "style_warnings" in done_event
        assert len(done_event["style_warnings"]) == 1
        assert done_event["style_warnings"][0]["pattern"] == "熊熊系列"
        assert done_event["style_warnings"][0]["text"] == "熊熊烈火"
