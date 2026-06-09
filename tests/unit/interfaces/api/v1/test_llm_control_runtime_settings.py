import pytest

from application.core.config.config_loader import reload_config
from interfaces.api.v1.workbench import llm_control
from interfaces.api.v1.workbench.llm_control import ModelListRequest
from interfaces.api.v1.workbench.llm_control_runtime_settings import (
    get_llm_control_runtime_settings,
)


def test_llm_control_runtime_settings_follow_performance_config(tmp_path):
    config_path = tmp_path / "performance.yaml"
    config_path.write_text(
        """
workbench:
  llm_control:
    model_list_timeout_ms: 12345
    panel_cache_ttl_seconds: 0.75
    plaza_cache_ttl_seconds: 1.25
""",
        encoding="utf-8",
    )

    try:
        reload_config(str(config_path))
        settings = get_llm_control_runtime_settings()

        assert settings.model_list_timeout_ms == 12345
        assert settings.panel_cache_ttl_seconds == pytest.approx(0.75)
        assert settings.plaza_cache_ttl_seconds == pytest.approx(1.25)
    finally:
        reload_config()


@pytest.mark.asyncio
async def test_list_models_uses_configured_default_timeout(tmp_path, monkeypatch):
    config_path = tmp_path / "performance.yaml"
    config_path.write_text(
        """
workbench:
  llm_control:
    model_list_timeout_ms: 12345
""",
        encoding="utf-8",
    )
    captured = {}

    class FakeResponse:
        text = ""
        status_code = 200
        reason_phrase = "OK"

        def raise_for_status(self):
            return None

        def json(self):
            return {"data": [{"id": "model-a", "owned_by": "test"}]}

    class FakeAsyncClient:
        def __init__(self, *, timeout, trust_env):
            captured["timeout"] = timeout
            captured["trust_env"] = trust_env

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, headers):
            captured["url"] = url
            return FakeResponse()

    try:
        reload_config(str(config_path))
        monkeypatch.setattr(llm_control.httpx, "AsyncClient", FakeAsyncClient)

        result = await llm_control.list_models(
            ModelListRequest(protocol="openai", base_url="https://example.test", api_key="key")
        )

        assert captured["timeout"] == pytest.approx(12.345)
        assert captured["trust_env"] is False
        assert result.items[0].id == "model-a"
    finally:
        reload_config()


@pytest.mark.asyncio
async def test_plaza_init_uses_configured_cache_ttl(tmp_path, monkeypatch):
    config_path = tmp_path / "performance.yaml"
    config_path.write_text(
        """
workbench:
  llm_control:
    plaza_cache_ttl_seconds: 100
""",
        encoding="utf-8",
    )
    calls = []

    class FakeManager:
        def ensure_seeded(self):
            calls.append("seed")

        def get_stats(self):
            calls.append("stats")
            return {"categories": {"generation": len(calls)}}

        def get_nodes_by_category(self):
            calls.append("nodes")
            return {}

    try:
        reload_config(str(config_path))
        llm_control._invalidate_plaza_cache()
        monkeypatch.setattr(llm_control, "get_prompt_manager", lambda: FakeManager())

        first = await llm_control.plaza_init()
        second = await llm_control.plaza_init()

        assert first is second
        assert calls == ["seed", "stats", "nodes"]
    finally:
        llm_control._invalidate_plaza_cache()
        reload_config()


@pytest.mark.asyncio
async def test_plaza_init_cache_can_be_disabled(tmp_path, monkeypatch):
    config_path = tmp_path / "performance.yaml"
    config_path.write_text(
        """
workbench:
  llm_control:
    plaza_cache_ttl_seconds: 0
""",
        encoding="utf-8",
    )
    calls = []

    class FakeManager:
        def ensure_seeded(self):
            calls.append("seed")

        def get_stats(self):
            calls.append("stats")
            return {"categories": {"generation": len(calls)}}

        def get_nodes_by_category(self):
            calls.append("nodes")
            return {}

    try:
        reload_config(str(config_path))
        llm_control._invalidate_plaza_cache()
        monkeypatch.setattr(llm_control, "get_prompt_manager", lambda: FakeManager())

        await llm_control.plaza_init()
        await llm_control.plaza_init()

        assert calls == ["seed", "stats", "nodes", "seed", "stats", "nodes"]
    finally:
        llm_control._invalidate_plaza_cache()
        reload_config()
