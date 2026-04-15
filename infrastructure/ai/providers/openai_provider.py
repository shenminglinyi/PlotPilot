"""OpenAI LLM 提供商实现"""
import logging
import re
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx
from openai import AsyncOpenAI

from domain.ai.services.llm_service import GenerationConfig, GenerationResult
from domain.ai.value_objects.prompt import Prompt
from domain.ai.value_objects.token_usage import TokenUsage
from infrastructure.ai.config.settings import Settings
from infrastructure.ai.llm_runtime_flags import (
    force_compat_no_think_extras,
    is_llm_reasoning_disabled,
    use_qwen_assistant_prefill,
)
from infrastructure.ai.model_resolution import resolve_openai_chat_model
from .base import BaseProvider

logger = logging.getLogger(__name__)


def _should_apply_local_no_think_extras(base_url: Optional[str]) -> bool:
    return bool((base_url or "").strip()) or force_compat_no_think_extras()


# Qwen3.5 / R1 等常见思考段标记（关闭思考后仍可能残留在 content中）
_THINK_TAG_BLOCK = re.compile(
    r"\x3cthink\x3e[\s\S]*?\x3c/think\x3e",
    re.IGNORECASE | re.DOTALL,
)
#部分 Qwen 发行版使用双尖括号
_THINK_DOUBLE_ANGLE = re.compile(
    r"\x3c\x3cthink\x3e\x3e[\s\S]*?\x3c\x3c/think\x3e\x3e",
    re.IGNORECASE | re.DOTALL,
)
_REDACTED_THINKING = re.compile(
    r"<think>[\s\S]*?</think>",
    re.IGNORECASE | re.DOTALL,
)


def _strip_text(val: Any) -> Optional[str]:
    if isinstance(val, str):
        s = val.strip()
        return s if s else None
    return None


def _text_from_content_field(raw: Any) -> Optional[str]:
    """解析 message.content：字符串或多模态列表。"""
    s = _strip_text(raw)
    if s:
        return s
    if isinstance(raw, list):
        parts: list[str] = []
        for block in raw:
            if isinstance(block, dict):
                if block.get("type") == "text" and block.get("text"):
                    t = _strip_text(block["text"])
                    if t:
                        parts.append(t)
            else:
                t = _strip_text(getattr(block, "text", None))
                if t:
                    parts.append(t)
        if parts:
            return "".join(parts)
    return None


def _strip_thinking_markers(text: str) -> str:
    """去掉模型输出的思考围栏，便于 JSON 等下游解析。"""
    s = _THINK_TAG_BLOCK.sub("", text)
    s = _THINK_DOUBLE_ANGLE.sub("", s)
    s = _REDACTED_THINKING.sub("", s)
    low = s.lower()
    if "\x3cthink\x3e" in low and "\x3c/think\x3e" not in low:
        parts = re.split(r"(?i)\x3cthink\x3e", s, maxsplit=1)
        if len(parts) == 2:
            s = parts[1]
    if "<think>" in low and "</think>" not in low:
        parts = re.split(r"(?i)<think>", s, maxsplit=1)
        if len(parts) == 2:
            s = parts[1]
    return s.strip()


def _maybe_strip_for_no_think(text: str) -> str:
    if not text or not is_llm_reasoning_disabled():
        return text
    return _strip_thinking_markers(text)


def _build_chat_messages(prompt: Prompt, base_url: Optional[str]) -> List[Dict[str, str]]:
    """构造 chat messages；在本地兼容栈上可对 Qwen3.5 追加 assistant 预填。"""
    messages: List[Dict[str, str]] = [
        {"role": "system", "content": prompt.system},
        {"role": "user", "content": prompt.user},
    ]
    if (
        _should_apply_local_no_think_extras(base_url)
        and is_llm_reasoning_disabled()
        and use_qwen_assistant_prefill()
    ):
        # Qwen：单空格即可触发「续写 assistant」跳过思考（bug-tracker #1559）
        messages.append({"role": "assistant", "content": " "})
    return messages


def _openai_no_think_request_options(base_url: Optional[str]) -> Dict[str, Any]:
    """关闭思考时附加参数：仅对配置了 base_url 的兼容网关发送扩展字段，避免官方 OpenAI 400。"""
    if not is_llm_reasoning_disabled():
        return {}
    if not _should_apply_local_no_think_extras(base_url):
        return {}
    extra: Dict[str, Any] = {
        "reasoning": "off",
        "chat_template_kwargs": {"enable_thinking": False},
    }
    if use_qwen_assistant_prefill():
        extra["continue_assistant_turn"] = True
    return {"extra_body": extra}


def _extract_chat_message_text(message: Any) -> str:
    """从 assistant message 取正文。兼容某些部署将输出放在 reasoning 字段的情况。"""
    if message is None:
        return ""

    primary = _text_from_content_field(getattr(message, "content", None))
    if primary:
        return _maybe_strip_for_no_think(primary)

    if is_llm_reasoning_disabled():
        return ""

    for attr in ("reasoning", "reasoning_content"):
        alt = _strip_text(getattr(message, attr, None))
        if alt:
            return _maybe_strip_for_no_think(alt)

    try:
        data = message.model_dump(mode="python", exclude_none=False)
    except Exception:
        data = {}
    if isinstance(data, dict):
        for key in ("content", "reasoning", "reasoning_content"):
            if key == "content":
                t = _text_from_content_field(data.get(key))
            else:
                t = _strip_text(data.get(key))
            if t:
                return _maybe_strip_for_no_think(t)
    return ""


def _extract_stream_delta_text(delta: Any) -> Optional[str]:
    """流式 chunk：content为空时尝试 reasoning / reasoning_content。"""
    if delta is None:
        return None
    order = ("content",)
    if not is_llm_reasoning_disabled():
        order = ("content", "reasoning", "reasoning_content")
    for attr in order:
        s = _strip_text(getattr(delta, attr, None))
        if s:
            return s
    return None


class OpenAIProvider(BaseProvider):
    """OpenAI LLM 提供商实现
    
    使用 OpenAI API 实现 LLM 服务。
    """

    def __init__(self, settings: Settings):
        """初始化 OpenAI 提供商
        
        Args:
            settings: AI 配置设置
            
        Raises:
            ValueError: 如果 API key 未设置
        """
        super().__init__(settings)
        
        if not settings.api_key:
            raise ValueError("API key is required for OpenAIProvider")
            
        # 初始化 AsyncOpenAI 客户端
        client_kwargs = {
            "api_key": settings.api_key,
            # 规避 openai/httpx 版本组合下 `proxies` 参数不兼容问题：
            # 显式注入 http_client，避免 SDK 内部创建默认 AsyncClient 时触发 TypeError。
            "http_client": httpx.AsyncClient(timeout=300.0),
        }
        if settings.base_url:
            client_kwargs["base_url"] = settings.base_url
            
        self.async_client = AsyncOpenAI(**client_kwargs)

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
            messages = _build_chat_messages(prompt, self.settings.base_url)

            response = await self.async_client.chat.completions.create(
                model=resolve_openai_chat_model(config.model),
                messages=messages,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
                **_openai_no_think_request_options(self.settings.base_url),
            )
            
            if not response.choices:
                raise RuntimeError("API returned no choices")

            message = response.choices[0].message
            content = _extract_chat_message_text(message)
            if not content:
                finish = getattr(response.choices[0], "finish_reason", None)
                logger.warning(
                    "Chat completion has no extractable text (finish_reason=%s). "
                    "If using reasoning models, ensure OPENAI_MODEL matches the loaded model.",
                    finish,
                )
                raise RuntimeError("API returned empty content")
            
            input_tokens = response.usage.prompt_tokens if response.usage else 0
            output_tokens = response.usage.completion_tokens if response.usage else 0
            token_usage = TokenUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens
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
        """流式生成内容
        
        Args:
            prompt: 提示词
            config: 生成配置
            
        Yields:
            生成的文本片段
            
        Raises:
            RuntimeError: 当流式生成失败时
        """
        try:
            messages = _build_chat_messages(prompt, self.settings.base_url)

            stream = await self.async_client.chat.completions.create(
                model=resolve_openai_chat_model(config.model),
                messages=messages,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
                stream=True,
                **_openai_no_think_request_options(self.settings.base_url),
            )
            
            async for chunk in stream:
                if not chunk.choices:
                    continue
                piece = _extract_stream_delta_text(chunk.choices[0].delta)
                if piece:
                    yield piece
                    
        except Exception as e:
            logger.error(f"[Stream] Failed: {e}")
            raise RuntimeError(f"Failed to stream text: {str(e)}") from e
