import uuid
import difflib
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class ChapterVersionService:

    def __init__(self, db, chapter_repository):
        self.db = db
        self.chapter_repository = chapter_repository

    def list_versions(self, novel_id: str, chapter_number: int) -> List[Dict[str, Any]]:
        sql = """
            SELECT id, chapter_id, novel_id, chapter_number, summary, created_at
            FROM chapter_versions
            WHERE novel_id = ? AND chapter_number = ?
            ORDER BY created_at DESC
        """
        rows = self.db.fetch_all(sql, (novel_id, chapter_number))
        return [dict(row) for row in rows]

    def get_version(self, version_id: str) -> Optional[Dict[str, Any]]:
        sql = "SELECT * FROM chapter_versions WHERE id = ?"
        row = self.db.fetch_one(sql, (version_id,))
        return dict(row) if row else None

    def create_version(
        self,
        novel_id: str,
        chapter_number: int,
        content: str,
        summary: str = "",
    ) -> str:
        from domain.novel.value_objects.novel_id import NovelId

        chapter = self.chapter_repository.get_by_novel_and_number(
            NovelId(novel_id), chapter_number
        )
        if not chapter:
            raise ValueError(f"Chapter not found: {novel_id}/{chapter_number}")

        chapter_id = chapter.id.value if hasattr(chapter.id, "value") else chapter.id
        version_id = str(uuid.uuid4())
        sql = """
            INSERT INTO chapter_versions (id, chapter_id, novel_id, chapter_number, content, summary, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        self.db.execute(
            sql,
            (
                version_id,
                chapter_id,
                novel_id,
                chapter_number,
                content,
                summary,
                datetime.utcnow().isoformat(),
            ),
        )
        self.db.get_connection().commit()
        logger.info(
            "[ChapterVersion] created version %s for %s/%s",
            version_id,
            novel_id,
            chapter_number,
        )
        return version_id

    def diff_versions(
        self, novel_id: str, chapter_number: int, v1_id: str, v2_id: str
    ) -> Dict[str, Any]:
        v1 = self.get_version(v1_id)
        v2 = self.get_version(v2_id)
        if not v1:
            raise ValueError(f"Version not found: {v1_id}")
        if not v2:
            raise ValueError(f"Version not found: {v2_id}")
        if v1["novel_id"] != novel_id or v2["novel_id"] != novel_id:
            raise ValueError("Version does not belong to the specified novel")
        if v1["chapter_number"] != chapter_number or v2["chapter_number"] != chapter_number:
            raise ValueError("Version does not belong to the specified chapter")

        lines1 = v1["content"].splitlines(keepends=True)
        lines2 = v2["content"].splitlines(keepends=True)

        additions = []
        deletions = []
        for diff in difflib.unified_diff(lines1, lines2, lineterm=""):
            if diff.startswith("+") and not diff.startswith("+++"):
                additions.append(diff[1:])
            elif diff.startswith("-") and not diff.startswith("---"):
                deletions.append(diff[1:])

        return {
            "v1_id": v1_id,
            "v2_id": v2_id,
            "additions": additions,
            "deletions": deletions,
        }

    def rollback_to_version(
        self, novel_id: str, chapter_number: int, version_id: str
    ) -> Dict[str, Any]:
        from domain.novel.value_objects.novel_id import NovelId

        version = self.get_version(version_id)
        if not version:
            raise ValueError(f"Version not found: {version_id}")
        if version["novel_id"] != novel_id:
            raise ValueError("Version does not belong to the specified novel")
        if version["chapter_number"] != chapter_number:
            raise ValueError("Version does not belong to the specified chapter")

        chapter = self.chapter_repository.get_by_novel_and_number(
            NovelId(novel_id), chapter_number
        )
        if not chapter:
            raise ValueError(f"Chapter not found: {novel_id}/{chapter_number}")

        current_content = chapter.content
        snapshot_version_id = self.create_version(
            novel_id,
            chapter_number,
            current_content,
            summary="回滚前自动快照",
        )

        chapter.update_content(version["content"])
        self.chapter_repository.save(chapter)

        logger.info(
            "[ChapterVersion] rolled back %s/%s to version %s (snapshot %s)",
            novel_id,
            chapter_number,
            version_id,
            snapshot_version_id,
        )

        return {
            "snapshot_version_id": snapshot_version_id,
            "restored_version_id": version_id,
        }
