"""SQLite Chapter Candidate Draft Repository。"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from infrastructure.persistence.database.connection import DatabaseConnection


class SqliteChapterCandidateDraftRepository:
    """chapter_candidate_drafts 表读写。"""

    def __init__(self, db: DatabaseConnection):
        self.db = db

    def create(
        self,
        *,
        novel_id: str,
        chapter_number: int,
        source: str,
        title: str,
        content: str,
        rationale: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        branch_name: str = "main",
        status: str = "draft",
    ) -> Dict[str, Any]:
        draft_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        self.db.execute(
            """
            INSERT INTO chapter_candidate_drafts (
                id, novel_id, chapter_number, branch_name, source, status,
                title, content, rationale, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                draft_id,
                novel_id,
                int(chapter_number),
                branch_name,
                source,
                status,
                title or "",
                content,
                rationale or "",
                json.dumps(metadata or {}, ensure_ascii=False),
                now,
                now,
            ),
        )
        self.db.commit()
        return self.get(draft_id)

    def list_by_chapter(
        self,
        novel_id: str,
        chapter_number: int,
        *,
        branch_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        sql = """
            SELECT * FROM chapter_candidate_drafts
            WHERE novel_id = ? AND chapter_number = ?
        """
        params: List[Any] = [novel_id, int(chapter_number)]
        if branch_name:
            sql += " AND branch_name = ?"
            params.append(branch_name)
        sql += " ORDER BY created_at DESC"
        rows = self.db.fetch_all(sql, tuple(params))
        return [self._row_to_dict(row) for row in rows]

    def get(self, draft_id: str) -> Optional[Dict[str, Any]]:
        row = self.db.fetch_one(
            "SELECT * FROM chapter_candidate_drafts WHERE id = ?",
            (draft_id,),
        )
        if not row:
            return None
        return self._row_to_dict(row)

    def update_status(self, draft_id: str, status: str) -> Optional[Dict[str, Any]]:
        now = datetime.utcnow().isoformat()
        self.db.execute(
            """
            UPDATE chapter_candidate_drafts
            SET status = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, now, draft_id),
        )
        self.db.commit()
        return self.get(draft_id)

    def delete(self, draft_id: str) -> None:
        self.db.execute(
            "DELETE FROM chapter_candidate_drafts WHERE id = ?",
            (draft_id,),
        )
        self.db.commit()

    @staticmethod
    def _row_to_dict(row: Dict[str, Any]) -> Dict[str, Any]:
        metadata_raw = row.get("metadata_json")
        try:
            metadata = json.loads(metadata_raw) if metadata_raw else {}
        except (TypeError, json.JSONDecodeError):
            metadata = {}

        data = dict(row)
        data["metadata"] = metadata
        return data
