"""选题立项领域模型。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, Optional
from uuid import uuid4


class TopicIdeaStatus(str, Enum):
    """选题候选状态。"""

    DRAFT = "draft"
    ADOPTED = "adopted"
    ARCHIVED = "archived"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clean_text(value: Optional[str]) -> str:
    return (value or "").strip()


def _clean_list(values: Optional[Iterable[str] | str]) -> list[str]:
    if not values:
        return []
    if isinstance(values, str):
        text = _clean_text(values)
        return [text] if text else []
    result: list[str] = []
    for value in values:
        text = _clean_text(str(value))
        if text and text not in result:
            result.append(text)
    return result


def _clean_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _normalize_status(status: TopicIdeaStatus | str) -> TopicIdeaStatus:
    if isinstance(status, TopicIdeaStatus):
        return status
    try:
        return TopicIdeaStatus(str(status).strip())
    except ValueError as exc:
        raise ValueError(f"Invalid topic idea status: {status}") from exc


@dataclass
class TopicIdea:
    """选题立项池候选。"""

    title: str
    genre: str = ""
    world_preset: str = ""
    length_tier: str = ""
    logline: str = ""
    premise: str = ""
    protagonist_hook: str = ""
    core_conflict: str = ""
    opening_hook: str = ""
    selling_points: list[str] = field(default_factory=list)
    long_term_potential: str = ""
    risk_notes: list[str] = field(default_factory=list)
    market_tags: list[str] = field(default_factory=list)
    score: int = 0
    adopted_novel_id: Optional[str] = None
    source_brief: dict[str, Any] = field(default_factory=dict)
    development_notes: dict[str, Any] = field(default_factory=dict)
    evaluation: dict[str, Any] = field(default_factory=dict)
    status: TopicIdeaStatus | str = TopicIdeaStatus.DRAFT
    id: str = field(default_factory=lambda: f"topic-{uuid4().hex}")
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        self.id = _clean_text(self.id) or f"topic-{uuid4().hex}"
        self.title = _clean_text(self.title)
        if not self.title:
            raise ValueError("Topic idea title cannot be empty")

        self.genre = _clean_text(self.genre)
        self.world_preset = _clean_text(self.world_preset)
        self.length_tier = _clean_text(self.length_tier)
        self.logline = _clean_text(self.logline)
        self.premise = _clean_text(self.premise)
        self.protagonist_hook = _clean_text(self.protagonist_hook)
        self.core_conflict = _clean_text(self.core_conflict)
        self.opening_hook = _clean_text(self.opening_hook)
        self.selling_points = _clean_list(self.selling_points)
        self.long_term_potential = _clean_text(self.long_term_potential)
        self.risk_notes = _clean_list(self.risk_notes)
        self.market_tags = _clean_list(self.market_tags)
        self.source_brief = _clean_dict(self.source_brief)
        self.development_notes = _clean_dict(self.development_notes)
        self.evaluation = _clean_dict(self.evaluation)
        self.status = _normalize_status(self.status)
        self.adopted_novel_id = _clean_text(self.adopted_novel_id) or None

        try:
            self.score = int(round(float(self.score)))
        except (TypeError, ValueError):
            self.score = 0
        self.score = max(0, min(100, self.score))

    def update_status(
        self,
        status: TopicIdeaStatus | str,
        adopted_novel_id: Optional[str] = None,
    ) -> None:
        """更新状态并刷新更新时间。"""
        self.status = _normalize_status(status)
        if adopted_novel_id is not None:
            self.adopted_novel_id = _clean_text(adopted_novel_id) or None
        if self.status != TopicIdeaStatus.ADOPTED:
            self.adopted_novel_id = None
        self.updated_at = _now()
