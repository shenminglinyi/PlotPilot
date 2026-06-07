"""故事引擎领域事件 — 全项目统一的事件类型系统

engine/core/ports（EventPort 契约）与 engine/infrastructure/events（EventBus 实现）
均从此模块导入。聚合根事件见 domain.shared.events.AggregateDomainEvent。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

from domain.shared.time_utils import utcnow


@dataclass(frozen=True, kw_only=True)
class StoryDomainEvent:
    """故事引擎领域事件基类（不可变）"""

    event_type: str
    story_id: str
    timestamp: str = field(default_factory=lambda: utcnow().isoformat())
    source: str = ""
    trace_id: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "event_type": self.event_type,
            "story_id": self.story_id,
            "timestamp": self.timestamp,
            "source": self.source,
            "trace_id": self.trace_id,
        }
        if self.payload:
            result["payload"] = self.payload
        return result


@dataclass(frozen=True, kw_only=True)
class ChapterCompletedEvent(StoryDomainEvent):
    """章节完成事件"""

    event_type: str = "chapter_completed"
    chapter_number: int = 0
    chapter_title: str = ""
    word_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type,
            "story_id": self.story_id,
            "chapter_number": self.chapter_number,
            "chapter_title": self.chapter_title,
            "word_count": self.word_count,
            "timestamp": self.timestamp,
            "source": self.source,
            "trace_id": self.trace_id,
        }


@dataclass(frozen=True, kw_only=True)
class CharacterTraumaEvent(StoryDomainEvent):
    """角色创伤事件"""

    event_type: str = "character_trauma"
    character_id: str = ""
    character_name: str = ""
    trigger_event: str = ""
    changes: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type,
            "story_id": self.story_id,
            "character_id": self.character_id,
            "character_name": self.character_name,
            "trigger_event": self.trigger_event,
            "changes": self.changes,
            "timestamp": self.timestamp,
            "source": self.source,
            "trace_id": self.trace_id,
        }


@dataclass(frozen=True, kw_only=True)
class ForeshadowStatusChangedEvent(StoryDomainEvent):
    """伏笔状态变更事件"""

    event_type: str = "foreshadow_status_changed"
    foreshadow_id: str = ""
    old_status: str = ""
    new_status: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type,
            "story_id": self.story_id,
            "foreshadow_id": self.foreshadow_id,
            "old_status": self.old_status,
            "new_status": self.new_status,
            "timestamp": self.timestamp,
            "source": self.source,
            "trace_id": self.trace_id,
        }


@dataclass(frozen=True, kw_only=True)
class PhaseTransitionEvent(StoryDomainEvent):
    """故事阶段转换事件"""

    event_type: str = "phase_transition"
    from_phase: str = ""
    to_phase: str = ""
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type,
            "story_id": self.story_id,
            "from_phase": self.from_phase,
            "to_phase": self.to_phase,
            "reason": self.reason,
            "timestamp": self.timestamp,
            "source": self.source,
            "trace_id": self.trace_id,
        }


# EventPort 契约别名 — 引擎端口层统一使用此名称
DomainEvent = StoryDomainEvent

__all__ = [
    "StoryDomainEvent",
    "DomainEvent",
    "ChapterCompletedEvent",
    "CharacterTraumaEvent",
    "ForeshadowStatusChangedEvent",
    "PhaseTransitionEvent",
]
