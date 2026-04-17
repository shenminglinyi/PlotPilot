"""章节生成质量控制 DTO。"""
from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class ChapterGenerationMetricsDTO:
    novel_id: str
    chapter_number: int
    generated_via: str
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
    created_at: str | None = None
    updated_at: str | None = None

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ChapterGenerationMetricsDTO":
        return cls(
            novel_id=str(payload.get("novel_id") or ""),
            chapter_number=int(payload.get("chapter_number") or 0),
            generated_via=str(payload.get("generated_via") or "manual"),
            target=int(payload.get("target") or 0),
            actual=int(payload.get("actual") or 0),
            tolerance=float(payload.get("tolerance") or 0.15),
            delta=int(payload.get("delta") or 0),
            status=str(payload.get("status") or "ok"),
            within_tolerance=bool(payload.get("within_tolerance")),
            action=str(payload.get("action") or "none"),
            expansion_attempts=int(payload.get("expansion_attempts") or 0),
            trim_applied=bool(payload.get("trim_applied")),
            fallback_used=bool(payload.get("fallback_used")),
            min_allowed=int(payload.get("min_allowed") or 0),
            max_allowed=int(payload.get("max_allowed") or 0),
            created_at=payload.get("created_at"),
            updated_at=payload.get("updated_at"),
        )
