import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from application.engine.services.resource_manager import (
    ResourceConfig,
    ResourceManager,
    ThreadPoolResource,
    shutdown_resource_manager_if_initialized,
)


def test_thread_pool_resource_shutdown_does_not_wait_for_running_tasks():
    started = threading.Event()
    release = threading.Event()
    resource = ThreadPoolResource(
        ThreadPoolExecutor(max_workers=1, thread_name_prefix="test-resource"),
        name="test-resource",
    )

    def wait_until_released():
        started.set()
        return release.wait()

    future = resource.submit(wait_until_released)
    assert started.wait(timeout=1.0)

    try:
        start = time.perf_counter()
        assert resource.shutdown(timeout=0.01) is True
        elapsed = time.perf_counter() - start

        assert elapsed < 0.2
        assert resource.health_check() is False
        with pytest.raises(RuntimeError):
            resource.submit(lambda: None)
    finally:
        release.set()
        future.result(timeout=1.0)


def test_thread_pool_resource_health_uses_configured_pending_threshold():
    resource = ThreadPoolResource(
        ThreadPoolExecutor(max_workers=1, thread_name_prefix="test-resource"),
        name="test-resource",
        config=ResourceConfig(max_pending_tasks=0),
    )

    try:
        assert resource.health_check() is False
    finally:
        resource.shutdown()


def test_shutdown_resource_manager_if_initialized_does_not_create_manager(monkeypatch):
    monkeypatch.setattr(ResourceManager, "_instance", None)

    shutdown_resource_manager_if_initialized(timeout=0.01)

    assert ResourceManager._instance is None


def test_shutdown_resource_manager_if_initialized_stops_existing_manager(monkeypatch):
    calls = []
    manager = SimpleNamespace(
        _initialized=True,
        shutdown=lambda timeout: calls.append(timeout),
    )
    monkeypatch.setattr(ResourceManager, "_instance", manager)

    shutdown_resource_manager_if_initialized(timeout=0.25)

    assert calls == [0.25]
