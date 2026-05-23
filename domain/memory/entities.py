from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional
from uuid import uuid4


@dataclass
class NarrativeEntity:
    id: str = field(default_factory=lambda: str(uuid4()))
    novel_id: str = ""
    entity_type: str = "character"
    canonical_name: str = ""
    aliases: List[str] = field(default_factory=list)
    lifecycle_status: str = "active"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MemoryAtom:
    id: str = field(default_factory=lambda: str(uuid4()))
    novel_id: str = ""
    entity_id: str = ""
    entity_type: str = "character"
    memory_type: str = "fact"
    scope: str = "global"
    source: str = "manual"
    status: str = "candidate"
    payload: Dict[str, Any] = field(default_factory=dict)
    chapter_number: Optional[int] = None
    text_span: str = ""
    confidence: float = 0.5

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MemoryProjection:
    novel_id: str
    entity_id: str
    entity_type: str = "character"
    projection_type: str = "character"
    version: int = 1
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MemoryCalibrationAction:
    id: str = field(default_factory=lambda: str(uuid4()))
    novel_id: str = ""
    atom_id: str = ""
    action: str = "confirm"
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

