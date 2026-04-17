"""字数控制结果 DTO。"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class WordControlDTO:
    target: int
    actual: int
    tolerance: float
    delta: int
    status: str
    within_tolerance: bool
    action: str
    expansion_attempts: int
    trim_applied: bool
    fallback_used: bool
    min_allowed: int
    max_allowed: int

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
