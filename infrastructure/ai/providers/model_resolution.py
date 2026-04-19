"""解析 LLM 请求使用的模型 ID（禁止在业务代码中写死具体模型名）。"""
from __future__ import annotations


def require_resolved_model_id(
    config_model: str,
    settings_default: str,
    *,
    provider_label: str,
) -> str:
    """合并 GenerationConfig 与 Settings 中的模型字段；二者均为空则抛出明确错误。"""
    resolved = (config_model or "").strip() or (settings_default or "").strip()
    if not resolved:
        raise ValueError(
            f"{provider_label}：未配置模型 ID。请在 LLM 控制台当前激活配置中填写「模型名」，"
            "或设置相应的环境变量后重新加载。"
        )
    return resolved
