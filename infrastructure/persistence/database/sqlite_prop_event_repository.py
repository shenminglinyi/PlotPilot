from __future__ import annotations
import json
from datetime import datetime
from typing import List

from domain.prop.repositories.prop_event_repository import PropEventRepository
from domain.prop.value_objects.prop_event import PropEvent, PropEventType, PropEventSource


class SqlitePropEventRepository(PropEventRepository):
    def __init__(self, db):
        self._db = db

    def save(self, event: PropEvent) -> None:
        self._db.execute(
            """INSERT OR IGNORE INTO prop_events
               (id, novel_id, prop_id, chapter_number, event_type,
                actor_character_id, from_holder_id, to_holder_id,
                description, source, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                event.id, event.novel_id, event.prop_id, event.chapter_number,
                event.event_type.value,
                event.actor_character_id, event.from_holder_id, event.to_holder_id,
                event.description, event.source.value, event.created_at,
            ),
        )
        self._db.get_connection().commit()

    def list_for_prop(self, prop_id: str) -> List[PropEvent]:
        rows = self._db.fetch_all(
            "SELECT * FROM prop_events WHERE prop_id = ? ORDER BY chapter_number, created_at",
            (prop_id,),
        )
        return [self._row_to_event(r) for r in rows]

    def list_for_chapter(self, novel_id: str, chapter: int) -> List[PropEvent]:
        rows = self._db.fetch_all(
            "SELECT * FROM prop_events WHERE novel_id = ? AND chapter_number = ? ORDER BY created_at",
            (novel_id, chapter),
        )
        return [self._row_to_event(r) for r in rows]

    @staticmethod
    def _row_to_event(row) -> PropEvent:
        d = dict(row)
        return PropEvent(
            id=d["id"],
            prop_id=d["prop_id"],
            novel_id=d["novel_id"],
            chapter_number=d["chapter_number"],
            event_type=PropEventType(d["event_type"]),
            source=PropEventSource(d.get("source", "MANUAL")),
            description=d.get("description", ""),
            actor_character_id=d.get("actor_character_id"),
            from_holder_id=d.get("from_holder_id"),
            to_holder_id=d.get("to_holder_id"),
            created_at=d.get("created_at", ""),
        )
