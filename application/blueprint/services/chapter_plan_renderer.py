"""Rendering helpers for chapter execution plans."""
from __future__ import annotations

from typing import Any, Callable, List


def stringify_plan_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return "、".join(
            text for item in value if (text := stringify_plan_value(item))
        )
    if isinstance(value, dict):
        for key in ("content", "summary", "description", "text", "purpose", "decision", "change"):
            text = stringify_plan_value(value.get(key))
            if text:
                return text
        return "；".join(
            f"{key}：{text}"
            for key, raw in value.items()
            if (text := stringify_plan_value(raw))
        )
    return str(value).strip()


def format_scene_transition(item: Any, index: int) -> str:
    if not isinstance(item, dict):
        return stringify_plan_value(item)
    scene = stringify_plan_value(item.get("scene") or item.get("name")) or f"场景{index}"
    location = stringify_plan_value(item.get("location") or item.get("place")) or "未定地点"
    cast = stringify_plan_value(item.get("cast") or item.get("characters") or item.get("roles")) or "未定人物"
    purpose = stringify_plan_value(
        item.get("purpose") or item.get("event") or item.get("summary") or item.get("description")
    )
    return f"{scene} → {location} | {cast} | {purpose}".strip()


def format_dialogue(item: Any, index: int) -> str:
    if not isinstance(item, dict):
        text = stringify_plan_value(item)
        return f"对话{index}：{text}" if text and not text.startswith("对话") else text
    speaker = stringify_plan_value(item.get("speaker") or item.get("from") or item.get("role"))
    line = stringify_plan_value(item.get("line") or item.get("says") or item.get("content"))
    reply = stringify_plan_value(item.get("reply") or item.get("response") or item.get("to"))
    purpose = stringify_plan_value(item.get("purpose") or item.get("effect") or item.get("result"))
    parts = []
    if speaker or line:
        parts.append(f"{speaker}→{line}".strip("→"))
    if reply:
        parts.append(reply)
    if purpose:
        parts.append(purpose)
    return f"对话{index}：" + " | ".join(parts)


def format_event(item: Any, index: int) -> str:
    if not isinstance(item, dict):
        text = stringify_plan_value(item)
        return f"事件{index}：{text}" if text and not text.startswith("事件") else text
    phase = stringify_plan_value(item.get("phase") or item.get("type") or item.get("stage"))
    content = stringify_plan_value(
        item.get("content") or item.get("event") or item.get("summary") or item.get("description")
    )
    label = f"事件{index}"
    if phase:
        label += f"（{phase}）"
    return f"{label}：{content}"


def format_decision(item: Any) -> str:
    if not isinstance(item, dict):
        return stringify_plan_value(item)
    actor = stringify_plan_value(item.get("actor") or item.get("character") or item.get("role"))
    decision = stringify_plan_value(item.get("decision") or item.get("action") or item.get("content"))
    purpose = stringify_plan_value(item.get("purpose") or item.get("result") or item.get("effect"))
    text = f"{actor}→{decision}".strip("→")
    if purpose:
        text += f"→{purpose}"
    return text


def render_list_section(items: Any, formatter: Callable[[Any, int], str]) -> List[str]:
    if not isinstance(items, list):
        text = stringify_plan_value(items)
        return [text] if text else []
    out: List[str] = []
    for index, item in enumerate(items, start=1):
        text = formatter(item, index)
        if text:
            out.append(text)
    return out


def render_chapter_execution_plan(chapter_plan: Any) -> str:
    if isinstance(chapter_plan, str):
        return chapter_plan.strip()
    if not isinstance(chapter_plan, dict):
        return ""

    opening = stringify_plan_value(
        chapter_plan.get("opening_entry")
        or chapter_plan.get("opening")
        or chapter_plan.get("entry_point")
        or chapter_plan.get("cut_in")
    )
    scenes = render_list_section(
        chapter_plan.get("scene_transitions") or chapter_plan.get("scenes"),
        format_scene_transition,
    )
    dialogues = render_list_section(
        chapter_plan.get("key_dialogues") or chapter_plan.get("dialogues"),
        format_dialogue,
    )
    events = render_list_section(
        chapter_plan.get("event_chain") or chapter_plan.get("events"),
        format_event,
    )
    decisions = render_list_section(
        chapter_plan.get("character_decisions") or chapter_plan.get("decisions"),
        lambda item, _index: format_decision(item),
    )
    payoffs = render_list_section(
        chapter_plan.get("payoff_reversals") or chapter_plan.get("payoffs") or chapter_plan.get("reversals"),
        lambda item, _index: stringify_plan_value(item),
    )
    state = chapter_plan.get("protagonist_state_change") or chapter_plan.get("state_change")
    if isinstance(state, dict):
        state_lines = [
            f"{key}：{text}"
            for key, raw in state.items()
            if (text := stringify_plan_value(raw))
        ]
    else:
        state_text = stringify_plan_value(state)
        state_lines = [state_text] if state_text else []

    sections = [
        ("一、开篇切入点：", [opening] if opening else []),
        ("二、场景转换列表：", scenes),
        (f"三、关键对话（{len(dialogues)}组）：", dialogues),
        (f"四、剧情事件链（{len(events)}个事件）：", events),
        ("五、角色关键决策：", decisions),
        ("六、爽点/反转设计：", payoffs),
        ("七、主角状态变化：", state_lines),
    ]
    rendered: list[str] = []
    for title, lines in sections:
        rendered.append(title)
        rendered.extend(lines or ["（待补充）"])
    return "\n".join(rendered).strip()


def render_lightweight_act_chapter_outline(row: dict[str, Any]) -> str:
    """Render the slim act-chain row as a readable placeholder before preplanning."""
    try:
        number = int(row.get("number") or 0)
    except (TypeError, ValueError):
        number = 0
    handoff_label = "开篇入口" if number == 1 else "承接上一章"
    lines = [
        f"主事件：{stringify_plan_value(row.get('main_event'))}",
        f"{handoff_label}：{stringify_plan_value(row.get('handoff_from_previous'))}",
        f"交给下一章：{stringify_plan_value(row.get('handoff_to_next'))}",
    ]
    threads = stringify_plan_value(row.get("required_threads"))
    if threads:
        lines.append(f"需推进线索：{threads}")
    location = stringify_plan_value(row.get("location_hint"))
    if location:
        lines.append(f"地点提示：{location}")
    cast = stringify_plan_value(row.get("cast_hint") or row.get("characters"))
    if cast:
        lines.append(f"出场提示：{cast}")
    thrill = stringify_plan_value(row.get("thrill_type") or row.get("thrill_description"))
    if thrill:
        lines.append(f"回报类型：{thrill}")
    foreshadow = stringify_plan_value(row.get("foreshadow_detail") or row.get("foreshadow_action"))
    if foreshadow:
        lines.append(f"伏笔操作：{foreshadow}")
    return "\n".join(line for line in lines if not line.endswith("：")).strip()
