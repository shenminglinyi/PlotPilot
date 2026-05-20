"""CharacterId — 全项目统一的角色 ID 值对象

单一真实来源：domain/bible、domain/cast、domain/character、engine/core
均从此模块导入或 re-export。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CharacterId:
    """角色 ID 值对象"""

    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            raise ValueError("Character ID cannot be empty")

    @classmethod
    def generate(cls) -> CharacterId:
        return cls(str(uuid.uuid4()))

    def __str__(self) -> str:
        return self.value

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, CharacterId):
            return False
        return self.value == other.value

    def __hash__(self) -> int:
        return hash(self.value)
