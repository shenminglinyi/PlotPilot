"""LLM 控制台 API 辅助逻辑测试。"""

from interfaces.api.v1.workbench.llm_control import _fallback_model_items_for_gateway


def test_fallback_model_items_for_dashscope_kimi_gateway_keeps_current_model_first():
    items = _fallback_model_items_for_gateway(
        "https://coding-intl.dashscope.aliyuncs.com/v1",
        "kimi-k2.5",
    )

    assert [item.id for item in items][:2] == ["kimi-k2.5", "kimi-k2.6"]
    assert all(item.owned_by == "fallback" for item in items)


def test_fallback_model_items_for_unknown_gateway_returns_empty():
    assert _fallback_model_items_for_gateway("https://api.deepseek.com", "") == []
