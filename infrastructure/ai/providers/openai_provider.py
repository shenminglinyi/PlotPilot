"""OpenAI-compatible provider supporting chat completions and responses APIs."""
import json
import logging
from typing import Any, AsyncIterator

import httpx

from domain.ai.services.llm_service import GenerationConfig, GenerationResult
from domain.ai.value_objects.prompt import Prompt
from domain.ai.value_objects.token_usage import TokenUsage
from infrastructure.ai.config.settings import Settings
from infrastructure.ai.model_defaults import get_openai_default_model
from .base import BaseProvider

logger = logging.getLogger(__name__)


class OpenAIProvider(BaseProvider):
    """Provider for OpenAI-compatible chat completions and responses APIs."""

    def __init__(self, settings: Settings, api_format: str = "openai_chat_completions"):
        super().__init__(settings)

        if not settings.api_key:
            raise ValueError("API key is required for OpenAIProvider")

        self.api_format = (api_format or "openai_chat_completions").strip().lower()
        base_url = (settings.base_url or "https://api.openai.com/v1").rstrip("/")
        self.chat_url = f"{base_url}/chat/completions"
        self.responses_url = f"{base_url}/responses"
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
        url = self._request_url()

        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(url, headers=self.headers, json=payload)
                response.raise_for_status()

                content_type = response.headers.get("content-type", "").lower()
                if "text/event-stream" in content_type:
                    content, prompt_tokens, completion_tokens = self._collect_sse_text(response.text)
                else:
                    data = response.json()
                    content = self._extract_content(data)
                    prompt_tokens, completion_tokens = self._extract_usage(data)

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
        url = self._request_url()

        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                async with client.stream("POST", url, headers=self.headers, json=payload) as response:
                    response.raise_for_status()

                    content_type = response.headers.get("content-type", "").lower()
                    if "text/event-stream" not in content_type:
                        text = await response.aread()
                        decoded = text.decode(errors="replace")
                        try:
                            data = json.loads(decoded)
                            content = self._extract_content(data)
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

    def _request_url(self) -> str:
        return self.responses_url if self.api_format == "openai_responses" else self.chat_url

    def _build_payload(self, prompt: Prompt, config: GenerationConfig, stream: bool) -> dict[str, Any]:
        model = config.model or get_openai_default_model()
        if self.api_format == "openai_responses":
            payload: dict[str, Any] = {
                "model": model,
                "instructions": prompt.system,
                "input": prompt.user,
                "max_output_tokens": config.max_tokens,
                "stream": stream,
            }
            if config.temperature is not None:
                payload["temperature"] = config.temperature
            return payload

        return {
            "model": model,
            "messages": [
                {"role": "system", "content": prompt.system},
                {"role": "user", "content": prompt.user},
            ],
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "stream": stream,
        }

    def _extract_content(self, data: Any) -> str:
        if self.api_format == "openai_responses":
            return self._extract_responses_content(data)
        return self._extract_chat_content(data)

    def _extract_usage(self, data: Any) -> tuple[int, int]:
        if not isinstance(data, dict):
            return 0, 0

        usage = data.get("usage", {})
        if self.api_format == "openai_responses" and not usage and isinstance(data.get("response"), dict):
            usage = data["response"].get("usage", {})
        if not isinstance(usage, dict):
            return 0, 0

        if self.api_format == "openai_responses":
            input_tokens = int(usage.get("input_tokens", 0) or 0)
            output_tokens = int(usage.get("output_tokens", 0) or 0)
            if not input_tokens and not output_tokens:
                input_tokens = int(usage.get("prompt_tokens", 0) or 0)
                output_tokens = int(usage.get("completion_tokens", 0) or 0)
            return input_tokens, output_tokens

        return (
            int(usage.get("prompt_tokens", 0) or 0),
            int(usage.get("completion_tokens", 0) or 0),
        )

    def _extract_chat_content(self, data: Any) -> str:
        if not isinstance(data, dict):
            return ""
        choices = data.get("choices") or []
        if not choices:
            return ""
        message = choices[0].get("message") or {}
        return self._coerce_content_to_text(message.get("content", ""))

    def _extract_responses_content(self, data: Any) -> str:
        if not isinstance(data, dict):
            return ""

        output_text = data.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text

        if isinstance(output_text, list):
            joined = "".join(str(item) for item in output_text if item)
            if joined.strip():
                return joined

        pieces: list[str] = []
        for item in data.get("output") or []:
            if not isinstance(item, dict):
                continue

            item_text = item.get("text")
            if item_text:
                pieces.append(str(item_text))

            message = item.get("message")
            if isinstance(message, dict):
                pieces.append(self._coerce_content_to_text(message.get("content", "")))

            content = item.get("content")
            pieces.append(self._coerce_content_to_text(content))

        return "".join(piece for piece in pieces if piece)

    def _coerce_content_to_text(self, content: Any) -> str:
        if isinstance(content, str):
            return content

        if not isinstance(content, list):
            return ""

        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue

            if not isinstance(item, dict):
                continue

            text = item.get("text")
            if isinstance(text, str):
                parts.append(text)
                continue

            nested_text = item.get("output_text")
            if isinstance(nested_text, str):
                parts.append(nested_text)

        return "".join(parts)

    def _collect_sse_text(self, raw_text: str) -> tuple[str, int, int]:
        pieces: list[str] = []
        prompt_tokens = 0
        completion_tokens = 0
        fallback_content = ""

        for block in raw_text.split("\n\n"):
            for piece in self._parse_sse_event(block):
                pieces.append(piece)

            data_obj = self._parse_sse_data_object(block)
            if self.api_format == "openai_responses" and not fallback_content:
                fallback_content = self._extract_responses_sse_fallback(data_obj)
            next_prompt_tokens, next_completion_tokens = self._extract_usage(data_obj)
            if next_prompt_tokens:
                prompt_tokens = next_prompt_tokens
            if next_completion_tokens:
                completion_tokens = next_completion_tokens

        content = "".join(pieces) or fallback_content
        return content, prompt_tokens, completion_tokens

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

            if self.api_format == "openai_responses":
                pieces.extend(self._parse_responses_sse_data(data))
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
                pieces.append(self._coerce_content_to_text(content))

        return pieces

    def _parse_responses_sse_data(self, data: Any) -> list[str]:
        if not isinstance(data, dict):
            return []

        event_type = str(data.get("type") or "")
        pieces: list[str] = []

        if event_type in {
            "response.output_text.delta",
            "response.refusal.delta",
            "response.reasoning_summary_text.delta",
        }:
            delta = data.get("delta")
            if isinstance(delta, str) and delta:
                pieces.append(delta)
            return pieces

        return pieces

    def _extract_responses_sse_fallback(self, data: Any) -> str:
        if not isinstance(data, dict):
            return ""

        event_type = str(data.get("type") or "")
        if event_type in {
            "response.output_text.done",
            "response.refusal.done",
            "response.reasoning_summary_text.done",
        }:
            text = data.get("text")
            if isinstance(text, str):
                return text

        if event_type == "response.completed":
            return self._extract_responses_content(data.get("response"))

        return self._extract_responses_content(data)

    def _parse_sse_data_object(self, event_text: str) -> Any:
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
