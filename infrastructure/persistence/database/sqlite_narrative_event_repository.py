"""SQLite Narrative Event Repository 实现"""
import json
import logging
from typing import Optional
from uuid import uuid4
from domain.novel.repositories.narrative_event_repository import NarrativeEventRepository
from infrastructure.persistence.database.connection import DatabaseConnection

logger = logging.getLogger(__name__)


class SqliteNarrativeEventRepository(NarrativeEventRepository):
    """SQLite Narrative Event Repository 实现"""

    def __init__(self, db: DatabaseConnection):
        self.db = db

    def list_up_to_chapter(self, novel_id: str, max_chapter_inclusive: int) -> list[dict]:
        """获取指定章节及之前的所有事件

        Args:
            novel_id: 小说 ID
            max_chapter_inclusive: 最大章节号（包含）

        Returns:
            事件列表，按 chapter_number ASC 排序
        """
        sql = """
            SELECT event_id, novel_id, chapter_number, event_summary, mutations, tags, timestamp_ts
            FROM narrative_events
            WHERE novel_id = ? AND chapter_number <= ?
            ORDER BY chapter_number ASC
        """
        rows = self.db.fetch_all(sql, (novel_id, max_chapter_inclusive))

        # 反序列化 mutations 和 tags JSON
        events = []
        for row in rows:
            event = dict(row)
            event["mutations"] = json.loads(event["mutations"])
            event["tags"] = json.loads(event["tags"])
            events.append(event)

        return events

    def append_event(
        self,
        novel_id: str,
        chapter_number: int,
        event_summary: str,
        mutations: list[dict],
        tags: list[str] = None
    ) -> str:
        """追加新事件

        Args:
            novel_id: 小说 ID
            chapter_number: 章节号
            event_summary: 事件摘要
            mutations: 变更列表
            tags: 事件标签列表（可选，默认空列表）

        Returns:
            新创建的 event_id
        """
        event_id = str(uuid4())
        mutations_json = json.dumps(mutations, ensure_ascii=False)
        tags_json = json.dumps(tags if tags is not None else [], ensure_ascii=False)

        sql = """
            INSERT INTO narrative_events (event_id, novel_id, chapter_number, event_summary, mutations, tags)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        self.db.execute(sql, (event_id, novel_id, chapter_number, event_summary, mutations_json, tags_json))
        self.db.get_connection().commit()

        logger.info(f"Appended event {event_id} for novel {novel_id} chapter {chapter_number}")
        return event_id

    def upsert_event(
        self,
        event_id: str,
        novel_id: str,
        chapter_number: int,
        event_summary: str,
        mutations: list[dict],
        tags: list[str] = None,
    ) -> str:
        """Insert or update an event by a caller-provided idempotency key."""
        mutations_json = json.dumps(mutations, ensure_ascii=False)
        tags_json = json.dumps(tags if tags is not None else [], ensure_ascii=False)

        sql = """
            INSERT INTO narrative_events (event_id, novel_id, chapter_number, event_summary, mutations, tags)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_id) DO UPDATE SET
                novel_id = excluded.novel_id,
                chapter_number = excluded.chapter_number,
                event_summary = excluded.event_summary,
                mutations = excluded.mutations,
                tags = excluded.tags
        """
        self.db.execute(sql, (event_id, novel_id, chapter_number, event_summary, mutations_json, tags_json))
        self.db.get_connection().commit()

        logger.info(f"Upserted event {event_id} for novel {novel_id} chapter {chapter_number}")
        return event_id

    def get_event(self, novel_id: str, event_id: str) -> Optional[dict]:
        """获取单个事件

        Args:
            novel_id: 小说 ID
            event_id: 事件 ID

        Returns:
            事件字典，如果不存在返回 None
        """
        sql = """
            SELECT event_id, novel_id, chapter_number, event_summary, mutations, tags, timestamp_ts
            FROM narrative_events
            WHERE novel_id = ? AND event_id = ?
        """
        row = self.db.fetch_one(sql, (novel_id, event_id))

        if not row:
            return None

        event = dict(row)
        event["mutations"] = json.loads(event["mutations"])
        event["tags"] = json.loads(event["tags"])
        return event

    def update_event(
        self,
        novel_id: str,
        event_id: str,
        event_summary: str,
        tags: list[str]
    ) -> None:
        """更新事件

        Args:
            novel_id: 小说 ID
            event_id: 事件 ID
            event_summary: 新的事件摘要
            tags: 新的标签列表
        """
        tags_json = json.dumps(tags, ensure_ascii=False)

        sql = """
            UPDATE narrative_events
            SET event_summary = ?, tags = ?
            WHERE novel_id = ? AND event_id = ?
        """
        self.db.execute(sql, (event_summary, tags_json, novel_id, event_id))
        self.db.get_connection().commit()

        logger.info(f"Updated event {event_id} for novel {novel_id}")
