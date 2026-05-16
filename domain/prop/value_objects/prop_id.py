from __future__ import annotations
import uuid
from dataclasses import dataclass

@dataclass(frozen=True)
class PropId:
    value: str

    def __post_init__(self):
        if not self.value:
            raise ValueError("PropId 不能为空")

    @classmethod
    def generate(cls) -> "PropId":
        return cls(str(uuid.uuid4()))

    def __str__(self) -> str:
        return self.value
