"""Runtime state shared by API and background orchestration."""
from __future__ import annotations

import logging
import multiprocessing
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Callable, Dict


class AppRuntime:
    """Small runtime facade for process-shared novel state."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger(__name__)
        self._mp_manager: Any | None = None
        self._shared_state: dict | None = None

    def get_shared_state(self) -> dict:
        if self._shared_state is not None:
            return self._shared_state
        self._mp_manager = multiprocessing.Manager()
        self._shared_state = self._mp_manager.dict()
        self._logger.info("Startup: multiprocessing shared state initialized")
        return self._shared_state

    def update_shared_novel_state(self, novel_id: str, **fields: Any) -> None:
        state = self.get_shared_state()
        key = f"novel:{novel_id}"
        current = dict(state.get(key, {}))
        fields["novel_id"] = novel_id
        current.update(fields)
        current["_updated_at"] = time.time()
        state[key] = current

    def get_shared_novel_state(self, novel_id: str) -> Dict[str, Any]:
        state = self.get_shared_state()
        key = f"novel:{novel_id}"
        return dict(state.get(key, {}))


class BackendLifecycle:
    """Startup/shutdown orchestration for the backend process.

    The FastAPI entrypoint supplies process-specific callbacks for daemon
    lifecycle and Windows cleanup. This keeps infrastructure recovery and
    graceful shutdown out of ``interfaces.main`` without changing behavior.
    """

    def __init__(
        self,
        *,
        logger: logging.Logger | None = None,
        startup_time: float | None = None,
        start_daemon: Callable[[], None],
        stop_daemon: Callable[[], None],
        cleanup_orphans: Callable[[], None] | None = None,
        start_force_exit_watchdog: Callable[[], None] | None = None,
    ) -> None:
        self._logger = logger or logging.getLogger(__name__)
        self._startup_time = startup_time or time.time()
        self._start_daemon = start_daemon
        self._stop_daemon = stop_daemon
        self._cleanup_orphans = cleanup_orphans
        self._start_force_exit_watchdog = start_force_exit_watchdog

    def startup(self, registered_route_count: int) -> None:
        self._logger.info("Startup: loading application modules and route table")
        self._logger.info("Startup: FastAPI application is ready")
        self._logger.info("Startup: registered routes=%s", registered_route_count)

        if os.name == "nt" and self._cleanup_orphans is not None:
            self._logger.info("Startup: checking for orphan Windows backend processes")
            self._cleanup_orphans()

        from infrastructure.persistence.database.write_dispatch import startup_sqlite_writes_bypass_queue

        with startup_sqlite_writes_bypass_queue():
            self.stop_all_running_novels()

        self.bootstrap_persistence_consumer()
        self.recover_drafts()
        self._start_daemon()
        self.init_dag_node_registry()

    def shutdown(self) -> None:
        """Run graceful shutdown hooks shared by uvicorn and desktop shutdown."""
        if self._start_force_exit_watchdog is not None:
            self._start_force_exit_watchdog()
        self._stop_daemon()
        self.close_database(skip_checkpoint=True)
        self.checkpoint_sqlite_wal_safe()
        self.close_llm_service()
        self.log_stopped("PlotPilot service stopped")

    def windows_forced_shutdown(self) -> None:
        self._stop_daemon()
        self.close_database(skip_checkpoint=True)
        self.checkpoint_sqlite_wal_safe()
        self.log_stopped("PlotPilot service stopped (Windows forced exit)")
        logging.shutdown()
        os._exit(0)

    def bootstrap_persistence_consumer(self) -> None:
        try:
            from application.engine.services.persistence_queue import (
                get_persistence_queue,
                initialize_persistence_queue,
                register_persistence_handlers,
            )

            initialize_persistence_queue()
            register_persistence_handlers()
            get_persistence_queue().start_consumer()
            self._logger.info("Startup: persistence consumer is ready")
        except Exception as exc:
            self._logger.warning(
                "Startup: persistence consumer bootstrap failed; falling back to direct writes: %s",
                exc,
            )

    def checkpoint_sqlite_wal_safe(self) -> None:
        """Best-effort WAL checkpoint during desktop graceful shutdown."""
        try:
            from application.paths import get_db_path

            conn = sqlite3.connect(get_db_path(), timeout=2.0)
            try:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA busy_timeout=2000")
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            finally:
                conn.close()
        except Exception as exc:
            self._logger.warning("Shutdown: WAL checkpoint failed: %s", exc)

    def close_database(self, *, skip_checkpoint: bool) -> None:
        try:
            from infrastructure.persistence.database.connection import get_database

            get_database().close_all(skip_checkpoint=skip_checkpoint)
        except Exception as exc:
            self._logger.warning("Shutdown: database close failed: %s", exc)

    def close_llm_service(self) -> None:
        try:
            import asyncio

            from interfaces.api.dependencies import get_llm_service

            service = get_llm_service()
            if not hasattr(service, "aclose"):
                return
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(service.aclose())
                else:
                    loop.run_until_complete(service.aclose())
            except RuntimeError:
                pass
        except Exception:
            pass

    def log_stopped(self, title: str) -> None:
        from interfaces.api.middleware.logging_config import log_lifecycle_banner

        uptime = time.time() - self._startup_time
        log_lifecycle_banner(
            self._logger,
            title=title,
            fields={"Uptime": f"{uptime:.2f}s ({uptime / 3600:.2f}h)"},
            logo=None,
        )

    def stop_all_running_novels(self) -> None:
        """Mark previously running novels as stopped during process startup."""
        from infrastructure.persistence.database import connection as db_connection
        from infrastructure.persistence.database.connection import get_database
        from application.paths import get_db_path

        db_path = get_db_path()
        db_path_str = str(Path(db_path))
        db_path_obj = Path(db_path) if isinstance(db_path, str) else db_path

        if not db_path_obj.exists():
            self._logger.warning("Startup: database file does not exist: %s", db_path)
            return

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                db = get_database(db_path_str)

                chk = db.fetch_one(
                    "SELECT 1 AS ok FROM sqlite_master WHERE type='table' AND name='novels' LIMIT 1"
                )
                if chk is None:
                    self._logger.info("Startup: novels table is not present; skipping running-novel reset")
                    return

                cnt_row = db.fetch_one(
                    "SELECT COUNT(*) AS c FROM novels WHERE autopilot_status = 'running'"
                )
                running_count = int(cnt_row["c"]) if cnt_row and cnt_row.get("c") is not None else 0

                if running_count > 0:
                    db.execute(
                        """UPDATE novels SET autopilot_status = 'stopped', updated_at = CURRENT_TIMESTAMP
                           WHERE autopilot_status = 'running'"""
                    )
                    db.commit()
                    self._logger.info(
                        "Startup: marked %s running novels as stopped after service restart",
                        running_count,
                    )
                else:
                    self._logger.info("Startup: no running novels need reset")

                try:
                    db.get_connection().execute("PRAGMA wal_checkpoint(TRUNCATE)")
                except Exception:
                    pass
                return

            except sqlite3.OperationalError as exc:
                if "disk I/O error" in str(exc) and attempt < max_retries:
                    self._logger.warning(
                        "Startup: running-novel reset hit disk I/O error on attempt %s/%s; "
                        "clearing WAL leftovers and retrying",
                        attempt,
                        max_retries,
                    )
                    for suffix in ("-wal", "-shm"):
                        wal_file = db_path_obj.parent / (db_path_obj.name + suffix)
                        if wal_file.exists():
                            try:
                                wal_file.unlink()
                                self._logger.info("Startup: removed leftover WAL file: %s", wal_file)
                            except OSError as unlink_err:
                                self._logger.warning(
                                    "Startup: failed to remove WAL file %s: %s",
                                    wal_file,
                                    unlink_err,
                                )
                    try:
                        if db_connection._db_instance is not None:
                            db_connection._db_instance.close_all(skip_checkpoint=True)
                    except Exception:
                        pass
                    db_connection._db_instance = None
                    time.sleep(1.0 * attempt)
                else:
                    self._logger.error(
                        "Startup: failed to reset running novels: db=%s err=%s",
                        db_path_obj,
                        exc,
                        exc_info=True,
                    )
                    return
            except Exception as exc:
                self._logger.error(
                    "Startup: failed to reset running novels: db=%s err=%s",
                    db_path_obj,
                    exc,
                    exc_info=True,
                )
                return

    def recover_drafts(self) -> None:
        try:
            from application.engine.services.draft_aof import recover_all_drafts

            recovered = recover_all_drafts()
            if recovered > 0:
                self._logger.info("Startup: recovered %s chapter drafts from AOF", recovered)
            else:
                self._logger.info("Startup: AOF recovery found no draft leftovers")
        except Exception as exc:
            self._logger.warning("Startup: AOF recovery failed: %s", exc)

    def init_dag_node_registry(self) -> None:
        try:
            from application.engine.dag.nodes import (  # noqa: F401
                anti_ai_nodes,
                context_nodes,
                execution_nodes,
                ext_supplement_nodes,
                gateway_nodes,
                gen_supplement_nodes,
                planning_nodes,
                review_nodes,
                validation_nodes,
                world_nodes,
            )
            from application.engine.dag.registry import NodeRegistry

            self._logger.info("DAG 节点注册表已初始化: %s", sorted(NodeRegistry.all_types()))
        except Exception as exc:
            self._logger.warning("DAG 节点注册表初始化失败（DAG 引擎将不可用）: %s", exc)
