"""ClaudeChapterSummarizer 测试"""
import os
import pytest
from unittest.mock import Mock, AsyncMock, patch
from infrastructure.ai.claude_chapter_summarizer import ClaudeChapterSummarizer
from infrastructure.ai.prompt_gateway import PromptGatewayRenderResult
from infrastructure.ai.prompt_contracts.chapter_summarizer import CHAPTER_SUMMARIZER_CONTRACT
from domain.ai.services.llm_service import GenerationResult
from domain.ai.value_objects.prompt import Prompt
from domain.ai.value_objects.token_usage import TokenUsage


class TestClaudeChapterSummarizer:
    """ClaudeChapterSummarizer 测试"""

    @pytest.fixture
    def mock_llm_service(self):
        """创建 mock LLM service"""
        service = Mock()
        service.generate = AsyncMock()
        return service

    @pytest.fixture
    def prompt_gateway(self):
        """创建 fake prompt gateway，避免单测依赖全局 CPMS/SQLite 状态。"""
        gateway = Mock()

        def _render(_contract, variables):
            return PromptGatewayRenderResult(
                prompt=Prompt(
                    system=f"章节摘要，限制 {variables['max_length']} 字",
                    user=f"请摘要：{variables['content']}",
                ),
                node_key=CHAPTER_SUMMARIZER_CONTRACT.node_key,
                contract_version=CHAPTER_SUMMARIZER_CONTRACT.version,
                source="test",
                variables=variables,
            )

        gateway.render.side_effect = _render
        return gateway

    @pytest.fixture
    def summarizer(self, mock_llm_service, prompt_gateway):
        """创建 summarizer 实例"""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-api-key"}):
            summarizer = ClaudeChapterSummarizer(
                mock_llm_service,
                prompt_gateway=prompt_gateway,
            )
            yield summarizer

    @pytest.mark.asyncio
    async def test_summarize_basic(self, summarizer, mock_llm_service):
        """测试基本摘要生成"""
        content = "This is a long chapter content. " * 100
        expected_summary = "This is a concise summary of the chapter."

        mock_result = GenerationResult(
            content=expected_summary,
            token_usage=TokenUsage(input_tokens=100, output_tokens=20)
        )
        mock_llm_service.generate.return_value = mock_result

        result = await summarizer.summarize(content)

        assert result == expected_summary
        mock_llm_service.generate.assert_called_once()

        # Verify the CPMS prompt was rendered correctly
        call_args = mock_llm_service.generate.call_args
        prompt = call_args[0][0]
        assert "摘要" in prompt.system
        assert content.strip() in prompt.user

    @pytest.mark.asyncio
    async def test_summarize_with_max_length(self, summarizer, mock_llm_service):
        """测试指定最大长度的摘要"""
        content = "Chapter content here."
        max_length = 150
        expected_summary = "Short summary."

        mock_result = GenerationResult(
            content=expected_summary,
            token_usage=TokenUsage(input_tokens=50, output_tokens=10)
        )
        mock_llm_service.generate.return_value = mock_result

        result = await summarizer.summarize(content, max_length=max_length)

        assert result == expected_summary

        # Verify max_length was included in the prompt
        call_args = mock_llm_service.generate.call_args
        prompt = call_args[0][0]
        assert str(max_length) in prompt.system or str(max_length) in prompt.user

    @pytest.mark.asyncio
    async def test_summarize_empty_content(self, summarizer, mock_llm_service):
        """测试空内容处理"""
        with pytest.raises(ValueError, match="章节内容不能为空"):
            await summarizer.summarize("")

    @pytest.mark.asyncio
    async def test_summarize_whitespace_only(self, summarizer, mock_llm_service):
        """测试仅空白字符的内容"""
        with pytest.raises(ValueError, match="章节内容不能为空"):
            await summarizer.summarize("   \n\t  ")

    @pytest.mark.asyncio
    async def test_summarize_api_error(self, summarizer, mock_llm_service):
        """测试 API 错误处理"""
        content = "Some content"
        mock_llm_service.generate.side_effect = RuntimeError("API Error")

        with pytest.raises(RuntimeError, match="章节摘要生成失败"):
            await summarizer.summarize(content)

    def test_missing_api_key(self, mock_llm_service):
        """测试缺少 API key"""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="缺少 ANTHROPIC_API_KEY"):
                ClaudeChapterSummarizer(mock_llm_service)

    def test_auth_token_fallback_allows_initialization(self, mock_llm_service):
        """ANTHROPIC_AUTH_TOKEN 与控制面板 env fallback 保持一致。"""
        with patch.dict(os.environ, {"ANTHROPIC_AUTH_TOKEN": "test-token"}, clear=True):
            summarizer = ClaudeChapterSummarizer(mock_llm_service)

        assert summarizer.llm_service is mock_llm_service

    @pytest.mark.asyncio
    async def test_summarize_uses_injected_model(self, mock_llm_service, prompt_gateway):
        """显式注入模型时不依赖 WRITING_MODEL。"""
        summarizer = ClaudeChapterSummarizer(
            mock_llm_service,
            api_key="test-api-key",
            model="writer-test-model",
            prompt_gateway=prompt_gateway,
        )
        mock_llm_service.generate.return_value = GenerationResult(
            content="summary",
            token_usage=TokenUsage(input_tokens=10, output_tokens=10),
        )

        await summarizer.summarize("chapter content")

        config = mock_llm_service.generate.call_args[0][1]
        assert config.model == "writer-test-model"


@pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY") or not os.getenv("ANTHROPIC_MODEL"),
    reason="ANTHROPIC_API_KEY and ANTHROPIC_MODEL must both be set for live integration tests"
)
class TestClaudeChapterSummarizerIntegration:
    """ClaudeChapterSummarizer 集成测试（需要真实 API key 与模型 ID）"""

    @pytest.fixture
    def summarizer(self):
        """创建真实 summarizer 实例"""
        from infrastructure.ai.config.settings import Settings
        from infrastructure.ai.providers.anthropic_provider import AnthropicProvider

        settings = Settings(
            api_key=os.getenv("ANTHROPIC_API_KEY"),
            default_model=os.getenv("ANTHROPIC_MODEL", ""),
        )
        llm_service = AnthropicProvider(settings)
        return ClaudeChapterSummarizer(llm_service)

    @pytest.mark.asyncio
    async def test_real_summarize(self, summarizer):
        """测试真实摘要生成"""
        content = """
        In the beginning of the chapter, the protagonist wakes up in a strange room.
        They don't remember how they got there. The walls are covered with mysterious symbols.
        As they explore the room, they find a hidden door behind a bookshelf.
        The door leads to a long corridor with flickering lights.
        At the end of the corridor, they hear voices speaking in an unknown language.
        """ * 10  # Make it longer to test summarization

        result = await summarizer.summarize(content, max_length=200)

        assert result is not None
        assert len(result) > 0
        assert len(result) <= 250  # Allow some buffer
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_real_summarize_custom_length(self, summarizer):
        """测试自定义长度的真实摘要"""
        content = "This is a test chapter. " * 50

        result = await summarizer.summarize(content, max_length=100)

        assert result is not None
        assert len(result) > 0
        assert len(result) <= 120  # Allow some buffer
