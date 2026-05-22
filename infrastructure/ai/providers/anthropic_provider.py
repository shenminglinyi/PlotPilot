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
        # 🔥 分层超时：避免 API 卡住时整个进程挂起
        _sdk_timeout = httpx.Timeout(
            connect=settings.connect_timeout,
            read=settings.read_timeout,
            write=60.0,
            pool=30.0,
        )
        self._http_client_sync = httpx.Client(timeout=_sdk_timeout, trust_env=False)
        self._http_client_async = httpx.AsyncClient(timeout=_sdk_timeout, trust_env=False)
        self.client = Anthropic(**official_client_kw, http_client=self._http_client_sync)
        self.async_client = AsyncAnthropic(**official_client_kw, http_client=self._http_client_async)

        # 流式端点专用 httpx client（长生命周期，跨请求复用连接池）
        self._stream_http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=self.settings.connect_timeout,
                read=self.settings.read_timeout,
                write=60.0,
                pool=30.0,
            ),
            trust_env=False,
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
            # 🔥 response_format 自适应：
            # Anthropic 原生支持 json_schema 格式的 response_format（2024+），
            # 但通过兼容网关（如智谱 Anthropic 兼容端点）可能不支持。
            # 安全策略：只传递 Anthropic 原生格式的 response_format
            if config.response_format:
                fmt = config.response_format
                # OpenAI 格式 → Anthropic 格式自动转换
                if fmt.get("type") == "json_object":
                    # Anthropic 没有 json_object，但可以通过 prompt 约束
                    # 在 system prompt 末尾追加 JSON 输出提示
                    create_kwargs["system"] = create_kwargs["system"] + "\n\n请只输出有效的 JSON 对象，不要包含其他文字。"
                elif fmt.get("type") == "json_schema":
                    # Anthropic 支持 json_schema（需要 API 版本 2024+）
                    create_kwargs["response_format"] = fmt

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
            async for chunk in response.aiter_text():
                buffer += chunk.replace("\r\n", "\n")
                while "\n\n" in buffer:
                    event_text, buffer = buffer.split("\n\n", 1)
                    text_content = self._parse_sse_event(event_text)
                    if text_content:
                        yield text_content

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
            async for chunk in self._stream_via_httpx(prompt, config):
                yielded_any = True
                yield chunk
        except Exception as e:
            httpx_error = e
            logger.warning(
                "[Stream] httpx SSE failed (%s), will try SDK fallback",
                self._format_stream_error(e),
            )

        if yielded_any:
            return

        try:
            async for chunk in self._stream_via_sdk(prompt, config):
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
