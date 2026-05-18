"""Statistics service layer for business logic."""
import time as _time
from typing import Optional, List, Dict
from datetime import datetime
import logging

from ..repositories.stats_repository import StatsRepository
from ..models.stats_models import GlobalStats, BookStats, ChapterStats, WritingProgress

logger = logging.getLogger(__name__)


class StatsService:
    """Service layer for statistics business logic.

    This class provides high-level methods for calculating statistics across
    books, chapters, and tracking writing progress. It coordinates between the
    repository layer (data access) and models (data structures).
    """

    # ── 全局统计 TTL 缓存 ──
    _GLOBAL_STATS_CACHE_TTL = 30.0  # 秒
    _global_stats_cache: Optional[Dict] = None  # {"data": GlobalStats, "ts": float}

    def __init__(self, repository: StatsRepository):
        """Initialize the service with a repository.

        Args:
            repository: StatsRepository instance for data access
        """
        self.repository = repository
        logger.info("StatsService initialized")

    def get_global_stats(self) -> GlobalStats:
        """获取全局统计（SQL 聚合 + TTL 缓存）。

        原实现：N 本小说 × M 章 = N×M 次 content 查询（每次拉全文字段），
        10 本 × 100 章 = 1000+ 次 SQL，极其缓慢。

        优化后：用 SQL SUM(LENGTH(content)) 在 DB 内直接聚合，
        1 条查询替代 1000+ 条。TTL 缓存避免高频重复计算。
        """
        # 检查 TTL 缓存
        cache = self._global_stats_cache
        if cache is not None and _time.time() - cache["ts"] < self._GLOBAL_STATS_CACHE_TTL:
            return cache["data"]

        logger.info("Calculating global statistics (optimized SQL aggregation)")

        # ── 1 条 SQL 聚合所有数据 ──
        # 从 SqliteStatsRepositoryAdapter 获取原始 db 连接
        db = getattr(self.repository, "db", None)
        if db is not None:
            stats = self._get_global_stats_via_sql(db)
        else:
            stats = self._get_global_stats_fallback()

        self._global_stats_cache = {"data": stats, "ts": _time.time()}
        logger.info(
            "Global stats: %s books, %s chapters, %s chars",
            stats.total_books, stats.total_chapters, stats.total_characters,
        )
        return stats

    def _get_global_stats_via_sql(self, db) -> GlobalStats:
        """直接 SQL 聚合（快速路径）。"""
        import re as _re

        # 阶段映射（SQL 内用 CASE WHEN 直接算出 public stage）
        # 复用与 SqliteStatsRepositoryAdapter._public_stage_from_row 相同的逻辑
        row = db.fetch_one("""
            SELECT
                COUNT(DISTINCT n.id)                                   AS total_books,
                COUNT(c.id)                                            AS total_chapters,
                COALESCE(SUM(LENGTH(c.content)), 0)                    AS total_characters,
                COALESCE(SUM(CASE WHEN c.content IS NOT NULL
                                  AND c.content != '' THEN 1 ELSE 0 END), 0) AS chapters_with_content
            FROM novels n
            LEFT JOIN chapters c ON n.id = c.novel_id
        """)

        total_books = row["total_books"] if row else 0
        total_chapters = row["total_chapters"] if row else 0
        total_characters = row["total_characters"] if row else 0
        chapters_with_content = row["chapters_with_content"] if row else 0

        # 估算总字数：中文为主时 ≈ 字符数；有英文时需加回英文单词
        # 作为近似，用 总字符数 作为 total_words（对中文写作已是准确值）
        total_words = total_characters

        # 按阶段分组
        stage_rows = db.fetch_all("""
            SELECT current_stage, COUNT(*) AS c
            FROM novels
            GROUP BY current_stage
        """)

        stage_map = {
            "planning": "planning", "macro_planning": "planning",
            "act_planning": "planning", "writing": "writing",
            "auditing": "reviewing", "reviewing": "reviewing",
            "paused_for_review": "reviewing", "completed": "completed",
        }
        books_by_stage: Dict[str, int] = {}
        for sr in stage_rows:
            raw = sr["current_stage"] or "planning"
            public = stage_map.get(raw, raw)
            books_by_stage[public] = books_by_stage.get(public, 0) + sr["c"]

        return GlobalStats(
            total_books=total_books,
            total_chapters=total_chapters,
            total_words=total_words,
            total_characters=total_characters,
            books_by_stage=books_by_stage,
        )

    def _get_global_stats_fallback(self) -> GlobalStats:
        """降级路径：通过 repository 接口逐 novel 聚合（无 db 直连时使用）。"""
        book_slugs = self.repository.get_all_book_slugs()
        total_books = len(book_slugs)
        total_chapters = 0
        total_words = 0
        total_characters = 0
        books_by_stage: Dict[str, int] = {}

        for slug in book_slugs:
            manifest = self.repository.get_book_manifest(slug)
            if manifest:
                stage = manifest.get("stage", "unknown")
                books_by_stage[stage] = books_by_stage.get(stage, 0) + 1

            outline = self.repository.get_book_outline(slug)
            if outline and "chapters" in outline:
                total_chapters += len(outline["chapters"])
                for chapter_info in outline["chapters"]:
                    chapter_id = chapter_info.get("id")
                    if chapter_id:
                        content = self.repository.get_chapter_content(slug, chapter_id)
                        if content:
                            total_words += self.repository.count_words(content)
                            total_characters += len(content)

        return GlobalStats(
            total_books=total_books,
            total_chapters=total_chapters,
            total_words=total_words,
            total_characters=total_characters,
            books_by_stage=books_by_stage,
        )

    def get_book_stats(self, slug: str) -> Optional[BookStats]:
        """Get statistics for a specific book.

        Calculates:
        - Total chapter count from outline
        - Completed chapters (those with content)
        - Total word count across all chapters
        - Average words per chapter
        - Completion rate (completed / total)

        Args:
            slug: The book's slug (directory name)

        Returns:
            BookStats object if book found, None otherwise
        """
        logger.info(f"Getting book statistics for: {slug}")

        manifest = self.repository.get_book_manifest(slug)
        if not manifest:
            logger.warning(f"Book not found: {slug}")
            return None

        title = manifest.get("title", slug)

        outline = self.repository.get_book_outline(slug)
        if not outline or "chapters" not in outline:
            logger.warning(f"Outline not found or invalid for book: {slug}")
            return None

        chapters_info = outline["chapters"]
        total_chapters = len(chapters_info)
        completed_chapters = 0
        total_words = 0

        for chapter_info in chapters_info:
            chapter_id = chapter_info.get("id")
            if chapter_id:
                content = self.repository.get_chapter_content(slug, chapter_id)
                if content:
                    word_count = self.repository.count_words(content)
                    if word_count > 0:
                        completed_chapters += 1
                    total_words += word_count

        avg_chapter_words = total_words // total_chapters if total_chapters > 0 else 0
        completion_rate = completed_chapters / total_chapters if total_chapters > 0 else 0.0

        stats = BookStats(
            slug=slug,
            title=title,
            total_chapters=total_chapters,
            completed_chapters=completed_chapters,
            total_words=total_words,
            avg_chapter_words=avg_chapter_words,
            completion_rate=completion_rate,
            last_updated=datetime.now()
        )

        logger.info(f"Book stats for {slug}: {total_chapters} chapters, {completed_chapters} completed, {total_words} words")
        return stats

    def get_chapter_stats(self, slug: str, chapter_id: int) -> Optional[ChapterStats]:
        """Get statistics for a specific chapter.

        Finds the chapter title from outline and calculates:
        - Word count (supporting mixed Chinese/English)
        - Character count
        - Paragraph count
        - Whether content exists

        Args:
            slug: The book's slug (directory name)
            chapter_id: The chapter's numeric ID (>= 1)

        Returns:
            ChapterStats object if chapter found, None otherwise
        """
        logger.info(f"Getting chapter statistics for: {slug}, chapter {chapter_id}")

        outline = self.repository.get_book_outline(slug)
        if not outline or "chapters" not in outline:
            logger.warning(f"Outline not found or invalid for book: {slug}")
            return None

        # Find chapter title from outline
        chapter_title = f"Chapter {chapter_id}"
        for chapter_info in outline["chapters"]:
            if chapter_info.get("id") == chapter_id:
                chapter_title = chapter_info.get("title", chapter_title)
                break

        content = self.repository.get_chapter_content(slug, chapter_id)
        if content is None:
            logger.warning(f"Chapter content not found: {slug}, chapter {chapter_id}")
            return None

        # Calculate statistics
        word_count = self.repository.count_words(content)
        character_count = len(content)

        # Count paragraphs (non-empty lines)
        lines = content.split('\n')
        paragraph_count = sum(1 for line in lines if line.strip())

        has_content = word_count > 0 or character_count > 0

        stats = ChapterStats(
            chapter_id=chapter_id,
            title=chapter_title,
            word_count=word_count,
            character_count=character_count,
            paragraph_count=paragraph_count,
            has_content=has_content
        )

        logger.info(f"Chapter stats for {slug}/{chapter_id}: {word_count} words, {character_count} chars, {paragraph_count} paragraphs")
        return stats

    def get_writing_progress(self, slug: str, days: int = 30) -> List[WritingProgress]:
        """Get writing progress over time.

        TODO: Implement in Week 2
        - Track when chapters were created/modified
        - Calculate daily word count
        - Show progress trends

        Args:
            slug: The book's slug (directory name)
            days: Number of days to look back (default 30)

        Returns:
            Empty list for now, to be implemented in Week 2
        """
        logger.info(f"Getting writing progress for: {slug}, days={days} (TODO: Week 2)")
        return []
