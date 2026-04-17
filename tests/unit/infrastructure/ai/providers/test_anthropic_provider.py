"""AnthropicProvider 测试"""
import json
import pytest
from unittest.mock import AsyncMock, Mock, patch
from domain.ai.value_objects.prompt import Prompt
from domain.ai.services.llm_service import GenerationConfig
from infrastructure.ai.config.settings import Settings
from infrastructure.ai.providers.anthropic_provider import AnthropicProvider


class TestAnthropicProvider:
    """AnthropicProvider 测试"""

    @pytest.fixture(autouse=True)
    def clear_proxy_env(self, monkeypatch):
        """隔离宿主机代理环境，避免污染测试。"""
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
            monkeypatch.delenv(key, raising=False)

    @pytest.fixture
    def settings(self):
        """创建测试配置"""
        return Settings(api_key="test-api-key")

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

        with patch.object(provider.async_client.messages, 'create', new_callable=AsyncMock) as mock_create:
            mock_create.return_value = Mock(
                content=[Mock(type="text", text="Hi there!")],
                usage=Mock(input_tokens=10, output_tokens=5)
            )
            result = await provider.generate(prompt, config)

            assert result.content == "Hi there!"
            assert result.token_usage.input_tokens == 10
            assert result.token_usage.output_tokens == 5

            mock_create.assert_called_once()
            call_kwargs = mock_create.call_args[1]
            assert call_kwargs['model'] == "claude-3-5-sonnet-20241022"
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

        with patch.object(provider.async_client.messages, 'create', new_callable=AsyncMock) as mock_create:
            mock_create.return_value = Mock(
                content=[Mock(type="text", text="Response")],
                usage=Mock(input_tokens=20, output_tokens=10)
            )
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

        assert json.loads(result.content) == {"score": 88}

    @pytest.mark.asyncio
    async def test_generate_accepts_tool_use_input_blocks(self, provider):
        """测试 tool_use block 的 input 内容可被序列化为文本。"""
        prompt = Prompt(system="You are helpful", user="Hello")
        config = GenerationConfig()

        provider.async_client.messages.create = AsyncMock(return_value=Mock(
            content=[Mock(type="tool_use", input={"summary": "ok", "count": 2})],
            usage=Mock(input_tokens=10, output_tokens=5)
        ))

        result = await provider.generate(prompt, config)

        assert json.loads(result.content) == {"summary": "ok", "count": 2}

    @pytest.mark.asyncio
    async def test_generate_empty_content(self, provider):
        """测试 API 返回空 content"""
        prompt = Prompt(system="You are helpful", user="Hello")
        config = GenerationConfig()

        with patch.object(provider.async_client.messages, 'create', new_callable=AsyncMock) as mock_create:
            mock_create.return_value = Mock(
                content=[],
                usage=Mock(input_tokens=10, output_tokens=5)
            )
            with pytest.raises(RuntimeError, match="empty content"):
                await provider.generate(prompt, config)

    @pytest.mark.asyncio
    async def test_generate_api_error(self, provider):
        """测试 API 错误转换"""
        prompt = Prompt(system="You are helpful", user="Hello")
        config = GenerationConfig()

        with patch.object(provider.async_client.messages, 'create', new_callable=AsyncMock) as mock_create:
            mock_create.side_effect = Exception("Anthropic API Error")

        with pytest.raises(RuntimeError, match="Failed to generate text"):
            await provider.generate(prompt, config)

    @pytest.mark.asyncio
    async def test_generate_network_error(self, provider):
        """测试网络错误处理"""
        prompt = Prompt(system="You are helpful", user="Hello")
        config = GenerationConfig()

        with patch.object(provider.async_client.messages, 'create', new_callable=AsyncMock) as mock_create:
            mock_create.side_effect = ConnectionError("Network unreachable")

        with pytest.raises(RuntimeError, match="Failed to generate text"):
            await provider.generate(prompt, config)

    def test_missing_api_key(self):
        """测试缺少 API key"""
        settings = Settings(api_key=None)

        with pytest.raises(ValueError, match="API key is required"):
            AnthropicProvider(settings)

    def test_initialization_ignores_ambient_proxy_env(self, monkeypatch):
        """测试初始化时不信任环境代理变量"""
        monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:18080")
        monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:18080")
        monkeypatch.setenv("ALL_PROXY", "socks5://127.0.0.1:10808")

        sync_client_kwargs = {}
        async_client_kwargs = {}

        def _fake_sync_client(**kwargs):
            sync_client_kwargs.update(kwargs)
            return Mock()

        def _fake_async_client(**kwargs):
            async_client_kwargs.update(kwargs)
            return Mock()

        settings = Settings(api_key="test-api-key", base_url="https://api.example.com")

        with patch("infrastructure.ai.providers.anthropic_provider.Anthropic", side_effect=_fake_sync_client), \
             patch("infrastructure.ai.providers.anthropic_provider.AsyncAnthropic", side_effect=_fake_async_client):
            AnthropicProvider(settings)

        assert sync_client_kwargs["http_client"].trust_env is False
        assert async_client_kwargs["http_client"].trust_env is False

    @pytest.mark.asyncio
    async def test_stream_generate_ignores_ambient_proxy_env(self, provider):
        """测试流式正文请求不信任环境代理变量"""
        prompt = Prompt(system="You are helpful", user="Hello")
        config = GenerationConfig(model="claude-3-5-sonnet-20241022", temperature=0.7, max_tokens=32)

        class _FakeStreamResponse:
            status_code = 200

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def aread(self):
                return b""

            async def aiter_text(self):
                yield ""

        class _FakeAsyncClient:
            def __init__(self, *args, **kwargs):
                self.kwargs = kwargs

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            def stream(self, *args, **kwargs):
                return _FakeStreamResponse()

        with patch("infrastructure.ai.providers.anthropic_provider.httpx.AsyncClient", side_effect=_FakeAsyncClient) as mock_async_client:
            chunks = [chunk async for chunk in provider.stream_generate(prompt, config)]

        assert chunks == []
        assert mock_async_client.call_args.kwargs["trust_env"] is False
