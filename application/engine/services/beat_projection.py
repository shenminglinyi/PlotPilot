"""Chapter beat projection helpers.

This module is the single projection boundary from planning artifacts to the
runtime beat shape used by generation, shared state, and chapter summaries.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from application.engine.dag.plan.schema import ChapterExecutionPlan
from application.engine.services.beat_models import Beat
from engine.pipeline.beat_contracts import serialize_beats_for_shared_state

logger = logging.getLogger(__name__)

OUTLINE_OBLIGATION_PREFIX = (
    "【章纲节选·须落实】以下要点必须写入正文（可合理扩写，不得跳过核心因果；"
    "人物姓名须与 Bible 一致）：\n"
)

FocusInferer = Callable[[str], str]
ExpansionHintBuilder = Callable[[str, int], List[str]]


def _string_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _string(value: Any) -> str:
    return str(value).strip() if value not in (None, [], {}) else ""


def _default_function(intent: str, focus: str) -> str:
    text = intent or ""
    if any(k in text for k in ("突袭", "逼", "压制", "杀机", "遭遇")):
        return "pressure"
    if any(k in text for k in ("爆发", "震碎", "击败", "破局", "反制")):
        return "payoff"
    if any(k in text for k in ("发现", "徽记", "真相", "计划", "芯片")):
        return "reveal"
    if any(k in text for k in ("逃离", "离开", "转移", "赶往")):
        return "transition"
    return focus or "setup"


def _summarize_intent(intent: str, max_len: int = 48) -> str:
    """Short intent snippet for default contract fields (avoid repeating full paragraph)."""
    text = (intent or "").strip()
    if not text:
        return ""
    for sep in ("。", "！", "？", "；", ";", "\n"):
        idx = text.find(sep)
        if idx >= 8:
            text = text[: idx + 1]
            break
    text = text.strip()
    if len(text) > max_len:
        text = text[:max_len].rstrip("，。；; ") + "…"
    return text


def _default_visible_action(intent: str) -> str:
    summary = _summarize_intent(intent)
    if not summary:
        return "用可见动作、对白或选择落实本拍意图"
    return f"用可见动作、对白或选择落实：{summary}"


def _default_delta(intent: str) -> str:
    summary = _summarize_intent(intent)
    if not summary:
        return "本拍结束时，读者必须看到局势发生明确变化"
    return f"本拍结束时，局势须因「{summary}」出现可感变化"


def beat_sheet_to_plan_json(beat_sheet: Optional[Any]) -> Optional[Dict[str, Any]]:
    """Project a repository BeatSheet into the canonical plan input JSON."""
    if not beat_sheet:
        return None
    scenes_raw = getattr(beat_sheet, "scenes", None)
    if not scenes_raw:
        return None

    scenes: List[Dict[str, Any]] = []
    for scene in scenes_raw:
        scenes.append(
            {
                "title": getattr(scene, "title", "") or "",
                "goal": getattr(scene, "goal", "") or "",
                "estimated_words": getattr(scene, "estimated_words", None) or 600,
                "pov_character": getattr(scene, "pov_character", "") or "",
                "location": getattr(scene, "location", None),
                "tone": getattr(scene, "tone", None),
                "transition_from_prev": getattr(scene, "transition_from_prev", None),
            }
        )
    return {"scenes": scenes}


def beats_from_execution_plan(
    plan: ChapterExecutionPlan,
    *,
    outline: str,
    target_chapter_words: int,
    infer_focus: FocusInferer,
    build_expansion_hints: ExpansionHintBuilder,
) -> List[Beat]:
    """Project ``ChapterExecutionPlan.atoms`` into runtime Beats."""
    atoms = plan.atoms
    if not atoms:
        return []

    total_weight = sum(max(0.01, float(atom.weight)) for atom in atoms)
    mode = (plan.provenance or {}).get("mode", "")
    logger.info(
        "节拍投影（ChapterExecutionPlan）：%d 拍，provenance_mode=%s outline≈%d 字，整章目标 %d 字",
        len(atoms),
        mode,
        len((outline or "").strip()),
        target_chapter_words,
    )

    beats: List[Beat] = []
    for atom in atoms:
        intent = (atom.intent or "").strip()
        if not intent:
            continue

        share = max(0.01, float(atom.weight)) / total_weight
        target_words = max(1, int(target_chapter_words * share))
        ext = atom.extensions if isinstance(atom.extensions, dict) else {}

        raw_focus = ext.get("focus") or ext.get("type")
        focus = raw_focus.strip() if isinstance(raw_focus, str) and raw_focus.strip() else infer_focus(intent)
        function = _string(ext.get("function")) or _default_function(intent, focus)

        transition_raw = ext.get("transition_from_prev")
        transition = str(transition_raw).strip() if transition_raw else ""

        location_raw = ext.get("location_id")
        location_id = (
            str(location_raw).strip()
            if isinstance(location_raw, str) and location_raw.strip()
            else ""
        )
        location_refs = _string_list(ext.get("location_refs"))
        if not location_id and location_refs:
            location_id = location_refs[0]

        beats.append(
            Beat(
                description=intent,
                target_words=target_words,
                focus=focus,
                expansion_hints=build_expansion_hints(focus, target_words),
                scene_goal=intent,
                transition_from_prev=transition,
                location_id=location_id,
                function=function,
                pov=_string(ext.get("pov")),
                cast_refs=_string_list(ext.get("cast_refs")),
                location_refs=location_refs,
                prop_refs=_string_list(ext.get("prop_refs")),
                knowledge_refs=_string_list(ext.get("knowledge_refs")),
                visible_action=_string(ext.get("visible_action") or ext.get("active_action")) or _default_visible_action(intent),
                conflict=_string(ext.get("conflict")),
                delta=_string(ext.get("delta") or ext.get("required_delta")) or _default_delta(intent),
                handoff_to_next=_string(ext.get("handoff_to_next")),
                must_include=_string_list(ext.get("must_include")),
                must_not_include=_string_list(ext.get("must_not_include")),
            )
        )
    return beats


def planned_micro_beats_from_beats(beats: List[Any]) -> List[Dict[str, Any]]:
    """Serialize runtime Beats for /status, SSE, and chapter summary snapshots."""
    return serialize_beats_for_shared_state(beats)


__all__ = [
    "OUTLINE_OBLIGATION_PREFIX",
    "beat_sheet_to_plan_json",
    "beats_from_execution_plan",
    "planned_micro_beats_from_beats",
]
