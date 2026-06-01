"""AI 调用链路追踪上下文。

该模块只保存轻量、可并发隔离的 TraceContext，并提供 hash/preview 工具。
真正落库由 infrastructure.ai.trace_recorder 完成。
"""
from __future__ import annotations

import contextvars
import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Mapping

_TRACE_CONTEXT: contextvars.ContextVar["TraceContext | None"] = contextvars.ContextVar(
    "plotpilot_ai_trace_context",
    default=None,
)

REDACTED = "[已脱敏]"
SENSITIVE_FIELD_NAMES = {
    "api_key",
    "apikey",
    "authorization",
    "password",
    "secret",
    "token",
    "user_private_notes",
    "chapter_content",
}
SENSITIVE_FIELD_MARKERS = (
    "api_key",
    "authorization",
    "password",
    "secret",
    "token",
    "private",
)
DEFAULT_PREVIEW_CHARS = 320


@dataclass(slots=True)
class TraceContext:
    """一次 AI 调用链路的上下文。"""

    trace_id: str
    novel_id: str = ""
    operation: str = "ai_call"
    stage: str = ""
    stage_label: str = ""
    user_id: str | None = None
    parent_span_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    @classmethod
    def create(
        cls,
        *,
        novel_id: str | None = None,
        operation: str = "ai_call",
        stage: str = "",
        stage_label: str = "",
        user_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> "TraceContext":
        return cls(
            trace_id=str(uuid.uuid4()),
            novel_id=novel_id or "",
            operation=operation,
            stage=stage,
            stage_label=stage_label,
            user_id=user_id,
            metadata=dict(metadata or {}),
        )

    def new_span_id(self, prefix: str = "span") -> str:
        return f"{prefix}-{uuid.uuid4().hex[:12]}"


def get_current_trace() -> TraceContext | None:
    """返回当前异步上下文里的 trace；没有则返回 None。"""
    return _TRACE_CONTEXT.get()


def set_current_trace(trace: TraceContext | None) -> contextvars.Token:
    """设置当前 trace，返回 token 供调用方按需恢复。"""
    return _TRACE_CONTEXT.set(trace)


def reset_current_trace(token: contextvars.Token) -> None:
    _TRACE_CONTEXT.reset(token)


def ensure_trace(
    *,
    novel_id: str | None = None,
    operation: str = "ai_call",
    stage: str = "",
    stage_label: str = "",
    user_id: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> TraceContext:
    """确保当前上下文有 trace。

    若调用方没有显式传递 TraceContext，就创建一个自动 trace。ContextVar
    对 asyncio 任务是隔离的，不会把并发请求混在一起。
    """
    current = get_current_trace()
    if current is not None:
        if novel_id and not current.novel_id:
            current.novel_id = novel_id
        if operation and current.operation == "ai_call":
            current.operation = operation
        if stage and not current.stage:
            current.stage = stage
            current.stage_label = stage_label
        if metadata:
            current.metadata.update(dict(metadata))
        return current

    trace = TraceContext.create(
        novel_id=novel_id,
        operation=operation,
        stage=stage,
        stage_label=stage_label,
        user_id=user_id,
        metadata=metadata,
    )
    set_current_trace(trace)
    return trace


def extract_novel_id(payload: Mapping[str, Any] | None) -> str:
    """从常见变量名中提取 novel_id。"""
    if not payload:
        return ""
    for key in ("novel_id", "novelId", "novel", "book_id", "bookId"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def stable_json(value: Any) -> str:
    """生成稳定 JSON 文本；无法 JSON 化时退回 repr。"""
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    except Exception:
        return repr(value)


def content_hash(value: Any) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8", errors="replace")).hexdigest()


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return lowered in SENSITIVE_FIELD_NAMES or any(marker in lowered for marker in SENSITIVE_FIELD_MARKERS)


def preview_text(text: str, max_chars: int = DEFAULT_PREVIEW_CHARS) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]}...（共 {len(text)} 字）"


def preview_value(value: Any, *, max_chars: int = DEFAULT_PREVIEW_CHARS, depth: int = 3) -> Any:
    """生成可落库的脱敏预览，避免默认保存完整正文或密钥。"""
    if depth <= 0:
        return preview_text(str(value), max_chars)

    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, item in value.items():
            key_str = str(key)
            if _is_sensitive_key(key_str):
                out[key_str] = REDACTED
            else:
                out[key_str] = preview_value(item, max_chars=max_chars, depth=depth - 1)
        return out

    if isinstance(value, (list, tuple, set)):
        seq = list(value)
        preview = [preview_value(item, max_chars=max_chars, depth=depth - 1) for item in seq[:8]]
        if len(seq) > 8:
            preview.append(f"...（共 {len(seq)} 项）")
        return preview

    if isinstance(value, str):
        return preview_text(value, max_chars)

    if isinstance(value, (int, float, bool)) or value is None:
        return value

    return preview_text(str(value), max_chars)


def prompt_to_hash_payload(prompt: Any) -> dict[str, str]:
    return {
        "system": str(getattr(prompt, "system", "") or ""),
        "user": str(getattr(prompt, "user", "") or ""),
    }


def prompt_preview(prompt: Any) -> dict[str, str]:
    payload = prompt_to_hash_payload(prompt)
    return {
        "system": preview_text(payload["system"]),
        "user": preview_text(payload["user"]),
    }
