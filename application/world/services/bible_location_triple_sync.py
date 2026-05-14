"""Bible locations[] parent_id → triples（位于）幂等同步。"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List

from domain.bible.bible_location_tree import validate_location_forest
from domain.bible.triple import SourceType, Triple
from infrastructure.persistence.database.triple_repository import (
    BIBLE_ANCHOR_PREDICATE,
    TripleRepository,
)

logger = logging.getLogger(__name__)


def _map_location_kind(raw_type: str) -> str:
    t = str(raw_type or "")
    tl = t.lower()
    if "城" in t or "city" in tl:
        return "city"
    if any(k in t for k in ("区域", "域", "境", "荒", "谷", "原", "山脉")):
        return "region"
    if "region" in tl or "natural" in tl or "other" == tl.strip():
        return "region"
    if any(k in t for k in ("建筑", "楼", "殿", "阁", "府", "宫", "塔")):
        return "building"
    if "building" in tl:
        return "building"
    if any(k in t for k in ("势力", "宗", "门", "派", "盟", "族")):
        return "faction"
    if any(k in t for k in ("特殊", "秘境", "领域", "遗迹", "墟")):
        return "realm"
    if "realm" in tl:
        return "realm"
    return "region"


def stable_containment_triple_id(novel_id: str, bible_location_id: str) -> str:
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"plotpilot/{novel_id}/bible_location/{bible_location_id}/位于",
        )
    )


def stable_anchor_triple_id(novel_id: str, bible_location_id: str) -> str:
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"plotpilot/{novel_id}/bible_location/{bible_location_id}/地图地点",
        )
    )


class BibleLocationTripleSyncService:
    """将 Bible 地点树投影为 bible_generated + 位于 三元组。"""

    def __init__(self, triple_repository: TripleRepository) -> None:
        self._repo = triple_repository

    def sync_from_locations(self, novel_id: str, locations: List[Dict[str, Any]]) -> None:
        validate_location_forest(locations)
        normalized: List[Dict[str, Any]] = []
        for raw in locations:
            lid = str(raw.get("id") or "").strip()
            name = str(raw.get("name") or "").strip()
            p = raw.get("parent_id")
            parent_id = str(p).strip() if isinstance(p, str) and str(p).strip() else None
            loc_type = str(raw.get("type") or raw.get("location_type") or "").strip()
            normalized.append(
                {"id": lid, "name": name, "parent_id": parent_id, "type": loc_type}
            )

        current_ids = {loc["id"] for loc in normalized}
        id_to_row = {row["id"]: row for row in normalized}
        inserted = updated = deleted = 0

        for row in self._repo.list_bible_generated_containment_with_location_ids(novel_id):
            bid = str(row.get("bible_location_id") or "")
            tid = row.get("id")
            if bid and bid not in current_ids and tid:
                if self._repo.delete_triple_sync(str(tid)):
                    deleted += 1

        for row in self._repo.list_bible_generated_anchor_with_location_ids(novel_id):
            bid = str(row.get("bible_location_id") or "")
            tid = row.get("id")
            if bid and bid not in current_ids and tid:
                if self._repo.delete_triple_sync(str(tid)):
                    deleted += 1

        for loc in normalized:
            lid = loc["id"]
            meta = self._repo.get_containment_meta_by_bible_location_id(novel_id, lid)
            if not loc["parent_id"]:
                if meta and meta.get("source_type") == "bible_generated":
                    if self._repo.delete_triple_sync(str(meta["id"])):
                        deleted += 1
                continue

            if meta and meta.get("source_type") != "bible_generated":
                continue

            parent_id = loc["parent_id"]
            triple_id = stable_containment_triple_id(novel_id, lid)
            existed = meta is not None and meta.get("source_type") == "bible_generated"
            parent_row = id_to_row.get(parent_id, {})
            parent_name = str(parent_row.get("name") or "").strip() or parent_id
            subj_lt = _map_location_kind(loc.get("type", ""))
            obj_lt = _map_location_kind(parent_row.get("type", ""))
            triple = Triple(
                id=triple_id,
                novel_id=novel_id,
                subject_type="location",
                subject_id=lid,
                predicate="位于",
                object_type="location",
                object_id=parent_id,
                confidence=1.0,
                source_type=SourceType.BIBLE_GENERATED,
                description=loc["name"] or None,
                attributes={
                    "bible_location_id": lid,
                    "subject_label": loc["name"] or lid,
                    "object_label": parent_name,
                    "subject_importance": "normal",
                    "subject_location_type": subj_lt,
                    "object_importance": "normal",
                    "object_location_type": obj_lt,
                },
            )
            self._repo.persist_triple_sync(novel_id, triple)
            if existed:
                updated += 1
            else:
                inserted += 1

        anchor_inserted = 0
        for loc in normalized:
            lid = loc["id"]
            if not lid:
                continue
            display = (loc["name"] or lid).strip() or lid
            lt = _map_location_kind(loc.get("type", ""))
            anchor = Triple(
                id=stable_anchor_triple_id(novel_id, lid),
                novel_id=novel_id,
                subject_type="location",
                subject_id=lid,
                predicate=BIBLE_ANCHOR_PREDICATE,
                object_type="location",
                object_id=lid,
                confidence=1.0,
                source_type=SourceType.BIBLE_GENERATED,
                description=display,
                attributes={
                    "bible_location_id": lid,
                    "subject_label": display,
                    "object_label": display,
                    "subject_importance": "normal",
                    "subject_location_type": lt,
                    "object_importance": "normal",
                    "object_location_type": lt,
                },
            )
            self._repo.persist_triple_sync(novel_id, anchor)
            anchor_inserted += 1

        logger.info(
            "bible location triple sync novel=%s inserted=%s updated=%s deleted=%s anchors=%s",
            novel_id,
            inserted,
            updated,
            deleted,
            anchor_inserted,
        )
