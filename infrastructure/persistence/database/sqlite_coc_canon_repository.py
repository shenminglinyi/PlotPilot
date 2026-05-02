"""SQLite repository for CoC canon registry."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from infrastructure.persistence.database.connection import DatabaseConnection


class SqliteCocCanonRepository:
    """CoC 正典注册表仓储。"""

    def __init__(self, db: DatabaseConnection):
        self.db = db

    def get_entry_by_id(self, entry_id: str) -> Optional[dict[str, Any]]:
        return self.db.fetch_one(
            "SELECT * FROM coc_canon_entries WHERE id = ?",
            (entry_id,),
        )

    def get_entry_by_key(self, novel_id: str, canon_type: str, title: str) -> Optional[dict[str, Any]]:
        return self.db.fetch_one(
            """
            SELECT * FROM coc_canon_entries
            WHERE novel_id = ? AND canon_type = ? AND title = ?
            """,
            (novel_id, canon_type, title),
        )

    def get_entry_by_title(self, novel_id: str, title: str) -> Optional[dict[str, Any]]:
        return self.db.fetch_one(
            """
            SELECT * FROM coc_canon_entries
            WHERE novel_id = ? AND title = ?
            ORDER BY
                CASE lock_level
                    WHEN 'absolute' THEN 0
                    WHEN 'strict' THEN 1
                    ELSE 2
                END,
                updated_at DESC
            LIMIT 1
            """,
            (novel_id, title),
        )

    def list_entries(self, novel_id: str) -> list[dict[str, Any]]:
        return self.db.fetch_all(
            """
            SELECT * FROM coc_canon_entries
            WHERE novel_id = ?
            ORDER BY
                CASE lock_level
                    WHEN 'absolute' THEN 0
                    WHEN 'strict' THEN 1
                    ELSE 2
                END,
                canon_type ASC,
                title ASC
            """,
            (novel_id,),
        )

    def list_events(self, novel_id: str, *, limit: int = 100) -> list[dict[str, Any]]:
        return self.db.fetch_all(
            """
            SELECT
                e.id,
                e.entry_id,
                c.novel_id,
                c.canon_type,
                c.title,
                e.chapter_number,
                e.event_type,
                e.evidence,
                e.notes,
                e.created_at
            FROM coc_canon_events e
            JOIN coc_canon_entries c ON c.id = e.entry_id
            WHERE c.novel_id = ?
            ORDER BY e.chapter_number DESC, e.created_at DESC
            LIMIT ?
            """,
            (novel_id, int(limit)),
        )

    def upsert_entry(
        self,
        *,
        entry_id: Optional[str],
        novel_id: str,
        canon_type: str,
        title: str,
        public_facts: str,
        hidden_truth: str,
        lock_level: str,
        mutable_notes: str,
        status: str,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        existing = self.get_entry_by_id(entry_id) if entry_id else self.get_entry_by_key(
            novel_id,
            canon_type,
            title,
        )
        if existing:
            self.db.execute(
                """
                UPDATE coc_canon_entries
                SET canon_type = ?, title = ?, public_facts = ?, hidden_truth = ?,
                    lock_level = ?, mutable_notes = ?, status = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    canon_type,
                    title,
                    public_facts,
                    hidden_truth,
                    lock_level,
                    mutable_notes,
                    status,
                    now,
                    existing["id"],
                ),
            )
            saved_id = existing["id"]
        else:
            saved_id = str(uuid.uuid4())
            self.db.execute(
                """
                INSERT INTO coc_canon_entries (
                    id, novel_id, canon_type, title, public_facts, hidden_truth,
                    lock_level, mutable_notes, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    saved_id,
                    novel_id,
                    canon_type,
                    title,
                    public_facts,
                    hidden_truth,
                    lock_level,
                    mutable_notes,
                    status,
                    now,
                    now,
                ),
            )
        self.db.commit()
        return self.get_entry_by_id(saved_id) or {}

    def create_event(
        self,
        *,
        entry_id: str,
        chapter_number: int,
        event_type: str,
        evidence: str,
        notes: str,
    ) -> dict[str, Any]:
        event_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        self.db.execute(
            """
            INSERT INTO coc_canon_events (
                id, entry_id, chapter_number, event_type, evidence, notes, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                entry_id,
                int(chapter_number),
                event_type,
                evidence,
                notes,
                now,
            ),
        )
        self.db.commit()
        return self.db.fetch_one(
            """
            SELECT
                e.id,
                e.entry_id,
                c.novel_id,
                c.canon_type,
                c.title,
                e.chapter_number,
                e.event_type,
                e.evidence,
                e.notes,
                e.created_at
            FROM coc_canon_events e
            JOIN coc_canon_entries c ON c.id = e.entry_id
            WHERE e.id = ?
            """,
            (event_id,),
        ) or {}
