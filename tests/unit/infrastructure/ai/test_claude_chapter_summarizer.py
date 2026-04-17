"""ClaudeChapterSummarizer 测试"""
import os
import pytest
from unittest.mock import Mock, AsyncMock, patch
from infrastructure.ai.claude_chapter_summarizer import ClaudeChapterSummarizer
from domain.ai.services.llm_service import GenerationResult
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
    def summarizer(self, mock_llm_service):
        """创建 summarizer 实例"""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-api-key"}):
            summarizer = ClaudeChapterSummarizer(mock_llm_service)
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

        # Verify the prompt was constructed correctly
        call_args = mock_llm_service.generate.call_args
        prompt = call_args[0][0]
        assert "summarize" in prompt.system.lower()
        assert content in prompt.user

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
        with pytest.raises(ValueError, match="Content cannot be empty"):
            await summarizer.summarize("")

    @pytest.mark.asyncio
    async def test_summarize_whitespace_only(self, summarizer, mock_llm_service):
        """测试仅空白字符的内容"""
        with pytest.raises(ValueError, match="Content cannot be empty"):
            await summarizer.summarize("   \n\t  ")

    @pytest.mark.asyncio
    async def test_summarize_api_error(self, summarizer, mock_llm_service):
        """测试 API 错误处理"""
        content = "Some content"
        mock_llm_service.generate.side_effect = RuntimeError("API Error")

        with pytest.raises(RuntimeError, match="Failed to summarize chapter"):
            await summarizer.summarize(content)

    def test_missing_api_key(self, mock_llm_service):
        """测试缺少 API key"""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="ANTHROPIC_API_KEY environment variable is required"):
                ClaudeChapterSummarizer(mock_llm_service)


@pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY")
    or os.getenv("ANTHROPIC_API_KEY", "").startswith("test-"),
    reason="ANTHROPIC_API_KEY not set or placeholder"
)
class TestClaudeChapterSummarizerIntegration:
    """ClaudeChapterSummarizer 集成测试（需要真实 API key）"""

    @pytest.fixture
    def summarizer(self):
        """创建真实 summarizer 实例"""
        from infrastructure.ai.config.settings import Settings
        from infrastructure.ai.providers.anthropic_provider import AnthropicProvider

        settings = Settings(api_key=os.getenv("ANTHROPIC_API_KEY"))
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
