"""Statistics repository adapter for new DDD architecture.

This adapter bridges the gap between the legacy stats API (which expects
manifest.json files and slug-based identifiers) and the new DDD architecture
(which uses JSON files with UUID-based identifiers).
"""
from pathlib import Path
from typing import Optional, Dict, List
import json
import logging

logger = logging.getLogger(__name__)


class StatsRepositoryAdapter:
    """Adapter to make new architecture data compatible with stats API.

    This adapter:
    1. Reads from data/novels/*.json instead of data/{slug}/manifest.json
    2. Converts novel-id to slug for API compatibility
    3. Extracts chapter data from the novel JSON structure
    """

    def __init__(self, data_root: Path):
        """Initialize the adapter with data root path.

        Args:
            data_root: Path to the data directory (contains novels/ and bibles/)
        """
        self.data_root = Path(data_root)
        self.novels_dir = self.data_root / "novels"
        logger.info(f"StatsRepositoryAdapter initialized with data_root: {self.data_root}")

    def get_all_book_slugs(self) -> List[str]:
        """Get all book slugs (novel IDs) by scanning novels directory.

        Returns:
            List of novel IDs that can be used as slugs
        """
        slugs = []
        try:
            if not self.novels_dir.exists():
                logger.warning(f"Novels directory does not exist: {self.novels_dir}")
                return slugs

            for novel_file in self.novels_dir.glob("*.json"):
                # Use the filename (without .json) as the slug
                slug = novel_file.stem
                slugs.append(slug)
            logger.info(f"Found {len(slugs)} novels: {slugs}")
        except Exception as e:
            logger.error(f"Error scanning novels directory: {e}")
        return slugs

    def get_book_manifest(self, slug: str) -> Optional[Dict]:
        """Read a novel's data and convert to manifest format.

        Args:
            slug: The novel's ID (used as slug)

        Returns:
            Dictionary in manifest format, or None if not found/error
        """
        try:
            novel_path = self.novels_dir / f"{slug}.json"
            if not novel_path.exists():
                logger.warning(f"Novel not found: {slug}")
                return None

            with open(novel_path, 'r', encoding='utf-8') as f:
                novel_data = json.load(f)

            # Convert new format to legacy manifest format
            manifest = {
                "title": novel_data.get("title", ""),
                "author": novel_data.get("author", ""),
                "slug": slug,
                "stage": novel_data.get("stage", "planning"),
                "target_chapters": novel_data.get("target_chapters", 0),
                "chapters": novel_data.get("chapters", [])
            }

            logger.debug(f"Successfully read manifest for novel: {slug}")
            return manifest
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in novel file {slug}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error reading novel {slug}: {e}")
            return None

    def get_book_outline(self, slug: str) -> Optional[Dict]:
        """Expose chapter list in the shape expected by StatsService.

        New architecture stores chapters inside ``novels/{slug}.json``; there is no
        separate outline.json. We map ``chapters[].number`` to outline ``id`` so
        :meth:`get_chapter_content` and stats aggregation stay aligned.

        Args:
            slug: The novel's ID (used as slug)

        Returns:
            ``{"chapters": [{"id": int, "title": str}, ...]}`` or None
        """
        manifest = self.get_book_manifest(slug)
        if not manifest:
            return None
        raw = manifest.get("chapters") or []
        outline_chapters = []
        for ch in raw:
            num = ch.get("number")
            if num is None:
                continue
            try:
                chapter_num = int(num)
            except (TypeError, ValueError):
                continue
            outline_chapters.append({
                "id": chapter_num,
                "title": (ch.get("title") or "").strip(),
            })
        if not outline_chapters:
            outline_chapters = self._outline_chapters_from_disk(slug)
        return {"chapters": outline_chapters}

    def _outline_chapters_from_disk(self, slug: str) -> List[Dict]:
        """当 novel 聚合里 chapters 为空时，从 ``novels/{slug}/chapters/*.json`` 扫描章列表。

        与 :class:`FileChapterRepository` 落盘路径一致，避免统计 API 与 v1 章节 API 脱节。
        """
        ch_dir = self.novels_dir / slug / "chapters"
        if not ch_dir.is_dir():
            return []
        out: List[Dict] = []
        for p in sorted(ch_dir.glob("*.json")):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                num = data.get("number")
                if num is None:
                    continue
                chapter_num = int(num)
                out.append(
                    {
                        "id": chapter_num,
                        "title": (data.get("title") or "").strip(),
                    }
                )
            except (json.JSONDecodeError, TypeError, ValueError) as e:
                logger.warning(f"Skip chapter file {p}: {e}")
        out.sort(key=lambda x: x["id"])
        return out

    def _chapter_content_from_disk(self, slug: str, chapter_id: int) -> Optional[str]:
        """按章节号从 ``novels/{slug}/chapters/*.json`` 读取正文。"""
        data = self._chapter_data_from_disk(slug, chapter_id)
        if data is None:
            return None
        raw = data.get("content")
        return raw if isinstance(raw, str) else None

    def _chapter_data_from_disk(self, slug: str, chapter_id: int) -> Optional[Dict]:
        """按章节号从 ``novels/{slug}/chapters/*.json`` 读取章节 JSON。"""
        ch_dir = self.novels_dir / slug / "chapters"
        if not ch_dir.is_dir():
            return None
        for p in ch_dir.glob("*.json"):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                num = data.get("number")
                if num is None:
                    continue
                if int(num) != chapter_id:
                    continue
                try:
                    data["_file_mtime"] = p.stat().st_mtime
                except OSError:
                    pass
                return data
            except (json.JSONDecodeError, TypeError, ValueError) as e:
                logger.warning(f"Skip chapter file {p}: {e}")
        return None

    @staticmethod
    def _chapter_number_equals(ch: Dict, chapter_id: int) -> bool:
        n = ch.get("number")
        if n is None:
            return False
        try:
            return int(n) == chapter_id
        except (TypeError, ValueError):
            return False

    def get_chapter_content(self, slug: str, chapter_id: int) -> Optional[str]:
        """Read a chapter's content from the novel data.

        Args:
            slug: The novel's ID (used as slug)
            chapter_id: The chapter's numeric ID (>= 1)

        Returns:
            String containing chapter content, or None if not found/error
        """
        try:
            manifest = self.get_book_manifest(slug)
            if not manifest:
                return None

            chapters = manifest.get("chapters", [])

            for chapter in chapters:
                if not self._chapter_number_equals(chapter, chapter_id):
                    continue
                content = chapter.get("content", "")
                if isinstance(content, str) and content.strip():
                    logger.debug(f"Successfully read chapter {chapter_id} for novel: {slug}")
                    return content
                disk = self._chapter_content_from_disk(slug, chapter_id)
                if disk is not None:
                    return disk
                return content if isinstance(content, str) else None

            disk_only = self._chapter_content_from_disk(slug, chapter_id)
            if disk_only is not None:
                return disk_only

            logger.warning(f"Chapter {chapter_id} not found in novel {slug}")
            return None
        except Exception as e:
            logger.error(f"Error reading chapter {chapter_id} for novel {slug}: {e}")
            return None

    def get_chapter_progress_records(self, slug: str) -> List[Dict]:
        """Return chapter content and write timestamps from novel aggregate or chapter files."""
        try:
            manifest = self.get_book_manifest(slug)
            if not manifest:
                return []
            outline = self.get_book_outline(slug) or {"chapters": []}
            manifest_chapters = manifest.get("chapters", []) or []
            records: List[Dict] = []
            for item in outline.get("chapters", []):
                try:
                    chapter_num = int(item.get("id"))
                except (TypeError, ValueError):
                    continue
                aggregate = next((ch for ch in manifest_chapters if self._chapter_number_equals(ch, chapter_num)), None)
                disk_data = self._chapter_data_from_disk(slug, chapter_num) or {}
                source = disk_data or aggregate or {}
                content = source.get("content")
                if not isinstance(content, str):
                    continue
                written_at = (
                    source.get("updated_at")
                    or source.get("created_at")
                    or source.get("completed_at")
                    or source.get("_file_mtime")
                )
                records.append(
                    {
                        "chapter_id": chapter_num,
                        "title": item.get("title", ""),
                        "content": content,
                        "written_at": written_at,
                    }
                )
            return records
        except Exception as e:
            logger.error(f"Error building progress records for novel {slug}: {e}")
            return []

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
