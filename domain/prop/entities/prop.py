from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from domain.prop.value_objects.lifecycle_state import LifecycleState, validate_transition
from domain.prop.value_objects.prop_category import PropCategory
from domain.prop.value_objects.prop_event import PropEvent, PropEventType, PropEventSource
from domain.prop.value_objects.prop_id import PropId

@dataclass
class Prop:
    """道具聚合根 — 封装完整生命周期逻辑"""
    id: PropId
    novel_id: str
    name: str
    description: str = ""
    aliases: List[str] = field(default_factory=list)
    category: PropCategory = PropCategory.OTHER
    lifecycle_state: LifecycleState = LifecycleState.DORMANT
    introduced_chapter: Optional[int] = None
    resolved_chapter: Optional[int] = None
    holder_character_id: Optional[str] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    _pending_events: List[PropEvent] = field(default_factory=list, repr=False)

    def apply_event(self, event: PropEvent) -> None:
        target_state = event.target_lifecycle_state()
        if target_state is not None:
            validate_transition(self.lifecycle_state, target_state)
            self.lifecycle_state = target_state

        if event.event_type == PropEventType.INTRODUCED and self.introduced_chapter is None:
            self.introduced_chapter = event.chapter_number

        if event.event_type == PropEventType.RESOLVED:
            self.resolved_chapter = event.chapter_number

        if event.is_transfer() and event.to_holder_id is not None:
            self.holder_character_id = event.to_holder_id

        self.updated_at = datetime.utcnow().isoformat()
        self._pending_events.append(event)

    def pop_pending_events(self) -> List[PropEvent]:
        events = list(self._pending_events)
        self._pending_events.clear()
        return events

    def is_active_in_chapter(self, chapter: int) -> bool:
        intro = self.introduced_chapter or 9999
        resolved = self.resolved_chapter or 9999
        return intro <= chapter < resolved

    def display_state(self) -> str:
        labels = {
            LifecycleState.DORMANT:     "未登场",
            LifecycleState.INTRODUCED:  "已登场",
            LifecycleState.ACTIVE:      "使用中",
            LifecycleState.DAMAGED:     "损毁",
            LifecycleState.RESOLVED:    "已结局",
        }
        return labels.get(self.lifecycle_state, self.lifecycle_state.value)
