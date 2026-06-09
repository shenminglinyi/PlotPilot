import asyncio
import time

import pytest

from application.core.config.config_loader import reload_config
from application.core.async_bridge import shutdown_async_bridge_executor_if_initialized
from application.engine.services.state_bootstrap import StateBootstrap
from application.engine.services.state_bootstrap_settings import (
    StateBootstrapSettings,
    get_state_bootstrap_settings,
)


def test_state_bootstrap_settings_follow_performance_config(tmp_path):
    config_path = tmp_path / "performance.yaml"
    config_path.write_text(
        """
state_bootstrap:
  triple_fetch_timeout_seconds: 0.25
""",
        encoding="utf-8",
    )

    try:
        reload_config(str(config_path))
        settings = get_state_bootstrap_settings()

        assert settings.triple_fetch_timeout_seconds == pytest.approx(0.25)
    finally:
        reload_config()


def test_triple_fetch_worker_timeout_does_not_wait_for_slow_runner():
    bootstrap = StateBootstrap(
        shared_state=object(),
        settings=StateBootstrapSettings(triple_fetch_timeout_seconds=0.01),
    )

    async def slow_fetch():
        await asyncio.sleep(0.2)
        return ["late"]

    async def active_loop_caller():
        return bootstrap._run_async_triple_fetch(
            "novel-1",
            slow_fetch,
        )

    try:
        start = time.perf_counter()
        result = asyncio.run(active_loop_caller())
        elapsed = time.perf_counter() - start

        assert result == []
        assert elapsed < 0.15
    finally:
        shutdown_async_bridge_executor_if_initialized()
