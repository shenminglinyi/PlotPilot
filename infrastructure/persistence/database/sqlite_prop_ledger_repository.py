"""SQLite repository for NovelPro prop ledger."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from infrastructure.persistence.database.connection import DatabaseConnection


class SqlitePropLedgerRepository:
    """关键道具账本。"""

    def __init__(self, db: DatabaseConnection):
        self.db = db

    def get_item_by_name(self, novel_id: str, name: str) -> Optional[dict[str, Any]]:
        return self.db.fetch_one(
            """
            SELECT * FROM prop_ledger_items
            WHERE novel_id = ? AND name = ?
            """,
            (novel_id, name),
        )

    def list_items(self, novel_id: str) -> list[dict[str, Any]]:
        return self.db.fetch_all(
            """
            SELECT * FROM prop_ledger_items
            WHERE novel_id = ?
            ORDER BY
                CASE importance
                    WHEN 'major' THEN 0
                    WHEN 'normal' THEN 1
                    ELSE 2
                END,
                COALESCE(last_seen_chapter, first_seen_chapter, 0) DESC,
                updated_at DESC
            """,
            (novel_id,),
        )

    def list_events(self, novel_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        return self.db.fetch_all(
            """
            SELECT * FROM prop_ledger_events
            WHERE novel_id = ?
            ORDER BY chapter_number DESC, created_at DESC
            LIMIT ?
            """,
            (novel_id, int(limit)),
        )

    def upsert_item(
        self,
        *,
        novel_id: str,
        name: str,
        category: str,
        status: str,
        current_holder: str,
        current_location: str,
        first_seen_chapter: Optional[int],
        last_seen_chapter: Optional[int],
        importance: str,
        description: str,
        notes: str,
    ) -> dict[str, Any]:
        existing = self.get_item_by_name(novel_id, name)
        now = datetime.utcnow().isoformat()
        if existing:
            self.db.execute(
                """
                UPDATE prop_ledger_items
                SET category = ?, status = ?, current_holder = ?, current_location = ?,
                    first_seen_chapter = ?, last_seen_chapter = ?, importance = ?,
                    description = ?, notes = ?, updated_at = ?
                WHERE novel_id = ? AND name = ?
                """,
                (
                    category,
                    status,
                    current_holder,
                    current_location,
                    first_seen_chapter,
                    last_seen_chapter,
                    importance,
                    description,
                    notes,
                    now,
                    novel_id,
                    name,
                ),
            )
        else:
            self.db.execute(
                """
                INSERT INTO prop_ledger_items (
                    id, novel_id, name, category, status, current_holder,
                    current_location, first_seen_chapter, last_seen_chapter,
                    importance, description, notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    novel_id,
                    name,
                    category,
                    status,
                    current_holder,
                    current_location,
                    first_seen_chapter,
                    last_seen_chapter,
                    importance,
                    description,
                    notes,
                    now,
                    now,
                ),
            )
        self.db.commit()
        return self.get_item_by_name(novel_id, name) or {}

    def create_event(
        self,
        *,
        novel_id: str,
        prop_id: str,
        prop_name: str,
        chapter_number: int,
        event_type: str,
        holder: str,
        location: str,
        status: str,
        evidence: str,
        notes: str,
    ) -> dict[str, Any]:
        event_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        self.db.execute(
            """
            INSERT INTO prop_ledger_events (
                id, novel_id, prop_id, prop_name, chapter_number, event_type,
                holder, location, status, evidence, notes, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                novel_id,
                prop_id,
                prop_name,
                int(chapter_number),
                event_type,
                holder,
                location,
                status,
                evidence,
                notes,
                now,
            ),
        )
        self.db.execute(
            """
            UPDATE prop_ledger_items
            SET current_holder = COALESCE(NULLIF(?, ''), current_holder),
                current_location = COALESCE(NULLIF(?, ''), current_location),
                status = COALESCE(NULLIF(?, ''), status),
                last_seen_chapter = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (holder, location, status, int(chapter_number), now, prop_id),
        )
        self.db.commit()
        return self.db.fetch_one(
            "SELECT * FROM prop_ledger_events WHERE id = ?",
            (event_id,),
        ) or {}
