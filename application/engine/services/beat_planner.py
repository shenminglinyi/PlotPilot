"""Rule-based beat planning helpers.

This module holds deterministic beat-planning rules that do not need the full
``ContextBuilder`` dependency graph. ``ContextBuilder`` keeps compatibility
wrappers for now, but the planning behavior lives here.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

from application.engine.dtos.emotion_beat_card import EmotionBeatCard


def segment_user_outline(outline: str, *, max_beats: int = 12) -> List[str]:
    """Split a user outline into executable beat-sized segments."""
    text = (outline or "").strip()
    if not text:
        return []
    if re.search(r"(?m)^\s*\d+[\.、．\)]", text):
        parts = re.split(r"\n(?=\s*\d+[\.、．\)]\s)", text)
        segs = [p.strip() for p in parts if p.strip()]
        if len(segs) >= 2:
            return segs
    if re.search(r"(?m)^\s*[-*•]\s+\S", text):
        parts = re.split(r"\n(?=\s*[-*•]\s)", text)
        segs = [p.strip() for p in parts if p.strip()]
        if len(segs) >= 2:
            return segs
    paras = [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]
    if len(paras) >= 2:
        return paras
    if len(text) >= 20:
        sents = [
            s.strip()
            for s in re.split(r"(?<=[。！？；])", text)
            if len(s.strip()) > 8
        ]
        if len(sents) >= 2:
            return sents
    if len(text) >= 400:
        n = min(max_beats, max(2, (len(text) + 499) // 500))
        approx = max(1, len(text) // n)
        segs: List[str] = []
        idx = 0
        for k in range(n):
            if k == n - 1:
                chunk = text[idx:].strip()
            else:
                end = min(len(text), idx + approx)
                brk = end
                for j in range(end, min(len(text), end + 80)):
                    if text[j] in "。！？；":
                        brk = j + 1
                        break
                chunk = text[idx:brk].strip()
                idx = brk
            if chunk:
                segs.append(chunk)
        if len(segs) >= 2:
            return segs
    return [text]


def infer_focus_from_outline(outline: str) -> str:
    """Infer the generation focus for an outline fragment."""
    combined = (outline or "").lower()
    if any(kw in combined for kw in ["战斗", "打斗", "对决"]):
        return "action"
    if any(kw in combined for kw in ["争吵", "对话", "谈判"]):
        return "dialogue"
    if any(kw in combined for kw in ["发现", "真相", "悬念"]):
        return "suspense"
    if any(kw in combined for kw in ["情绪", "内心", "回忆"]):
        return "emotion"
    return "sensory"


def generate_expansion_hints(
    focus: str,
    target_words: int,
    expansion_hints: Optional[Dict[str, List[str]]] = None,
) -> List[str]:
    """Return focus-specific expansion hints sized to the target beat length."""
    base_hints = (expansion_hints or {}).get(focus, [])
    if target_words >= 1000:
        return base_hints[:4]
    if target_words >= 600:
        return base_hints[:3]
    return base_hints[:2]


def make_minimal_card(
    segment: str,
    focus: str,
    target_words: int,
    *,
    forbidden_drift: str = "",
) -> EmotionBeatCard:
    """Build a deterministic fallback ``EmotionBeatCard`` for an outline segment."""
    goal = segment[:30].rstrip("，。！？；") if segment else "推进本拍剧情"
    return EmotionBeatCard(
        goal=goal,
        obstacle="待写作过程中具体化",
        active_action=f"主角通过可见行为推进「{goal}」",
        delta="本拍结束时，情节/关系/信息差至少一项发生改变",
        emotion_gap="读者此刻期待看到局势出现转变",
        hook_delta="本拍末尾留一个让读者想翻页的疑问或画面",
        sensory_anchor="写一处与当前处境绑定的具体感官细节",
        forbidden_drift=forbidden_drift or "禁止连续两段没有动作、对话、决定之一",
        function=focus,
        target_words=target_words,
    )


__all__ = [
    "generate_expansion_hints",
    "infer_focus_from_outline",
    "make_minimal_card",
    "segment_user_outline",
]
