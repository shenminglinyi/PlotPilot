"""Anthropic LLM 提供商实现"""
import json
import logging
from typing import Any, AsyncIterator

import httpx
from anthropic import Anthropic, AsyncAnthropic

from domain.ai.services.llm_service import GenerationConfig, GenerationResult
from domain.ai.value_objects.prompt import Prompt
from domain.ai.value_objects.token_usage import TokenUsage
from infrastructure.ai.config.settings import Settings
from .base import BaseProvider
from .model_resolution import require_resolved_model_id

logger = logging.getLogger(__name__)


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
    """Anthropic LLM 提供商实现

    使用 Anthropic API 实现 LLM 服务。

    双端点策略：
    - generate() (规划/分析): 使用官方 SDK，走官方 API (HTTPS)
    - stream_generate() (正文生成): 使用自定义 httpx，走代理服务器
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

        # 归一化 base_url：去掉尾部 /v1（SDK 内部会自动拼 /v1/messages）
        base = settings.base_url.rstrip("/") if settings.base_url else None
        if base and base.endswith("/v1"):
            base = base[:-3]

        official_client_kw = {
            "api_key": settings.api_key,
            "timeout": 300.0,  # 5 分钟超时
            "max_retries": 2,
            "default_headers": {
                "User-Agent": "claude-cli/2.1.87 (external, cli)",
                **(settings.extra_headers or {}),
            },
            "default_query": settings.extra_query or None,
        }
        if base:
            official_client_kw["base_url"] = base

        # SDK 内置 httpx 默认 trust_env=True，会走系统 HTTP(S)_PROXY，本机代理 TLS 常导致 ConnectError。
        _sdk_timeout = httpx.Timeout(300.0)
        self._http_client_sync = httpx.Client(timeout=_sdk_timeout, trust_env=False)
        self._http_client_async = httpx.AsyncClient(timeout=_sdk_timeout, trust_env=False)
        self.client = Anthropic(**official_client_kw, http_client=self._http_client_sync)
        self.async_client = AsyncAnthropic(**official_client_kw, http_client=self._http_client_async)

        # 兼容旧字段：若其他模块引用，保留归一化后的值
        self.proxy_base_url = base
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
        try:
            model_id = require_resolved_model_id(
                config.model,
                self.settings.default_model,
                provider_label="Anthropic / Claude",
            )
            # 构建请求参数
            create_kwargs = {
                "model": model_id,
                "temperature": config.temperature,
                "max_tokens": config.max_tokens,
                "system": prompt.system,
                "messages": [{"role": "user", "content": prompt.user}],
            }
            # 如果指定了 response_format，传递给 API 强制 JSON 输出
            if config.response_format:
                create_kwargs["response_format"] = config.response_format

            # 使用 async_client 避免阻塞 asyncio 事件循环
            response = await self.async_client.messages.create(**create_kwargs)

            # 防御性检查：验证 content 列表非空
            if not response.content:
                raise RuntimeError("API returned empty content")

            parts = []
            for block in response.content:
                text = _extract_text_from_content_block(block)
                if text:
                    parts.append(text)

            content = "\n".join(part.strip() for part in parts if part and part.strip()).strip()
            if not content:
                raise RuntimeError("API returned no text content")

            # 创建 token 使用统计
            token_usage = TokenUsage(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens
            )

            return GenerationResult(content=content, token_usage=token_usage)

        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"Failed to generate text: {str(e)}") from e

    async def stream_generate(
        self,
        prompt: Prompt,
        config: GenerationConfig
    ) -> AsyncIterator[str]:
        """流式生成内容。

        直接使用 httpx 解析 SSE 流，走代理服务器（如果配置了 base_url）。
        用于正文生成场景，支持 HTTP 代理。
        """
        base_url = self.settings.base_url or "https://api.anthropic.com"
        url = f"{base_url}/v1/messages"
        logger.debug(f"[Stream] Using endpoint: {url}")

        headers = {
            "x-api-key": self.settings.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            # 伪造 User-Agent 模拟 claude-cli
            "User-Agent": "claude-cli/2.1.87 (external, cli)",
            **(self.settings.extra_headers or {}),
        }

        model_id = require_resolved_model_id(
            config.model,
            self.settings.default_model,
            provider_label="Anthropic / Claude",
        )
        payload = {
            "model": model_id,
            "max_tokens": config.max_tokens,
            "temperature": config.temperature,
            "system": prompt.system,
            "messages": [{"role": "user", "content": prompt.user}],
            "stream": True,
        }
        payload.update(self.settings.extra_body or {})

        logger.debug(f"[Stream] Calling {url}")

        try:
            async with httpx.AsyncClient(
                timeout=self.settings.timeout_seconds,
                trust_env=False,
            ) as client:
                async with client.stream(
                    "POST",
                    url,
                    headers=headers,
                    params=self.settings.extra_query or None,
                    json=payload,
                ) as response:
                    if response.status_code != 200:
                        error_body = await response.aread()
                        raise RuntimeError(f"API error {response.status_code}: {error_body.decode()}")

                    buffer = ""
                    async for chunk in response.aiter_text():
                        buffer += chunk

                        # 解析 SSE 事件
                        while "\n\n" in buffer:
                            event_text, buffer = buffer.split("\n\n", 1)
                            text_content = self._parse_sse_event(event_text)
                            if text_content:
                                yield text_content

        except Exception as e:
            logger.error(f"[Stream] Failed: {e}")
            raise RuntimeError(f"Failed to stream text: {str(e)}") from e

    def _parse_sse_event(self, event_text: str) -> str:
        """解析单个 SSE 事件，返回文本内容（如果有）。"""
        lines = event_text.strip().split("\n")
        event_type = None
        data = None

        for line in lines:
            if line.startswith("event:"):
                event_type = line[6:].strip()
            elif line.startswith("data:"):
                data = line[5:].strip()

        if not data:
            return ""

        try:
            parsed = json.loads(data)
        except json.JSONDecodeError:
            return ""

        # 只处理 content_block_delta 事件
        if parsed.get("type") == "content_block_delta":
            delta = parsed.get("delta", {})
            if delta.get("type") == "text_delta":
                return delta.get("text", "")

        return ""
