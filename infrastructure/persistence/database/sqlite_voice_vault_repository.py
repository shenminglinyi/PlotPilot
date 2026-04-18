"""SQLite Voice Vault Repository Implementation"""
import logging
from typing import List, Optional
from uuid import uuid4
from datetime import datetime, timezone
from domain.novel.repositories.voice_vault_repository import VoiceVaultRepository
from infrastructure.persistence.database.connection import DatabaseConnection

logger = logging.getLogger(__name__)


class SqliteVoiceVaultRepository(VoiceVaultRepository):
    """SQLite Voice Vault Repository 实现"""

    def __init__(self, db: DatabaseConnection):
        self.db = db

    def append_sample(
        self,
        novel_id: str,
        chapter_number: int,
        scene_type: Optional[str],
        ai_original: str,
        author_refined: str,
        diff_analysis: str
    ) -> str:
        """添加文风样本"""
        sample_id = str(uuid4())
        sql = """
            INSERT INTO voice_vault (
                sample_id, novel_id, chapter_number, scene_type,
                ai_original, author_refined, diff_analysis, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        now = datetime.now(timezone.utc).isoformat()
        self.db.execute(sql, (
            sample_id,
            novel_id,
            chapter_number,
            scene_type,
            ai_original,
            author_refined,
            diff_analysis,
            now
        ))
        self.db.get_connection().commit()
        logger.info(f"Added voice sample: {sample_id} for novel {novel_id}")
        return sample_id

    def list_samples(self, novel_id: str, limit: Optional[int] = None) -> List[dict]:
        """列出小说的文风样�?""
        sql = """
            SELECT sample_id, novel_id, chapter_number, scene_type,
                   ai_original, author_refined, diff_analysis, created_at
            FROM voice_vault
            WHERE novel_id = ?
            ORDER BY created_at DESC
        """
        if limit is not None:
            sql += f" LIMIT {int(limit)}"

        rows = self.db.fetch_all(sql, (novel_id,))
        return [dict(row) for row in rows]

    def get_sample_count(self, novel_id: str) -> int:
        """获取小说的样本数�?""
        sql = "SELECT COUNT(*) as count FROM voice_vault WHERE novel_id = ?"
        row = self.db.fetch_one(sql, (novel_id,))
        return row['count'] if row else 0

    def get_by_novel(
        self, novel_id: str, pov_character_id: Optional[str] = None
    ) -> List[dict]:
        """获取小说的所有样本（用于指纹计算�?""
        # Note: Current schema doesn't have pov_character_id, so we ignore it for now
        sql = """
            SELECT author_refined as content
            FROM voice_vault
            WHERE novel_id = ?
            ORDER BY created_at ASC
        """
        rows = self.db.fetch_all(sql, (novel_id,))
        return [dict(row) for row in rows]
