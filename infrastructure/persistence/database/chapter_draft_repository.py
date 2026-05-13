"""章节历史草稿仓储（章节重新生成前的版本快照）"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import List, Optional

from infrastructure.persistence.database.connection import DatabaseConnection

logger = logging.getLogger(__name__)

_MAX_DRAFTS_PER_CHAPTER = 10  # 每章最多保留的历史版本数


class ChapterDraftRecord:
    """章节历史草稿数据对象"""

    def __init__(
        self,
        id: str,
        novel_id: str,
        chapter_id: str,
        chapter_number: int,
        content: str,
        outline: str,
        source: str,
        word_count: int,
        created_at: str,
    ) -> None:
        self.id = id
        self.novel_id = novel_id
        self.chapter_id = chapter_id
        self.chapter_number = chapter_number
        self.content = content
        self.outline = outline
        self.source = source
        self.word_count = word_count
        self.created_at = created_at


class ChapterDraftRepository:
    """章节历史草稿仓储：追加写入、按时间倒序列出、自动修剪旧版本。"""

    def __init__(self, db: DatabaseConnection) -> None:
        self.db = db

    def save_draft(
        self,
        novel_id: str,
        chapter_id: str,
        chapter_number: int,
        content: str,
        outline: str = "",
        source: str = "manual_save",
    ) -> ChapterDraftRecord:
        """保存一个历史草稿快照，并自动修剪超出上限的旧版本。

        Args:
            source: 'pre_regen'=重新生成前自动快照 | 'manual_save'=手动触发 | 'auto_gen'=首次生成
        """
        if not content or not content.strip():
            raise ValueError("不能保存空内容的草稿")

        draft_id = str(uuid.uuid4())
        word_count = len(content.replace(" ", ""))
        now = datetime.utcnow().isoformat()

        sql = """
            INSERT INTO chapter_drafts
                (id, novel_id, chapter_id, chapter_number, content, outline, source, word_count, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        self.db.execute(sql, (
            draft_id, novel_id, chapter_id, chapter_number,
            content, outline, source, word_count, now
        ))
        logger.info(
            "Saved chapter draft: novel=%s chapter=%s source=%s words=%d",
            novel_id, chapter_number, source, word_count
        )

        self._trim_old_drafts(novel_id, chapter_number)

        return ChapterDraftRecord(
            id=draft_id,
            novel_id=novel_id,
            chapter_id=chapter_id,
            chapter_number=chapter_number,
            content=content,
            outline=outline,
            source=source,
            word_count=word_count,
            created_at=now,
        )

    def list_drafts(
        self,
        novel_id: str,
        chapter_number: int,
        limit: int = _MAX_DRAFTS_PER_CHAPTER,
    ) -> List[ChapterDraftRecord]:
        """列出指定章节的历史草稿，按时间倒序排列（最新在前）。"""
        sql = """
            SELECT id, novel_id, chapter_id, chapter_number, content, outline,
                   source, word_count, created_at
            FROM chapter_drafts
            WHERE novel_id = ? AND chapter_number = ?
            ORDER BY created_at DESC
            LIMIT ?
        """
        rows = self.db.fetch_all(sql, (novel_id, chapter_number, limit))
        return [self._row_to_record(r) for r in rows]

    def get_draft(self, draft_id: str) -> Optional[ChapterDraftRecord]:
        """按 ID 获取单条草稿。"""
        sql = """
            SELECT id, novel_id, chapter_id, chapter_number, content, outline,
                   source, word_count, created_at
            FROM chapter_drafts
            WHERE id = ?
        """
        row = self.db.fetch_one(sql, (draft_id,))
        return self._row_to_record(row) if row else None

    def _trim_old_drafts(self, novel_id: str, chapter_number: int) -> None:
        """删除超出上限的最旧草稿。"""
        delete_sql = """
            DELETE FROM chapter_drafts
            WHERE id IN (
                SELECT id FROM chapter_drafts
                WHERE novel_id = ? AND chapter_number = ?
                ORDER BY created_at DESC
                LIMIT -1 OFFSET ?
            )
        """
        self.db.execute(delete_sql, (novel_id, chapter_number, _MAX_DRAFTS_PER_CHAPTER))

    @staticmethod
    def _row_to_record(row: dict) -> ChapterDraftRecord:
        return ChapterDraftRecord(
            id=row["id"],
            novel_id=row["novel_id"],
            chapter_id=row["chapter_id"],
            chapter_number=row["chapter_number"],
            content=row["content"],
            outline=row["outline"],
            source=row["source"],
            word_count=row["word_count"],
            created_at=row["created_at"],
        )
