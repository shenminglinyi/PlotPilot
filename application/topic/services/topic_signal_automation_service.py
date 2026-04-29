"""市场信号自动采集后台服务。"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

from application.topic.dtos import TopicMarketSignalCollectRequestDTO

logger = logging.getLogger(__name__)


class TopicSignalAutomationService:
    """轻量后台线程：按配置定时抓取市场信号。"""

    def __init__(self, topic_service, poll_interval_seconds: int = 60):
        self._topic_service = topic_service
        self._poll_interval_seconds = max(10, int(poll_interval_seconds or 60))
        self._stop_event = threading.Event()
        self._worker: threading.Thread | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            if self._worker and self._worker.is_alive():
                return
            self._stop_event.clear()
            self._worker = threading.Thread(
                target=self._worker_loop,
                daemon=True,
                name="topic-signal-automation",
            )
            self._worker.start()
            logger.info("TopicSignalAutomationService worker thread started")

    def stop(self) -> None:
        with self._lock:
            self._stop_event.set()
            worker = self._worker
            self._worker = None
        if worker and worker.is_alive():
            worker.join(timeout=2.0)

    def run_pending_once(self, force: bool = False) -> bool:
        settings = self._topic_service.get_market_signal_settings()
        if not settings.enabled and not force:
            return False
        if not force and not self._is_due(settings):
            return False
        now = datetime.now(timezone.utc).isoformat()
        try:
            self._topic_service.collect_market_signals(
                TopicMarketSignalCollectRequestDTO(
                    source_keys=settings.selected_source_keys,
                    limit_per_source=settings.limit_per_source,
                )
            )
            self._topic_service.update_market_signal_settings(
                {
                    "last_run_at": now,
                    "last_status": "success",
                    "last_error": "",
                }
            )
            return True
        except Exception as exc:
            logger.warning("topic signal automation run failed: %s", exc)
            self._topic_service.update_market_signal_settings(
                {
                    "last_run_at": now,
                    "last_status": "error",
                    "last_error": str(exc),
                }
            )
            return False

    def _worker_loop(self) -> None:
        self.run_forever(stop_event=self._stop_event, run_immediately=False)

    def run_forever(self, stop_event: threading.Event | None = None, run_immediately: bool = True) -> None:
        """按配置持续采集，供独立守护进程复用。"""
        active_stop_event = stop_event or self._stop_event
        if run_immediately:
            try:
                self.run_pending_once(force=False)
            except Exception as exc:
                logger.warning("topic signal automation loop failed: %s", exc)

        while not active_stop_event.wait(self._poll_interval_seconds):
            try:
                self.run_pending_once(force=False)
            except Exception as exc:
                logger.warning("topic signal automation loop failed: %s", exc)

    @staticmethod
    def _is_due(settings) -> bool:
        last_run_at = str(getattr(settings, "last_run_at", "") or "").strip()
        if not last_run_at:
            return True
        try:
            last_dt = datetime.fromisoformat(last_run_at)
        except ValueError:
            return True
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        delta_seconds = (datetime.now(timezone.utc) - last_dt.astimezone(timezone.utc)).total_seconds()
        return delta_seconds >= max(15, int(getattr(settings, "interval_minutes", 180) or 180)) * 60
