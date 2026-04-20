"""读者模拟结果的 SQLite 仓储实现。"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class ReaderSimulationRepository:
    """读者模拟结果仓储（SQLite）"""

    def __init__(self, db=None):
        self._db = db

    def _get_db(self):
        if self._db:
            return self._db
        from infrastructure.persistence.database.connection import get_database
        return get_database()

    def ensure_table(self) -> None:
        """确保表存在（首次调用时自动建表）。"""
        from pathlib import Path
        migration_path = (
            Path(__file__).parent / "migrations" / "add_reader_simulations.sql"
        )
        db = self._get_db()
        if migration_path.exists():
            sql = migration_path.read_text(encoding="utf-8")
            db.executescript(sql)

    def save(
        self,
        novel_id: str,
        chapter_number: int,
        overall_readability: float,
        chapter_hook_strength: str,
        pacing_verdict: str,
        avg_scores: Dict[str, float],
        feedbacks_json: str,
    ) -> str:
        """保存一条分析记录，返回 id。"""
        record_id = uuid.uuid4().hex[:12]
        db = self._get_db()
        db.execute(
            """INSERT INTO reader_simulations
               (id, novel_id, chapter_number, overall_readability,
                chapter_hook_strength, pacing_verdict,
                avg_suspense_retention, avg_thrill_score,
                avg_churn_risk, avg_emotional_resonance,
                feedbacks_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record_id,
                novel_id,
                chapter_number,
                overall_readability,
                chapter_hook_strength,
                pacing_verdict,
                avg_scores.get("suspense_retention", 50.0),
                avg_scores.get("thrill_score", 50.0),
                avg_scores.get("churn_risk", 30.0),
                avg_scores.get("emotional_resonance", 50.0),
                feedbacks_json,
                datetime.utcnow().isoformat(),
            ),
        )
        db.commit()
        return record_id

    def get_latest(
        self, novel_id: str, chapter_number: int,
    ) -> Optional[Dict]:
        """获取某章最新的读者模拟记录。"""
        db = self._get_db()
        cursor = db.execute(
            """SELECT * FROM reader_simulations
               WHERE novel_id = ? AND chapter_number = ?
               ORDER BY created_at DESC LIMIT 1""",
            (novel_id, chapter_number),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return dict(row)

    def list_by_novel(self, novel_id: str) -> List[Dict]:
        """获取某本小说所有章节的最新记录（每章一条）。"""
        db = self._get_db()
        cursor = db.execute(
            """SELECT rs.* FROM reader_simulations rs
               INNER JOIN (
                   SELECT novel_id, chapter_number, MAX(created_at) as max_created
                   FROM reader_simulations
                   WHERE novel_id = ?
                   GROUP BY novel_id, chapter_number
               ) latest ON rs.novel_id = latest.novel_id
                       AND rs.chapter_number = latest.chapter_number
                       AND rs.created_at = latest.max_created
               ORDER BY rs.chapter_number""",
            (novel_id,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_high_churn_chapters(
        self, novel_id: str, threshold: float = 60.0,
    ) -> List[Dict]:
        """获取劝退风险高的章节（用于告警）。"""
        db = self._get_db()
        cursor = db.execute(
            """SELECT * FROM reader_simulations
               WHERE novel_id = ? AND avg_churn_risk >= ?
               ORDER BY avg_churn_risk DESC""",
            (novel_id, threshold),
        )
        return [dict(row) for row in cursor.fetchall()]
