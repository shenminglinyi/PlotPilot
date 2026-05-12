from __future__ import annotations
import json
from typing import List, Optional

from domain.shared.time_utils import utcnow_iso

from domain.prop.entities.prop import Prop
from domain.prop.repositories.prop_repository import PropRepository
from domain.prop.value_objects.lifecycle_state import LifecycleState
from domain.prop.value_objects.prop_category import PropCategory
from domain.prop.value_objects.prop_id import PropId

_COLS = (
    "id, novel_id, name, description, aliases_json, prop_category, "
    "lifecycle_state, introduced_chapter, resolved_chapter, "
    "holder_character_id, attributes_json, created_at, updated_at"
)


def _row_to_prop(row) -> Prop:
    d = dict(row)
    return Prop(
        id=PropId(d["id"]),
        novel_id=d["novel_id"],
        name=d["name"],
        description=d.get("description", ""),
        aliases=json.loads(d.get("aliases_json") or "[]"),
        category=PropCategory(d.get("prop_category", "OTHER")),
        lifecycle_state=LifecycleState(d.get("lifecycle_state", "DORMANT")),
        introduced_chapter=d.get("introduced_chapter"),
        resolved_chapter=d.get("resolved_chapter"),
        holder_character_id=d.get("holder_character_id"),
        attributes=json.loads(d.get("attributes_json") or "{}"),
        created_at=d.get("created_at", ""),
        updated_at=d.get("updated_at", ""),
    )


class SqliteUnifiedPropRepository(PropRepository):
    def __init__(self, db):
        self._db = db

    def get(self, prop_id: PropId) -> Optional[Prop]:
        row = self._db.fetch_one(
            f"SELECT {_COLS} FROM unified_props WHERE id = ?", (prop_id.value,)
        )
        return _row_to_prop(row) if row else None

    def list_by_novel(self, novel_id: str) -> List[Prop]:
        rows = self._db.fetch_all(
            f"SELECT {_COLS} FROM unified_props WHERE novel_id = ? ORDER BY created_at ASC",
            (novel_id,),
        )
        return [_row_to_prop(r) for r in rows]

    def list_active(self, novel_id: str, chapter: int) -> List[Prop]:
        rows = self._db.fetch_all(
            f"""SELECT {_COLS} FROM unified_props
                WHERE novel_id = ?
                  AND lifecycle_state NOT IN ('DORMANT','RESOLVED')
                  AND (introduced_chapter IS NULL OR introduced_chapter <= ?)
                  AND (resolved_chapter IS NULL OR resolved_chapter > ?)
                ORDER BY name""",
            (novel_id, chapter, chapter),
        )
        return [_row_to_prop(r) for r in rows]

    def save(self, prop: Prop) -> None:
        now = utcnow_iso()
        self._db.execute(
            """INSERT INTO unified_props (
                id, novel_id, name, description, aliases_json, prop_category,
                lifecycle_state, introduced_chapter, resolved_chapter,
                holder_character_id, attributes_json, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name, description=excluded.description,
                aliases_json=excluded.aliases_json,
                prop_category=excluded.prop_category,
                lifecycle_state=excluded.lifecycle_state,
                introduced_chapter=excluded.introduced_chapter,
                resolved_chapter=excluded.resolved_chapter,
                holder_character_id=excluded.holder_character_id,
                attributes_json=excluded.attributes_json,
                updated_at=excluded.updated_at""",
            (
                prop.id.value, prop.novel_id, prop.name, prop.description,
                json.dumps(prop.aliases, ensure_ascii=False),
                prop.category.value, prop.lifecycle_state.value,
                prop.introduced_chapter, prop.resolved_chapter,
                prop.holder_character_id,
                json.dumps(prop.attributes, ensure_ascii=False),
                prop.created_at, now,
            ),
        )
        self._db.get_connection().commit()

    def delete(self, prop_id: PropId) -> None:
        self._db.execute("DELETE FROM unified_props WHERE id = ?", (prop_id.value,))
        self._db.get_connection().commit()
