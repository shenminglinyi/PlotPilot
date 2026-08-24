"""OpenAIProvider 测试"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from application.ai.llm_retry_policy import LLM_MAX_TOTAL_ATTEMPTS
from domain.ai.services.llm_service import DEFAULT_MAX_OUTPUT_TOKENS, GenerationConfig
from domain.ai.value_objects.prompt import Prompt
from infrastructure.ai.config.settings import Settings
from infrastructure.ai.providers.openai_provider import OpenAIProvider


class _FakeStream:
    def __init__(self, chunks):
        self._chunks = iter(chunks)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._chunks)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class TestOpenAIProviderLegacy:
    """use_legacy_chat_completions=True → Chat Completions API"""

    @pytest.fixture
    def settings(self):
        return Settings(api_key="test-api-key", use_legacy_chat_completions=True)

    @pytest.fixture
    def provider(self, settings):
        return OpenAIProvider(settings)

    def test_initialization(self, provider, settings):
        assert provider.settings == settings
        assert provider.async_client is not None
        assert provider._use_legacy is True

    def test_http_timeout_uses_settings(self):
        provider = OpenAIProvider(
            Settings(
                api_key="test-api-key",
                connect_timeout=4,
                read_timeout=40,
                write_timeout=8,
                pool_timeout=2,
            )
        )

        timeout = provider._http_client.timeout
        assert timeout.connect == 4
        assert timeout.read == 40
        assert timeout.write == 8
        assert timeout.pool == 2

    @pytest.mark.anyio
    async def test_generate_requires_model_id(self, provider):
        prompt = Prompt(system="s", user="u")
        config = GenerationConfig(model="", max_tokens=32, temperature=0.5)
        with pytest.raises(ValueError, match="未配置模型 ID"):
            await provider.generate(prompt, config)

    @pytest.mark.anyio
    async def test_generate_non_stream(self, provider):
        prompt = Prompt(system="You are helpful", user="Hello")
        config = GenerationConfig(model="gpt-4o", temperature=0.7, max_tokens=4096)
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Hi there!"))],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
        )

        with patch.object(provider.async_client.chat.completions, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = response

            result = await provider.generate(prompt, config)

            assert result.content == "Hi there!"
            assert result.token_usage.input_tokens == 10
            assert result.token_usage.output_tokens == 5

            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs["model"] == "gpt-4o"
            assert call_kwargs["temperature"] == 0.7
            assert call_kwargs["max_tokens"] == DEFAULT_MAX_OUTPUT_TOKENS

    @pytest.mark.anyio
    async def test_generate_accepts_message_content_as_list_of_text_parts(self, provider):
        """聚合网关 / 新协议常返回 content 为 [{type,text}] 列表，而非纯字符串。"""
        prompt = Prompt(system="s", user="u")
        config = GenerationConfig(model="gpt-4o", temperature=0, max_tokens=64)
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=[
                            {"type": "text", "text": '{"a":'},
                            {"type": "text", "text": ' 1}'},
                        ]
                    )
                )
            ],
            usage=SimpleNamespace(prompt_tokens=3, completion_tokens=4),
        )

        with patch.object(provider.async_client.chat.completions, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = response

            result = await provider.generate(prompt, config)

            assert result.content == '{"a":\n 1}'

    @pytest.mark.anyio
    async def test_generate_json_schema_downgrades_within_same_protocol(self, provider):
        """同协议能力适配：网关拒绝 json_schema → 重发 json_object（允许的 A→B 链）。"""
        prompt = Prompt(system="s", user="u")
        config = GenerationConfig(
            model="gpt-4o",
            response_format={"type": "json_schema", "json_schema": {"name": "x"}},
        )
        ok_response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"a":1}'))],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
        )
        import httpx as _httpx
        import openai as _openai

        request = _httpx.Request("POST", "https://api.example/v1/chat/completions")
        bad_request = _openai.BadRequestError(
            "json_schema unsupported",
            response=_httpx.Response(400, request=request),
            body=None,
        )

        with patch.object(provider.async_client.chat.completions, "create", new_callable=AsyncMock) as mock_create:
            mock_create.side_effect = [bad_request, ok_response]

            result = await provider.generate(prompt, config)

            assert result.content == '{"a":1}'
            second_call = mock_create.await_args_list[1].kwargs
            assert second_call["response_format"]["type"] == "json_object"

    @pytest.mark.anyio
    async def test_stream_generate(self, provider):
        prompt = Prompt(system="You are helpful", user="Hello")
        config = GenerationConfig(model="gpt-4o", temperature=0.7, max_tokens=32)
        stream = _FakeStream([
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="Hi"))]),
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=" there"))]),
            SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=None))]),
        ])

        with patch.object(provider.async_client.chat.completions, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = stream

            chunks = [chunk async for chunk in provider.stream_generate(prompt, config)]

            assert chunks == ["Hi", " there"]
            assert mock_create.await_args.kwargs["stream"] is True

    @pytest.mark.anyio
    async def test_generate_empty_content_raises(self, provider):
        prompt = Prompt(system="You are helpful", user="Hello")
        config = GenerationConfig(model="test-model")
        empty_response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=None))],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
        )

        empty_stream = _FakeStream([
            SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content=None))],
                usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
            ),
        ])

        with patch.object(provider.async_client.chat.completions, "create", new_callable=AsyncMock) as mock_create:
            mock_create.side_effect = [empty_response, empty_stream] * LLM_MAX_TOTAL_ATTEMPTS

            with pytest.raises(RuntimeError, match="empty content"):
                await provider.generate(prompt, config)

            # 全程停留在 Chat Completions 协议内（非流式→流式聚合），无跨协议切换
            assert mock_create.await_count == LLM_MAX_TOTAL_ATTEMPTS * 2

    def test_missing_api_key(self):
        with pytest.raises(ValueError, match="API key is required"):
            OpenAIProvider(Settings(api_key=None))


class TestOpenAIProviderResponses:
    """use_legacy_chat_completions=False（默认）→ Responses API"""

    @pytest.fixture
    def settings(self):
        return Settings(api_key="test-api-key", use_legacy_chat_completions=False)

    @pytest.fixture
    def provider(self, settings):
        return OpenAIProvider(settings)

    def test_default_uses_responses(self, provider):
        assert provider._use_legacy is False

    @pytest.mark.anyio
    async def test_generate_non_stream(self, provider):
        prompt = Prompt(system="You are helpful", user="Hello")
        config = GenerationConfig(model="gpt-4o", temperature=0.5, max_tokens=2048)
        response = SimpleNamespace(
            output=[
                SimpleNamespace(
                    type="message",
                    content=[SimpleNamespace(type="text", text="Hi from responses!")],
                )
            ],
            usage=SimpleNamespace(prompt_tokens=8, completion_tokens=4),
        )

        with patch.object(provider.async_client.responses, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = response

            result = await provider.generate(prompt, config)

            assert result.content == "Hi from responses!"
            assert result.token_usage.input_tokens == 8
            assert result.token_usage.output_tokens == 4

            call_kwargs = mock_create.call_args.kwargs
            assert call_kwargs["model"] == "gpt-4o"
            assert call_kwargs["temperature"] == 0.5
            assert call_kwargs["max_output_tokens"] == DEFAULT_MAX_OUTPUT_TOKENS

    @pytest.mark.anyio
    async def test_generate_responses_joins_multiple_text_parts(self, provider):
        prompt = Prompt(system="s", user="u")
        config = GenerationConfig(model="gpt-4o", temperature=0, max_tokens=32)
        response = SimpleNamespace(
            output=[
                SimpleNamespace(
                    type="message",
                    content=[SimpleNamespace(type="text", text="Line1")],
                ),
                SimpleNamespace(
                    type="message",
                    content=[SimpleNamespace(type="text", text="Line2")],
                ),
            ],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=2),
        )

        with patch.object(provider.async_client.responses, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = response

            result = await provider.generate(prompt, config)

            assert result.content == "Line1\nLine2"

    @pytest.mark.anyio
    async def test_stream_generate(self, provider):
        prompt = Prompt(system="You are helpful", user="Hello")
        config = GenerationConfig(model="gpt-4o", temperature=0.7, max_tokens=32)
        stream = _FakeStream([
            SimpleNamespace(
                type="response.content_part.added",
                part=SimpleNamespace(type="text", text="Hello"),
            ),
            SimpleNamespace(type="response.completed"),
        ])

        with patch.object(provider.async_client.responses, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = stream

            chunks = [chunk async for chunk in provider.stream_generate(prompt, config)]

            assert chunks == ["Hello"]
            assert mock_create.await_args.kwargs["stream"] is True

    @pytest.mark.anyio
    async def test_stream_generate_extracts_output_text_delta(self, provider):
        prompt = Prompt(system="You are helpful", user="Hello")
        config = GenerationConfig(model="gpt-4o", temperature=0.7, max_tokens=32)
        stream = _FakeStream([
            SimpleNamespace(type="response.output_text.delta", delta="Hel"),
            SimpleNamespace(type="response.output_text.delta", delta="lo"),
            SimpleNamespace(type="response.completed"),
        ])

        with patch.object(provider.async_client.responses, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = stream

            chunks = [chunk async for chunk in provider.stream_generate(prompt, config)]

            assert chunks == ["Hel", "lo"]
            assert mock_create.await_args.kwargs["stream"] is True

    @pytest.mark.anyio
    async def test_responses_unsupported_raises_without_protocol_fallback(self, provider):
        """验收：网关不支持 Responses API（404/400）→ 直接报错，绝不静默换协议重发。"""
        import httpx as _httpx
        import openai as _openai

        prompt = Prompt(system="You are helpful", user="Hello")
        config = GenerationConfig(model="gpt-4o")

        request = _httpx.Request("POST", "https://gw.example/v1/responses")
        responses_mock = AsyncMock(side_effect=_openai.NotFoundError("not found", response=_httpx.Response(404, request=request), body=None))
        chat_mock = AsyncMock()

        with patch.object(provider.async_client.responses, "create", responses_mock), \
             patch.object(provider.async_client.chat.completions, "create", chat_mock):
            with pytest.raises(Exception):
                await provider.generate(prompt, config)

        assert chat_mock.await_count == 0

    @pytest.mark.anyio
    async def test_generate_empty_responses_raises(self, provider):
        prompt = Prompt(system="You are helpful", user="Hello")
        config = GenerationConfig(model="test-model")
        response = SimpleNamespace(
            output=[],
            usage=SimpleNamespace(prompt_tokens=5, completion_tokens=0),
        )

        with patch.object(provider.async_client.responses, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = response

            with pytest.raises(RuntimeError, match="empty content"):
                await provider.generate(prompt, config)


class TestProfilePassthrough:
    """profile 的 use_legacy_chat_completions 正确透传到 OpenAIProvider"""

    def test_legacy_flag_passed_through(self):
        settings_legacy = Settings(api_key="k", use_legacy_chat_completions=True)
        provider_legacy = OpenAIProvider(settings_legacy)
        assert provider_legacy._use_legacy is True

        settings_new = Settings(api_key="k", use_legacy_chat_completions=False)
        provider_new = OpenAIProvider(settings_new)
        assert provider_new._use_legacy is False

    def test_default_is_responses(self):
        settings = Settings(api_key="k")
        provider = OpenAIProvider(settings)
        assert provider._use_legacy is False
