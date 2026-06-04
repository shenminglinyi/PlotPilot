"""Continuation handler for setup.plot_outline."""
from __future__ import annotations

import json
import re
from typing import Any, Mapping

from application.ai_invocation.continuation import ContinuationContext, register_continuation_handler

_PHASE_SCHEMA = [
    {"phase": "opening", "label": "开篇阶段", "range_percent": "1-15%"},
    {"phase": "development", "label": "发展阶段", "range_percent": "15-40%"},
    {"phase": "deepening", "label": "深化阶段", "range_percent": "40-70%"},
    {"phase": "climax", "label": "高潮阶段", "range_percent": "70-90%"},
    {"phase": "ending", "label": "收尾阶段", "range_percent": "90-100%"},
]


def _visible_length(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


def _parse_json_object(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw)
    except Exception as exc:
        raise ValueError("剧情总纲 JSON 解析失败") from exc
    if not isinstance(parsed, Mapping):
        raise ValueError("剧情总纲输出必须是 JSON 对象")
    return dict(parsed)


def _target_chapters(context: ContinuationContext) -> int:
    aliases = context.session.variable_plan.aliases if context.session.variable_plan is not None else {}
    setup_context = context.session.context.get("setup_context") if isinstance(context.session.context.get("setup_context"), Mapping) else {}
    raw = aliases.get("target_chapters") if isinstance(aliases, Mapping) else None
    if raw in (None, "", 0):
        raw = setup_context.get("target_chapters")
    try:
        value = int(raw or 0)
    except (TypeError, ValueError):
        value = 0
    return max(1, value or 100)


def _chapter_ranges(target_chapters: int) -> list[tuple[int, int]]:
    ratios = [0.15, 0.40, 0.70, 0.90, 1.0]
    ends = []
    previous = 0
    for index, ratio in enumerate(ratios):
        if index == len(ratios) - 1:
            end = target_chapters
        else:
            end = max(previous + 1, round(target_chapters * ratio))
            remaining_min = len(ratios) - index - 1
            end = min(end, target_chapters - remaining_min)
        ends.append(end)
        previous = end
    starts = [1, *(end + 1 for end in ends[:-1])]
    return list(zip(starts, ends))


def _normalize_stage_plan(raw_items: Any, *, target_chapters: int) -> list[dict[str, Any]]:
    if not isinstance(raw_items, list):
        raise ValueError("plot_outline.stage_plan 必须是数组")
    if len(raw_items) != 5:
        raise ValueError("plot_outline.stage_plan 必须包含 5 个阶段")

    ranges = _chapter_ranges(target_chapters)
    normalized: list[dict[str, Any]] = []
    seen_phases: set[str] = set()
    for index, schema in enumerate(_PHASE_SCHEMA):
        raw = raw_items[index] if index < len(raw_items) else None
        if not isinstance(raw, Mapping):
            raise ValueError(f"plot_outline.stage_plan[{index}] 必须是对象")
        phase = str(raw.get("phase") or schema["phase"]).strip().lower()
        if phase != schema["phase"]:
            raise ValueError(f"plot_outline.stage_plan[{index}].phase 必须为 {schema['phase']}")
        if phase in seen_phases:
            raise ValueError("plot_outline.stage_plan.phase 不能重复")
        seen_phases.add(phase)
        summary = str(raw.get("summary") or "").strip()
        if not summary:
            raise ValueError(f"plot_outline.stage_plan[{index}].summary 不能为空")
        key_goals_raw = raw.get("key_goals")
        key_goals = []
        if isinstance(key_goals_raw, list):
            key_goals = [str(item).strip() for item in key_goals_raw if str(item).strip()]
        chapter_start, chapter_end = ranges[index]
        normalized.append(
            {
                "phase": schema["phase"],
                "label": str(raw.get("label") or schema["label"]).strip() or schema["label"],
                "range_percent": str(raw.get("range_percent") or schema["range_percent"]).strip() or schema["range_percent"],
                "chapter_start": chapter_start,
                "chapter_end": chapter_end,
                "summary": summary,
                "key_goals": key_goals,
            }
        )
    return normalized


def setup_plot_outline_handler(context: ContinuationContext) -> Mapping[str, Any]:
    payload = _parse_json_object(context.decision.accepted_content or "")
    raw_outline = payload.get("plot_outline")
    if not isinstance(raw_outline, Mapping):
        raise ValueError("缺少 plot_outline 对象")

    outline = dict(raw_outline)
    main_story_overview = str(outline.get("main_story_overview") or "").strip()
    if not main_story_overview:
        raise ValueError("plot_outline.main_story_overview 不能为空")
    overview_length = _visible_length(main_story_overview)
    if overview_length < 120 or overview_length > 900:
        raise ValueError("plot_outline.main_story_overview 字数不符合要求，建议控制在 200-500 字")

    expected_ending = str(outline.get("expected_ending") or "").strip()
    if not expected_ending:
        raise ValueError("plot_outline.expected_ending 不能为空")

    core_conflict = str(outline.get("core_conflict") or "").strip()
    if not core_conflict:
        raise ValueError("plot_outline.core_conflict 不能为空")

    target_chapters = _target_chapters(context)
    stage_plan = _normalize_stage_plan(outline.get("stage_plan"), target_chapters=target_chapters)
    normalized_outline = {
        "main_story_overview": main_story_overview,
        "stage_plan": stage_plan,
        "expected_ending": expected_ending,
        "core_conflict": core_conflict,
    }
    return {
        "novel_id": str(context.session.context.get("novel_id") or ""),
        "plot_outline": normalized_outline,
        "main_story_overview": main_story_overview,
        "stage_plan": stage_plan,
        "expected_ending": expected_ending,
        "core_conflict": core_conflict,
        "session_id": context.session.id,
    }


def register_setup_plot_outline_continuation() -> None:
    register_continuation_handler("setup_plot_outline", setup_plot_outline_handler)
