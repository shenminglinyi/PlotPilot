"""双螺旋编年史：按 chapter_index 拉链聚合剧情时间线与语义快照（BFF 聚合，底层表物理隔离）。"""
from __future__ import annotations

import re
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_CHAPTER_IN_TEXT = re.compile(r"第\s*(\d+)\s*章")
_CANDIDATE_ACCEPT_IN_NAME = re.compile(r"^\[候选稿采纳\]\s*第\s*\d+\s*章\s*[·•]\s*(.+?)\s*$")


def infer_chapter_from_texts(*parts: str) -> Optional[int]:
    for p in parts:
        if not p:
            continue
        m = _CHAPTER_IN_TEXT.search(p)
        if m:
            return int(m.group(1))
    return None


def anchor_chapter_from_pointers(
    pointer_ids: List[str],
    id_to_number: Dict[str, int],
) -> Optional[int]:
    nums = [id_to_number[i] for i in pointer_ids if i in id_to_number]
    return max(nums) if nums else None


def infer_snapshot_origin(name: str) -> Dict[str, Optional[str]]:
    raw_name = (name or "").strip()
    match = _CANDIDATE_ACCEPT_IN_NAME.match(raw_name)
    if match:
        return {
            "origin_type": "candidate_accept",
            "candidate_source": match.group(1).strip() or None,
        }
    return {
        "origin_type": "snapshot",
        "candidate_source": None,
    }


def build_chronicles_rows(
    timeline_notes: List[Tuple[str, str, str, str]],
    snapshots: List[Dict[str, Any]],
    id_to_number: Dict[str, int],
) -> List[Dict[str, Any]]:
    """
    timeline_notes: list of (id, time_point, event, description)
    snapshots: rows with id, name, trigger_type, branch_name, created_at, description, chapter_pointers (list)
    """
    max_num = max(id_to_number.values(), default=1)
    snap_fallback = max_num if max_num >= 1 else 1

    buckets: Dict[int, Dict[str, List]] = {}

    def ensure(ch: int) -> Dict[str, List]:
        if ch not in buckets:
            buckets[ch] = {"story_events": [], "snapshots": []}
        return buckets[ch]

    for idx, (nid, tp, ev, desc) in enumerate(timeline_notes):
        inferred = infer_chapter_from_texts(tp or "", ev or "", desc or "")
        ch = inferred if inferred is not None else idx + 1
        ch = max(1, ch)
        ensure(ch)["story_events"].append(
            {
                "note_id": nid,
                "time": (tp or "").strip() or "（未标注时间）",
                "title": (ev or "").strip(),
                "description": (desc or "").strip(),
                "source_chapter": inferred,
            }
        )

    for snap in snapshots:
        ptrs = snap.get("chapter_pointers") or []
        if not isinstance(ptrs, list):
            ptrs = []
        anchor = anchor_chapter_from_pointers([str(x) for x in ptrs], id_to_number)
        ch = anchor if anchor is not None else snap_fallback
        ch = max(1, ch)
        ensure(ch)["snapshots"].append(
            {
                "id": snap.get("id"),
                "kind": snap.get("trigger_type") or "AUTO",
                "name": snap.get("name") or "",
                "branch_name": snap.get("branch_name") or "main",
                "created_at": snap.get("created_at"),
                "description": (snap.get("description") or "").strip() or None,
                "anchor_chapter": anchor,
                **infer_snapshot_origin(snap.get("name") or ""),
            }
        )

    if not buckets:
        return []

    out: List[Dict[str, Any]] = []
    for ch in sorted(buckets.keys()):
        b = buckets[ch]
        out.append(
            {
                "chapter_index": ch,
                "story_events": b["story_events"],
                "snapshots": b["snapshots"],
            }
        )

    return out
