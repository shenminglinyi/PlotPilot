"""Anthropic LLM 提供商实现 - 支持 OpenRouter"""
import json
import logging
import os
from typing import Any, AsyncIterator

import httpx

from domain.ai.services.llm_service import GenerationConfig, GenerationResult
from domain.ai.value_objects.prompt import Prompt
from domain.ai.value_objects.token_usage import TokenUsage
from infrastructure.ai.config.settings import Settings
from .base import BaseProvider

logger = logging.getLogger(__name__)

# 从环境变量读取模型配置，OpenRouter 默认使用 elephant-alpha
DEFAULT_MODEL = os.getenv("ANTHROPIC_MODEL", "openrouter/elephant-alpha")


def _extract_text_from_content_block(block: Any) -> str:
    """尽量从兼容端点返回的 content block 中提取文本。"""
    if block is None:
        return ""

    if isinstance(block, str):
        return block

    text = getattr(block, "text", None)
    if isinstance(text, str) and text.strip():
        return text

    if isinstance(block, dict):
        for key in ("text", "content", "value"):
            value = block.get(key)
            if isinstance(value, str) and value.strip():
                return value
        if block.get("type") == "json" and block.get("json") is not None:
            try:
                return json.dumps(block["json"], ensure_ascii=False)
            except Exception:
                return str(block["json"])

    block_type = getattr(block, "type", None)
    if block_type in {"json", "input_json", "output_json"}:
        json_payload = getattr(block, "json", None)
        if json_payload is not None:
            try:
                return json.dumps(json_payload, ensure_ascii=False)
            except Exception:
                return str(json_payload)

    return ""


class AnthropicProvider(BaseProvider):
    """Anthropic LLM 提供商实现 - 支持 OpenRouter OpenAI 兼容格式

    使用 OpenAI 兼容 API 格式，支持 OpenRouter 等代理服务。
    """

    def __init__(self, settings: Settings):
        """初始化 Anthropic 提供商

        Args:
            settings: AI 配置设置

        Raises:
            ValueError: 如果 API key 未设置
        """
        super().__init__(settings)

        if not settings.api_key:
            raise ValueError("API key is required for AnthropicProvider")

        # API 配置
        self.api_key = settings.api_key
        # 如果设置了 base_url，使用它；否则使用 OpenRouter 默认地址
        self.base_url = settings.base_url or "https://openrouter.ai/api/v1"

        logger.info(f"AnthropicProvider initialized with base_url: {self.base_url}")

    def _get_headers(self) -> dict:
        """获取请求头"""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://localhost",
            "X-Title": "PlotPilot",
        }

    def _convert_prompt_to_openai_format(self, prompt: Prompt) -> list:
        """将 Prompt 转换为 OpenAI 格式"""
        messages = []
        if prompt.system:
            messages.append({"role": "system", "content": prompt.system})
        messages.extend(prompt.to_messages())
        return messages

    async def generate(
        self,
        prompt: Prompt,
        config: GenerationConfig
    ) -> GenerationResult:
        """生成文本

        Args:
            prompt: 提示词
            config: 生成配置

        Returns:
            生成结果

        Raises:
            RuntimeError: 当 API 调用失败或返回空内容时
        """
        url = f"{self.base_url}/chat/completions"
        headers = self._get_headers()

        payload = {
            "model": config.model or DEFAULT_MODEL,
            "messages": self._convert_prompt_to_openai_format(prompt),
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
        }

        logger.debug(f"[Generate] Calling {url} with model {payload['model']}")

        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(url, headers=headers, json=payload)

                if response.status_code != 200:
                    error_text = response.text
                    logger.error(f"API error {response.status_code}: {error_text}")
                    raise RuntimeError(f"API error {response.status_code}: {error_text}")

                data = response.json()

                if not data.get("choices") or len(data["choices"]) == 0:
                    raise RuntimeError("API returned empty choices")

                content = data["choices"][0].get("message", {}).get("content", "")
                if not content:
                    raise RuntimeError("API returned empty content")

                usage = data.get("usage", {})
                token_usage = TokenUsage(
                    input_tokens=usage.get("prompt_tokens", 0),
                    output_tokens=usage.get("completion_tokens", 0)
                )

                return GenerationResult(content=content, token_usage=token_usage)

        except RuntimeError:
            raise
        except Exception as e:
            logger.error(f"Failed to generate text: {e}")
            raise RuntimeError(f"Failed to generate text: {str(e)}") from e

    async def stream_generate(
        self,
        prompt: Prompt,
        config: GenerationConfig
    ) -> AsyncIterator[str]:
        """流式生成内容。

        使用 OpenAI 兼容的 SSE 流格式。
        """
        url = f"{self.base_url}/chat/completions"
        headers = self._get_headers()

        payload = {
            "model": config.model or DEFAULT_MODEL,
            "messages": self._convert_prompt_to_openai_format(prompt),
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "stream": True,
        }

        logger.debug(f"[Stream] Calling {url} with model {payload['model']}")

        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                async with client.stream("POST", url, headers=headers, json=payload) as response:
                    if response.status_code != 200:
                        error_body = await response.aread()
                        raise RuntimeError(f"API error {response.status_code}: {error_body.decode()}")

                    buffer = ""
                    async for chunk in response.aiter_text():
                        buffer += chunk

                        # 解析 SSE 事件
                        while "\n\n" in buffer:
                            event_text, buffer = buffer.split("\n\n", 1)
                            text_content = self._parse_openai_sse_event(event_text)
                            if text_content:
                                yield text_content

        except Exception as e:
            logger.error(f"[Stream] Failed: {e}")
            raise RuntimeError(f"Failed to stream text: {str(e)}") from e

    def _parse_openai_sse_event(self, event_text: str) -> str:
        """解析 OpenAI 格式的 SSE 事件，返回文本内容（如果有）。"""
        lines = event_text.strip().split("\n")
        data = None

        for line in lines:
            if line.startswith("data:"):
                data = line[5:].strip()

        if not data:
            return ""

        # 处理 [DONE] 标记
        if data == "[DONE]":
            return ""

        try:
            parsed = json.loads(data)
        except json.JSONDecodeError:
            return ""

        # OpenAI 格式：choices[0].delta.content
        choices = parsed.get("choices", [])
        if not choices:
            return ""

        delta = choices[0].get("delta", {})
        return delta.get("content", "")
