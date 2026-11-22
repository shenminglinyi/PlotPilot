"""Anthropic LLM 提供商实现"""
from contextlib import aclosing
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
from infrastructure.ai.loopback_transport import (
    LoopbackOnlyAsyncTransport,
    LoopbackOnlySyncTransport,
)
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
        _sdk_timeout = build_httpx_timeout(settings.http_timeout_settings)
        _loopback_only = bool(getattr(settings, "loopback_only", False))
        self._http_client_sync = httpx.Client(
            timeout=_sdk_timeout,
            trust_env=False,
            follow_redirects=False,
            transport=LoopbackOnlySyncTransport() if _loopback_only else None,
        )
        self._http_client_async = httpx.AsyncClient(
            timeout=_sdk_timeout,
            trust_env=False,
            follow_redirects=False,
            transport=LoopbackOnlyAsyncTransport() if _loopback_only else None,
        )
        self.client = Anthropic(**official_client_kw, http_client=self._http_client_sync)
        self.async_client = AsyncAnthropic(**official_client_kw, http_client=self._http_client_async)

        # 流式端点专用 httpx client（长生命周期，跨请求复用连接池）
        self._stream_http_client = httpx.AsyncClient(
            timeout=build_httpx_timeout(self.settings.http_timeout_settings),
            trust_env=False,
            follow_redirects=False,
            transport=LoopbackOnlyAsyncTransport() if _loopback_only else None,
        )

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

    async def _stream_via_httpx(
        self,
        prompt: Prompt,
        config: GenerationConfig,
    ) -> AsyncIterator[str]:
        """通过 httpx 直接解析 SSE，兼容部分网关的非标准流式响应。"""
        base_url = self.settings.base_url or "https://api.anthropic.com"
        url = f"{base_url}/v1/messages"
        logger.debug("[Stream] Using httpx endpoint: %s", url)

        headers = {
            "x-api-key": self.settings.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "User-Agent": "claude-cli/2.1.87 (external, cli)",
            **(self.settings.extra_headers or {}),
        }
        _, payload = self._build_message_request(prompt, config, stream=True)

        logger.debug("[Stream] Calling %s", url)
        async with self._stream_http_client.stream(
            "POST",
            url,
            headers=headers,
            params=self.settings.extra_query or None,
            json=payload,
        ) as response:
            if response.status_code != 200:
                error_body = await response.aread()
                raise RuntimeError(
                    f"API error {response.status_code}: {error_body.decode(errors='replace')}"
                )

            buffer = ""
            pending_cr = False
            events_received = 0
            protocol_mode = "unknown"
            saw_anthropic_stop = False
            saw_compat_done = False

            def _consume_event(raw_evt: str) -> str:
                nonlocal events_received, protocol_mode, saw_anthropic_stop, saw_compat_done
                events_received += 1
                text_out, evt_mode, is_complete = self._parse_sse_event_with_state(
                    raw_evt, protocol_mode
                )
                if evt_mode == "anthropic":
                    protocol_mode = "anthropic"
                    if is_complete:
                        saw_anthropic_stop = True
                elif evt_mode == "compat":
                    if protocol_mode == "unknown":
                        protocol_mode = "compat"
                    if is_complete and protocol_mode == "compat":
                        saw_compat_done = True
                if events_received <= 3:
                    logger.info(
                        "[Stream] SSE event #%d raw=%s parsed=%s",
                        events_received,
                        raw_evt[:500],
                        text_out[:200] if text_out else "(empty)",
                    )
                return text_out

            async for chunk in response.aiter_text():
                if not chunk:
                    continue
                if pending_cr:
                    if chunk.startswith("\n"):
                        chunk = chunk[1:]
                    pending_cr = False
                if not chunk:
                    while "\n\n" in buffer:
                        event_text, buffer = buffer.split("\n\n", 1)
                        text_content = _consume_event(event_text)
                        if text_content:
                            yield text_content
                    continue
                if chunk.endswith("\r"):
                    pending_cr = True
                    body = chunk[:-1]
                    buffer += body.replace("\r\n", "\n").replace("\r", "\n") + "\n"
                else:
                    buffer += chunk.replace("\r\n", "\n").replace("\r", "\n")
                while "\n\n" in buffer:
                    event_text, buffer = buffer.split("\n\n", 1)
                    text_content = _consume_event(event_text)
                    if text_content:
                        yield text_content
            if buffer.strip():
                text_content = _consume_event(buffer)
                if text_content:
                    yield text_content

            stream_completed = (
                saw_anthropic_stop
                if protocol_mode == "anthropic"
                else (saw_compat_done if protocol_mode == "compat" else False)
            )
            if not stream_completed:
                raise RuntimeError(
                    "Upstream SSE stream ended prematurely before protocol completion event"
                )

    async def _stream_via_sdk(
        self,
        prompt: Prompt,
        config: GenerationConfig,
    ) -> AsyncIterator[str]:
        """通过官方 SDK 流式读取，网关断开 raw SSE 时作为回退。"""
        model_id, payload = self._build_message_request(prompt, config, stream=False)
        logger.info("[Stream] Falling back to SDK stream for model=%s", model_id)
        async with self.async_client.messages.stream(**payload) as stream:
            async for text in stream.text_stream:
                if text:
                    yield text

    async def stream_generate(
        self,
        prompt: Prompt,
        config: GenerationConfig
    ) -> AsyncIterator[str]:
        """流式生成内容。

        优先 httpx 解析 SSE（兼容部分代理）；若连接被网关提前断开或零输出，
        自动回退到 Anthropic SDK 的 stream API。
        """
        httpx_error: Exception | None = None
        yielded_any = False

        try:
            async with aclosing(self._stream_via_httpx(prompt, config)) as httpx_stream:
                async for chunk in httpx_stream:
                    yielded_any = True
                    yield chunk
        except Exception as e:
            if yielded_any:
                detail = self._format_stream_error(e)
                logger.error(
                    "[Stream] httpx SSE failed after partial output (%s); aborting without SDK replay",
                    detail,
                )
                raise RuntimeError(
                    f"Stream interrupted after partial output: {detail}"
                ) from e
            httpx_error = e
            logger.warning(
                "[Stream] httpx SSE failed before output (%s), will try SDK fallback",
                self._format_stream_error(e),
            )

        if yielded_any:
            return

        sdk_yielded = False
        try:
            async with aclosing(self._stream_via_sdk(prompt, config)) as sdk_stream:
                async for chunk in sdk_stream:
                    sdk_yielded = True
                    yield chunk
        except Exception as sdk_error:
            sdk_detail = self._format_stream_error(sdk_error)
            if httpx_error is not None:
                httpx_detail = self._format_stream_error(httpx_error)
                logger.error(
                    "[Stream] Failed: httpx=%s; sdk=%s",
                    httpx_detail,
                    sdk_detail,
                )
                raise RuntimeError(
                    f"Failed to stream text: httpx={httpx_detail}; sdk={sdk_detail}"
                ) from sdk_error
            logger.error("[Stream] Failed: %s", sdk_detail)
            raise RuntimeError(f"Failed to stream text: {sdk_detail}") from sdk_error

        if not sdk_yielded:
            model_id = config.model or self.settings.default_model
            detail = (
                f"httpx={self._format_stream_error(httpx_error)}"
                if httpx_error
                else "httpx returned no events"
            )
            raise RuntimeError(
                f"Both streaming paths produced zero output for model={model_id}: {detail}"
            )

    _ANTHROPIC_NATIVE_TYPES: frozenset[str] = frozenset(
        {
            "ping",
            "message_start",
            "content_block_start",
            "content_block_delta",
            "content_block_stop",
            "message_delta",
            "message_stop",
        }
    )

    def _parse_sse_event_with_state(
        self,
        event_text: str,
        current_mode: str = "unknown",
    ) -> tuple[str, str, bool]:
        """解析单个 SSE 事件，返回 (文本内容, 协议模式, 是否收到显式结束帧)。"""
        lines = event_text.splitlines()
        event_type = ""
        data_lines: list[str] = []

        for line in lines:
            if line.startswith("event:"):
                event_type = line[6:].strip().lower()
            elif line.startswith("data:"):
                raw_data = line[6:] if line.startswith("data: ") else line[5:]
                data_lines.append(raw_data)

        data = "\n".join(data_lines).strip()

        if event_type == "error":
            detail: Any = data[:240] if data else "error event received"
            if data:
                try:
                    err_parsed = json.loads(data)
                    if isinstance(err_parsed, dict):
                        detail = err_parsed.get("error") or err_parsed
                    elif err_parsed is not None:
                        detail = err_parsed
                except json.JSONDecodeError:
                    pass
            raise RuntimeError(f"Upstream SSE error: {detail}")

        next_mode = (
            "anthropic"
            if event_type in self._ANTHROPIC_NATIVE_TYPES
            else current_mode
        )

        if event_type == "message_stop":
            if data and data != "[DONE]":
                try:
                    stop_parsed = json.loads(data)
                    if isinstance(stop_parsed, dict) and (
                        stop_parsed.get("type") == "error" or stop_parsed.get("error")
                    ):
                        err_obj = stop_parsed.get("error") or stop_parsed
                        raise RuntimeError(f"Upstream SSE error: {err_obj}")
                except json.JSONDecodeError:
                    pass
            return ("", "anthropic", True)

        if not data:
            return ("", next_mode, False)

        if data == "[DONE]":
            if next_mode == "anthropic":
                return ("", "anthropic", False)
            return ("", "compat", True)

        try:
            parsed = json.loads(data)
        except json.JSONDecodeError:
            return ("", next_mode, False)

        if not isinstance(parsed, dict):
            return ("", next_mode, False)

        if parsed.get("type") == "error" or parsed.get("error"):
            err_obj = parsed.get("error") or parsed
            raise RuntimeError(f"Upstream SSE error: {err_obj}")

        msg_type = str(parsed.get("type") or "").strip().lower()
        if msg_type == "message_stop":
            return ("", "anthropic", True)

        if msg_type in self._ANTHROPIC_NATIVE_TYPES:
            next_mode = "anthropic"
        elif next_mode == "unknown":
            next_mode = "compat"

        # Anthropic 原生
        if msg_type == "content_block_delta":
            delta = parsed.get("delta", {})
            if isinstance(delta, dict) and delta.get("type") == "text_delta":
                return (str(delta.get("text") or ""), "anthropic", False)

        # Anthropic content_block_start (某些模型把 text 放在这里)
        if msg_type == "content_block_start":
            block = parsed.get("content_block", {})
            if isinstance(block, dict) and block.get("type") == "text" and block.get("text"):
                return (str(block["text"]), "anthropic", False)

        # OpenAI / DeepSeek 兼容格式
        choices = parsed.get("choices", [])
        if choices and isinstance(choices, list) and isinstance(choices[0], dict):
            delta = choices[0].get("delta", {})
            if isinstance(delta, dict):
                content = delta.get("content", "")
                if content:
                    return (str(content), next_mode, False)
                text = delta.get("text", "")
                if text:
                    return (str(text), next_mode, False)

        # 通用 fallback: 一层 delta.text 或 delta.content
        delta = parsed.get("delta", {})
        if isinstance(delta, dict):
            text = delta.get("text") or delta.get("content")
            if text:
                return (str(text), next_mode, False)

        # 最通用: 顶层 text/content 字段
        text = parsed.get("text") or parsed.get("content")
        if isinstance(text, str) and text.strip():
            return (text, next_mode, False)

        return ("", next_mode, False)

    def _parse_sse_event(self, event_text: str) -> str:
        """解析单个 SSE 事件，返回文本内容（如果有）。"""
        text_out, _, _ = self._parse_sse_event_with_state(event_text, "unknown")
        return text_out
