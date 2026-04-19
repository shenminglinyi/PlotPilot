# domain/novel/entities/subtext_ledger_entry.py
"""伏笔手账本条目（手动）：主角或读者当下的疑问，本阶段兑现即可，不必写长文。"""
from datetime import datetime
from typing import Optional
from dataclasses import dataclass


@dataclass(frozen=True)
class SubtextLedgerEntry:
    """不可变值对象。"""

    id: str
    chapter: int
    character_id: str
    question: str
    status: str  # "pending" | "consumed"
    consumed_at_chapter: Optional[int] = None
    suggested_resolve_chapter: Optional[int] = None
    resolve_chapter_window: Optional[int] = None
    importance: str = "medium"
    created_at: datetime = None

    def __post_init__(self):
        if self.created_at is None:
            object.__setattr__(self, "created_at", datetime.utcnow())

        if self.status not in ("pending", "consumed"):
            raise ValueError(f"Invalid status: {self.status}. Must be 'pending' or 'consumed'")

        if self.status == "consumed" and self.consumed_at_chapter is None:
            raise ValueError("consumed_at_chapter must be set when status is 'consumed'")

        if self.status == "pending" and self.consumed_at_chapter is not None:
            raise ValueError("consumed_at_chapter must be None when status is 'pending'")

        valid_importance = ("low", "medium", "high", "critical")
        if self.importance not in valid_importance:
            raise ValueError(f"Invalid importance: {self.importance}. Must be one of {valid_importance}")

        if self.suggested_resolve_chapter is not None and self.suggested_resolve_chapter < self.chapter:
            raise ValueError("suggested_resolve_chapter must be >= chapter (埋入章节)")
