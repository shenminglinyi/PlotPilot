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
from infrastructure.ai.http_timeout import build_httpx_timeout
from .base import BaseProvider
from .model_resolution import require_resolved_model_id

logger = logging.getLogger(__name__)


def _json_response_instruction(response_format: dict[str, Any]) -> str:
    """Build prompt-side JSON constraints for Anthropic Messages API."""
    fmt_type = response_format.get("type")
    if fmt_type == "json_schema":
        schema_payload = response_format.get("json_schema") or {}
        schema = schema_payload.get("schema") or {}
        schema_name = schema_payload.get("name") or "response"
        try:
            schema_text = json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            schema_text = str(schema)
        return (
            "\n\n请只输出一个有效 JSON 对象，不要包含 Markdown 或额外文字。"
            f"\nJSON 对象需符合 `{schema_name}` schema：{schema_text}"
        )
    if fmt_type == "json_object":
        return "\n\n请只输出一个有效 JSON 对象，不要包含 Markdown 或额外文字。"
    return ""


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

    使用 Anthropic 官方 SDK 实现 LLM 服务：
    - generate(): 非流式生成（SDK messages.create）
    - stream_generate(): 流式生成（SDK messages.stream，唯一流式路径）
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
        _sdk_timeout = build_httpx_timeout(settings.http_timeout_settings)
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
            # Anthropic Messages API does not accept OpenAI-style response_format.
            # Keep structured output provider-agnostic by moving the constraint into
            # the prompt; structured_json_pipeline will parse and validate it.
            if config.response_format:
                fmt = config.response_format
                instruction = _json_response_instruction(fmt)
                if instruction:
                    create_kwargs["system"] = create_kwargs["system"] + instruction

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

    def _build_message_request(
        self,
        prompt: Prompt,
        config: GenerationConfig,
        *,
        stream: bool = False,
    ) -> tuple[str, dict[str, Any]]:
        """构建 Messages API 请求体，供 generate / stream 共用。"""
        model_id = require_resolved_model_id(
            config.model,
            self.settings.default_model,
            provider_label="Anthropic / Claude",
        )
        payload: dict[str, Any] = {
            "model": model_id,
            "max_tokens": config.max_tokens,
            "temperature": config.temperature,
            "system": prompt.system,
            "messages": [{"role": "user", "content": prompt.user}],
        }
        if stream:
            payload["stream"] = True
        payload.update(self.settings.extra_body or {})
        return model_id, payload

    @staticmethod
    def _format_stream_error(exc: BaseException) -> str:
        message = str(exc).strip()
        if message:
            return f"{type(exc).__name__}: {message}"
        return f"{type(exc).__name__}: {exc!r}"

    async def _stream_via_sdk(
        self,
        prompt: Prompt,
        config: GenerationConfig,
    ) -> AsyncIterator[str]:
        """通过官方 SDK 流式读取（唯一流式路径）。"""
        model_id, payload = self._build_message_request(prompt, config, stream=False)
        async with self.async_client.messages.stream(**payload) as stream:
            async for text in stream.text_stream:
                if text:
                    yield text

    async def stream_generate(
        self,
        prompt: Prompt,
        config: GenerationConfig
    ) -> AsyncIterator[str]:
        """流式生成内容（唯一路径：Anthropic SDK stream）。

        失败直接报错，不在 httpx SSE / SDK 两条协议路径之间回退。
        """
        try:
            async for text in self._stream_via_sdk(prompt, config):
                yield text
        except Exception as e:
            detail = self._format_stream_error(e)
            logger.error("[Stream] Failed: %s", detail)
            raise RuntimeError(f"Failed to stream text: {detail}") from e
