"""PropEventHandler 实现 — 将道具事件自动写入知识图谱三元组。"""
from __future__ import annotations
import logging
import uuid
from datetime import datetime

from domain.prop.entities.prop import Prop
from domain.prop.value_objects.prop_event import PropEvent, PropEventType

logger = logging.getLogger(__name__)

# 事件类型 → 三元组谓词映射
_PREDICATE_MAP = {
    PropEventType.INTRODUCED:  "获得",
    PropEventType.USED:        "使用",
    PropEventType.TRANSFERRED: "转让",
    PropEventType.DAMAGED:     "损毁",
    PropEventType.REPAIRED:    "修复",
    PropEventType.UPGRADED:    "强化",
    PropEventType.RESOLVED:    "消亡",
}


class TriplePropEventHandler:
    """将道具事件写入 triples 表（与知识图谱联动）。"""

    def __init__(self, db):
        self._db = db

    async def handle(self, prop: Prop, event: PropEvent) -> None:
        predicate = _PREDICATE_MAP.get(event.event_type)
        if not predicate:
            return
        now = datetime.utcnow().isoformat()
        try:
            if event.event_type == PropEventType.TRANSFERRED:
                if event.from_holder_id:
                    self._write_triple(
                        event.novel_id, event.from_holder_id, "转让",
                        prop.name, event.chapter_number, now,
                    )
                if event.to_holder_id:
                    self._write_triple(
                        event.novel_id, event.to_holder_id, "获得",
                        prop.name, event.chapter_number, now,
                    )
            elif event.actor_character_id:
                self._write_triple(
                    event.novel_id, event.actor_character_id, predicate,
                    prop.name, event.chapter_number, now,
                )
            else:
                self._write_triple(
                    event.novel_id, prop.name, predicate,
                    f"第{event.chapter_number}章", event.chapter_number, now,
                    subject_type="prop",
                )
        except Exception as e:
            logger.warning("[TripleHandler] 三元组写入失败 prop=%s: %s", prop.name, e)

    def _write_triple(
        self, novel_id, subject, predicate, obj,
        chapter, now, subject_type="character",
    ):
        self._db.execute(
            """INSERT OR IGNORE INTO triples
               (id, novel_id, subject, predicate, object, subject_type,
                chapter_index, source, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                str(uuid.uuid4()), novel_id, subject, predicate, obj,
                subject_type, chapter, "prop_event", now,
            ),
        )
        self._db.get_connection().commit()
