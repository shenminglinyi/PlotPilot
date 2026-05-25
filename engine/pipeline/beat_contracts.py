"""Beat contract helpers for StoryPipeline.

These helpers keep beat-card preservation out of the large pipeline class while
retaining the existing runtime shape: callers still receive beat-like objects
with ``description``, ``target_words``, ``focus`` and ``card_prompt_block``.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, List


_OBLIGATION_PREFIX_HEAD = "【章纲节选·须落实】"


def _string_list(obj: Any, key: str) -> List[str]:
    value = _field(obj, key, None)
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _clean_description(text: str) -> str:
    raw = str(text or "").strip()
    while _OBLIGATION_PREFIX_HEAD in raw:
        start = raw.find(_OBLIGATION_PREFIX_HEAD)
        nl = raw.find("\n", start)
        if nl < 0:
            raw = raw[:start].strip()
            break
        raw = (raw[:start] + raw[nl + 1:]).strip()
    return raw


def serialize_beats_for_shared_state(beats: Any) -> list:
    """Serialize planned beats for shared-state snapshots."""
    out = []
    for b in beats or []:
        cards = _collect_cards(b)
        card = cards[0] if cards else None
        out.append({
            "description": _field(b, "description", "") or "",
            "target_words": int(_field(b, "target_words", 0) or 0),
            "focus": _field(b, "focus", "") or "pacing",
            "location_id": _field(b, "location_id", "") or "",
            "function": _field(b, "function", "") or "",
            "pov": _field(b, "pov", "") or "",
            "cast_refs": _string_list(b, "cast_refs"),
            "location_refs": _string_list(b, "location_refs"),
            "prop_refs": _string_list(b, "prop_refs"),
            "knowledge_refs": _string_list(b, "knowledge_refs"),
            "entity_manifest": _field(b, "entity_manifest", None) or {},
            "visible_action": _field(b, "visible_action", "") or "",
            "conflict": _field(b, "conflict", "") or "",
            "delta": _field(b, "delta", "") or "",
            "handoff_to_next": _field(b, "handoff_to_next", "") or "",
            "must_include": _string_list(b, "must_include"),
            "must_not_include": _string_list(b, "must_not_include"),
            "active_action": (_field(card, "active_action", "") or "") if card else "",
            "emotion_gap": (_field(card, "emotion_gap", "") or "") if card else "",
            "forbidden_drift": (_field(card, "forbidden_drift", "") or "") if card else "",
            "beat_cards": [_card_to_dict(c) for c in cards],
        })
    return out


def merge_beats_by_target(beats: list, total_target: int) -> list:
    """Merge beats by chapter target while preserving all card prompt blocks."""
    if not beats or len(beats) <= 1:
        return beats

    if total_target <= 2200:
        # Short chapters stay as a single LLM call so the overall word budget is
        # easier to control. The merged beat still exposes ordered sub-beats in
        # the prompt instead of flattening them into one overloaded action.
        merged = beats[0]
        for b in beats[1:]:
            merged = merge_two_beats(merged, b)
        return [merged]

    if total_target <= 3200:
        mid = max(1, len(beats) // 2)
        first = beats[0]
        for b in beats[1:mid]:
            first = merge_two_beats(first, b)
        second = beats[mid]
        for b in beats[mid + 1:]:
            second = merge_two_beats(second, b)
        return [first, second]

    min_beat = 350
    result = list(beats)
    changed = True
    while changed:
        changed = False
        new_result = []
        i = 0
        while i < len(result):
            tw = getattr(result[i], "target_words", 0) or 0
            if tw < min_beat and i + 1 < len(result):
                new_result.append(merge_two_beats(result[i], result[i + 1]))
                i += 2
                changed = True
            else:
                new_result.append(result[i])
                i += 1
        result = new_result
    return result


def merge_two_beats(a: Any, b: Any) -> Any:
    """Merge two beat-like objects without dropping either prompt card."""
    subbeat_descriptions = _collect_descriptions(a) + _collect_descriptions(b)
    subbeat_card_blocks = _collect_card_blocks(a) + _collect_card_blocks(b)
    desc = _join_descriptions(subbeat_descriptions)
    cpb = _join_card_blocks(subbeat_card_blocks)
    focus = _merge_focus(a, b)
    sg_a = getattr(a, "scene_goal", "") or ""
    sg_b = getattr(b, "scene_goal", "") or ""

    cards = _collect_cards(a) + _collect_cards(b)
    entity_manifest = _merge_entity_manifest(a, b)
    expansion_hints = list(dict.fromkeys(
        list(getattr(a, "expansion_hints", None) or [])
        + list(getattr(b, "expansion_hints", None) or [])
    ))[:4]

    return SimpleNamespace(
        description=desc,
        target_words=(getattr(a, "target_words", 0) or 0) + (getattr(b, "target_words", 0) or 0),
        focus=focus,
        expansion_hints=expansion_hints,
        scene_goal=f"{sg_a} {sg_b}".strip(),
        transition_from_prev=getattr(a, "transition_from_prev", "") or "",
        location_id=getattr(a, "location_id", "") or getattr(b, "location_id", "") or "",
        function=getattr(a, "function", "") or getattr(b, "function", "") or "",
        pov=getattr(a, "pov", "") or getattr(b, "pov", "") or "",
        cast_refs=list(dict.fromkeys(_string_list(a, "cast_refs") + _string_list(b, "cast_refs"))),
        location_refs=list(dict.fromkeys(_string_list(a, "location_refs") + _string_list(b, "location_refs"))),
        prop_refs=list(dict.fromkeys(_string_list(a, "prop_refs") + _string_list(b, "prop_refs"))),
        knowledge_refs=list(dict.fromkeys(_string_list(a, "knowledge_refs") + _string_list(b, "knowledge_refs"))),
        entity_manifest=entity_manifest,
        visible_action="；".join(x for x in [getattr(a, "visible_action", ""), getattr(b, "visible_action", "")] if x),
        conflict="；".join(x for x in [getattr(a, "conflict", ""), getattr(b, "conflict", "")] if x),
        delta="；".join(x for x in [getattr(a, "delta", ""), getattr(b, "delta", "")] if x),
        handoff_to_next=getattr(b, "handoff_to_next", "") or getattr(a, "handoff_to_next", "") or "",
        must_include=list(dict.fromkeys(_string_list(a, "must_include") + _string_list(b, "must_include"))),
        must_not_include=list(dict.fromkeys(_string_list(a, "must_not_include") + _string_list(b, "must_not_include"))),
        emotion_beat_card=cards[0] if cards else None,
        emotion_beat_cards=cards,
        subbeat_descriptions=subbeat_descriptions,
        subbeat_card_blocks=subbeat_card_blocks,
        card_prompt_block=cpb,
    )


def _collect_cards(beat: Any) -> List[Any]:
    cards: List[Any] = []
    seen: set[int] = set()
    for card in _field(beat, "emotion_beat_cards", None) or _field(beat, "beat_cards", None) or []:
        if card is not None and id(card) not in seen:
            cards.append(card)
            seen.add(id(card))
    card = _field(beat, "emotion_beat_card", None)
    if card is not None and id(card) not in seen:
        cards.append(card)
    return cards


def _card_to_dict(card: Any) -> dict:
    return {
        "goal": _field(card, "goal", "") or "",
        "obstacle": _field(card, "obstacle", "") or "",
        "active_action": _field(card, "active_action", "") or "",
        "delta": _field(card, "delta", "") or "",
        "emotion_gap": _field(card, "emotion_gap", "") or "",
        "hook_delta": _field(card, "hook_delta", "") or "",
        "sensory_anchor": _field(card, "sensory_anchor", "") or "",
        "forbidden_drift": _field(card, "forbidden_drift", "") or "",
    }


def _field(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _collect_descriptions(beat: Any) -> List[str]:
    descriptions = getattr(beat, "subbeat_descriptions", None)
    if isinstance(descriptions, list) and descriptions:
        return [str(x).strip() for x in descriptions if str(x).strip()]
    desc = _clean_description(getattr(beat, "description", "") or "")
    return [desc] if desc else []


def _collect_card_blocks(beat: Any) -> List[dict]:
    blocks = getattr(beat, "subbeat_card_blocks", None)
    if isinstance(blocks, list) and blocks:
        return [
            {
                "target_words": int((item or {}).get("target_words", 0) or 0),
                "block": str((item or {}).get("block", "") or "").strip(),
            }
            for item in blocks
            if str((item or {}).get("block", "") or "").strip()
        ]
    block = str(getattr(beat, "card_prompt_block", "") or "").strip()
    if not block:
        return []
    return [{
        "target_words": int(getattr(beat, "target_words", 0) or 0),
        "block": block,
    }]


def _join_descriptions(descriptions: List[str]) -> str:
    if not descriptions:
        return ""
    if len(descriptions) == 1:
        return descriptions[0]
    lines = ["本次一次性写完整章正文，覆盖以下连续节拍："]
    lines.extend(f"{idx}. {desc}" for idx, desc in enumerate(descriptions, 1))
    lines.append("以上节拍必须按顺序自然衔接，不要写成提纲或分标题。")
    return "\n".join(lines)


def _join_card_blocks(card_blocks: List[dict]) -> str:
    if not card_blocks:
        return ""
    if len(card_blocks) == 1:
        return card_blocks[0]["block"]

    parts = []
    for idx, item in enumerate(card_blocks, 1):
        target_words = item.get("target_words") or 0
        word_hint = f"（约{target_words}字）" if target_words else ""
        parts.append(f"━━━ 子节拍 {idx}{word_hint}\n{item['block']}")
    return "\n\n".join(parts)


def _merge_focus(a: Any, b: Any) -> str:
    focus_a = getattr(a, "focus", "mixed") or "mixed"
    focus_b = getattr(b, "focus", "mixed") or "mixed"
    return focus_a if focus_a == focus_b else "mixed"


def _merge_entity_manifest(a: Any, b: Any) -> dict:
    manifests = [
        _field(a, "entity_manifest", None) or {},
        _field(b, "entity_manifest", None) or {},
    ]
    refs = []
    seen: set[tuple[str, str]] = set()
    novel_id = ""
    chapter_number = 0
    for manifest in manifests:
        if not isinstance(manifest, dict):
            continue
        novel_id = novel_id or str(manifest.get("novel_id") or "")
        chapter_number = chapter_number or int(manifest.get("chapter_number") or 0)
        for ref in manifest.get("refs") or []:
            if not isinstance(ref, dict):
                continue
            key = (str(ref.get("kind") or ""), str(ref.get("id") or ""))
            if not key[0] or not key[1] or key in seen:
                continue
            seen.add(key)
            refs.append(ref)
    if not refs:
        return {}
    return {"novel_id": novel_id, "chapter_number": chapter_number, "refs": refs}
