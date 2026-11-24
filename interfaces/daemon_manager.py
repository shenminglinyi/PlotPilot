"""Autopilot daemon process lifecycle management."""
from __future__ import annotations

import asyncio
import logging
import multiprocessing
import os
import signal
import subprocess
from dataclasses import dataclass
from typing import Any, Callable

from application.core.config.config_loader import get_config
from application.core.config.runtime_settings_utils import positive_float, section_value
from interfaces.api.settings import BackendSettings, get_backend_settings


logger = logging.getLogger(__name__)

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


@dataclass(frozen=True)
class DaemonStatus:
    running: bool
    pid: int | None


@dataclass(frozen=True)
class DaemonLifecycleSettings:
    error_sleep_seconds: float = 10.0
    powershell_list_timeout_seconds: float = 15.0
    wmic_list_timeout_seconds: float = 8.0
    orphan_taskkill_timeout_seconds: float = 5.0
    graceful_join_timeout_seconds: float = 2.0
    terminate_join_timeout_seconds: float = 1.0
    sigkill_join_timeout_seconds: float = 1.0
    windows_taskkill_timeout_seconds: float = 3.0


def get_daemon_lifecycle_settings() -> DaemonLifecycleSettings:
    daemon = getattr(get_config(), "daemon", None)
    section = getattr(daemon, "lifecycle", None)
    defaults = DaemonLifecycleSettings()
    return DaemonLifecycleSettings(
        error_sleep_seconds=positive_float(
            section_value(section, "error_sleep_seconds", defaults.error_sleep_seconds),
            defaults.error_sleep_seconds,
        ),
        powershell_list_timeout_seconds=positive_float(
            section_value(
                section,
                "powershell_list_timeout_seconds",
                defaults.powershell_list_timeout_seconds,
            ),
            defaults.powershell_list_timeout_seconds,
        ),
        wmic_list_timeout_seconds=positive_float(
            section_value(section, "wmic_list_timeout_seconds", defaults.wmic_list_timeout_seconds),
            defaults.wmic_list_timeout_seconds,
        ),
        orphan_taskkill_timeout_seconds=positive_float(
            section_value(
                section,
                "orphan_taskkill_timeout_seconds",
                defaults.orphan_taskkill_timeout_seconds,
            ),
            defaults.orphan_taskkill_timeout_seconds,
        ),
        graceful_join_timeout_seconds=positive_float(
            section_value(
                section,
                "graceful_join_timeout_seconds",
                defaults.graceful_join_timeout_seconds,
            ),
            defaults.graceful_join_timeout_seconds,
        ),
        terminate_join_timeout_seconds=positive_float(
            section_value(
                section,
                "terminate_join_timeout_seconds",
                defaults.terminate_join_timeout_seconds,
            ),
            defaults.terminate_join_timeout_seconds,
        ),
        sigkill_join_timeout_seconds=positive_float(
            section_value(
                section,
                "sigkill_join_timeout_seconds",
                defaults.sigkill_join_timeout_seconds,
            ),
            defaults.sigkill_join_timeout_seconds,
        ),
        windows_taskkill_timeout_seconds=positive_float(
            section_value(
                section,
                "windows_taskkill_timeout_seconds",
                defaults.windows_taskkill_timeout_seconds,
            ),
            defaults.windows_taskkill_timeout_seconds,
        ),
    )


def is_expected_daemon_shutdown_exception(exc: BaseException) -> bool:
    """Treat hot-reload and process-stop interruptions as normal daemon exits."""
    current = exc
    visited = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        if isinstance(current, (KeyboardInterrupt, asyncio.CancelledError)):
            return True
        current = current.__cause__ or current.__context__
    return False


def run_autopilot_daemon_process(
    stop_event,
    log_level: int,
    log_file: str,
    stream_queue=None,
    shared_state=None,
    persistence_queue=None,
) -> None:
    """Run the autopilot daemon in an isolated child process."""
    from interfaces.api.middleware.logging_config import setup_logging

    process_logger = logging.getLogger(__name__)
    lifecycle_settings = get_daemon_lifecycle_settings()
    setup_logging(level=log_level, log_file=log_file)

    if stream_queue is not None:
        from application.engine.services.streaming_bus import inject_stream_queue

        inject_stream_queue(stream_queue)
        process_logger.info("守护进程：流式队列已注入")

    if shared_state is not None:
        try:
            import sys

            sys.modules["__shared_state"] = shared_state
            from application.engine.services.shared_state_repository import (
                get_shared_state_repository,
                inject_shared_dict,
            )

            inject_shared_dict(shared_state)
            process_logger.info("守护进程：共享状态字典已注入")

            from application.engine.services.state_publisher import get_state_publisher

            get_state_publisher()
            process_logger.info("守护进程：状态发布器已初始化")
        except Exception as exc:
            process_logger.warning("共享状态注入失败（可忽略）: %s", exc)

    if persistence_queue is not None:
        try:
            from application.engine.services.persistence_queue import inject_persistence_queue

            inject_persistence_queue(persistence_queue)
            process_logger.info("守护进程：持久化队列已注入")
        except Exception as exc:
            process_logger.warning("持久化队列注入失败（可忽略）: %s", exc)

    try:
        from application.engine.services.novel_stop_signal import inject_novel_stop_events

        inject_novel_stop_events()
    except Exception as exc:
        process_logger.debug("小说停止信号模块初始化失败（可忽略）: %s", exc)

    try:
        from scripts.start_daemon import build_daemon

        daemon = build_daemon()
        process_logger.info("守护进程已启动（独立进程），开始轮询...")

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        process_logger.info("守护进程：持久化事件循环已创建")

        while not stop_event.is_set():
            try:
                try:
                    from application.engine.services.streaming_bus import streaming_bus

                    streaming_bus.consume_stop_signals()
                except Exception:
                    pass

                try:
                    from application.engine.services.shared_state_repository import (
                        get_shared_state_repository,
                    )

                    get_shared_state_repository().update_daemon_heartbeat()
                except Exception:
                    pass

                active_novels = daemon._get_active_novels()
                if active_novels:
                    for novel in active_novels:
                        if stop_event.is_set():
                            break
                        loop.run_until_complete(daemon._process_novel(novel))

                stop_event.wait(timeout=daemon.poll_interval)

            except BaseException as exc:
                if stop_event.is_set() or is_expected_daemon_shutdown_exception(exc):
                    process_logger.info("守护进程在停止/热重载期间中断，正常退出")
                    break
                process_logger.error("守护进程异常: %s", exc, exc_info=True)
                stop_event.wait(timeout=lifecycle_settings.error_sleep_seconds)

    except BaseException as exc:
        if stop_event.is_set() or is_expected_daemon_shutdown_exception(exc):
            process_logger.info("守护进程收到停止信号，正常退出")
        else:
            process_logger.error("守护进程初始化失败: %s", exc, exc_info=True)
    finally:
        process_logger.info("守护进程已停止")


def cleanup_orphan_python_processes(logger_: logging.Logger | None = None) -> None:
    """Compatibility hook: never kill processes without an ownership handle.

    A matching executable name or command line does not prove that a process is
    orphaned. Production, portable and test instances can legitimately coexist.
    AutopilotDaemonManager.stop() owns its Process handle and is the only cleanup
    path allowed to terminate that managed child. Unknown processes are left to
    the OS or explicit user action after a crash.
    """
    (logger_ or logger).info(
        "Skip global process cleanup; managed children are stopped by their owning manager"
    )


class AutopilotDaemonManager:
    """Owns the API process view of the autopilot daemon child process."""

    def __init__(
        self,
        *,
        logger: logging.Logger | None = None,
        log_level: int,
        log_file: str,
        shared_state_provider: Callable[[], dict],
        settings_provider: Callable[[], BackendSettings] = get_backend_settings,
        lifecycle_settings_provider: Callable[[], DaemonLifecycleSettings] = get_daemon_lifecycle_settings,
        process_factory: Callable[..., Any] = multiprocessing.Process,
        event_factory: Callable[[], Any] = multiprocessing.Event,
    ) -> None:
        self._logger = logger or logging.getLogger(__name__)
        self._log_level = log_level
        self._log_file = log_file
        self._shared_state_provider = shared_state_provider
        self._settings_provider = settings_provider
        self._lifecycle_settings_provider = lifecycle_settings_provider
        self._process_factory = process_factory
        self._event_factory = event_factory
        self.process = None
        self.stop_event = None

    def status(self) -> DaemonStatus:
        running = self.process is not None and self.process.is_alive()
        return DaemonStatus(
            running=running,
            pid=self.process.pid if self.process else None,
        )

    def cleanup_orphans(self) -> None:
        cleanup_orphan_python_processes(self._logger)

    def start(self) -> None:
        if self.process is not None and self.process.is_alive():
            self._logger.warning("守护进程已在运行，跳过重复启动")
            return

        if self._settings_provider().disable_auto_daemon:
            self._logger.info("守护进程自动启动已禁用（DISABLE_AUTO_DAEMON=1）")
            return

        from application.engine.services.streaming_bus import init_streaming_bus

        stream_queue = init_streaming_bus()
        shared_state = self._shared_state_provider()

        from application.engine.services.shared_state_repository import (
            init_shared_state_repository,
        )

        shared_state_repo = init_shared_state_repository(shared_state)
        self._logger.info("共享状态仓库已初始化")

        from application.engine.services.state_bootstrap import bootstrap_state

        bootstrap_stats = bootstrap_state()
        self._logger.info("状态已从 DB 加载到共享内存: %s", bootstrap_stats)

        from application.engine.services.query_service import init_query_service

        init_query_service(shared_state_repo)
        self._logger.info("查询服务已初始化")

        from application.engine.services.persistence_queue import (
            get_persistence_queue,
            initialize_persistence_queue,
            register_persistence_handlers,
        )

        persistence_queue = initialize_persistence_queue()
        register_persistence_handlers()

        queue = get_persistence_queue()
        if not queue.is_consumer_running():
            queue.start_consumer()
            self._logger.info("持久化消费者线程已启动（单一写入者模式）")
        else:
            self._logger.debug("持久化消费者已在启动早期就绪（守护进程阶段不重复启动）")

        self.stop_event = self._event_factory()
        self.process = self._process_factory(
            target=run_autopilot_daemon_process,
            args=(
                self.stop_event,
                self._log_level,
                self._log_file,
                stream_queue,
                shared_state,
                persistence_queue,
            ),
            name="AutopilotDaemon",
            daemon=True,
        )
        self.process.start()
        self._logger.info("守护进程已创建并启动（独立进程模式，流式队列 + 共享状态 + 持久化队列已传递）")

    def stop(self) -> None:
        daemon_pid = self.process.pid if self.process else None

        try:
            from application.engine.services.persistence_queue import shutdown_persistence_queue_if_initialized

            shutdown_persistence_queue_if_initialized()
        except Exception as exc:
            self._logger.debug("停止持久化消费者失败（可忽略）: %s", exc)

        try:
            from application.engine.services.streaming_bus import streaming_bus

            streaming_bus.publish_stop_signal("__all__")
        except Exception as exc:
            self._logger.debug("发布全局停止信号失败（可忽略）: %s", exc)

        if self.stop_event:
            self._logger.info("正在停止守护进程...")
            self.stop_event.set()

        if self.process and self.process.is_alive():
            lifecycle_settings = self._lifecycle_settings_provider()
            self.process.join(timeout=lifecycle_settings.graceful_join_timeout_seconds)
            if self.process.is_alive():
                self._logger.warning("守护进程未在超时时间内停止，强制终止")
                self.process.terminate()
                self.process.join(timeout=lifecycle_settings.terminate_join_timeout_seconds)
                if self.process.is_alive():
                    self._logger.warning("守护进程仍未停止，使用 SIGKILL")
                    try:
                        os.kill(self.process.pid, signal.SIGKILL)
                        self.process.join(timeout=lifecycle_settings.sigkill_join_timeout_seconds)
                    except Exception as exc:
                        self._logger.error("强制终止守护进程失败: %s", exc)
            else:
                self._logger.info("守护进程已成功停止")

        if os.name == "nt" and daemon_pid:
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(daemon_pid)],
                    capture_output=True,
                    timeout=self._lifecycle_settings_provider().windows_taskkill_timeout_seconds,
                    creationflags=NO_WINDOW,
                )
                self._logger.info("Windows: 已通过 taskkill 终止守护进程 PID=%s", daemon_pid)
            except Exception as exc:
                self._logger.debug("taskkill 终止守护进程失败（可能已退出）: %s", exc)

        self.process = None
        self.stop_event = None

        if os.name == "nt":
            self.cleanup_orphans()

    def restart(self) -> None:
        self.stop()
        self.start()
        self._logger.info("守护进程已因配置变更重启")
