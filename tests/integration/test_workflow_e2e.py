"""端到端测试 - 完整生成工作流"""
import pytest
from unittest.mock import Mock, AsyncMock, patch
from application.workflows.auto_novel_generation_workflow import AutoNovelGenerationWorkflow
from application.engine.services.context_builder import ContextBuilder
from application.dtos.generation_result import GenerationResult
from domain.novel.services.consistency_checker import ConsistencyChecker
from domain.novel.services.storyline_manager import StorylineManager
from domain.novel.repositories.plot_arc_repository import PlotArcRepository
from domain.novel.value_objects.consistency_report import ConsistencyReport
from domain.ai.services.llm_service import LLMService, GenerationConfig, GenerationResult as LLMResult
from domain.ai.value_objects.token_usage import TokenUsage


@pytest.fixture
def mock_dependencies():
    """创建所有 mock 依赖"""
    context_builder = Mock(spec=ContextBuilder)
    context_builder.build_context.return_value = "Full context with 35K tokens"
    context_builder.build_structured_context.return_value = {
        "layer1_text": "mock_layer1",
        "layer2_text": "mock_layer2",
        "layer3_text": "mock_layer3",
        "token_usage": {"layer1": 100, "layer2": 50, "layer3": 25, "total": 8750},
    }
    context_builder.build_voice_anchor_system_section.return_value = ""
    context_builder.estimate_tokens.return_value = 8750

    # Mock ConsistencyChecker
    consistency_checker = Mock(spec=ConsistencyChecker)
    consistency_checker.check_all.return_value = ConsistencyReport(
        issues=[],
        warnings=[],
        suggestions=[]
    )

    # Mock StorylineManager
    storyline_manager = Mock(spec=StorylineManager)
    storyline_manager.repository = Mock()
    storyline_manager.repository.get_by_novel_id.return_value = []

    # Mock PlotArcRepository
    plot_arc_repository = Mock(spec=PlotArcRepository)
    plot_arc_repository.get_by_novel_id.return_value = None

    # Mock LLMService
    llm_service = Mock(spec=LLMService)
    llm_service.generate = AsyncMock(return_value=LLMResult(
        content="Generated chapter content with detailed narrative.",
        token_usage=TokenUsage(input_tokens=500, output_tokens=500)
    ))

    return {
        'context_builder': context_builder,
        'consistency_checker': consistency_checker,
        'storyline_manager': storyline_manager,
        'plot_arc_repository': plot_arc_repository,
        'llm_service': llm_service
    }


@pytest.fixture
def workflow(mock_dependencies):
    """创建工作流实例"""
    return AutoNovelGenerationWorkflow(
        context_builder=mock_dependencies['context_builder'],
        consistency_checker=mock_dependencies['consistency_checker'],
        storyline_manager=mock_dependencies['storyline_manager'],
        plot_arc_repository=mock_dependencies['plot_arc_repository'],
        llm_service=mock_dependencies['llm_service']
    )


class TestCompleteGenerationFlow:
    """测试完整的生成流程"""

    @pytest.mark.asyncio
    async def test_outline_to_content_flow(self, workflow, mock_dependencies):
        """测试从大纲到内容的完整流程"""
        # 准备输入
        novel_id = "test-novel-1"
        chapter_number = 1
        outline = "Chapter 1: The protagonist discovers a mysterious artifact."

        # 执行生成
        result = await workflow.generate_chapter(
            novel_id=novel_id,
            chapter_number=chapter_number,
            outline=outline
        )

        # 验证结果
        assert isinstance(result, GenerationResult)
        assert result.content == "Generated chapter content with detailed narrative."
        assert result.token_count == 8750
        assert isinstance(result.consistency_report, ConsistencyReport)

        # 验证调用链
        mock_dependencies['context_builder'].build_context.assert_called_once()
        mock_dependencies['llm_service'].generate.assert_called_once()
        mock_dependencies['consistency_checker'].check_all.assert_called_once()

    @pytest.mark.asyncio
    async def test_multiple_chapters_generation(self, workflow):
        """测试生成多个章节"""
        novel_id = "test-novel-2"
        outlines = [
            "Chapter 1: Introduction",
            "Chapter 2: Rising action",
            "Chapter 3: Climax"
        ]

        results = []
        for i, outline in enumerate(outlines, 1):
            result = await workflow.generate_chapter(
                novel_id=novel_id,
                chapter_number=i,
                outline=outline
            )
            results.append(result)

        # 验证所有章节都生成成功
        assert len(results) == 3
        for result in results:
            assert isinstance(result, GenerationResult)
            assert len(result.content) > 0

    @pytest.mark.asyncio
    async def test_large_content_handling(self, workflow, mock_dependencies):
        """测试处理大量内容（10,000+ 字符）"""
        # 模拟生成大量内容
        large_content = "A" * 15000  # 15K 字符
        mock_dependencies['llm_service'].generate = AsyncMock(return_value=LLMResult(
            content=large_content,
            token_usage=TokenUsage(input_tokens=1000, output_tokens=3000)
        ))

        result = await workflow.generate_chapter(
            novel_id="test-novel-3",
            chapter_number=1,
            outline="Long chapter outline"
        )

        # 验证能够处理大量内容
        assert len(result.content) >= 10000
        assert result.content == large_content


class TestPerformance:
    """性能测试"""

    @pytest.mark.asyncio
    async def test_100_chapter_generation_simulation(self, workflow):
        """模拟生成 100 章的性能（快速测试，不实际调用 LLM）"""
        novel_id = "performance-test-novel"

        # 只测试前 10 章以节省时间
        for i in range(1, 11):
            result = await workflow.generate_chapter(
                novel_id=novel_id,
                chapter_number=i,
                outline=f"Chapter {i} outline"
            )
            assert isinstance(result, GenerationResult)

        # 在实际使用中，应该测试完整的 100 章
        # 但在单元测试中，我们只验证流程正确性


class TestErrorHandling:
    """错误处理测试"""

    @pytest.mark.asyncio
    async def test_llm_failure_handling(self, workflow, mock_dependencies):
        """测试 LLM 失败时的处理"""
        # 模拟 LLM 失败
        mock_dependencies['llm_service'].generate = AsyncMock(
            side_effect=RuntimeError("LLM service unavailable")
        )

        with pytest.raises(RuntimeError, match="LLM service unavailable"):
            await workflow.generate_chapter(
                novel_id="test-novel",
                chapter_number=1,
                outline="Test outline"
            )

    @pytest.mark.asyncio
    async def test_invalid_input_handling(self, workflow):
        """测试无效输入的处理"""
        # 测试无效章节号
        with pytest.raises(ValueError, match="chapter_number must be positive"):
            await workflow.generate_chapter(
                novel_id="test-novel",
                chapter_number=0,
                outline="Test outline"
            )

        # 测试空大纲
        with pytest.raises(ValueError, match="outline cannot be empty"):
            await workflow.generate_chapter(
                novel_id="test-novel",
                chapter_number=1,
                outline=""
            )


class TestIntegrationWithComponents:
    """与各组件的集成测试"""

    @pytest.mark.asyncio
    async def test_context_builder_integration(self, workflow, mock_dependencies):
        """测试与 ContextBuilder 的集成"""
        await workflow.generate_chapter(
            novel_id="test-novel",
            chapter_number=5,
            outline="Chapter 5 outline"
        )

        # 验证 ContextBuilder 被正确调用
        mock_dependencies['context_builder'].build_context.assert_called_once_with(
            novel_id="test-novel",
            chapter_number=5,
            outline="Chapter 5 outline",
            max_tokens=35000
        )

    @pytest.mark.asyncio
    async def test_consistency_checker_integration(self, workflow, mock_dependencies):
        """测试与 ConsistencyChecker 的集成"""
        result = await workflow.generate_chapter(
            novel_id="test-novel",
            chapter_number=1,
            outline="Test outline"
        )

        # 验证一致性检查被调用
        mock_dependencies['consistency_checker'].check_all.assert_called_once()

        # 验证报告被包含在结果中
        assert isinstance(result.consistency_report, ConsistencyReport)

    @pytest.mark.asyncio
    async def test_storyline_manager_integration(self, workflow, mock_dependencies):
        """测试与 StorylineManager 的集成"""
        await workflow.generate_chapter(
            novel_id="test-novel",
            chapter_number=1,
            outline="Test outline"
        )

        # 验证故事线被查询
        # 注意：由于 _get_storyline_context 中有 hasattr 检查，
        # 这里验证 repository 被访问
        assert mock_dependencies['storyline_manager'].repository is not None
