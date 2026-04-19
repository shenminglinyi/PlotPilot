"""AnthropicProvider 测试"""
import pytest
from unittest.mock import AsyncMock, Mock
from domain.ai.value_objects.prompt import Prompt
from domain.ai.services.llm_service import GenerationConfig
from infrastructure.ai.config.settings import Settings
from infrastructure.ai.providers.anthropic_provider import AnthropicProvider


class TestAnthropicProvider:
    """AnthropicProvider 测试"""

    @pytest.fixture
    def settings(self):
        """创建测试配置"""
        return Settings(api_key="test-api-key", default_model="test-anthropic-model")

    @pytest.fixture
    def provider(self, settings):
        """创建 provider 实例"""
        return AnthropicProvider(settings)

    def test_initialization(self, provider, settings):
        """测试初始化"""
        assert provider.settings == settings
        assert provider.client is not None

    @pytest.mark.asyncio
    async def test_generate_with_default_config(self, provider):
        """测试使用默认配置生成"""
        prompt = Prompt(system="You are helpful", user="Hello")
        config = GenerationConfig(
            model="claude-3-5-sonnet-20241022",
            temperature=0.7,
            max_tokens=4096
        )

        mock_create = AsyncMock(return_value=Mock(
            content=[Mock(type="text", text="Hi there!")],
            usage=Mock(input_tokens=10, output_tokens=5)
        ))
        provider.async_client.messages.create = mock_create

        result = await provider.generate(prompt, config)

        assert result.content == "Hi there!"
        assert result.token_usage.input_tokens == 10
        assert result.token_usage.output_tokens == 5

        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["model"] == "claude-3-5-sonnet-20241022"
        assert call_kwargs['temperature'] == 0.7
        assert call_kwargs['max_tokens'] == 4096

    @pytest.mark.asyncio
    async def test_generate_with_custom_config(self, provider):
        """测试使用自定义配置生成"""
        prompt = Prompt(system="You are helpful", user="Hello")
        config = GenerationConfig(
            model="claude-3-opus-20240229",
            temperature=0.5,
            max_tokens=2048
        )

        mock_create = AsyncMock(return_value=Mock(
            content=[Mock(type="text", text="Response")],
            usage=Mock(input_tokens=20, output_tokens=10)
        ))
        provider.async_client.messages.create = mock_create

        await provider.generate(prompt, config)

        call_kwargs = mock_create.call_args[1]
        assert call_kwargs['model'] == "claude-3-opus-20240229"
        assert call_kwargs['temperature'] == 0.5
        assert call_kwargs['max_tokens'] == 2048

    @pytest.mark.asyncio
    async def test_generate_accepts_text_blocks_without_type(self, provider):
        """测试兼容端点未返回标准 type=text 时仍能提取文本。"""
        prompt = Prompt(system="You are helpful", user="Hello")
        config = GenerationConfig()

        provider.async_client.messages.create = AsyncMock(return_value=Mock(
            content=[Mock(text='{"ok": true}')],
            usage=Mock(input_tokens=10, output_tokens=5)
        ))

        result = await provider.generate(prompt, config)

        assert result.content == '{"ok": true}'

    @pytest.mark.asyncio
    async def test_generate_accepts_json_blocks(self, provider):
        """测试 JSON block 可回退为字符串内容。"""
        prompt = Prompt(system="You are helpful", user="Hello")
        config = GenerationConfig()

        provider.async_client.messages.create = AsyncMock(return_value=Mock(
            content=[Mock(type="output_json", json={"score": 88})],
            usage=Mock(input_tokens=10, output_tokens=5)
        ))

        result = await provider.generate(prompt, config)

        assert result.content == '{"score": 88}'

    @pytest.mark.asyncio
    async def test_generate_empty_content(self, provider):
        """测试 API 返回空 content"""
        prompt = Prompt(system="You are helpful", user="Hello")
        config = GenerationConfig()

        provider.async_client.messages.create = AsyncMock(return_value=Mock(
            content=[],
            usage=Mock(input_tokens=10, output_tokens=5)
        ))

        with pytest.raises(RuntimeError, match="empty content"):
            await provider.generate(prompt, config)

    @pytest.mark.asyncio
    async def test_generate_api_error(self, provider):
        """测试 API 错误转换"""
        prompt = Prompt(system="You are helpful", user="Hello")
        config = GenerationConfig()

        mock_create = AsyncMock(side_effect=Exception("Anthropic API Error"))
        provider.async_client.messages.create = mock_create

        with pytest.raises(RuntimeError, match="Failed to generate text"):
            await provider.generate(prompt, config)

    @pytest.mark.asyncio
    async def test_generate_network_error(self, provider):
        """测试网络错误处理"""
        prompt = Prompt(system="You are helpful", user="Hello")
        config = GenerationConfig()

        mock_create = AsyncMock(side_effect=ConnectionError("Network unreachable"))
        provider.async_client.messages.create = mock_create

        with pytest.raises(RuntimeError, match="Failed to generate text"):
            await provider.generate(prompt, config)

    def test_missing_api_key(self):
        """测试缺少 API key"""
        settings = Settings(api_key=None)

        with pytest.raises(ValueError, match="API key is required"):
            AnthropicProvider(settings)
