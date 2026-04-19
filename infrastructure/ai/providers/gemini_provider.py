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

    async def generate(self, prompt: Prompt, config: GenerationConfig) -> GenerationResult:
        model_id = require_resolved_model_id(
            config.model,
            self.settings.default_model,
            provider_label="Gemini",
        )
        payload = self._build_payload(prompt, config)
        query = self._build_query()
        url = self._build_url(model_id, 'generateContent')
        timeout = httpx.Timeout(self.settings.timeout_seconds)

        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            response = await client.post(
                url,
                params=query,
                headers=self._build_headers(stream=False),
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

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
        timeout = httpx.Timeout(self.settings.timeout_seconds)

        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            async with client.stream(
                'POST',
                url,
                params=query,
                headers=self._build_headers(stream=True),
                json=payload,
            ) as response:
                response.raise_for_status()
                buffer = ''
                async for chunk in response.aiter_text():
                    buffer += chunk.replace('\r\n', '\n')
                    while '\n\n' in buffer:
                        event_text, buffer = buffer.split('\n\n', 1)
                        text = self._parse_sse_event(event_text)
                        if text:
                            yield text

    def _build_url(self, model: str, action: str) -> str:
        model_name = model.strip()
        if not model_name:
            raise ValueError('Gemini: 构建请求 URL 时模型名为空')
        return f'{self.base_url}/models/{model_name}:{action}'

    def _build_query(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        query: dict[str, Any] = {'key': self.settings.api_key}
        query.update(self.settings.extra_query or {})
        if extra:
            query.update(extra)
        return query

    def _build_headers(self, *, stream: bool) -> dict[str, str]:
        headers = {'Content-Type': 'application/json'}
        if stream:
            headers['Accept'] = 'text/event-stream'
        headers.update(self.settings.extra_headers or {})
        return headers

    def _build_payload(self, prompt: Prompt, config: GenerationConfig) -> dict[str, Any]:
        generation_config = {
            'temperature': config.temperature,
            'maxOutputTokens': config.max_tokens,
        }
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

    def _extract_text(self, data: dict[str, Any]) -> str:
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
        for line in event_text.splitlines():
            if line.startswith('data:'):
                data_lines.append(line[5:].strip())

        if not data_lines:
            return ''

        raw_payload = ''.join(data_lines).strip()
        if not raw_payload or raw_payload == '[DONE]':
            return ''

        try:
            payload = json.loads(raw_payload)
        except json.JSONDecodeError:
            logger.debug('Gemini SSE parse skip: %s', raw_payload[:120])
            return ''

        if isinstance(payload, list):
            return ''.join(self._extract_text(item) for item in payload if isinstance(item, dict))
        if isinstance(payload, dict):
            return self._extract_text(payload)
        return ''
