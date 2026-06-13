import asyncio

from application.core.config.config_loader import reload_config
from application.core import async_bridge


def teardown_function():
    async_bridge.shutdown_async_bridge_executor_if_initialized()
    reload_config()


def test_async_bridge_settings_follow_performance_config(tmp_path):
    config_path = tmp_path / "performance.yaml"
    config_path.write_text(
        """
async_bridge:
  max_workers: 2
""",
        encoding="utf-8",
    )

    reload_config(str(config_path))
    settings = async_bridge.get_async_bridge_settings()

    assert settings.max_workers == 2


def test_run_coroutine_sync_runs_directly_without_active_loop():
    result = async_bridge.run_coroutine_sync(lambda: _return_value("ok"))

    assert result == "ok"


def test_run_coroutine_sync_bridges_from_active_loop():
    async def caller():
        return async_bridge.run_coroutine_sync(lambda: _return_value("bridged"))

    assert asyncio.run(caller()) == "bridged"


def test_shutdown_async_bridge_does_not_create_executor():
    async_bridge.shutdown_async_bridge_executor_if_initialized()

    assert async_bridge._executor is None


async def _return_value(value):
    await asyncio.sleep(0)
    return value
