from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from domain.character.value_objects.character_id import CharacterId
from domain.shared.time_utils import utcnow_iso

@dataclass
class Character:
    """统一角色聚合根 — 合并 Bible / 引擎心理画像 / 动态状态"""
    id: CharacterId
    novel_id: str
    name: str
    description: str = ""
    public_profile: str = ""
    hidden_profile: str = ""
    reveal_chapter: Optional[int] = None
    role: str = ""
    faction_id: Optional[str] = None
    verbal_tic: str = ""
    idle_behavior: str = ""
    voice_style: str = ""
    sentence_pattern: str = ""
    speech_tempo: str = ""
    core_belief: str = ""
    moral_taboos: List[str] = field(default_factory=list)
    active_wounds: List[Dict[str, str]] = field(default_factory=list)
    mental_state: str = "NORMAL"
    mental_state_reason: str = ""
    emotional_arc: List[Dict[str, Any]] = field(default_factory=list)
    current_state_summary: str = ""
    last_updated_chapter: int = 0
    created_at: str = field(default_factory=utcnow_iso)
    updated_at: str = field(default_factory=utcnow_iso)

    def update_state(
        self,
        chapter: int,
        mental_state: Optional[str] = None,
        summary: Optional[str] = None,
        arc_entry: Optional[Dict[str, Any]] = None,
    ) -> None:
        if mental_state:
            self.mental_state = mental_state
        if summary:
            self.current_state_summary = summary
        if arc_entry:
            self.emotional_arc.append(arc_entry)
        self.last_updated_chapter = chapter
        self.updated_at = utcnow_iso()

    def to_voice_lock(self) -> str:
        parts = [f"[角色声纹 - {self.name}]"]
        if self.core_belief:
            parts.append(f"核心信念: {self.core_belief}")
        if self.verbal_tic:
            parts.append(f"口头禅: {self.verbal_tic}")
        if self.voice_style:
            parts.append(f"语言风格: {self.voice_style}")
        if self.mental_state != "NORMAL":
            parts.append(f"当前状态: {self.mental_state}（{self.mental_state_reason}）")
        return "\n".join(parts)
