"""SQLite Chapter Review Repository：章节审阅（审定）记录�?""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from application.audit.dtos.chapter_review_dto import ChapterReviewDTO
from infrastructure.persistence.database.connection import DatabaseConnection

logger = logging.getLogger(__name__)


class SqliteChapterReviewRepository:
    """chapter_reviews 表读写�?""

    def __init__(self, db: DatabaseConnection):
        self.db = db

    def get(self, novel_id: str, chapter_number: int) -> Optional[ChapterReviewDTO]:
        row = self.db.fetch_one(
            "SELECT status, memo, created_at, updated_at FROM chapter_reviews WHERE novel_id = ? AND chapter_number = ?",
            (novel_id, int(chapter_number)),
        )
        if not row:
            return None
        # sqlite3.Row behaves like dict in this codebase
        created_at = row.get("created_at")
        updated_at = row.get("updated_at")
        try:
            ca = datetime.fromisoformat(created_at) if isinstance(created_at, str) else datetime.now(timezone.utc)
        except Exception:
            ca = datetime.now(timezone.utc)
        try:
            ua = datetime.fromisoformat(updated_at) if isinstance(updated_at, str) else ca
        except Exception:
            ua = ca
        return ChapterReviewDTO(
            status=row.get("status", "draft"),
            memo=row.get("memo", "") or "",
            created_at=ca,
            updated_at=ua,
        )

    def upsert(self, novel_id: str, chapter_number: int, *, status: str, memo: str) -> ChapterReviewDTO:
        now = datetime.now(timezone.utc).isoformat()
        self.db.execute(
            """
            INSERT INTO chapter_reviews (novel_id, chapter_number, status, memo, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(novel_id, chapter_number) DO UPDATE SET
                status = excluded.status,
                memo = excluded.memo,
                updated_at = excluded.updated_at
            """,
            (novel_id, int(chapter_number), status, memo or "", now, now),
        )
        self.db.get_connection().commit()
        return self.get(novel_id, chapter_number) or ChapterReviewDTO(
            status=status,
            memo=memo or "",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

