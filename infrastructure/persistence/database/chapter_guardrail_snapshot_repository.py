"""章节保存后自动护栏结果快照（供 GET 读取，避免前端重复 POST）。"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class ChapterGuardrailSnapshotRepository:
    def __init__(self, db_pool: Any) -> None:
        self._db_pool = db_pool
        self._ensure_table()

    def _ensure_table(self) -> None:
        try:
            with self._db_pool.get_connection() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS chapter_guardrail_snapshots (
                        novel_id TEXT NOT NULL,
                        chapter_number INTEGER NOT NULL,
                        report_json TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (novel_id, chapter_number)
                    )
                    """
                )
                conn.commit()
        except Exception as e:
            logger.error("chapter_guardrail_snapshots 表创建失败: %s", e)

    def upsert(self, novel_id: str, chapter_number: int, report: Dict[str, Any]) -> None:
        payload = json.dumps(report, ensure_ascii=False)
        ts = datetime.now(timezone.utc).isoformat()
        with self._db_pool.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO chapter_guardrail_snapshots
                    (novel_id, chapter_number, report_json, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(novel_id, chapter_number) DO UPDATE SET
                    report_json = excluded.report_json,
                    updated_at = excluded.updated_at
                """,
                (novel_id, chapter_number, payload, ts),
            )
            conn.commit()

    def get(self, novel_id: str, chapter_number: int) -> Optional[Dict[str, Any]]:
        with self._db_pool.get_connection() as conn:
            row = conn.execute(
                """
                SELECT report_json FROM chapter_guardrail_snapshots
                WHERE novel_id = ? AND chapter_number = ?
                """,
                (novel_id, chapter_number),
            ).fetchone()
        if not row or not row[0]:
            return None
        try:
            return json.loads(row[0])
        except json.JSONDecodeError:
            return None
