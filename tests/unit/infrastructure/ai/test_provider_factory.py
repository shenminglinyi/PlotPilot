"""Provider 工厂缓存键的额外请求参数回归测试。"""

from application.ai.llm_control_service import LLMProfile
from infrastructure.ai.provider_factory import _make_cache_key


def _profile(**overrides):
    """构造最小可用的 LLM 配置档案，并允许覆盖指定字段。"""
    values = {
        "id": "profile-1",
        "name": "Test Profile",
        "api_key": "test-key",
        "model": "test-model",
    }
    values.update(overrides)
    return LLMProfile(**values)


def test_provider_cache_key_changes_with_extra_headers():
    """额外请求头变化时应生成不同的 Provider 缓存键。"""
    base = _profile()
    with_ua = _profile(extra_headers={"User-Agent": "UA"})

    assert _make_cache_key(base) != _make_cache_key(with_ua)


def test_provider_cache_key_changes_with_extra_query_and_body():
    """额外查询参数和请求体变化时都应刷新 Provider 缓存键。"""
    base = _profile()
    with_query = _profile(extra_query={"api-version": "2024-10-21"})
    with_body = _profile(extra_body={"reasoning_effort": "medium"})

    assert _make_cache_key(base) != _make_cache_key(with_query)
    assert _make_cache_key(base) != _make_cache_key(with_body)
