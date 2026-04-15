"""Bible 地点 parent_id 森林校验（无环、无悬空父）。"""
from __future__ import annotations

from typing import Any, Dict, List, Set


def validate_location_forest(locations: List[Dict[str, Any]]) -> None:
    """校验 id 唯一、parent_id 存在或为 None、无环。失败抛出 ValueError。"""
    ids: Set[str] = set()
    for loc in locations:
        lid = str(loc.get("id") or "").strip()
        if not lid:
            raise ValueError("location id empty")
        if lid in ids:
            raise ValueError(f"duplicate location id: {lid}")
        ids.add(lid)

    for loc in locations:
        pid = loc.get("parent_id")
        if pid is None or pid == "":
            continue
        p = str(pid).strip()
        if not p:
            continue
        if p not in ids:
            raise ValueError(f"orphan parent_id references missing id: {p}")

    id_to_parent: Dict[str, Optional[str]] = {}
    for loc in locations:
        lid = str(loc["id"]).strip()
        raw = loc.get("parent_id")
        if raw is None or raw == "":
            id_to_parent[lid] = None
        else:
            p = str(raw).strip()
            id_to_parent[lid] = p if p else None

    for start in ids:
        seen_path: Set[str] = set()
        cur: Optional[str] = start
        steps = 0
        while cur is not None:
            if cur in seen_path:
                raise ValueError("location parent_id cycle detected")
            seen_path.add(cur)
            cur = id_to_parent.get(cur)
            steps += 1
            if steps > len(ids) + 1:
                raise ValueError("location parent_id cycle detected")
