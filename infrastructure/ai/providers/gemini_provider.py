"""Gemini LLM 提供商实现（官方 generateContent / streamGenerateContent 协议）"""
from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

import httpx

from domain.ai.services.llm_service import GenerationConfig, GenerationResult
from domain.ai.value_objects.prompt import Prompt
from domain.ai.value_objects.token_usage import TokenUsage
from infrastructure.ai.config.settings import Settings
from infrastructure.ai.http_timeout import build_httpx_timeout
from infrastructure.ai.loopback_transport import LoopbackOnlyAsyncTransport
from .base import BaseProvider
from .model_resolution import require_resolved_model_id

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = 'https://generativelanguage.googleapis.com/v1beta'


class GeminiProvider(BaseProvider):
    def __init__(self, settings: Settings):
        super().__init__(settings)
        if not settings.api_key:
            raise ValueError('API key is required for GeminiProvider')
        self.base_url = (settings.base_url or DEFAULT_BASE_URL).rstrip('/')
        # 长生命周期 httpx client（跨请求复用连接池）
        self._http_client = httpx.AsyncClient(
            timeout=build_httpx_timeout(settings.http_timeout_settings),
            trust_env=False,
            follow_redirects=False,
            transport=(
                LoopbackOnlyAsyncTransport()
                if getattr(settings, 'loopback_only', False)
                else None
            ),
        )

    async def generate(self, prompt: Prompt, config: GenerationConfig) -> GenerationResult:
        model_id = require_resolved_model_id(
            config.model,
            self.settings.default_model,
            provider_label="Gemini",
        )
        payload = self._build_payload(prompt, config)
        query = self._build_query()
        url = self._build_url(model_id, 'generateContent')

        response = await self._http_client.post(
            url,
            params=query,
            headers=self._build_headers(stream=False),
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
        self._raise_if_payload_error(data, prefix='Gemini error')

        content = self._extract_text(data)
        if not content.strip():
            raise RuntimeError('Gemini returned empty content')

        usage = data.get('usageMetadata') or {}
        token_usage = TokenUsage(
            input_tokens=int(usage.get('promptTokenCount') or 0),
            output_tokens=int(usage.get('candidatesTokenCount') or 0),
        )
        return GenerationResult(content=content, token_usage=token_usage)

    async def stream_generate(self, prompt: Prompt, config: GenerationConfig) -> AsyncIterator[str]:
        model_id = require_resolved_model_id(
            config.model,
            self.settings.default_model,
            provider_label="Gemini",
        )
        payload = self._build_payload(prompt, config)
        query = self._build_query({'alt': 'sse'})
        url = self._build_url(model_id, 'streamGenerateContent')

        async with self._http_client.stream(
            'POST',
            url,
            params=query,
            headers=self._build_headers(stream=True),
            json=payload,
        ) as response:
            response.raise_for_status()
            buffer = ''
            pending_cr = False
            async for chunk in response.aiter_text():
                if not chunk:
                    continue
                if pending_cr:
                    if chunk.startswith('\n'):
                        chunk = chunk[1:]
                    pending_cr = False
                if not chunk:
                    while '\n\n' in buffer:
                        event_text, buffer = buffer.split('\n\n', 1)
                        text = self._parse_sse_event(event_text)
                        if text:
                            yield text
                    continue
                if chunk.endswith('\r'):
                    pending_cr = True
                    body = chunk[:-1]
                    buffer += body.replace('\r\n', '\n').replace('\r', '\n') + '\n'
                else:
                    buffer += chunk.replace('\r\n', '\n').replace('\r', '\n')
                while '\n\n' in buffer:
                    event_text, buffer = buffer.split('\n\n', 1)
                    text = self._parse_sse_event(event_text)
                    if text:
                        yield text
            if buffer.strip():
                text = self._parse_sse_event(buffer)
                if text:
                    yield text

    def _build_url(self, model: str, action: str) -> str:
        model_name = model.strip()
        if not model_name:
            raise ValueError('Gemini: 构建请求 URL 时模型名为空')
        return f'{self.base_url}/models/{model_name}:{action}'

    _OAUTH_RESERVED_QUERY_KEYS = frozenset({'key', 'api_key', 'apikey', 'access_token'})
    _OAUTH_RESERVED_HEADERS = frozenset(
        {
            'authorization',
            'proxy-authorization',
            'x-goog-api-key',
            'x-api-key',
            'api-key',
        }
    )

    def _build_query(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        oauth_mode = bool(getattr(self.settings, 'use_oauth_bearer', False))
        query: dict[str, Any] = {}
        for source in (self.settings.extra_query or {}, extra or {}):
            for raw_key, val in source.items():
                key_str = str(raw_key)
                if oauth_mode and key_str.strip().lower() in self._OAUTH_RESERVED_QUERY_KEYS:
                    raise ValueError(
                        f'Gemini OAuth bearer mode forbids query credential parameter: {raw_key!r}'
                    )
                query[key_str] = val
        if not oauth_mode:
            query['key'] = self.settings.api_key
        return query

    def _build_headers(self, *, stream: bool) -> dict[str, str]:
        oauth_mode = bool(getattr(self.settings, 'use_oauth_bearer', False))
        headers: dict[str, str] = {}
        for raw_name, raw_val in (self.settings.extra_headers or {}).items():
            name_str = str(raw_name).strip()
            if not name_str:
                continue
            if oauth_mode and name_str.lower() in self._OAUTH_RESERVED_HEADERS:
                raise ValueError(
                    f'Gemini OAuth bearer mode forbids authentication header override: {raw_name!r}'
                )
            headers[name_str] = str(raw_val)
        headers['Content-Type'] = 'application/json'
        if stream:
            headers['Accept'] = 'text/event-stream'
        if oauth_mode:
            headers['Authorization'] = f'Bearer {self.settings.api_key}'
        return headers

    def _build_payload(self, prompt: Prompt, config: GenerationConfig) -> dict[str, Any]:
        generation_config = {
            'temperature': config.temperature,
            'maxOutputTokens': config.max_tokens,
        }
        # 🔥 response_format 自适应：
        # Gemini 支持 responseMimeType 但不支持 json_schema 结构定义
        # OpenAI 的 json_object → Gemini 的 responseMimeType: application/json
        # OpenAI 的 json_schema → Gemini 的 responseMimeType + responseSchema
        if config.response_format:
            fmt = config.response_format
            if fmt.get("type") == "json_object":
                generation_config["responseMimeType"] = "application/json"
            elif fmt.get("type") == "json_schema":
                generation_config["responseMimeType"] = "application/json"
                # 如果 json_schema 中有 schema 定义，传递给 Gemini
                schema = fmt.get("json_schema", {}).get("schema")
                if schema:
                    generation_config["responseSchema"] = schema

        payload: dict[str, Any] = {
            'contents': [
                {
                    'role': 'user',
                    'parts': [{'text': prompt.user}],
                }
            ],
            'generationConfig': generation_config,
        }
        if prompt.system.strip():
            payload['systemInstruction'] = {
                'parts': [{'text': prompt.system}],
            }
        extra_body = dict(self.settings.extra_body or {})
        generation_override = extra_body.pop('generationConfig', None)
        if isinstance(generation_override, dict):
            payload['generationConfig'].update(generation_override)
        payload.update(extra_body)
        return payload

    @staticmethod
    def _raise_if_payload_error(payload: Any, *, prefix: str = 'Gemini SSE error') -> None:
        if isinstance(payload, dict):
            if 'error' in payload and payload.get('error') is not None:
                detail = payload.get('error')
                raise RuntimeError(f'{prefix}: {detail if detail != "" else payload}')
            return
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict) and 'error' in item and item.get('error') is not None:
                    detail = item.get('error')
                    raise RuntimeError(f'{prefix}: {detail if detail != "" else item}')

    def _extract_text(self, data: dict[str, Any]) -> str:
        self._raise_if_payload_error(data)
        pieces: list[str] = []
        for candidate in data.get('candidates') or []:
            content = candidate.get('content') or {}
            for part in content.get('parts') or []:
                if part.get('thought') is True:
                    continue
                text = part.get('text')
                if text:
                    pieces.append(str(text))
        return ''.join(pieces)

    def _parse_sse_event(self, event_text: str) -> str:
        data_lines: list[str] = []
        event_type = ''
        for line in event_text.splitlines():
            if line.startswith('event:'):
                event_type = line[6:].strip().lower()
            elif line.startswith('data:'):
                raw_data = line[6:] if line.startswith('data: ') else line[5:]
                data_lines.append(raw_data)

        raw_payload = '\n'.join(data_lines).strip()

        if event_type == 'error':
            detail: Any = raw_payload[:240] if raw_payload else 'error event received'
            if raw_payload:
                try:
                    err_parsed = json.loads(raw_payload)
                    if isinstance(err_parsed, dict):
                        detail = err_parsed.get('error') or err_parsed
                    elif err_parsed is not None:
                        detail = err_parsed
                except json.JSONDecodeError:
                    pass
            raise RuntimeError(f'Gemini SSE error: {detail}')

        if not raw_payload or raw_payload == '[DONE]':
            return ''

        try:
            payload = json.loads(raw_payload)
        except json.JSONDecodeError:
            logger.debug('Gemini SSE parse skip: %s', raw_payload[:120])
            return ''

        self._raise_if_payload_error(payload, prefix='Gemini SSE error')

        if isinstance(payload, list):
            return ''.join(self._extract_text(item) for item in payload if isinstance(item, dict))
        if isinstance(payload, dict):
            return self._extract_text(payload)
        return ''
