"""SQLite-based statistics repository adapter.

This adapter reads statistics data from the SQLite database instead of
the legacy file-based storage system.
"""
from pathlib import Path
from typing import Optional, Dict, List
import logging
import re

from infrastructure.persistence.database.connection import DatabaseConnection

logger = logging.getLogger(__name__)


def _public_stage_from_row(row: Dict) -> str:
    """数据库 current_stage -> 兼容旧统计接口 stage。"""
    current_stage = row.get("current_stage") or "planning"
    explicit_stage = row.get("stage")

    if explicit_stage and explicit_stage != "planning" and current_stage == "planning":
        return explicit_stage

    stage_map = {
        "planning": "planning",
        "macro_planning": "planning",
        "act_planning": "planning",
        "writing": "writing",
        "auditing": "reviewing",
        "reviewing": "reviewing",
        "paused_for_review": "reviewing",
        "completed": "completed",
    }
    return stage_map.get(current_stage, explicit_stage or "planning")


class SqliteStatsRepositoryAdapter:
    """Adapter to read statistics from SQLite database.

    This adapter:
    1. Reads from the novels and chapters tables in SQLite
    2. Provides the same interface as StatsRepositoryAdapter
    3. Calculates statistics on-the-fly from database data
    """

    def __init__(self, db: DatabaseConnection):
        """Initialize the adapter with database connection.

        Args:
            db: DatabaseConnection instance
        """
        self.db = db
        logger.info("SqliteStatsRepositoryAdapter initialized")

    def get_all_book_slugs(self) -> List[str]:
        """Get all book slugs (novel IDs) from database.

        Returns:
            List of novel IDs that can be used as slugs
        """
        try:
            sql = "SELECT id FROM novels ORDER BY created_at DESC"
            rows = self.db.fetch_all(sql)
            slugs = [row['id'] for row in rows]
            logger.info(f"Found {len(slugs)} novels in database")
            return slugs
        except Exception as e:
            logger.error(f"Error fetching novel slugs: {e}")
            return []

    def get_book_manifest(self, slug: str) -> Optional[Dict]:
        """Read a novel's data from database and convert to manifest format.

        Args:
            slug: The novel's ID (used as slug)

        Returns:
            Dictionary in manifest format, or None if not found/error
        """
        try:
            sql = "SELECT * FROM novels WHERE id = ? OR slug = ?"
            row = self.db.fetch_one(sql, (slug, slug))

            if not row:
                logger.warning(f"Novel not found: {slug}")
                return None

            # Convert database row to legacy manifest format
            manifest = {
                "title": row.get("title", ""),
                "author": row.get("author", "未知作者"),
                "slug": slug,
                "stage": _public_stage_from_row(row),
                "target_chapters": row.get("target_chapters", 0),
            }

            logger.debug(f"Successfully read manifest for novel: {slug}")
            return manifest
        except Exception as e:
            logger.error(f"Error reading novel {slug}: {e}")
            return None

    def get_book_outline(self, slug: str) -> Optional[Dict]:
        """Get chapter list from database in outline format.

        Args:
            slug: The novel's ID (used as slug)

        Returns:
            {"chapters": [{"id": int, "title": str}, ...]} or None
        """
        try:
            # First verify the novel exists
            manifest = self.get_book_manifest(slug)
            if not manifest:
                return None

            # Get chapters for this novel
            sql = """
                SELECT number, title
                FROM chapters
                WHERE novel_id = ?
                ORDER BY number ASC
            """
            rows = self.db.fetch_all(sql, (slug,))

            outline_chapters = []
            for row in rows:
                outline_chapters.append({
                    "id": row["number"],
                    "title": row.get("title", "").strip(),
                })

            return {"chapters": outline_chapters}
        except Exception as e:
            logger.error(f"Error reading outline for novel {slug}: {e}")
            return None

    def get_chapter_content(self, slug: str, chapter_id: int) -> Optional[str]:
        """Read a chapter's content from the database.

        Args:
            slug: The novel's ID (used as slug)
            chapter_id: The chapter's numeric ID (>= 1)

        Returns:
            String containing chapter content, or None if not found/error
        """
        try:
            sql = """
                SELECT content
                FROM chapters
                WHERE novel_id = ? AND number = ?
            """
            row = self.db.fetch_one(sql, (slug, chapter_id))

            if not row:
                logger.warning(f"Chapter {chapter_id} not found in novel {slug}")
                return None

            content = row.get("content", "")
            if isinstance(content, str):
                logger.debug(f"Successfully read chapter {chapter_id} for novel: {slug}")
                return content

            return None
        except Exception as e:
            logger.error(f"Error reading chapter {chapter_id} for novel {slug}: {e}")
            return None

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
