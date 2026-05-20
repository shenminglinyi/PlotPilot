"""守护进程主循环 — Phase 5 从 AutopilotDaemon 收拢到 engine/runtime"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class DaemonLoopHost(Protocol):
    """守护进程主循环所需的最小 host 接口"""

    poll_interval: int
    circuit_breaker: Any

    def _write_daemon_heartbeat(self) -> None: ...
    def _get_active_novels(self) -> list: ...
    def _cleanup_stale_stop_signals(self, active_novels: list) -> None: ...
    async def _process_novel(self, novel: Any) -> None: ...


def run_daemon_loop(host: DaemonLoopHost, *, banner: str | None = None) -> None:
    """守护进程主循环（事务最小化原则）

    AutopilotDaemon、StoryPipelineRunner、EngineDaemon 共用此循环。
    """
    if banner:
        logger.info("=" * 80)
        logger.info(banner)
        logger.info("=" * 80)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    loop_count = 0
    while True:
        loop_count += 1
        loop_start = time.time()

        host._write_daemon_heartbeat()

        if host.circuit_breaker and host.circuit_breaker.is_open():
            wait = host.circuit_breaker.wait_seconds()
            logger.warning("熔断器打开，暂停 %.0fs", wait)
            time.sleep(min(wait, host.poll_interval))
            continue

        try:
            try:
                from application.engine.services.streaming_bus import streaming_bus

                streaming_bus.consume_stop_signals()
            except Exception:
                pass

            active_novels = host._get_active_novels()

            if active_novels:
                host._cleanup_stale_stop_signals(active_novels)

            if loop_count % 10 == 1:
                logger.info("Loop #%s: 发现 %s 本活跃小说", loop_count, len(active_novels))

            if active_novels:
                for novel in active_novels:
                    novel_start = time.time()
                    loop.run_until_complete(host._process_novel(novel))
                    novel_elapsed = time.time() - novel_start
                    logger.debug(
                        "   [%s] 处理耗时: %.2fs",
                        getattr(getattr(novel, "novel_id", None), "value", novel),
                        novel_elapsed,
                    )

        except Exception as e:
            logger.error("Daemon 顶层异常: %s", e, exc_info=True)

        loop_elapsed = time.time() - loop_start
        if loop_elapsed > host.poll_interval * 2:
            logger.warning("Loop #%s 耗时过长: %.2fs", loop_count, loop_elapsed)

        time.sleep(host.poll_interval)
