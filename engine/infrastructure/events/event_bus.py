"""事件总线 — 领域事件驱动

事件类型定义见 domain.shared.story_events（单一来源）。
此模块提供 EventBus 运行时实现。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional

from domain.shared.story_events import (
    ChapterCompletedEvent,
    CharacterTraumaEvent,
    DomainEvent,
    ForeshadowStatusChangedEvent,
    PhaseTransitionEvent,
    StoryDomainEvent,
)

logger = logging.getLogger(__name__)

# 重导出 — 保持旧 import 路径可用
__all__ = [
    "DomainEvent",
    "StoryDomainEvent",
    "ChapterCompletedEvent",
    "CharacterTraumaEvent",
    "ForeshadowStatusChangedEvent",
    "PhaseTransitionEvent",
    "EventHandler",
    "EventBus",
    "get_event_bus",
]

# 事件处理器类型
EventHandler = Callable[[Any], Any]


class EventBus:
    """事件总线

    支持：
    - 同步/异步事件处理
    - 多个处理器订阅同一事件
    - 事件历史记录（调试用）
    """

    def __init__(self):
        self._handlers: Dict[str, List[EventHandler]] = {}
        self._event_history: List[Dict[str, Any]] = []
        self._max_history = 1000

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """订阅事件"""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)
        logger.debug(f"事件订阅: {event_type} -> {handler.__name__}")

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        """取消订阅"""
        if event_type in self._handlers:
            self._handlers[event_type] = [
                h for h in self._handlers[event_type] if h != handler
            ]

    async def publish(self, event: Any) -> None:
        """发布事件（异步）"""
        event_type = getattr(event, 'event_type', 'unknown')

        # 记录历史
        self._event_history.append(
            event.to_dict() if hasattr(event, 'to_dict') else {"event_type": event_type}
        )
        if len(self._event_history) > self._max_history:
            self._event_history = self._event_history[-self._max_history:]

        # 通知处理器
        handlers = self._handlers.get(event_type, [])
        for handler in handlers:
            try:
                result = handler(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"事件处理器异常: {event_type}, {handler.__name__}, {e}")

    def publish_sync(self, event: Any) -> None:
        """发布事件（同步）"""
        event_type = getattr(event, 'event_type', 'unknown')

        self._event_history.append(
            event.to_dict() if hasattr(event, 'to_dict') else {"event_type": event_type}
        )

        handlers = self._handlers.get(event_type, [])
        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"事件处理器异常: {event_type}, {handler.__name__}, {e}")

    def get_history(self, event_type: str = None, limit: int = 50) -> List[Dict[str, Any]]:
        """获取事件历史"""
        history = self._event_history
        if event_type:
            history = [e for e in history if e.get("event_type") == event_type]
        return history[-limit:]


# 全局事件总线实例
_event_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """获取全局事件总线"""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus
