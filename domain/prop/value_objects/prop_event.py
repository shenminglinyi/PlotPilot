from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from domain.shared.time_utils import utcnow_iso

class PropEventType(str, Enum):
    INTRODUCED  = "INTRODUCED"
    USED        = "USED"
    TRANSFERRED = "TRANSFERRED"
    DAMAGED     = "DAMAGED"
    REPAIRED    = "REPAIRED"
    UPGRADED    = "UPGRADED"
    RESOLVED    = "RESOLVED"

class PropEventSource(str, Enum):
    AUTO_PATTERN = "AUTO_PATTERN"
    AUTO_LLM     = "AUTO_LLM"
    MANUAL       = "MANUAL"

@dataclass(frozen=True)
class PropEvent:
    id: str
    prop_id: str
    novel_id: str
    chapter_number: int
    event_type: PropEventType
    source: PropEventSource
    description: str = ""
    actor_character_id: Optional[str] = None
    from_holder_id: Optional[str] = None
    to_holder_id: Optional[str] = None
    created_at: str = field(default_factory=utcnow_iso)

    def is_transfer(self) -> bool:
        return self.event_type == PropEventType.TRANSFERRED

    def target_lifecycle_state(self) -> Optional["LifecycleState"]:
        from domain.prop.value_objects.lifecycle_state import LifecycleState
        mapping = {
            PropEventType.INTRODUCED:  LifecycleState.INTRODUCED,
            PropEventType.USED:        LifecycleState.ACTIVE,
            PropEventType.DAMAGED:     LifecycleState.DAMAGED,
            PropEventType.REPAIRED:    LifecycleState.ACTIVE,
            PropEventType.RESOLVED:    LifecycleState.RESOLVED,
        }
        return mapping.get(self.event_type)
