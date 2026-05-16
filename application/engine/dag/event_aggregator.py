"""SSE 节点事件聚合器 -- 避免高频 SSE 事件淹没前端

策略：同节点取最新事件，每 flush_interval 批量推送一次。
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Dict, List, Optional

from application.engine.dag.models import NodeEvent

logger = logging.getLogger(__name__)


class NodeEventAggregator:
    """节点事件聚合器 -- 500ms 窗口内同节点取最新"""

    def __init__(self, flush_interval: float = 0.5):
        self._buffer: Dict[str, NodeEvent] = {}
        self._flush_interval = flush_interval
        self._lock = threading.Lock()
        self._on_flush: Optional[Callable[[List[NodeEvent]], None]] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def set_flush_callback(self, callback: Callable[[List[NodeEvent]], None]):
        """设置刷新回调"""
        self._on_flush = callback

    def push(self, event: NodeEvent):
        """推入事件（同节点取最新）"""
        with self._lock:
            self._buffer[event.node_id or event.type] = event

    def flush(self) -> List[NodeEvent]:
        """批量取出所有缓冲事件"""
        with self._lock:
            events = list(self._buffer.values())
            self._buffer.clear()
        return events

    def start(self):
        """启动后台定时刷新线程"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._flush_loop, daemon=True)
        self._thread.start()
        logger.info(f"NodeEventAggregator 启动，刷新间隔 {self._flush_interval}s")

    def stop(self):
        """停止刷新线程"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        # 刷新剩余事件
        remaining = self.flush()
        if remaining and self._on_flush:
            self._on_flush(remaining)

    def _flush_loop(self):
        while self._running:
            time.sleep(self._flush_interval)
            events = self.flush()
            if events and self._on_flush:
                try:
                    self._on_flush(events)
                except Exception as e:
                    logger.error(f"事件刷新回调异常: {e}")
