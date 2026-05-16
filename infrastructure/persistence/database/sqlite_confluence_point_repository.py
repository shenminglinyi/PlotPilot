from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import List, Optional

from domain.novel.entities.confluence_point import ConfluencePoint
from domain.novel.repositories.confluence_point_repository import ConfluencePointRepository
from infrastructure.persistence.database.connection import DatabaseConnection

logger = logging.getLogger(__name__)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS confluence_points (
    id TEXT PRIMARY KEY,
    novel_id TEXT NOT NULL,
    source_storyline_id TEXT NOT NULL,
    target_storyline_id TEXT NOT NULL,
    target_chapter INTEGER NOT NULL,
    merge_type TEXT NOT NULL,
    context_summary TEXT DEFAULT '',
    pre_reveal_hint TEXT DEFAULT '',
    behavior_guards TEXT DEFAULT '[]',
    resolved INTEGER DEFAULT 0,
    created_at TEXT,
    updated_at TEXT
)
"""


class SqliteConfluencePointRepository(ConfluencePointRepository):

    def __init__(self, db: DatabaseConnection):
        self.db = db
        self._ensure_table()

    def _conn(self):
        return self.db.get_connection()

    def _ensure_table(self):
        conn = self._conn()
        conn.execute(_CREATE_TABLE_SQL)
        conn.commit()

    def _now(self) -> str:
        return datetime.utcnow().isoformat()

    def save(self, cp: ConfluencePoint) -> None:
        now = self._now()
        conn = self._conn()
        try:
            conn.execute(
                """
                INSERT INTO confluence_points (
                    id, novel_id, source_storyline_id, target_storyline_id,
                    target_chapter, merge_type, context_summary,
                    pre_reveal_hint, behavior_guards, resolved,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    source_storyline_id = excluded.source_storyline_id,
                    target_storyline_id = excluded.target_storyline_id,
                    target_chapter = excluded.target_chapter,
                    merge_type = excluded.merge_type,
                    context_summary = excluded.context_summary,
                    pre_reveal_hint = excluded.pre_reveal_hint,
                    behavior_guards = excluded.behavior_guards,
                    resolved = excluded.resolved,
                    updated_at = excluded.updated_at
                """,
                (
                    cp.id,
                    cp.novel_id,
                    cp.source_storyline_id,
                    cp.target_storyline_id,
                    cp.target_chapter,
                    cp.merge_type,
                    cp.context_summary,
                    cp.pre_reveal_hint,
                    json.dumps(cp.behavior_guards, ensure_ascii=False),
                    1 if cp.resolved else 0,
                    now,
                    now,
                ),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def get_by_id(self, cp_id: str) -> Optional[ConfluencePoint]:
        row = self.db.fetch_one(
            "SELECT * FROM confluence_points WHERE id = ?", (cp_id,)
        )
        return self._row_to_entity(row) if row else None

    def get_by_novel_id(self, novel_id: str) -> List[ConfluencePoint]:
        rows = self.db.fetch_all(
            "SELECT * FROM confluence_points WHERE novel_id = ? ORDER BY target_chapter",
            (novel_id,),
        )
        return [self._row_to_entity(r) for r in rows]

    def get_by_source_storyline(self, storyline_id: str) -> List[ConfluencePoint]:
        rows = self.db.fetch_all(
            "SELECT * FROM confluence_points WHERE source_storyline_id = ? ORDER BY target_chapter",
            (storyline_id,),
        )
        return [self._row_to_entity(r) for r in rows]

    def delete(self, cp_id: str) -> None:
        conn = self._conn()
        try:
            conn.execute("DELETE FROM confluence_points WHERE id = ?", (cp_id,))
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def _row_to_entity(self, row: dict) -> ConfluencePoint:
        guards = []
        try:
            guards = json.loads(row.get("behavior_guards") or "[]")
        except (json.JSONDecodeError, TypeError):
            pass
        return ConfluencePoint(
            id=row["id"],
            novel_id=row["novel_id"],
            source_storyline_id=row["source_storyline_id"],
            target_storyline_id=row["target_storyline_id"],
            target_chapter=row["target_chapter"],
            merge_type=row["merge_type"],
            context_summary=row.get("context_summary", ""),
            pre_reveal_hint=row.get("pre_reveal_hint", ""),
            behavior_guards=guards,
            resolved=bool(row.get("resolved", 0)),
        )
