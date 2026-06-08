"""Shared policy for act and chapter pre-planning."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class ChapterPlanningPolicy:
    recent_chapter_limit: int = 3
    previous_ending_chars: int = 700
    recent_outline_chars: int = 700
    required_act_plan_fields: tuple[str, ...] = (
        "number",
        "title",
        "main_event",
        "handoff_from_previous",
        "handoff_to_next",
    )


DEFAULT_CHAPTER_PLANNING_POLICY = ChapterPlanningPolicy()


CHAPTER_EXECUTION_PLAN_MARKERS = (
    "一、开篇切入点",
    "二、场景转换列表",
    "三、关键对话",
    "四、剧情事件链",
    "五、角色关键决策",
    "六、爽点/反转设计",
    "七、主角状态变化",
)

CHAPTER_EXECUTION_PLAN_FORBIDDEN_MARKERS = (
    "故事单元检查",
    "情绪变化节点",
)


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return len(value) == 0
    return False


def validate_lightweight_act_plan(
    chapters: Any,
    *,
    expected_count: int,
    policy: ChapterPlanningPolicy = DEFAULT_CHAPTER_PLANNING_POLICY,
) -> list[str]:
    """Validate the slim act-level chapter chain before it is persisted."""
    errors: list[str] = []
    if not isinstance(chapters, list):
        return ["chapters must be a list"]
    if expected_count <= 0:
        errors.append("expected chapter count must be positive")
    if len(chapters) != expected_count:
        errors.append(f"expected {expected_count} chapters, got {len(chapters)}")

    for index, raw in enumerate(chapters, start=1):
        if not isinstance(raw, Mapping):
            errors.append(f"chapter {index} must be an object")
            continue
        try:
            number = int(raw.get("number"))
        except (TypeError, ValueError):
            number = None
        if number != index:
            errors.append(f"chapter {index} number must be {index}")
        for field in policy.required_act_plan_fields:
            if _is_blank(raw.get(field)):
                errors.append(f"chapter {index} missing required field: {field}")

    return errors


def has_rendered_chapter_execution_plan(text: str | None) -> bool:
    """Detect the seven-section execution script used by the prose pipeline."""
    value = (text or "").strip()
    if not value:
        return False
    if any(marker in value for marker in CHAPTER_EXECUTION_PLAN_FORBIDDEN_MARKERS):
        return False

    positions = [value.find(marker) for marker in CHAPTER_EXECUTION_PLAN_MARKERS]
    if any(position < 0 for position in positions):
        return False
    return positions == sorted(positions) and len(set(positions)) == len(positions)


def truncate_text(text: str | None, limit: int) -> str:
    value = (text or "").strip()
    if not value or limit <= 0:
        return ""
    return value if len(value) <= limit else value[-limit:]
