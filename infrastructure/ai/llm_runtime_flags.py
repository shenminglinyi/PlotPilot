"""LLM 运行时开关（环境变量）。"""
from __future__ import annotations

import os


def _env_truthy(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in ("1", "true", "yes")


def is_llm_reasoning_disabled() -> bool:
    """为真时：在 OpenAI 兼容请求中尽量关闭思考/推理；解析响应时不把 reasoning 当作最终输出。

    环境变量：``LLM_DISABLE_REASONING``（``1`` / ``true`` / ``yes`` 为开启）。
    """
    return _env_truthy("LLM_DISABLE_REASONING")


def force_compat_no_think_extras() -> bool:
    """未配置 ``OPENAI_BASE_URL`` 时仍向请求体注入 Qwen 兼容扩展字段（部分反向代理无 base_url）。"""
    return _env_truthy("LLM_FORCE_COMPAT_NO_THINK_EXTRAS")


def use_qwen_assistant_prefill() -> bool:
    """Qwen3.5：在消息末尾追加空的 assistant 段以跳过思考阶段（见相关 bug tracker #1559）。

    仅在 ``LLM_DISABLE_REASONING`` 生效且未显式关闭时启用：
    ``LLM_QWEN_ASSISTANT_PREFILL=false`` 可禁用。
    """
    if not is_llm_reasoning_disabled():
        return False
    v = (os.getenv("LLM_QWEN_ASSISTANT_PREFILL") or "").strip().lower()
    if v in ("0", "false", "no"):
        return False
    return True
