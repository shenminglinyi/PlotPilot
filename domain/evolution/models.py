from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from domain.evolution.contracts import CharacterStatus, SnapshotStatus


SCHEMA_VERSION = "v2.0"
SNAPSHOT_STATUSES = {status.value for status in SnapshotStatus}
CHARACTER_STATUSES = {status.value for status in CharacterStatus}


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class EvolutionState:
    scene: Dict[str, Any] = field(
        default_factory=lambda: {
            "time_anchor": "",
            "location": "",
            "unresolved_actions": [],
            "emotional_residue": "",
            "narrative_modifiers": [],
        }
    )
    characters: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    items: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    facts: Dict[str, Any] = field(
        default_factory=lambda: {
            "reader_known": [],
            "character_known": {},
            "hidden": [],
        }
    )
    debts: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    storylines: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    completed_events: List[str] = field(default_factory=list)
    applied_action_ids: List[str] = field(default_factory=list)

    @classmethod
    def empty(cls) -> "EvolutionState":
        return cls()

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "EvolutionState":
        raw = dict(data or {})
        state = cls()
        state.scene.update(raw.get("scene") or {})
        state.characters = deepcopy(raw.get("characters") or {})
        state.items = deepcopy(raw.get("items") or {})
        state.facts.update(raw.get("facts") or {})
        state.debts = deepcopy(raw.get("debts") or {})
        state.storylines = deepcopy(raw.get("storylines") or {})
        state.completed_events = list(raw.get("completed_events") or [])
        state.applied_action_ids = list(raw.get("applied_action_ids") or [])
        return state

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scene": deepcopy(self.scene),
            "characters": deepcopy(self.characters),
            "items": deepcopy(self.items),
            "facts": deepcopy(self.facts),
            "debts": deepcopy(self.debts),
            "storylines": deepcopy(self.storylines),
            "completed_events": list(self.completed_events),
            "applied_action_ids": list(self.applied_action_ids),
        }

    def clone(self) -> "EvolutionState":
        return EvolutionState.from_dict(self.to_dict())


@dataclass
class EvolutionAction:
    action_id: str
    type: str
    payload: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    source_refs: List[Dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EvolutionAction":
        return cls(
            action_id=str(data.get("action_id") or ""),
            type=str(data.get("type") or ""),
            payload=dict(data.get("payload") or {}),
            confidence=float(data.get("confidence", 1.0) or 0.0),
            source_refs=list(data.get("source_refs") or []),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "type": self.type,
            "payload": deepcopy(self.payload),
            "confidence": self.confidence,
            "source_refs": deepcopy(self.source_refs),
        }


@dataclass
class ReducerError:
    action_id: str
    action_type: str
    message: str
    level: Literal["warning", "blocking"] = "blocking"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "action_type": self.action_type,
            "message": self.message,
            "level": self.level,
        }


@dataclass
class EvolutionConflict:
    conflict_id: str
    conflict_type: str
    level: str
    message: str
    resolution_status: str = "open"
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conflict_id": self.conflict_id,
            "conflict_type": self.conflict_type,
            "level": self.level,
            "message": self.message,
            "resolution_status": self.resolution_status,
            "payload": deepcopy(self.payload),
        }


@dataclass
class ChapterEvolutionSnapshot:
    snapshot_id: str
    novel_id: str
    branch_id: str
    chapter_number: int
    schema_version: str = SCHEMA_VERSION
    status: str = "active"
    opening_state: EvolutionState = field(default_factory=EvolutionState.empty)
    delta_actions: List[EvolutionAction] = field(default_factory=list)
    machine_state: EvolutionState = field(default_factory=EvolutionState.empty)
    human_override_patches: List[Dict[str, Any]] = field(default_factory=list)
    ending_state: EvolutionState = field(default_factory=EvolutionState.empty)
    source_refs: List[Dict[str, Any]] = field(default_factory=list)
    conflicts: List[Dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=utcnow_iso)
    updated_at: str = field(default_factory=utcnow_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "novel_id": self.novel_id,
            "branch_id": self.branch_id,
            "chapter_number": self.chapter_number,
            "schema_version": self.schema_version,
            "status": self.status,
            "opening_state": self.opening_state.to_dict(),
            "delta_actions": [a.to_dict() for a in self.delta_actions],
            "machine_state": self.machine_state.to_dict(),
            "human_override_patches": deepcopy(self.human_override_patches),
            "ending_state": self.ending_state.to_dict(),
            "source_refs": deepcopy(self.source_refs),
            "conflicts": deepcopy(self.conflicts),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
