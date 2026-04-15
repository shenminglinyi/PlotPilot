"""按 Provider 将 GenerationConfig.model 解析为实际 API model标识。"""
from __future__ import annotations

import os
from typing import Optional


def resolve_openai_chat_model(requested: Optional[str]) -> str:
    """OpenAI 兼容 Chat Completions：未指定或仍为 Anthropic 系 id 时回退到 OPENAI_MODEL。"""
    default = (os.getenv("OPENAI_MODEL") or "gpt-4o").strip() or "gpt-4o"
    if not requested or not str(requested).strip():
        return default
    r = str(requested).strip()
    if r.lower().startswith("claude"):
        return default
    return r


def resolve_anthropic_model(requested: Optional[str]) -> str:
    """Anthropic Messages：未指定或误留 OpenAI/本地 id 时回退到 ANTHROPIC_MODEL。"""
    default = (os.getenv("ANTHROPIC_MODEL") or "claude-sonnet-4-6").strip() or "claude-sonnet-4-6"
    if not requested or not str(requested).strip():
        return default
    r = str(requested).strip()
    low = r.lower()
    if low.startswith("gpt-") or low.startswith("openai/"):
        return default
    return r
