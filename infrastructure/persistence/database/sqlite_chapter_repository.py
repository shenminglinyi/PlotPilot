"""SQLite Chapter Repository 实现"""
import logging
import json
from typing import Optional, List
from datetime import datetime
from domain.novel.entities.chapter import Chapter
from domain.novel.value_objects.chapter_id import ChapterId
from domain.novel.value_objects.novel_id import NovelId
from domain.novel.repositories.chapter_repository import ChapterRepository
from infrastructure.persistence.database.connection import DatabaseConnection

logger = logging.getLogger(__name__)


class SqliteChapterRepository(ChapterRepository):
    """SQLite Chapter Repository 实现"""

    def __init__(self, db: DatabaseConnection):
        self.db = db

    def save(self, chapter: Chapter) -> None:
        """保存章节"""
        sql = """
            INSERT INTO chapters (id, novel_id, number, title, content, outline, status,
                                  tension_score, plot_tension, emotional_tension, pacing_tension,
                                  created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                content = excluded.content,
                outline = excluded.outline,
                status = excluded.status,
                tension_score = excluded.tension_score,
                plot_tension = excluded.plot_tension,
                emotional_tension = excluded.emotional_tension,
                pacing_tension = excluded.pacing_tension,
                updated_at = excluded.updated_at
        """
        now = datetime.utcnow().isoformat()
        chapter_id = chapter.id.value if hasattr(chapter.id, 'value') else chapter.id
        novel_id = chapter.novel_id.value if hasattr(chapter.novel_id, 'value') else chapter.novel_id
        status = chapter.status.value if hasattr(chapter.status, 'value') else chapter.status
        self.db.execute(sql, (
            chapter_id,
            novel_id,
            chapter.number,
            chapter.title,
            chapter.content,
            chapter.outline,  # 使用实体的 outline 字段
            status,
            chapter.tension_score,
            chapter.plot_tension,
            chapter.emotional_tension,
            chapter.pacing_tension,
            now,
            now
        ))
        self.db.get_connection().commit()
        logger.info(f"Saved chapter: {chapter_id}")

    def get_by_id(self, chapter_id: ChapterId) -> Optional[Chapter]:
        """根据 ID 获取章节"""
        sql = "SELECT * FROM chapters WHERE id = ?"
        row = self.db.fetch_one(sql, (chapter_id.value,))

        if not row:
            return None

        return self._row_to_chapter(row)

    def get_by_novel_and_number(self, novel_id: NovelId, number: int) -> Optional[Chapter]:
        """根据小说 ID 和章节号获取章节"""
        sql = "SELECT * FROM chapters WHERE novel_id = ? AND number = ?"
        row = self.db.fetch_one(sql, (novel_id.value, number))

        if not row:
            return None

        return self._row_to_chapter(row)

    def list_by_novel(self, novel_id: NovelId) -> List[Chapter]:
        """列出小说的所有章节"""
        sql = "SELECT * FROM chapters WHERE novel_id = ? ORDER BY number ASC"
        rows = self.db.fetch_all(sql, (novel_id.value,))

        return [self._row_to_chapter(row) for row in rows]

    def delete(self, chapter_id: ChapterId) -> None:
        """删除章节
        
        需要先清理关联数据：
        - triples 表通过 (novel_id, chapter_number) 外键引用章节
        - 由于 novel_id 是 NOT NULL，ON DELETE SET NULL 会失败
        - 所以需要先将相关 triples 的 chapter_number 设为 NULL
        """
        # 1. 获取章节信息以确定 novel_id 和章节号
        chapter = self.get_by_id(chapter_id)
        if not chapter:
            logger.warning(f"Chapter not found for deletion: {chapter_id.value}")
            return
        
        novel_id = chapter.novel_id.value if hasattr(chapter.novel_id, 'value') else chapter.novel_id
        chapter_number = chapter.number
        
        # 2. 先处理 triples 表中引用此章节的记录（将 chapter_number 设为 NULL）
        # 注意：triples 表有 FOREIGN KEY (novel_id, chapter_number) REFERENCES chapters ON DELETE SET NULL
        # 但 novel_id 是 NOT NULL，所以直接删除章节会导致约束失败
        # 正确做法：先将 triples 中相关记录的 chapter_number 设为 NULL
        update_triples_sql = """
            UPDATE triples 
            SET chapter_number = NULL, updated_at = ?
            WHERE novel_id = ? AND chapter_number = ?
        """
        now = datetime.utcnow().isoformat()
        self.db.execute(update_triples_sql, (now, novel_id, chapter_number))
        
        # 3. 删除 triple_more_chapters 中关联此章节的记录
        delete_more_sql = """
            DELETE FROM triple_more_chapters 
            WHERE novel_id = ? AND chapter_number = ?
        """
        self.db.execute(delete_more_sql, (novel_id, chapter_number))
        
        # 4. 删除章节
        sql = "DELETE FROM chapters WHERE id = ?"
        self.db.execute(sql, (chapter_id.value,))
        self.db.get_connection().commit()
        logger.info(f"Deleted chapter: {chapter_id.value}")

    def exists(self, chapter_id: ChapterId) -> bool:
        """检查章节是否存在"""
        sql = "SELECT 1 FROM chapters WHERE id = ? LIMIT 1"
        row = self.db.fetch_one(sql, (chapter_id.value,))
        return row is not None

    def update_tension_score(self, novel_id: str, chapter_number: int, score: float) -> None:
        """更新章节张力分数"""
        if not 0 <= score <= 100:
            raise ValueError(f"Tension score must be between 0 and 100, got {score}")

        sql = """
            UPDATE chapters
            SET tension_score = ?, updated_at = ?
            WHERE novel_id = ? AND number = ?
        """
        now = datetime.utcnow().isoformat()
        self.db.execute(sql, (score, now, novel_id, chapter_number))
        self.db.get_connection().commit()
        logger.info(f"Updated tension score for novel {novel_id} chapter {chapter_number}: {score}")

    def _row_to_chapter(self, row: dict) -> Chapter:
        """将数据库行转换为 Chapter 实体"""
        from domain.novel.value_objects.novel_id import NovelId
        from domain.novel.entities.chapter import ChapterStatus
        raw_status = row.get('status', 'draft')
        try:
            status = ChapterStatus(raw_status)
        except ValueError:
            status = ChapterStatus.DRAFT
        return Chapter(
            id=row['id'],
            novel_id=NovelId(row['novel_id']),
            number=row['number'],
            title=row['title'],
            content=row['content'],
            outline=row.get('outline', ''),
            status=status,
            tension_score=row.get('tension_score', 50.0),
            plot_tension=row.get('plot_tension', 50.0),
            emotional_tension=row.get('emotional_tension', 50.0),
            pacing_tension=row.get('pacing_tension', 50.0),
        )
