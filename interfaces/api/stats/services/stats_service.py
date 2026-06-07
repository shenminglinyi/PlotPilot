"""Statistics service layer for business logic."""
from typing import Any, Optional, List, Dict
from datetime import datetime, timedelta, time
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

    def __init__(self, repository: StatsRepository):
        """Initialize the service with a repository.

        Args:
            repository: StatsRepository instance for data access
        """
        self.repository = repository
        logger.info("StatsService initialized")

    def get_global_stats(self) -> GlobalStats:
        """Get global statistics across all books.

        Iterates through all books and aggregates totals:
        - Total books count
        - Total chapters across all books
        - Total word count
        - Total character count
        - Books categorized by stage

        Returns:
            GlobalStats object with aggregated data
        """
        logger.info("Calculating global statistics")

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

                # Calculate words and characters for this book
                for chapter_info in outline["chapters"]:
                    chapter_id = chapter_info.get("id")
                    if chapter_id:
                        content = self.repository.get_chapter_content(slug, chapter_id)
                        if content:
                            word_count = self.repository.count_words(content)
                            total_words += word_count
                            total_characters += len(content)

        stats = GlobalStats(
            total_books=total_books,
            total_chapters=total_chapters,
            total_words=total_words,
            total_characters=total_characters,
            books_by_stage=books_by_stage
        )

        logger.info(f"Global stats: {total_books} books, {total_chapters} chapters, {total_words} words")
        return stats

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

        Aggregates chapter records by their latest available write timestamp.
        Repository adapters may expose ``get_chapter_progress_records``; when a
        repository cannot provide timestamps, this method returns an empty list
        instead of fabricating progress.

        Args:
            slug: The book's slug (directory name)
            days: Number of days to look back (default 30)

        Returns:
            List of daily writing progress records within the lookback window
        """
        safe_days = max(1, min(int(days or 30), 365))
        logger.info(f"Getting writing progress for: {slug}, days={safe_days}")

        provider = getattr(self.repository, "get_chapter_progress_records", None)
        if not callable(provider):
            logger.info("Repository does not expose chapter progress records: %s", type(self.repository).__name__)
            return []

        records = provider(slug)
        if not records:
            return []

        now = datetime.now()
        start_day = (now - timedelta(days=safe_days - 1)).date()
        buckets: Dict[Any, Dict[str, int]] = {}

        for record in records:
            if not isinstance(record, dict):
                continue
            written_at = self._coerce_progress_datetime(record.get("written_at") or record.get("updated_at") or record.get("created_at"))
            if written_at is None or written_at.date() < start_day or written_at.date() > now.date():
                continue

            content = str(record.get("content") or "")
            words = record.get("word_count")
            if not isinstance(words, int):
                words = self.repository.count_words(content)
            if words <= 0:
                continue

            day = written_at.date()
            bucket = buckets.setdefault(day, {"words_written": 0, "chapters_completed": 0})
            bucket["words_written"] += words
            bucket["chapters_completed"] += 1

        return [
            WritingProgress(
                date=datetime.combine(day, time.min),
                words_written=data["words_written"],
                chapters_completed=data["chapters_completed"],
            )
            for day, data in sorted(buckets.items())
        ]

    @staticmethod
    def _coerce_progress_datetime(value: Any) -> Optional[datetime]:
        if isinstance(value, datetime):
            return value
        if isinstance(value, (int, float)):
            try:
                return datetime.fromtimestamp(value)
            except (OSError, OverflowError, ValueError):
                return None
        if isinstance(value, str) and value.strip():
            raw = value.strip()
            try:
                return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
            except ValueError:
                return None
        return None
