"""Beat contract helpers for StoryPipeline.

These helpers keep beat-card preservation out of the large pipeline class while
retaining the existing runtime shape: callers still receive beat-like objects
with ``description``, ``target_words``, ``focus`` and ``card_prompt_block``.
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, List


def serialize_beats_for_shared_state(beats: Any) -> list:
    """Serialize planned beats for shared-state snapshots."""
    out = []
    for b in beats or []:
        cards = _collect_cards(b)
        card = cards[0] if cards else None
        out.append({
            "description": getattr(b, "description", "") or "",
            "target_words": int(getattr(b, "target_words", 0) or 0),
            "focus": getattr(b, "focus", "") or "pacing",
            "location_id": getattr(b, "location_id", "") or "",
            "active_action": (getattr(card, "active_action", "") or "") if card else "",
            "emotion_gap": (getattr(card, "emotion_gap", "") or "") if card else "",
            "forbidden_drift": (getattr(card, "forbidden_drift", "") or "") if card else "",
            "beat_cards": [_card_to_dict(c) for c in cards],
        })
    return out


def merge_beats_by_target(beats: list, total_target: int) -> list:
    """Merge beats by chapter target while preserving all card prompt blocks."""
    if not beats or len(beats) <= 1:
        return beats

    if total_target <= 2200:
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
    desc = _join_descriptions(a, b)
    cpb = _join_card_blocks(a, b)
    focus = _merge_focus(a, b)
    sg_a = getattr(a, "scene_goal", "") or ""
    sg_b = getattr(b, "scene_goal", "") or ""

    cards = _collect_cards(a) + _collect_cards(b)
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
        emotion_beat_card=cards[0] if cards else None,
        emotion_beat_cards=cards,
        card_prompt_block=cpb,
    )


def _collect_cards(beat: Any) -> List[Any]:
    cards: List[Any] = []
    seen: set[int] = set()
    for card in getattr(beat, "emotion_beat_cards", None) or []:
        if card is not None and id(card) not in seen:
            cards.append(card)
            seen.add(id(card))
    card = getattr(beat, "emotion_beat_card", None)
    if card is not None and id(card) not in seen:
        cards.append(card)
    return cards


def _card_to_dict(card: Any) -> dict:
    return {
        "goal": getattr(card, "goal", "") or "",
        "obstacle": getattr(card, "obstacle", "") or "",
        "active_action": getattr(card, "active_action", "") or "",
        "delta": getattr(card, "delta", "") or "",
        "emotion_gap": getattr(card, "emotion_gap", "") or "",
        "hook_delta": getattr(card, "hook_delta", "") or "",
        "sensory_anchor": getattr(card, "sensory_anchor", "") or "",
        "forbidden_drift": getattr(card, "forbidden_drift", "") or "",
    }


def _join_descriptions(a: Any, b: Any) -> str:
    desc_a = getattr(a, "description", "") or ""
    desc_b = getattr(b, "description", "") or ""
    if desc_a and desc_b:
        return f"{desc_a}\n【随后，紧接着写】{desc_b}"
    return desc_a or desc_b


def _join_card_blocks(a: Any, b: Any) -> str:
    cpb_a = getattr(a, "card_prompt_block", "") or ""
    cpb_b = getattr(b, "card_prompt_block", "") or ""
    if cpb_a and cpb_b:
        tw_a = getattr(a, "target_words", 0) or 0
        tw_b = getattr(b, "target_words", 0) or 0
        return (
            f">>> 第一段（约{tw_a}字）\n{cpb_a}\n\n"
            f">>> 第二段（约{tw_b}字，紧接上文继续写）\n{cpb_b}"
        )
    return cpb_a or cpb_b


def _merge_focus(a: Any, b: Any) -> str:
    focus_a = getattr(a, "focus", "mixed") or "mixed"
    focus_b = getattr(b, "focus", "mixed") or "mixed"
    return focus_a if focus_a == focus_b else "mixed"
