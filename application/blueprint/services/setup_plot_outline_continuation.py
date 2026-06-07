"""Continuation handler for setup.plot_outline."""
from __future__ import annotations

import re
from typing import Any, Mapping

from application.ai.llm_json_extract import parse_llm_json_to_dict
from application.ai_invocation.continuation import ContinuationContext, register_continuation_handler
from application.ai_invocation.output_binding_resolution import (
    extract_bound_output_values,
    load_session_output_bindings,
)

_PHASE_SCHEMA = [
    {"phase": "opening", "label": "开篇阶段", "range_percent": "1-15%"},
    {"phase": "development", "label": "发展阶段", "range_percent": "15-40%"},
    {"phase": "deepening", "label": "深化阶段", "range_percent": "40-70%"},
    {"phase": "climax", "label": "高潮阶段", "range_percent": "70-90%"},
    {"phase": "ending", "label": "收尾阶段", "range_percent": "90-100%"},
]

_PHASE_ALIASES = {
    "opening": "opening",
    "open": "opening",
    "start": "opening",
    "beginning": "opening",
    "setup": "opening",
    "开篇": "opening",
    "开篇阶段": "opening",
    "开局": "opening",
    "起始": "opening",
    "development": "development",
    "develop": "development",
    "rising": "development",
    "rising_action": "development",
    "发展": "development",
    "发展阶段": "development",
    "展开": "development",
    "deepening": "deepening",
    "deepen": "deepening",
    "middle": "deepening",
    "mid": "deepening",
    "深化": "deepening",
    "深化阶段": "deepening",
    "深入": "deepening",
    "climax": "climax",
    "peak": "climax",
    "high": "climax",
    "高潮": "climax",
    "高潮阶段": "climax",
    "爆发": "climax",
    "ending": "ending",
    "end": "ending",
    "finale": "ending",
    "resolution": "ending",
    "收尾": "ending",
    "收尾阶段": "ending",
    "结尾": "ending",
    "结局": "ending",
}

_LEGACY_STAGE_KEY_ALIASES = [
    ("stage_opening_1_15", "stage_opening", "opening"),
    ("stage_develop_15_40", "stage_develop", "development"),
    ("stage_deepen_40_70", "stage_deepen", "deepening"),
    ("stage_climax_70_90", "stage_climax", "climax"),
    ("stage_end_90_100", "stage_end", "stage_ending", "ending"),
]

_MAIN_OVERVIEW_KEYS = (
    "main_story_overview",
    "outline_main",
    "main_axis",
    "overview",
    "story_overview",
    "故事主线概述",
    "主线概述",
    "故事概述",
)
_EXPECTED_ENDING_KEYS = (
    "expected_ending",
    "ending_expect",
    "ending_expectation",
    "expectedEnding",
    "ending",
    "finale",
    "预期结局",
    "预期结尾",
    "结局预期",
    "故事最终走向",
)
_CORE_CONFLICT_KEYS = (
    "core_conflict",
    "coreConflict",
    "conflict",
    "main_conflict",
    "核心冲突",
    "核心矛盾",
    "核心对抗",
)
_STAGE_PLAN_KEYS = ("stage_plan", "stages", "阶段规划")


def _visible_length(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


def _first_text(payload: Mapping[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            text = str(value).strip()
            if text:
                return text
    return ""


def _first_value(payload: Mapping[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in payload and payload.get(key) not in (None, ""):
            return payload.get(key)
    return None


def _normalize_outline_aliases(payload: Mapping[str, Any]) -> dict[str, Any]:
    outline = dict(payload)
    outline["main_story_overview"] = _first_text(outline, _MAIN_OVERVIEW_KEYS)
    outline["expected_ending"] = _first_text(outline, _EXPECTED_ENDING_KEYS)
    outline["core_conflict"] = _first_text(outline, _CORE_CONFLICT_KEYS)
    stage_plan = _first_value(outline, _STAGE_PLAN_KEYS)
    if stage_plan is not None:
        outline["stage_plan"] = stage_plan
    return outline


def _parse_json_object(raw: str) -> dict[str, Any]:
    parsed, errors = parse_llm_json_to_dict(raw)
    if parsed is None:
        detail = errors[0] if errors else "未知错误"
        raise ValueError(f"剧情总纲 JSON 解析失败: {detail}")
    if not isinstance(parsed, Mapping):
        raise ValueError("剧情总纲输出必须是 JSON 对象")
    return dict(parsed)


def _coerce_legacy_outline(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    if "plot_outline" in payload:
        raw_outline = payload.get("plot_outline")
        return _normalize_outline_aliases(raw_outline) if isinstance(raw_outline, Mapping) else None

    normalized_payload = _normalize_outline_aliases(payload)
    outline_main = normalized_payload["main_story_overview"]
    expected_ending = normalized_payload["expected_ending"]
    core_conflict = normalized_payload["core_conflict"]
    raw_stage_plan = normalized_payload.get("stage_plan")
    if not outline_main or not expected_ending or not core_conflict or not isinstance(raw_stage_plan, Mapping):
        return None

    stage_plan = _coerce_legacy_stage_plan(raw_stage_plan)
    if stage_plan is None:
        return None
    return {
        "main_story_overview": outline_main,
        "stage_plan": stage_plan,
        "expected_ending": expected_ending,
        "core_conflict": core_conflict,
    }


def _coerce_bound_outline(
    payload: Mapping[str, Any],
    *,
    context: ContinuationContext,
) -> dict[str, Any] | None:
    bindings = load_session_output_bindings(context.session)
    if not bindings:
        return None
    _, by_variable_key = extract_bound_output_values(payload, bindings)
    raw_outline = by_variable_key.get("plot.outline")
    stage_plan = by_variable_key.get("plot.stage_plan")
    overview = by_variable_key.get("plot.main_story_overview")
    expected_ending = by_variable_key.get("plot.expected_ending")
    core_conflict = by_variable_key.get("plot.core_conflict")
    if isinstance(raw_outline, Mapping):
        outline = dict(raw_outline)
        if stage_plan is not None:
            outline["stage_plan"] = stage_plan
        if overview not in (None, ""):
            outline["main_story_overview"] = str(overview).strip()
        if expected_ending not in (None, ""):
            outline["expected_ending"] = str(expected_ending).strip()
        if core_conflict not in (None, ""):
            outline["core_conflict"] = str(core_conflict).strip()
        return _normalize_outline_aliases(outline)
    if stage_plan is None and not any(value not in (None, "") for value in (overview, expected_ending, core_conflict)):
        return None
    outline: dict[str, Any] = {}
    if overview not in (None, ""):
        outline["main_story_overview"] = str(overview).strip()
    if expected_ending not in (None, ""):
        outline["expected_ending"] = str(expected_ending).strip()
    if core_conflict not in (None, ""):
        outline["core_conflict"] = str(core_conflict).strip()
    if stage_plan is not None:
        outline["stage_plan"] = stage_plan
    return _normalize_outline_aliases(outline)


def _coerce_legacy_stage_plan(raw_stage_plan: Mapping[str, Any]) -> list[dict[str, Any]] | None:
    stage_plan: list[dict[str, Any]] = []
    for schema, legacy_keys in zip(_PHASE_SCHEMA, _LEGACY_STAGE_KEY_ALIASES):
        raw_value = None
        for key in legacy_keys:
            if raw_stage_plan.get(key) not in (None, ""):
                raw_value = raw_stage_plan.get(key)
                break
        if raw_value is None:
            return None
        if isinstance(raw_value, Mapping):
            stage_item = {
                **dict(raw_value),
                "phase": schema["phase"],
                "label": str(raw_value.get("label") or schema["label"]).strip() or schema["label"],
            }
            if not str(stage_item.get("summary") or stage_item.get("阶段任务") or stage_item.get("内容") or "").strip():
                return None
            stage_plan.append(stage_item)
            continue
        summary = str(raw_value).strip()
        if not summary:
            return None
        stage_plan.append(
            {
                "phase": schema["phase"],
                "label": schema["label"],
                "range_percent": schema["range_percent"],
                "summary": summary,
                "key_goals": [],
            }
        )
    return stage_plan


def _target_chapters(context: ContinuationContext) -> int:
    aliases = context.session.variable_plan.aliases if context.session.variable_plan is not None else {}
    setup_context = context.session.context.get("setup_context") if isinstance(context.session.context.get("setup_context"), Mapping) else {}
    raw = aliases.get("novel.target_chapters") if isinstance(aliases, Mapping) else None
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


def _coerce_chapter_number(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _canonical_phase(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return _PHASE_ALIASES.get(text, "")


def _range_percent_label(chapter_start: int, chapter_end: int, *, total_chapters: int) -> str:
    total = max(1, total_chapters)
    start_percent = max(1, min(100, int((chapter_start - 1) / total * 100)))
    end_percent = max(start_percent, min(100, int(chapter_end / total * 100)))
    return f"{start_percent}-{end_percent}%"


def _normalize_stage_plan(raw_items: Any, *, target_chapters: int) -> list[dict[str, Any]]:
    if not isinstance(raw_items, list):
        raise ValueError("plot_outline.stage_plan 必须是数组")
    if len(raw_items) != 5:
        raise ValueError("plot_outline.stage_plan 必须包含 5 个阶段")

    ranges = _chapter_ranges(target_chapters)
    total_chapters = max(
        target_chapters,
        *(
            _coerce_chapter_number(item.get("chapter_end")) or 0
            for item in raw_items
            if isinstance(item, Mapping)
        ),
    )
    normalized: list[dict[str, Any]] = []
    for index, schema in enumerate(_PHASE_SCHEMA):
        raw = raw_items[index] if index < len(raw_items) else None
        if not isinstance(raw, Mapping):
            raise ValueError(f"plot_outline.stage_plan[{index}] 必须是对象")
        summary = str(raw.get("summary") or raw.get("阶段任务") or raw.get("内容") or "").strip()
        if not summary:
            content_parts = [
                str(value).strip()
                for key, value in raw.items()
                if key not in {"phase", "label", "range_percent", "key_goals", "chapter_start", "chapter_end"}
                and str(value).strip()
            ]
            summary = "\n".join(content_parts)
        if not summary:
            raise ValueError(f"plot_outline.stage_plan[{index}] 至少需要一个内容字段")
        key_goals_raw = raw.get("key_goals")
        key_goals = []
        if isinstance(key_goals_raw, list):
            key_goals = [str(item).strip() for item in key_goals_raw if str(item).strip()]
        default_start, default_end = ranges[index]
        chapter_start = _coerce_chapter_number(raw.get("chapter_start")) or default_start
        chapter_end = _coerce_chapter_number(raw.get("chapter_end")) or default_end
        if chapter_start > chapter_end:
            raise ValueError(f"plot_outline.stage_plan[{index}] 章节范围不合法")
        extra_fields = {
            key: value
            for key, value in raw.items()
            if key not in {
                "phase",
                "label",
                "range_percent",
                "summary",
                "key_goals",
                "chapter_start",
                "chapter_end",
            }
        }
        raw_phase = str(raw.get("phase") or "").strip()
        raw_label = str(raw.get("label") or "").strip()
        source_phase = _canonical_phase(raw_phase) or _canonical_phase(raw_label)
        if source_phase and source_phase != schema["phase"]:
            extra_fields.setdefault("source_phase", raw_phase or raw_label)
        normalized.append(
            {
                **extra_fields,
                "phase": schema["phase"],
                "label": str(raw.get("label") or schema["label"]).strip() or schema["label"],
                "range_percent": _range_percent_label(
                    chapter_start,
                    chapter_end,
                    total_chapters=total_chapters,
                ),
                "chapter_start": chapter_start,
                "chapter_end": chapter_end,
                "summary": summary,
                "key_goals": key_goals,
            }
        )
    return normalized


def normalize_setup_plot_outline_payload(
    raw_outline: Mapping[str, Any],
    *,
    target_chapters: int,
) -> dict[str, Any]:
    outline = _normalize_outline_aliases(raw_outline)
    raw_stage_plan = outline.get("stage_plan")
    if isinstance(raw_stage_plan, Mapping):
        coerced_stage_plan = _coerce_legacy_stage_plan(raw_stage_plan)
        if coerced_stage_plan is not None:
            outline["stage_plan"] = coerced_stage_plan
    stage_plan = _normalize_stage_plan(outline.get("stage_plan"), target_chapters=target_chapters)
    extra_outline_fields = {
        key: value
        for key, value in outline.items()
        if key != "stage_plan" and value not in (None, "")
    }
    return {
        **extra_outline_fields,
        "stage_plan": stage_plan,
    }


def setup_plot_outline_handler(context: ContinuationContext) -> Mapping[str, Any]:
    payload = _parse_json_object(context.decision.accepted_content or "")
    bound_outline = _coerce_bound_outline(payload, context=context)
    legacy_outline = _coerce_legacy_outline(payload)
    if isinstance(bound_outline, Mapping) and isinstance(legacy_outline, Mapping):
        raw_outline = {
            **dict(legacy_outline),
            **{key: value for key, value in dict(bound_outline).items() if value not in (None, "")},
        }
    else:
        raw_outline = bound_outline or legacy_outline
    if not isinstance(raw_outline, Mapping):
        raise ValueError("缺少 plot_outline 对象")

    target_chapters = _target_chapters(context)
    normalized_outline = normalize_setup_plot_outline_payload(raw_outline, target_chapters=target_chapters)
    result: dict[str, Any] = {
        "novel_id": str(context.session.context.get("novel_id") or ""),
        "plot_outline": normalized_outline,
        "stage_plan": normalized_outline["stage_plan"],
        "session_id": context.session.id,
    }
    for key in ("main_story_overview", "expected_ending", "core_conflict"):
        if normalized_outline.get(key):
            result[key] = normalized_outline[key]
    return result


def register_setup_plot_outline_continuation() -> None:
    register_continuation_handler("setup_plot_outline", setup_plot_outline_handler)
