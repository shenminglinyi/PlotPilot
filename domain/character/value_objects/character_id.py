from __future__ import annotations
import uuid
from dataclasses import dataclass

@dataclass(frozen=True)
class CharacterId:
    value: str

    def __post_init__(self):
        if not self.value:
            raise ValueError("CharacterId 不能为空")

    @classmethod
    def generate(cls) -> "CharacterId":
        return cls(str(uuid.uuid4()))

    def __str__(self) -> str:
        return self.value
