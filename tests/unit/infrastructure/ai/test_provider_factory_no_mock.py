"""回归：LLM 未配置时 Provider 工厂必须直接报错，不再退回 MockProvider。

背景：此前未配置（无档案 / 缺 API Key 或模型名）会静默挂 MockProvider，
返回结构占位文案，前端显示「生成完成」——假成功。修复后必须抛
LLMNotConfiguredError，让失败冒到调用方。
"""
from __future__ import annotations

import pytest

from application.ai.llm_control_service import LLMControlService, LLMProfile
from domain.ai.errors import LLMNotConfiguredError
from infrastructure.ai.provider_factory import LLMProviderFactory


def _profile(**overrides) -> LLMProfile:
    base = dict(
        id="p1",
        name="测试档案",
        api_key="sk-test",
        model="gpt-4o-mini",
        protocol="openai",
    )
    base.update(overrides)
    return LLMProfile(**base)


def test_create_from_profile_without_profile_raises():
    factory = LLMProviderFactory(LLMControlService())
    with pytest.raises(LLMNotConfiguredError) as exc:
        factory.create_from_profile(None)
    assert "未找到任何 LLM 配置" in str(exc.value)


def test_create_from_profile_with_missing_api_key_raises():
    factory = LLMProviderFactory(LLMControlService())
    with pytest.raises(LLMNotConfiguredError) as exc:
        factory.create_from_profile(_profile(api_key="  "))
    assert "缺少 API Key" in str(exc.value)


def test_create_from_profile_with_missing_model_raises():
    factory = LLMProviderFactory(LLMControlService())
    with pytest.raises(LLMNotConfiguredError) as exc:
        factory.create_from_profile(_profile(model=""))
    assert "缺少 API Key" in str(exc.value)


def test_create_from_profile_id_unknown_id_raises():
    factory = LLMProviderFactory(LLMControlService())
    with pytest.raises(LLMNotConfiguredError) as exc:
        factory.create_from_profile_id("no-such-profile")
    assert "no-such-profile" in str(exc.value)
