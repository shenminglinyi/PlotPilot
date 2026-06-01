"""Statistics data access layer for book content analysis."""
from pathlib import Path
from typing import Optional, Dict, List
import json
import logging

logger = logging.getLogger(__name__)


class StatsRepository:
    """Repository for accessing book statistics data.

    This class provides methods to read book manifests, outlines, and chapter
    content for statistical analysis. It handles file system operations and
    provides proper error handling and logging.
    """

    def __init__(self, books_root: Path):
        """Initialize the repository with a books root path.

        Args:
            books_root: Path to the books directory containing book folders
        """
        self.books_root = Path(books_root)
        logger.info(f"StatsRepository initialized with books_root: {self.books_root}")

    def get_all_book_slugs(self) -> List[str]:
        """Get all book slugs by scanning for manifest.json files.

        Returns:
            List of book slugs (directory names) that contain manifest.json files
        """
        slugs = []
        try:
            for book_dir in self.books_root.iterdir():
                if book_dir.is_dir():
                    manifest_file = book_dir / "manifest.json"
                    if manifest_file.exists():
                        slugs.append(book_dir.name)
            logger.info(f"Found {len(slugs)} books: {slugs}")
        except Exception as e:
            logger.error(f"Error scanning books directory: {e}")
        return slugs

    def get_book_manifest(self, slug: str) -> Optional[Dict]:
        """Read a book's manifest.json file.

        Args:
            slug: The book's slug (directory name)

        Returns:
            Dictionary containing manifest data, or None if not found/error
        """
        try:
            manifest_path = self.books_root / slug / "manifest.json"
            if not manifest_path.exists():
                logger.warning(f"Manifest not found for book: {slug}")
                return None

            with open(manifest_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logger.debug(f"Successfully read manifest for book: {slug}")
                return data
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in manifest for book {slug}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error reading manifest for book {slug}: {e}")
            return None

    def get_book_outline(self, slug: str) -> Optional[Dict]:
        """Read a book's outline.json file.

        Args:
            slug: The book's slug (directory name)

        Returns:
            Dictionary containing outline data, or None if not found/error
        """
        try:
            outline_path = self.books_root / slug / "outline.json"
            if not outline_path.exists():
                logger.warning(f"Outline not found for book: {slug}")
                return None

            with open(outline_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logger.debug(f"Successfully read outline for book: {slug}")
                return data
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in outline for book {slug}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error reading outline for book {slug}: {e}")
            return None

    def get_chapter_content(self, slug: str, chapter_id: int) -> Optional[str]:
        """Read a chapter's body.md content.

        Args:
            slug: The book's slug (directory name)
            chapter_id: The chapter's numeric ID (>= 1)

        Returns:
            String containing chapter content, or None if not found/error
        """
        try:
            chapter_path = self.books_root / slug / "chapters" / f"ch-{chapter_id:04d}" / "body.md"
            if not chapter_path.exists():
                logger.warning(f"Chapter content not found for book {slug}, chapter {chapter_id}")
                return None

            with open(chapter_path, 'r', encoding='utf-8') as f:
                content = f.read()
                logger.debug(f"Successfully read chapter {chapter_id} for book: {slug}")
                return content
        except Exception as e:
            logger.error(f"Error reading chapter {chapter_id} for book {slug}: {e}")
            return None

    def get_chapter_progress_records(self, slug: str) -> List[Dict]:
        """Return chapter content with filesystem write timestamps for progress aggregation."""
        outline = self.get_book_outline(slug)
        if not outline:
            return []
        records: List[Dict] = []
        for chapter in outline.get("chapters", []):
            chapter_id = chapter.get("id")
            try:
                chapter_num = int(chapter_id)
            except (TypeError, ValueError):
                continue
            chapter_path = self.books_root / slug / "chapters" / f"ch-{chapter_num:04d}" / "body.md"
            content = self.get_chapter_content(slug, chapter_num)
            if content is None:
                continue
            try:
                written_at = chapter_path.stat().st_mtime
            except OSError:
                written_at = None
            records.append(
                {
                    "chapter_id": chapter_num,
                    "title": chapter.get("title", ""),
                    "content": content,
                    "written_at": written_at,
                }
            )
        return records

    def count_words(self, text: str) -> int:
        """Count words in text, supporting both Chinese and English.

        Chinese characters are counted individually (each character = 1 word).
        English words are counted using whitespace separation.

        Args:
            text: The text to analyze

        Returns:
            Total word count (Chinese characters + English words)
        """
        if not text or not text.strip():
            return 0

        import re

        # Count Chinese characters (including CJK Unified Ideographs and Extension blocks)
        chinese_pattern = r'[\u4e00-\u9fff\u3400-\u4dbf\U00020000-\U0002a6df\U0002a700-\U0002b73f\U0002b740-\U0002b81f\U0002b820-\U0002ceaf]'
        chinese_chars = len(re.findall(chinese_pattern, text))

        # Count English words (ASCII letters sequences)
        # Remove Chinese text first to avoid double-counting
        english_text = re.sub(chinese_pattern, '', text)
        english_words = len(re.findall(r'\b[a-zA-Z]+\b', english_text))

        total_words = chinese_chars + english_words
        logger.debug(f"Word count: {total_words} (Chinese: {chinese_chars}, English: {english_words})")
        return total_words
