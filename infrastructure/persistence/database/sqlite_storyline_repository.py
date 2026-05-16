"""SQLite 故事线仓储。"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import List, Optional

from domain.novel.entities.storyline import Storyline
from domain.novel.repositories.storyline_repository import StorylineRepository
from domain.novel.value_objects.novel_id import NovelId
from domain.novel.value_objects.storyline_milestone import StorylineMilestone
from domain.novel.value_objects.storyline_status import StorylineStatus
from domain.novel.value_objects.storyline_type import StorylineType
from infrastructure.persistence.database.connection import DatabaseConnection

logger = logging.getLogger(__name__)


def _encode_str_list(items: List[str]) -> str:
    return json.dumps(list(items or []), ensure_ascii=False)


def _decode_str_list(text: str) -> List[str]:
    if not text or not text.strip():
        return []
    try:
        data = json.loads(text)
        return list(data) if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


class SqliteStorylineRepository(StorylineRepository):
    def __init__(self, db: DatabaseConnection):
        self.db = db

    def _conn(self):
        return self.db.get_connection()

    def _now(self) -> str:
        return datetime.utcnow().isoformat()

    def save(self, storyline: Storyline) -> None:
        now = self._now()
        conn = self._conn()
        try:
            # Check if we need to add new columns
            cursor = conn.execute("PRAGMA table_info(storylines)")
            columns = {row[1] for row in cursor.fetchall()}

            if 'name' not in columns:
                conn.execute("ALTER TABLE storylines ADD COLUMN name TEXT DEFAULT ''")
            if 'description' not in columns:
                conn.execute("ALTER TABLE storylines ADD COLUMN description TEXT DEFAULT ''")
            if 'last_active_chapter' not in columns:
                conn.execute("ALTER TABLE storylines ADD COLUMN last_active_chapter INTEGER DEFAULT 0")
            if 'progress_summary' not in columns:
                conn.execute("ALTER TABLE storylines ADD COLUMN progress_summary TEXT DEFAULT ''")
            if 'role' not in columns:
                conn.execute("ALTER TABLE storylines ADD COLUMN role TEXT DEFAULT 'main'")
            if 'parent_id' not in columns:
                conn.execute("ALTER TABLE storylines ADD COLUMN parent_id TEXT")
            if 'chapter_weight' not in columns:
                conn.execute("ALTER TABLE storylines ADD COLUMN chapter_weight REAL DEFAULT 1.0")

            conn.execute(
                """
                INSERT INTO storylines (
                    id, novel_id, storyline_type, status,
                    estimated_chapter_start, estimated_chapter_end,
                    current_milestone_index, name, description,
                    last_active_chapter, progress_summary,
                    role, parent_id, chapter_weight,
                    extensions, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '{}', ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    novel_id = excluded.novel_id,
                    storyline_type = excluded.storyline_type,
                    status = excluded.status,
                    estimated_chapter_start = excluded.estimated_chapter_start,
                    estimated_chapter_end = excluded.estimated_chapter_end,
                    current_milestone_index = excluded.current_milestone_index,
                    name = excluded.name,
                    description = excluded.description,
                    last_active_chapter = excluded.last_active_chapter,
                    progress_summary = excluded.progress_summary,
                    role = excluded.role,
                    parent_id = excluded.parent_id,
                    chapter_weight = excluded.chapter_weight,
                    updated_at = excluded.updated_at
                """,
                (
                    storyline.id,
                    storyline.novel_id.value,
                    storyline.storyline_type.value,
                    storyline.status.value,
                    storyline.estimated_chapter_start,
                    storyline.estimated_chapter_end,
                    storyline.current_milestone_index,
                    storyline.name,
                    storyline.description,
                    storyline.last_active_chapter,
                    storyline.progress_summary,
                    storyline.role.value,
                    storyline.parent_id,
                    storyline.chapter_weight,
                    now,
                    now,
                ),
            )
            conn.execute(
                "DELETE FROM storyline_milestones WHERE storyline_id = ?",
                (storyline.id,),
            )
            for m in storyline.milestones:
                mid = f"{storyline.id}-m-{m.order}"
                conn.execute(
                    """
                    INSERT INTO storyline_milestones (
                        id, storyline_id, milestone_order, title, description,
                        target_chapter_start, target_chapter_end,
                        prerequisite_list, milestone_triggers
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        mid,
                        storyline.id,
                        m.order,
                        m.title,
                        m.description,
                        m.target_chapter_start,
                        m.target_chapter_end,
                        _encode_str_list(m.prerequisites),
                        _encode_str_list(m.triggers),
                    ),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def get_by_id(self, storyline_id: str) -> Optional[Storyline]:
        row = self.db.fetch_one(
            "SELECT * FROM storylines WHERE id = ?", (storyline_id,)
        )
        if not row:
            return None
        return self._row_to_storyline(row)

    def get_by_novel_id(self, novel_id: NovelId) -> List[Storyline]:
        rows = self.db.fetch_all(
            "SELECT * FROM storylines WHERE novel_id = ? ORDER BY id",
            (novel_id.value,),
        )
        return [self._row_to_storyline(r) for r in rows]

    def _milestones(self, storyline_id: str) -> List[StorylineMilestone]:
        rows = self.db.fetch_all(
            """
            SELECT * FROM storyline_milestones
            WHERE storyline_id = ?
            ORDER BY milestone_order
            """,
            (storyline_id,),
        )
        out: List[StorylineMilestone] = []
        for r in rows:
            out.append(
                StorylineMilestone(
                    order=r["milestone_order"],
                    title=r["title"] or "",
                    description=r["description"] or "",
                    target_chapter_start=r["target_chapter_start"],
                    target_chapter_end=r["target_chapter_end"],
                    prerequisites=_decode_str_list(r["prerequisite_list"] or ""),
                    triggers=_decode_str_list(r["milestone_triggers"] or ""),
                )
            )
        return out

    def _row_to_storyline(self, row: dict) -> Storyline:
        from domain.novel.value_objects.storyline_role import StorylineRole
        sid = row["id"]
        milestones = self._milestones(sid)
        raw_role = row.get("role") or "main"
        try:
            role = StorylineRole(raw_role)
        except ValueError:
            role = StorylineRole.MAIN if raw_role in ("main_plot", "main") else StorylineRole.SUB
        return Storyline(
            id=sid,
            novel_id=NovelId(row["novel_id"]),
            storyline_type=StorylineType(row["storyline_type"]),
            status=StorylineStatus(row["status"]),
            estimated_chapter_start=row["estimated_chapter_start"],
            estimated_chapter_end=row["estimated_chapter_end"],
            milestones=milestones,
            current_milestone_index=row["current_milestone_index"],
            name=row.get("name", ""),
            description=row.get("description", ""),
            last_active_chapter=row.get("last_active_chapter", 0),
            progress_summary=row.get("progress_summary", ""),
            role=role,
            parent_id=row.get("parent_id"),
            chapter_weight=float(row.get("chapter_weight") or 1.0),
        )

    def delete(self, storyline_id: str) -> None:
        conn = self._conn()
        try:
            conn.execute("DELETE FROM storyline_milestones WHERE storyline_id = ?", (storyline_id,))
            conn.execute("DELETE FROM storylines WHERE id = ?", (storyline_id,))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
