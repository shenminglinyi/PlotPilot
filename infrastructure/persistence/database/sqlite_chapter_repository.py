"""SQLite Chapter Repository 实现"""
import logging
import sqlite3
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

    # 删除章节后重排序号：先加偏移避免 UNIQUE(novel_id, number) 冲突，再整体减回
    _RENUMBER_OFFSET = 1_000_000

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
        """删除章节：单写者内核下 API 线程只入队，由持久化消费者在 writer 上执行。"""
        from infrastructure.persistence.database.write_dispatch import (
            allow_direct_sqlite_writes,
            enqueue_delete_chapter,
            is_sqlite_writer_thread,
        )

        if allow_direct_sqlite_writes() or is_sqlite_writer_thread():
            self.execute_delete_on_writer(chapter_id)
            return

        chapter = self.get_by_id(chapter_id)
        if not chapter:
            logger.warning(f"Chapter not found for deletion: {chapter_id.value}")
            return

        cid = chapter_id.value
        if enqueue_delete_chapter(cid):
            logger.info(
                "章节删除已入队 %s novel=%s number=%s",
                cid,
                chapter.novel_id.value
                if hasattr(chapter.novel_id, "value")
                else chapter.novel_id,
                chapter.number,
            )
            return

        raise RuntimeError("持久化队列未就绪，章节删除未能入队")

    def execute_delete_on_writer(self, chapter_id: ChapterId) -> None:
        """仅在持久化消费者线程或直接写库模式下调用；保持原事务体（含 FK 切换与容错 DELETE）。"""
        chapter = self.get_by_id(chapter_id)
        if not chapter:
            logger.warning(f"Chapter not found for deletion (writer): {chapter_id.value}")
            return

        novel_id = chapter.novel_id.value if hasattr(chapter.novel_id, 'value') else chapter.novel_id
        deleted_number = chapter.number
        cid = chapter_id.value
        now = datetime.utcnow().isoformat()

        with self.db.transaction() as conn:
            conn.execute("PRAGMA foreign_keys = OFF")
            try:
                self._delete_chapter_transaction_body(
                    conn, novel_id, deleted_number, cid, now
                )
            finally:
                conn.execute("PRAGMA foreign_keys = ON")

        logger.info(
            "Deleted chapter %s novel=%s deleted_number=%s (renumber cascade applied)",
            cid,
            novel_id,
            deleted_number,
        )

    def _delete_chapter_transaction_body(
        self,
        conn: sqlite3.Connection,
        novel_id: str,
        deleted_number: int,
        chapter_row_id: str,
        now_iso: str,
    ) -> None:
        d = deleted_number
        off = self._RENUMBER_OFFSET

        conn.execute(
            """
            UPDATE triples
            SET chapter_number = NULL, updated_at = ?
            WHERE novel_id = ? AND chapter_number = ?
            """,
            (now_iso, novel_id, d),
        )
        conn.execute(
            "DELETE FROM triple_more_chapters WHERE novel_id = ? AND chapter_number = ?",
            (novel_id, d),
        )

        try:
            conn.execute(
                "DELETE FROM beat_sheets WHERE chapter_id = ?",
                (chapter_row_id,),
            )
        except sqlite3.OperationalError:
            pass

        try:
            conn.execute(
                "DELETE FROM chapter_scenes WHERE chapter_id = ?",
                (chapter_row_id,),
            )
        except sqlite3.OperationalError:
            pass

        try:
            conn.execute(
                "DELETE FROM chapter_elements WHERE chapter_id = ?",
                (chapter_row_id,),
            )
        except sqlite3.OperationalError:
            pass

        conn.execute(
            "DELETE FROM chapter_style_scores WHERE novel_id = ? AND chapter_number = ?",
            (novel_id, d),
        )
        conn.execute(
            "DELETE FROM narrative_events WHERE novel_id = ? AND chapter_number = ?",
            (novel_id, d),
        )
        conn.execute(
            "DELETE FROM voice_vault WHERE novel_id = ? AND chapter_number = ?",
            (novel_id, d),
        )
        conn.execute(
            """
            DELETE FROM chapter_summaries
            WHERE knowledge_id IN (SELECT id FROM knowledge WHERE novel_id = ?)
              AND chapter_number = ?
            """,
            (novel_id, d),
        )
        conn.execute(
            """
            DELETE FROM plot_points
            WHERE chapter_number = ?
              AND plot_arc_id IN (SELECT id FROM plot_arcs WHERE novel_id = ?)
            """,
            (d, novel_id),
        )
        conn.execute(
            """
            DELETE FROM chapter_reviews
            WHERE novel_id = ? AND chapter_number = ?
            """,
            (novel_id, d),
        )
        conn.execute(
            """
            DELETE FROM story_nodes
            WHERE novel_id = ? AND node_type = 'chapter' AND number = ?
            """,
            (novel_id, d),
        )

        conn.execute("DELETE FROM chapters WHERE id = ?", (chapter_row_id,))

        cur = conn.execute(
            """
            SELECT 1 FROM chapters
            WHERE novel_id = ? AND number > ?
            LIMIT 1
            """,
            (novel_id, d),
        )
        needs_shift = cur.fetchone() is not None

        if needs_shift:
            bump = off
            sub = off + 1
            threshold_after_bump = off + d

            conn.execute(
                """
                UPDATE chapters
                SET number = number + ?, updated_at = ?
                WHERE novel_id = ? AND number > ?
                """,
                (bump, now_iso, novel_id, d),
            )
            conn.execute(
                """
                UPDATE triples
                SET chapter_number = chapter_number + ?, updated_at = ?
                WHERE novel_id = ? AND chapter_number IS NOT NULL AND chapter_number > ?
                """,
                (bump, now_iso, novel_id, d),
            )
            conn.execute(
                """
                UPDATE triple_more_chapters
                SET chapter_number = chapter_number + ?
                WHERE novel_id = ? AND chapter_number > ?
                """,
                (bump, novel_id, d),
            )
            conn.execute(
                """
                UPDATE chapter_reviews
                SET chapter_number = chapter_number + ?, updated_at = ?
                WHERE novel_id = ? AND chapter_number > ?
                """,
                (bump, now_iso, novel_id, d),
            )
            conn.execute(
                """
                UPDATE chapter_style_scores
                SET chapter_number = chapter_number + ?
                WHERE novel_id = ? AND chapter_number > ?
                """,
                (bump, novel_id, d),
            )
            conn.execute(
                """
                UPDATE narrative_events
                SET chapter_number = chapter_number + ?
                WHERE novel_id = ? AND chapter_number > ?
                """,
                (bump, novel_id, d),
            )
            conn.execute(
                """
                UPDATE voice_vault
                SET chapter_number = chapter_number + ?
                WHERE novel_id = ? AND chapter_number > ?
                """,
                (bump, novel_id, d),
            )
            conn.execute(
                """
                UPDATE chapter_summaries
                SET chapter_number = chapter_number + ?, updated_at = ?
                WHERE knowledge_id IN (SELECT id FROM knowledge WHERE novel_id = ?)
                  AND chapter_number > ?
                """,
                (bump, now_iso, novel_id, d),
            )
            conn.execute(
                """
                UPDATE plot_points
                SET chapter_number = chapter_number + ?
                WHERE plot_arc_id IN (SELECT id FROM plot_arcs WHERE novel_id = ?)
                  AND chapter_number > ?
                """,
                (bump, novel_id, d),
            )
            conn.execute(
                """
                UPDATE story_nodes
                SET number = number + ?, updated_at = ?
                WHERE novel_id = ? AND node_type = 'chapter' AND number > ?
                """,
                (bump, now_iso, novel_id, d),
            )

            conn.execute(
                """
                UPDATE chapters
                SET number = number - ?, updated_at = ?
                WHERE novel_id = ? AND number > ?
                """,
                (sub, now_iso, novel_id, threshold_after_bump),
            )
            conn.execute(
                """
                UPDATE triples
                SET chapter_number = chapter_number - ?, updated_at = ?
                WHERE novel_id = ? AND chapter_number IS NOT NULL AND chapter_number > ?
                """,
                (sub, now_iso, novel_id, threshold_after_bump),
            )
            conn.execute(
                """
                UPDATE triple_more_chapters
                SET chapter_number = chapter_number - ?
                WHERE novel_id = ? AND chapter_number > ?
                """,
                (sub, novel_id, threshold_after_bump),
            )
            conn.execute(
                """
                UPDATE chapter_reviews
                SET chapter_number = chapter_number - ?, updated_at = ?
                WHERE novel_id = ? AND chapter_number > ?
                """,
                (sub, now_iso, novel_id, threshold_after_bump),
            )
            conn.execute(
                """
                UPDATE chapter_style_scores
                SET chapter_number = chapter_number - ?
                WHERE novel_id = ? AND chapter_number > ?
                """,
                (sub, novel_id, threshold_after_bump),
            )
            conn.execute(
                """
                UPDATE narrative_events
                SET chapter_number = chapter_number - ?
                WHERE novel_id = ? AND chapter_number > ?
                """,
                (sub, novel_id, threshold_after_bump),
            )
            conn.execute(
                """
                UPDATE voice_vault
                SET chapter_number = chapter_number - ?
                WHERE novel_id = ? AND chapter_number > ?
                """,
                (sub, novel_id, threshold_after_bump),
            )
            conn.execute(
                """
                UPDATE chapter_summaries
                SET chapter_number = chapter_number - ?, updated_at = ?
                WHERE knowledge_id IN (SELECT id FROM knowledge WHERE novel_id = ?)
                  AND chapter_number > ?
                """,
                (sub, now_iso, novel_id, threshold_after_bump),
            )
            conn.execute(
                """
                UPDATE plot_points
                SET chapter_number = chapter_number - ?
                WHERE plot_arc_id IN (SELECT id FROM plot_arcs WHERE novel_id = ?)
                  AND chapter_number > ?
                """,
                (sub, novel_id, threshold_after_bump),
            )
            conn.execute(
                """
                UPDATE story_nodes
                SET number = number - ?, updated_at = ?
                WHERE novel_id = ? AND node_type = 'chapter' AND number > ?
                """,
                (sub, now_iso, novel_id, threshold_after_bump),
            )

            conn.execute(
                """
                UPDATE chapter_summaries
                SET id = knowledge_id || '-ch' || CAST(chapter_number AS TEXT), updated_at = ?
                WHERE knowledge_id IN (SELECT id FROM knowledge WHERE novel_id = ?)
                """,
                (now_iso, novel_id),
            )
            conn.execute(
                """
                UPDATE plot_points
                SET id = plot_arc_id || '-p-' || CAST(chapter_number AS TEXT)
                WHERE plot_arc_id IN (SELECT id FROM plot_arcs WHERE novel_id = ?)
                """,
                (novel_id,),
            )

        conn.execute(
            """
            UPDATE triples
            SET first_appearance = CASE
                WHEN first_appearance > ? THEN first_appearance - 1
                WHEN first_appearance = ? THEN MAX(1, ? - 1)
                ELSE first_appearance END,
                updated_at = ?
            WHERE novel_id = ? AND first_appearance IS NOT NULL
            """,
            (d, d, d, now_iso, novel_id),
        )

        self._adjust_planning_bounds_after_delete(conn, novel_id, d, now_iso)

        try:
            conn.execute(
                """
                UPDATE memory_engine_state
                SET last_updated_chapter = CASE
                    WHEN last_updated_chapter > ? THEN last_updated_chapter - 1
                    WHEN last_updated_chapter = ? THEN MAX(0, ? - 1)
                    ELSE last_updated_chapter END,
                    updated_at = ?
                WHERE novel_id = ?
                """,
                (d, d, d, now_iso, novel_id),
            )
        except sqlite3.OperationalError:
            pass

        self._recompute_act_chapter_bounds(conn, novel_id, now_iso)

    def _adjust_planning_bounds_after_delete(
        self,
        conn: sqlite3.Connection,
        novel_id: str,
        d: int,
        now_iso: str,
    ) -> None:
        conn.execute(
            """
            UPDATE storylines
            SET estimated_chapter_start = CASE
                    WHEN estimated_chapter_start > ? THEN estimated_chapter_start - 1
                    WHEN estimated_chapter_start = ? THEN MAX(1, ? - 1)
                    ELSE estimated_chapter_start END,
                estimated_chapter_end = CASE
                    WHEN estimated_chapter_end > ? THEN estimated_chapter_end - 1
                    WHEN estimated_chapter_end = ? THEN MAX(1, ? - 1)
                    ELSE estimated_chapter_end END,
                updated_at = ?
            WHERE novel_id = ?
            """,
            (d, d, d, d, d, d, now_iso, novel_id),
        )
        conn.execute(
            """
            UPDATE storyline_milestones
            SET target_chapter_start = CASE
                    WHEN target_chapter_start > ? THEN target_chapter_start - 1
                    WHEN target_chapter_start = ? THEN MAX(1, ? - 1)
                    ELSE target_chapter_start END,
                target_chapter_end = CASE
                    WHEN target_chapter_end > ? THEN target_chapter_end - 1
                    WHEN target_chapter_end = ? THEN MAX(1, ? - 1)
                    ELSE target_chapter_end END
            WHERE storyline_id IN (SELECT id FROM storylines WHERE novel_id = ?)
            """,
            (d, d, d, d, d, d, novel_id),
        )
        conn.execute(
            """
            UPDATE novels
            SET last_audit_chapter_number = CASE
                    WHEN last_audit_chapter_number IS NULL THEN NULL
                    WHEN last_audit_chapter_number > ? THEN last_audit_chapter_number - 1
                    WHEN last_audit_chapter_number = ? THEN MAX(1, ? - 1)
                    ELSE last_audit_chapter_number END,
                current_chapter_in_act = CASE
                    WHEN current_chapter_in_act > ? THEN current_chapter_in_act - 1
                    WHEN current_chapter_in_act = ? THEN MAX(1, ? - 1)
                    ELSE current_chapter_in_act END,
                current_auto_chapters = CASE
                    WHEN current_auto_chapters > 0 THEN current_auto_chapters - 1
                    ELSE 0 END,
                updated_at = ?
            WHERE id = ?
            """,
            (d, d, d, d, d, d, now_iso, novel_id),
        )

    def _recompute_act_chapter_bounds(
        self,
        conn: sqlite3.Connection,
        novel_id: str,
        now_iso: str,
    ) -> None:
        act_rows = conn.execute(
            """
            SELECT id FROM story_nodes
            WHERE novel_id = ? AND node_type = 'act'
            """,
            (novel_id,),
        ).fetchall()
        for act_row in act_rows:
            act_id = act_row["id"]
            nums = conn.execute(
                """
                SELECT number FROM story_nodes
                WHERE parent_id = ? AND node_type = 'chapter'
                ORDER BY number ASC
                """,
                (act_id,),
            ).fetchall()
            if not nums:
                conn.execute(
                    """
                    UPDATE story_nodes
                    SET chapter_start = NULL, chapter_end = NULL, chapter_count = 0,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (now_iso, act_id),
                )
                continue
            nlist = [int(r["number"]) for r in nums]
            conn.execute(
                """
                UPDATE story_nodes
                SET chapter_start = ?, chapter_end = ?, chapter_count = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (min(nlist), max(nlist), len(nlist), now_iso, act_id),
            )

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
