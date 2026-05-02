"""SQLite repository for CoC clue ledger."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from infrastructure.persistence.database.connection import DatabaseConnection


class SqliteCocClueRepository:
    """CoC 线索账本仓储。"""

    def __init__(self, db: DatabaseConnection):
        self.db = db

    def get_item_by_id(self, item_id: str) -> Optional[dict[str, Any]]:
        return self.db.fetch_one(
            "SELECT * FROM coc_clue_items WHERE id = ?",
            (item_id,),
        )

    def get_item_by_key(self, novel_id: str, clue_key: str) -> Optional[dict[str, Any]]:
        return self.db.fetch_one(
            """
            SELECT * FROM coc_clue_items
            WHERE novel_id = ? AND clue_key = ?
            """,
            (novel_id, clue_key),
        )

    def list_items(self, novel_id: str) -> list[dict[str, Any]]:
        return self.db.fetch_all(
            """
            SELECT * FROM coc_clue_items
            WHERE novel_id = ?
            ORDER BY
                CASE status
                    WHEN 'active' THEN 0
                    WHEN 'resolved' THEN 1
                    ELSE 2
                END,
                CASE visibility
                    WHEN 'reader_known' THEN 0
                    WHEN 'protagonist_known' THEN 1
                    ELSE 2
                END,
                updated_at DESC
            """,
            (novel_id,),
        )

    def list_events(self, novel_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        return self.db.fetch_all(
            """
            SELECT
                e.id,
                e.clue_id,
                i.novel_id,
                i.clue_key,
                e.chapter_number,
                e.event_type,
                e.evidence,
                e.notes,
                e.created_at
            FROM coc_clue_events e
            JOIN coc_clue_items i ON i.id = e.clue_id
            WHERE i.novel_id = ?
            ORDER BY e.chapter_number DESC, e.created_at DESC
            LIMIT ?
            """,
            (novel_id, int(limit)),
        )

    def upsert_item(
        self,
        *,
        item_id: Optional[str],
        novel_id: str,
        clue_key: str,
        clue_text: str,
        visibility: str,
        reveal_chapter: Optional[int],
        known_by: str,
        confidence: float,
        lock_level: str,
        status: str,
        notes: str,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        existing = self.get_item_by_id(item_id) if item_id else self.get_item_by_key(novel_id, clue_key)
        if existing:
            self.db.execute(
                """
                UPDATE coc_clue_items
                SET clue_key = ?, clue_text = ?, visibility = ?, reveal_chapter = ?, known_by = ?,
                    confidence = ?, lock_level = ?, status = ?, notes = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    clue_key,
                    clue_text,
                    visibility,
                    reveal_chapter,
                    known_by,
                    float(confidence),
                    lock_level,
                    status,
                    notes,
                    now,
                    existing["id"],
                ),
            )
            saved_id = existing["id"]
        else:
            saved_id = str(uuid.uuid4())
            self.db.execute(
                """
                INSERT INTO coc_clue_items (
                    id, novel_id, clue_key, clue_text, visibility, reveal_chapter, known_by,
                    confidence, lock_level, status, notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    saved_id,
                    novel_id,
                    clue_key,
                    clue_text,
                    visibility,
                    reveal_chapter,
                    known_by,
                    float(confidence),
                    lock_level,
                    status,
                    notes,
                    now,
                    now,
                ),
            )
        self.db.commit()
        return self.get_item_by_id(saved_id) or {}

    def create_event(
        self,
        *,
        clue_id: str,
        chapter_number: int,
        event_type: str,
        evidence: str,
        notes: str,
    ) -> dict[str, Any]:
        event_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        self.db.execute(
            """
            INSERT INTO coc_clue_events (
                id, clue_id, chapter_number, event_type, evidence, notes, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                clue_id,
                int(chapter_number),
                event_type,
                evidence,
                notes,
                now,
            ),
        )
        self.db.execute(
            "UPDATE coc_clue_items SET updated_at = ? WHERE id = ?",
            (now, clue_id),
        )
        self.db.commit()
        return self.db.fetch_one(
            """
            SELECT
                e.id,
                e.clue_id,
                i.novel_id,
                i.clue_key,
                e.chapter_number,
                e.event_type,
                e.evidence,
                e.notes,
                e.created_at
            FROM coc_clue_events e
            JOIN coc_clue_items i ON i.id = e.clue_id
            WHERE e.id = ?
            """,
            (event_id,),
        ) or {}
