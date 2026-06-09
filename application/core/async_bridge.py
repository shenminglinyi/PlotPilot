"""Utilities for calling async code from synchronous call sites."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from threading import Lock
from typing import Awaitable, Callable, TypeVar

from application.core.config.config_loader import get_config
from application.core.config.runtime_settings_utils import positive_int, section_value

T = TypeVar("T")


@dataclass(frozen=True)
class AsyncBridgeSettings:
    max_workers: int = 4


def get_async_bridge_settings() -> AsyncBridgeSettings:
    section = getattr(get_config(), "async_bridge", None)
    defaults = AsyncBridgeSettings()
    return AsyncBridgeSettings(
        max_workers=positive_int(
            section_value(section, "max_workers", defaults.max_workers),
            defaults.max_workers,
        ),
    )


_executor: ThreadPoolExecutor | None = None
_executor_lock = Lock()


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is not None:
        return _executor
    with _executor_lock:
        if _executor is None:
            settings = get_async_bridge_settings()
            _executor = ThreadPoolExecutor(
                max_workers=settings.max_workers,
                thread_name_prefix="async-bridge",
            )
    return _executor


async def _await_with_optional_timeout(
    coroutine_factory: Callable[[], Awaitable[T]],
    timeout: float | None,
) -> T:
    coroutine = coroutine_factory()
    if timeout is None:
        return await coroutine
    return await asyncio.wait_for(coroutine, timeout=timeout)


def run_coroutine_sync(
    coroutine_factory: Callable[[], Awaitable[T]],
    *,
    timeout: float | None = None,
) -> T:
    """Run an async operation from sync code, even when an event loop is active."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_await_with_optional_timeout(coroutine_factory, timeout))

    future = _get_executor().submit(
        lambda: asyncio.run(_await_with_optional_timeout(coroutine_factory, timeout))
    )
    try:
        return future.result(timeout=timeout)
    except FuturesTimeoutError:
        future.cancel()
        raise


def shutdown_async_bridge_executor_if_initialized() -> None:
    """Stop async bridge workers without creating the shared executor."""
    global _executor
    with _executor_lock:
        executor = _executor
        _executor = None
    if executor is not None:
        executor.shutdown(wait=False, cancel_futures=True)
