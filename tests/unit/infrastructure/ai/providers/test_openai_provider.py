"""OpenAIProvider 测试"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from domain.ai.services.llm_service import GenerationConfig
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


class TestOpenAIProvider:
    @pytest.fixture
    def settings(self):
        return Settings(api_key="test-api-key")

    @pytest.fixture
    def provider(self, settings):
        return OpenAIProvider(settings)

    def test_initialization(self, provider, settings):
        assert provider.settings == settings
        assert provider.async_client is not None

    @pytest.mark.anyio
    async def test_generate_with_default_config(self, provider):
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
            assert call_kwargs["max_tokens"] == 4096

    @pytest.mark.anyio
    async def test_generate_falls_back_to_stream_when_content_is_empty(self, provider):
        prompt = Prompt(system="You are helpful", user="Hello")
        config = GenerationConfig(model="gpt-5.4", temperature=0, max_tokens=32)
        empty_response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=None))],
            usage=SimpleNamespace(prompt_tokens=19, completion_tokens=15),
        )
        stream = _FakeStream([
            SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content="OK"))],
                usage=None,
            ),
            SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content=None))],
                usage=SimpleNamespace(prompt_tokens=19, completion_tokens=17),
            ),
        ])

        with patch.object(provider.async_client.chat.completions, "create", new_callable=AsyncMock) as mock_create:
            mock_create.side_effect = [empty_response, stream]

            result = await provider.generate(prompt, config)

            assert result.content == "OK"
            assert result.token_usage.input_tokens == 19
            assert result.token_usage.output_tokens == 17
            assert mock_create.await_count == 2
            assert mock_create.await_args_list[1].kwargs["stream"] is True

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
        config = GenerationConfig()
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
            mock_create.side_effect = [empty_response, empty_stream]

            with pytest.raises(RuntimeError, match="empty content"):
                await provider.generate(prompt, config)

    def test_missing_api_key(self):
        with pytest.raises(ValueError, match="API key is required"):
            OpenAIProvider(Settings(api_key=None))
