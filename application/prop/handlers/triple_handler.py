"""Prop event handler that mirrors prop lifecycle events into triples."""
from __future__ import annotations

import logging
import uuid

from domain.prop.entities.prop import Prop
from domain.prop.value_objects.prop_event import PropEvent, PropEventType
from domain.shared.time_utils import utcnow_iso

logger = logging.getLogger(__name__)

_PREDICATE_MAP = {
    PropEventType.INTRODUCED: "获得",
    PropEventType.USED: "使用",
    PropEventType.TRANSFERRED: "转让",
    PropEventType.DAMAGED: "损毁",
    PropEventType.REPAIRED: "修复",
    PropEventType.UPGRADED: "强化",
    PropEventType.RESOLVED: "消亡",
}


class TriplePropEventHandler:
    """Write prop events into the triples table with canonical entity ids."""

    def __init__(self, db):
        self._db = db

    async def handle(self, prop: Prop, event: PropEvent) -> None:
        predicate = _PREDICATE_MAP.get(event.event_type)
        if not predicate:
            return
        now = utcnow_iso()
        try:
            if event.event_type == PropEventType.TRANSFERRED:
                if event.from_holder_id:
                    self._write_triple(
                        event.novel_id,
                        event.from_holder_id,
                        "转让",
                        prop.id.value,
                        event.chapter_number,
                        now,
                        subject_type="character",
                        subject_entity_id=event.from_holder_id,
                        object_entity_id=prop.id.value,
                        description=f"{event.from_holder_id} 转让 {prop.name}",
                    )
                if event.to_holder_id:
                    self._write_triple(
                        event.novel_id,
                        event.to_holder_id,
                        "获得",
                        prop.id.value,
                        event.chapter_number,
                        now,
                        subject_type="character",
                        subject_entity_id=event.to_holder_id,
                        object_entity_id=prop.id.value,
                        description=f"{event.to_holder_id} 获得 {prop.name}",
                    )
            elif event.actor_character_id:
                self._write_triple(
                    event.novel_id,
                    event.actor_character_id,
                    predicate,
                    prop.id.value,
                    event.chapter_number,
                    now,
                    subject_type="character",
                    subject_entity_id=event.actor_character_id,
                    object_entity_id=prop.id.value,
                    description=event.description or f"{event.actor_character_id} {predicate} {prop.name}",
                )
            else:
                self._write_triple(
                    event.novel_id,
                    prop.id.value,
                    predicate,
                    f"第{event.chapter_number}章",
                    event.chapter_number,
                    now,
                    subject_type="prop",
                    object_type="chapter",
                    subject_entity_id=prop.id.value,
                    object_entity_id=None,
                    description=event.description or f"{prop.name} {predicate}",
                )
        except Exception as e:
            logger.warning("[TripleHandler] triple write failed prop=%s: %s", prop.name, e)

    def _write_triple(
        self,
        novel_id: str,
        subject: str,
        predicate: str,
        obj: str,
        chapter: int,
        now: str,
        *,
        subject_type: str = "character",
        object_type: str = "prop",
        subject_entity_id: str | None = None,
        object_entity_id: str | None = None,
        description: str = "",
    ) -> None:
        existing = self._db.fetch_one(
            """
            SELECT id FROM triples
            WHERE novel_id = ?
              AND predicate = ?
              AND chapter_number = ?
              AND source_type = 'prop_event'
              AND COALESCE(subject_entity_id, subject) = ?
              AND COALESCE(object_entity_id, object) = ?
            LIMIT 1
            """,
            (
                novel_id,
                predicate,
                chapter,
                subject_entity_id or subject,
                object_entity_id or obj,
            ),
        )
        if existing:
            return

        self._db.execute(
            """
            INSERT OR IGNORE INTO triples (
                id, novel_id, subject, predicate, object, chapter_number,
                entity_type, description, source_type, subject_entity_id,
                object_entity_id, confidence, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                novel_id,
                subject,
                predicate,
                obj,
                chapter,
                subject_type,
                description,
                "prop_event",
                subject_entity_id or subject,
                object_entity_id if object_type != "chapter" else None,
                0.85,
                now,
            ),
        )
        self._db.get_connection().commit()
