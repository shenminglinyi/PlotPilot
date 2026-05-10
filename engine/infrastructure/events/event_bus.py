"""事件总线 — 领域事件驱动

核心事件：
- ChapterCompletedEvent：章节完成
- CharacterTraumaEvent：角色创伤
- ForeshadowStatusChangedEvent：伏笔状态变更
- PhaseTransitionEvent：故事阶段转换

设计原则：
- 解耦领域服务间通信
- 支持同步和异步处理
- 事件不可变
- 不使用继承（避免frozen dataclass的默认参数顺序问题）
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
import asyncio

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DomainEvent:
    """领域事件基类（不可变）"""
    event_type: str
    story_id: str
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type,
            "story_id": self.story_id,
            "timestamp": self.timestamp,
            "data": self.data,
        }


@dataclass(frozen=True)
class ChapterCompletedEvent:
    """章节完成事件"""
    event_type: str = "chapter_completed"
    story_id: str = ""
    chapter_number: int = 0
    chapter_title: str = ""
    word_count: int = 0
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type,
            "story_id": self.story_id,
            "chapter_number": self.chapter_number,
            "chapter_title": self.chapter_title,
            "word_count": self.word_count,
            "timestamp": self.timestamp,
        }


@dataclass(frozen=True)
class CharacterTraumaEvent:
    """角色创伤事件"""
    event_type: str = "character_trauma"
    story_id: str = ""
    character_id: str = ""
    character_name: str = ""
    trigger_event: str = ""
    changes: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type,
            "story_id": self.story_id,
            "character_id": self.character_id,
            "character_name": self.character_name,
            "trigger_event": self.trigger_event,
            "changes": self.changes,
            "timestamp": self.timestamp,
        }


@dataclass(frozen=True)
class ForeshadowStatusChangedEvent:
    """伏笔状态变更事件"""
    event_type: str = "foreshadow_status_changed"
    story_id: str = ""
    foreshadow_id: str = ""
    old_status: str = ""
    new_status: str = ""
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type,
            "story_id": self.story_id,
            "foreshadow_id": self.foreshadow_id,
            "old_status": self.old_status,
            "new_status": self.new_status,
            "timestamp": self.timestamp,
        }


@dataclass(frozen=True)
class PhaseTransitionEvent:
    """故事阶段转换事件"""
    event_type: str = "phase_transition"
    story_id: str = ""
    from_phase: str = ""
    to_phase: str = ""
    reason: str = ""
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type,
            "story_id": self.story_id,
            "from_phase": self.from_phase,
            "to_phase": self.to_phase,
            "reason": self.reason,
            "timestamp": self.timestamp,
        }


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
