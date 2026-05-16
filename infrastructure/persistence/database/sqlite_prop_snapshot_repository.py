from __future__ import annotations
import json
from typing import Any, Dict, Optional

from domain.shared.time_utils import utcnow_iso

from domain.prop.repositories.prop_snapshot_repository import PropSnapshotRepository


class SqlitePropSnapshotRepository(PropSnapshotRepository):
    def __init__(self, db):
        self._db = db

    def save_snapshot(
        self,
        prop_id: str,
        chapter_number: int,
        holder_character_id: Optional[str],
        lifecycle_state: str,
        attributes_snapshot: Dict[str, Any],
    ) -> None:
        now = utcnow_iso()
        self._db.execute(
            """INSERT INTO prop_chapter_snapshots
               (prop_id, chapter_number, holder_character_id, lifecycle_state,
                attributes_snapshot_json, captured_at)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(prop_id, chapter_number) DO UPDATE SET
                   holder_character_id=excluded.holder_character_id,
                   lifecycle_state=excluded.lifecycle_state,
                   attributes_snapshot_json=excluded.attributes_snapshot_json,
                   captured_at=excluded.captured_at""",
            (
                prop_id, chapter_number, holder_character_id, lifecycle_state,
                json.dumps(attributes_snapshot, ensure_ascii=False), now,
            ),
        )
        self._db.get_connection().commit()

    def get_snapshot(self, prop_id: str, chapter_number: int) -> Optional[Dict[str, Any]]:
        row = self._db.fetch_one(
            "SELECT * FROM prop_chapter_snapshots WHERE prop_id = ? AND chapter_number = ?",
            (prop_id, chapter_number),
        )
        if not row:
            return None
        d = dict(row)
        return {
            "prop_id": d["prop_id"],
            "chapter_number": d["chapter_number"],
            "holder_character_id": d.get("holder_character_id"),
            "lifecycle_state": d["lifecycle_state"],
            "attributes_snapshot": json.loads(d.get("attributes_snapshot_json") or "{}"),
            "captured_at": d.get("captured_at", ""),
        }
