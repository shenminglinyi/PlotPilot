"""Foreshadow实体 — 伏笔生命周期管理

统一入口：engine.core.entities.foreshadow
旧入口：engine.domain.entities.foreshadow（兼容层，re-export）

状态机升级：新增AWAKENING（苏醒）阶段
- PLANTED → REFERENCED → AWAKENING → RESOLVED
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List
import uuid


class ForeshadowStatus(str, Enum):
    """伏笔状态 — 4阶段生命周期"""
    PLANTED = "planted"          # 已埋下（草蛇灰线）
    REFERENCED = "referenced"    # 已提及（记忆强化）
    AWAKENING = "awakening"      # 苏醒中（唤醒铺垫）
    RESOLVED = "resolved"        # 已回收（填坑爆发）
    ABANDONED = "abandoned"      # 已放弃


@dataclass(frozen=True)
class ForeshadowId:
    """伏笔ID值对象"""
    value: str

    @classmethod
    def generate(cls) -> ForeshadowId:
        return cls(value=str(uuid.uuid4()))


class ForeshadowBinding:
    """伏笔绑定对象层级 — 从小到大"""
    CHARACTER = 1
    FACTION = 2
    EVENT = 3
    WORLD = 4

    LEVEL_NAMES = {
        1: "character",
        2: "faction",
        3: "event",
        4: "world",
    }

    @classmethod
    def validate_binding(cls, foreshadow: "Foreshadow") -> bool:
        if foreshadow.emotional_weight > 0.8:
            return foreshadow.binding_level >= cls.EVENT
        return True


@dataclass
class Foreshadow:
    """伏笔实体"""
    id: ForeshadowId
    description: str
    planted_in_chapter: int
    status: ForeshadowStatus = ForeshadowStatus.PLANTED
    importance: int = 2

    emotional_weight: float = 0.5
    planting_atmosphere: str = ""
    echo_instruction: str = ""
    binding_level: int = ForeshadowBinding.CHARACTER

    suggested_resolve_chapter: Optional[int] = None
    resolved_in_chapter: Optional[int] = None

    reference_chapters: List[int] = field(default_factory=list)
    reference_count: int = 0

    def __post_init__(self):
        if not isinstance(self.id, ForeshadowId):
            self.id = ForeshadowId(self.id) if isinstance(self.id, str) else self.id
        if self.planted_in_chapter < 1:
            raise ValueError("planted_in_chapter must be >= 1")
        if not self.description or not self.description.strip():
            raise ValueError("description cannot be empty")
        if not 0.0 <= self.emotional_weight <= 1.0:
            raise ValueError("emotional_weight must be between 0.0 and 1.0")

    @classmethod
    def create(
        cls,
        description: str,
        planted_in_chapter: int,
        emotional_weight: float = 0.5,
        binding_level: int = ForeshadowBinding.EVENT,
        planting_atmosphere: str = "",
        echo_instruction: str = "",
        suggested_resolve_chapter: Optional[int] = None,
    ) -> "Foreshadow":
        return cls(
            id=ForeshadowId.generate(),
            description=description,
            planted_in_chapter=planted_in_chapter,
            emotional_weight=emotional_weight,
            binding_level=binding_level,
            planting_atmosphere=planting_atmosphere,
            echo_instruction=echo_instruction,
            suggested_resolve_chapter=suggested_resolve_chapter,
        )

    def reference(self, chapter_number: int) -> None:
        if chapter_number not in self.reference_chapters:
            self.reference_chapters.append(chapter_number)
            self.reference_count += 1
        if self.status == ForeshadowStatus.PLANTED:
            self.status = ForeshadowStatus.REFERENCED

    def awaken(self) -> None:
        if self.status in (ForeshadowStatus.PLANTED, ForeshadowStatus.REFERENCED):
            self.status = ForeshadowStatus.AWAKENING

    def resolve(self, resolved_in_chapter: int) -> None:
        if self.status in (ForeshadowStatus.PLANTED, ForeshadowStatus.REFERENCED, ForeshadowStatus.AWAKENING):
            self.status = ForeshadowStatus.RESOLVED
            self.resolved_in_chapter = resolved_in_chapter

    def abandon(self) -> None:
        self.status = ForeshadowStatus.ABANDONED

    def is_core(self) -> bool:
        return self.emotional_weight > 0.8

    def validate_binding(self) -> bool:
        return ForeshadowBinding.validate_binding(self)

    def to_t0_awakening_instruction(self) -> str:
        if self.status != ForeshadowStatus.AWAKENING:
            return ""
        parts = [f"[伏笔苏醒提醒 - 第{self.planted_in_chapter}章埋设]"]
        parts.append(f"伏笔内容：{self.description}")
        if self.planting_atmosphere:
            parts.append(f"埋设氛围：{self.planting_atmosphere}")
        if self.echo_instruction:
            parts.append(f"呼应指令：{self.echo_instruction}")
        else:
            parts.append("请在描写相关场景时自然呼应此伏笔的氛围和意象")
        return "\n".join(parts)

    def to_dict(self) -> dict:
        return {
            "id": self.id.value,
            "description": self.description,
            "planted_in_chapter": self.planted_in_chapter,
            "status": self.status.value,
            "emotional_weight": self.emotional_weight,
            "binding_level": ForeshadowBinding.LEVEL_NAMES.get(self.binding_level, "unknown"),
            "reference_count": self.reference_count,
            "resolved_in_chapter": self.resolved_in_chapter,
        }
