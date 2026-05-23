from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Literal, Optional


Importance = Literal["major", "normal", "minor"]
NewCharacterPolicy = Literal["none", "ignore", "ephemeral", "create_bible_character"]


@dataclass
class CastSlotNotes:
    """Standard JSON stored in chapter_elements.notes for character cast slots."""

    source: str = "kernel"
    scene_function: str = "support"
    dramatic_pressure: str = ""
    knowledge_boundary: List[str] = field(default_factory=list)
    allowed_change: str = ""
    forbidden_drift: List[str] = field(default_factory=list)
    new_character_policy: NewCharacterPolicy = "none"
    needs_review: bool = False
    risk_flags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CastSlot:
    character_id: str
    name: str
    importance: Importance
    relation_type: str = "appears"
    appearance_order: Optional[int] = None
    notes: CastSlotNotes = field(default_factory=CastSlotNotes)
    is_new_suggestion: bool = True

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["notes"] = self.notes.to_dict()
        return data


@dataclass
class NewCharacterCandidate:
    name: str
    evidence: str
    narrative_function: str
    recommendation: NewCharacterPolicy
    confidence: float
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ChapterCastPlan:
    novel_id: str
    chapter_number: int
    slots: List[CastSlot] = field(default_factory=list)
    new_character_candidates: List[NewCharacterCandidate] = field(default_factory=list)
    generated_context: str = ""
    scheduling_log: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "novel_id": self.novel_id,
            "chapter_number": self.chapter_number,
            "slots": [s.to_dict() for s in self.slots],
            "new_character_candidates": [c.to_dict() for c in self.new_character_candidates],
            "new_character_hints": [
                c.name for c in self.new_character_candidates
                if c.recommendation in ("ephemeral", "create_bible_character")
            ],
            "generated_context": self.generated_context,
            "scheduling_log": list(self.scheduling_log),
        }


@dataclass
class CharacterContextLocks:
    t0: str = ""
    t1: str = ""
    t2: str = ""

    def combined(self) -> str:
        parts: List[str] = []
        if self.t0.strip():
            parts.append("【T0_CHARACTER_LOCK｜本章绝对锁定角色】\n" + self.t0.strip())
        if self.t1.strip():
            parts.append("【T1_CHARACTER_CONTEXT｜本章参与角色】\n" + self.t1.strip())
        if self.t2.strip():
            parts.append("【T2_CAST_PERMISSION｜过场许可】\n" + self.t2.strip())
        return "\n\n".join(parts)

    def to_dict(self) -> Dict[str, str]:
        return {"t0": self.t0, "t1": self.t1, "t2": self.t2, "combined": self.combined()}


@dataclass
class CharacterNarrativeProfile:
    character_id: str
    name: str
    base_profile: Dict[str, Any]
    current_state: Dict[str, Any]
    cast_history: List[Dict[str, Any]]
    relationship_edges: List[Dict[str, Any]]
    knowledge_facts: List[Dict[str, Any]]
    hidden_facts: List[Dict[str, Any]]
    open_debts: List[Dict[str, Any]]
    foreshadow_links: List[Dict[str, Any]]
    causal_links: List[Dict[str, Any]]
    recent_dialogue_samples: List[Dict[str, Any]]
    consistency_risks: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

