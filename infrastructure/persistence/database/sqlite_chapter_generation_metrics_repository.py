"""读写 chapter_generation_metrics 表。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from infrastructure.persistence.database.connection import DatabaseConnection


class SqliteChapterGenerationMetricsRepository:
    def __init__(self, db: DatabaseConnection):
        self.db = db

    def get(self, novel_id: str, chapter_number: int) -> Optional[Dict[str, Any]]:
        row = self.db.fetch_one(
            """
            SELECT
                novel_id,
                chapter_number,
                generated_via,
                target_word_count,
                actual_word_count,
                tolerance,
                delta,
                status,
                within_tolerance,
                action,
                expansion_attempts,
                trim_applied,
                fallback_used,
                created_at,
                updated_at
            FROM chapter_generation_metrics
            WHERE novel_id = ? AND chapter_number = ?
            """,
            (novel_id, int(chapter_number)),
        )
        if not row:
            return None
        return self._normalize_row(row)

    def upsert(self, novel_id: str, chapter_number: int, metrics: Dict[str, Any]) -> Dict[str, Any]:
        now = datetime.utcnow().isoformat()
        self.db.execute(
            """
            INSERT INTO chapter_generation_metrics (
                novel_id,
                chapter_number,
                generated_via,
                target_word_count,
                actual_word_count,
                tolerance,
                delta,
                status,
                within_tolerance,
                action,
                expansion_attempts,
                trim_applied,
                fallback_used,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(novel_id, chapter_number) DO UPDATE SET
                generated_via = excluded.generated_via,
                target_word_count = excluded.target_word_count,
                actual_word_count = excluded.actual_word_count,
                tolerance = excluded.tolerance,
                delta = excluded.delta,
                status = excluded.status,
                within_tolerance = excluded.within_tolerance,
                action = excluded.action,
                expansion_attempts = excluded.expansion_attempts,
                trim_applied = excluded.trim_applied,
                fallback_used = excluded.fallback_used,
                updated_at = excluded.updated_at
            """,
            (
                novel_id,
                int(chapter_number),
                str(metrics.get("generated_via") or "manual"),
                int(metrics.get("target")),
                int(metrics.get("actual")),
                float(metrics.get("tolerance", 0.15)),
                int(metrics.get("delta", 0)),
                str(metrics.get("status") or "ok"),
                1 if metrics.get("within_tolerance") else 0,
                str(metrics.get("action") or "none"),
                int(metrics.get("expansion_attempts", 0)),
                1 if metrics.get("trim_applied") else 0,
                1 if metrics.get("fallback_used") else 0,
                now,
                now,
            ),
        )
        self.db.get_connection().commit()
        return self.get(novel_id, chapter_number) or {}

    def get_book_summary(self, novel_id: str) -> Dict[str, Any]:
        row = self.db.fetch_one(
            """
            SELECT
                COUNT(*) AS total_measured,
                SUM(CASE WHEN within_tolerance = 1 THEN 1 ELSE 0 END) AS within_tolerance_count,
                SUM(CASE WHEN expansion_attempts > 0 THEN 1 ELSE 0 END) AS expansion_trigger_count,
                SUM(CASE WHEN trim_applied = 1 THEN 1 ELSE 0 END) AS trim_trigger_count,
                AVG(expansion_attempts) AS avg_expansion_attempts
            FROM chapter_generation_metrics
            WHERE novel_id = ?
            """,
            (novel_id,),
        ) or {}
        total = int(row.get("total_measured") or 0)
        within = int(row.get("within_tolerance_count") or 0)
        expansions = int(row.get("expansion_trigger_count") or 0)
        trims = int(row.get("trim_trigger_count") or 0)
        avg_attempts = float(row.get("avg_expansion_attempts") or 0.0)
        return {
            "total_measured": total,
            "within_tolerance_count": within,
            "pass_rate": (within / total) if total > 0 else None,
            "expansion_trigger_count": expansions,
            "trim_trigger_count": trims,
            "expansion_trigger_rate": (expansions / total) if total > 0 else None,
            "trim_trigger_rate": (trims / total) if total > 0 else None,
            "avg_expansion_attempts": avg_attempts,
        }

    def _normalize_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "novel_id": row.get("novel_id"),
            "chapter_number": int(row.get("chapter_number") or 0),
            "generated_via": row.get("generated_via") or "manual",
            "target": int(row.get("target_word_count") or 0),
            "actual": int(row.get("actual_word_count") or 0),
            "tolerance": float(row.get("tolerance") or 0.15),
            "delta": int(row.get("delta") or 0),
            "status": row.get("status") or "ok",
            "within_tolerance": bool(row.get("within_tolerance")),
            "action": row.get("action") or "none",
            "expansion_attempts": int(row.get("expansion_attempts") or 0),
            "trim_applied": bool(row.get("trim_applied")),
            "fallback_used": bool(row.get("fallback_used")),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
            "min_allowed": max(1, int((row.get("target_word_count") or 0) * (1 - float(row.get("tolerance") or 0.15)))),
            "max_allowed": max(1, int((row.get("target_word_count") or 0) * (1 + float(row.get("tolerance") or 0.15)))),
        }
