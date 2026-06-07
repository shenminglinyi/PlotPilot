from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Literal, Optional


class SnapshotStatus(str, Enum):
    ACTIVE = "active"
    STALE = "stale"
    BLOCKED = "blocked"


class CharacterStatus(str, Enum):
    ALIVE = "alive"
    DEAD = "dead"
    MISSING = "missing"
    AMBIGUOUS = "ambiguous"
    SEVERELY_INJURED = "severely_injured"


class ActionType(str, Enum):
    MOVE_CHARACTER = "MOVE_CHARACTER"
    SET_CHARACTER_STATUS = "SET_CHARACTER_STATUS"
    TRANSFER_ITEM = "TRANSFER_ITEM"
    REVEAL_FACT = "REVEAL_FACT"
    UPDATE_DEBT_PROGRESS = "UPDATE_DEBT_PROGRESS"
    UPDATE_STORYLINE_PROGRESS = "UPDATE_STORYLINE_PROGRESS"
    SET_SCENE_STATE = "SET_SCENE_STATE"
    SET_EMOTIONAL_RESIDUE = "SET_EMOTIONAL_RESIDUE"
    COMPLETE_EVENT = "COMPLETE_EVENT"


@dataclass(frozen=True)
class JSONPatchOperation:
    op: Literal["add", "replace", "remove"]
    path: str
    value: Optional[Any] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "JSONPatchOperation":
        op = str(data.get("op") or "")
        if op not in {"add", "replace", "remove"}:
            raise ValueError(f"unsupported patch op: {op}")
        path = str(data.get("path") or "")
        if not path.startswith("/"):
            raise ValueError(f"invalid patch path: {path}")
        return cls(op=op, path=path, value=data.get("value"))

    def to_dict(self) -> Dict[str, Any]:
        raw = {"op": self.op, "path": self.path}
        if self.op != "remove":
            raw["value"] = self.value
        return raw


@dataclass
class SceneStateContract:
    time_anchor: str = ""
    location: str = ""
    unresolved_actions: List[str] = field(default_factory=list)
    emotional_residue: str = ""
    narrative_modifiers: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any] | None) -> "SceneStateContract":
        raw = data or {}
        return cls(
            time_anchor=str(raw.get("time_anchor") or ""),
            location=str(raw.get("location") or ""),
            unresolved_actions=[str(x) for x in raw.get("unresolved_actions") or []],
            emotional_residue=str(raw.get("emotional_residue") or ""),
            narrative_modifiers=[str(x) for x in raw.get("narrative_modifiers") or []],
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "time_anchor": self.time_anchor,
            "location": self.location,
            "unresolved_actions": list(self.unresolved_actions),
            "emotional_residue": self.emotional_residue,
            "narrative_modifiers": list(self.narrative_modifiers),
        }


@dataclass
class CharacterStateContract:
    location: str = ""
    status: CharacterStatus = CharacterStatus.ALIVE
    inventory: List[str] = field(default_factory=list)
    known_facts: List[str] = field(default_factory=list)
    name: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any] | None) -> "CharacterStateContract":
        raw = data or {}
        valid = {s.value for s in CharacterStatus}
        status_raw = str(raw.get("status") or CharacterStatus.ALIVE.value)
        status = CharacterStatus(status_raw) if status_raw in valid else CharacterStatus.ALIVE
        return cls(
            location=str(raw.get("location") or ""),
            status=status,
            inventory=[str(x) for x in raw.get("inventory") or []],
            known_facts=[str(x) for x in raw.get("known_facts") or []],
            name=str(raw.get("name") or ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "location": self.location,
            "status": self.status.value,
            "inventory": list(self.inventory),
            "known_facts": list(self.known_facts),
            "name": self.name,
        }
