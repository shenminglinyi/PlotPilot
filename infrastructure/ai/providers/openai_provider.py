"""OpenAI-compatible LLM provider with robust SSE handling."""
import json
import logging
from typing import AsyncIterator

import httpx

from domain.ai.services.llm_service import GenerationConfig, GenerationResult
from domain.ai.value_objects.prompt import Prompt
from domain.ai.value_objects.token_usage import TokenUsage
from infrastructure.ai.config.settings import Settings
from infrastructure.ai.model_defaults import get_openai_default_model
from .base import BaseProvider

logger = logging.getLogger(__name__)

class OpenAIProvider(BaseProvider):
    """Provider for OpenAI-compatible chat completion APIs."""

    def __init__(self, settings: Settings):
        super().__init__(settings)

        if not settings.api_key:
            raise ValueError("API key is required for OpenAIProvider")

        base_url = (settings.base_url or "https://api.openai.com/v1").rstrip("/")
        self.chat_url = f"{base_url}/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {settings.api_key}",
            "Content-Type": "application/json",
        }

    async def generate(
        self,
        prompt: Prompt,
        config: GenerationConfig
    ) -> GenerationResult:
        payload = self._build_payload(prompt, config, stream=False)

        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(self.chat_url, headers=self.headers, json=payload)
                response.raise_for_status()

                content_type = response.headers.get("content-type", "").lower()
                if "text/event-stream" in content_type:
                    content, prompt_tokens, completion_tokens = self._collect_sse_text(response.text)
                else:
                    data = response.json()
                    content = self._extract_message_content(data)
                    usage = data.get("usage", {}) if isinstance(data, dict) else {}
                    prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
                    completion_tokens = int(usage.get("completion_tokens", 0) or 0)

                if not content or not content.strip():
                    raise RuntimeError("API returned empty content")

                return GenerationResult(
                    content=content,
                    token_usage=TokenUsage(
                        input_tokens=prompt_tokens,
                        output_tokens=completion_tokens,
                    ),
                )
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"Failed to generate text: {str(e)}") from e

    async def stream_generate(
        self,
        prompt: Prompt,
        config: GenerationConfig
    ) -> AsyncIterator[str]:
        payload = self._build_payload(prompt, config, stream=True)

        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                async with client.stream("POST", self.chat_url, headers=self.headers, json=payload) as response:
                    response.raise_for_status()

                    content_type = response.headers.get("content-type", "").lower()
                    if "text/event-stream" not in content_type:
                        text = await response.aread()
                        decoded = text.decode(errors="replace")
                        try:
                            data = json.loads(decoded)
                            content = self._extract_message_content(data)
                        except Exception:
                            content = decoded
                        if content:
                            yield content
                        return

                    buffer = ""
                    async for chunk in response.aiter_text():
                        buffer += chunk
                        while "\n\n" in buffer:
                            event_text, buffer = buffer.split("\n\n", 1)
                            for piece in self._parse_sse_event(event_text):
                                yield piece

                    if buffer.strip():
                        for piece in self._parse_sse_event(buffer):
                            yield piece
        except Exception as e:
            logger.error("[OpenAIProvider stream] Failed: %s", e)
            raise RuntimeError(f"Failed to stream text: {str(e)}") from e

    def _build_payload(self, prompt: Prompt, config: GenerationConfig, stream: bool) -> dict:
        return {
            "model": config.model or get_openai_default_model(),
            "messages": [
                {"role": "system", "content": prompt.system},
                {"role": "user", "content": prompt.user},
            ],
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "stream": stream,
        }

    def _extract_message_content(self, data: dict) -> str:
        if not isinstance(data, dict):
            return ""
        choices = data.get("choices") or []
        if not choices:
            return ""
        message = choices[0].get("message") or {}
        content = message.get("content", "")
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if text:
                        parts.append(str(text))
            return "".join(parts)
        return str(content or "")

    def _collect_sse_text(self, raw_text: str) -> tuple[str, int, int]:
        pieces: list[str] = []
        prompt_tokens = 0
        completion_tokens = 0

        for block in raw_text.split("\n\n"):
            for piece in self._parse_sse_event(block):
                pieces.append(piece)

            data_obj = self._parse_sse_data_object(block)
            if not isinstance(data_obj, dict):
                continue

            usage = data_obj.get("usage", {})
            if isinstance(usage, dict):
                prompt_tokens = int(usage.get("prompt_tokens", prompt_tokens) or prompt_tokens)
                completion_tokens = int(usage.get("completion_tokens", completion_tokens) or completion_tokens)

        return "".join(pieces), prompt_tokens, completion_tokens

    def _parse_sse_event(self, event_text: str) -> list[str]:
        payloads = self._extract_sse_payloads(event_text)
        pieces: list[str] = []

        for payload in payloads:
            if payload == "[DONE]":
                continue
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                continue

            choices = data.get("choices") or []
            if not choices:
                continue

            delta = choices[0].get("delta") or {}
            content = delta.get("content")
            if content:
                pieces.append(str(content))
                continue

            message = choices[0].get("message") or {}
            content = message.get("content")
            if content:
                pieces.append(str(content))

        return pieces

    def _parse_sse_data_object(self, event_text: str):
        payloads = self._extract_sse_payloads(event_text)
        for payload in payloads:
            if payload == "[DONE]":
                continue
            try:
                return json.loads(payload)
            except json.JSONDecodeError:
                continue
        return None

    def _extract_sse_payloads(self, event_text: str) -> list[str]:
        payloads: list[str] = []
        for line in event_text.splitlines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            payloads.append(line[5:].strip())
        return payloads
