"""
故事结构节点 Repository
"""

import sqlite3
import json
import logging
from contextlib import closing, contextmanager, nullcontext
from hashlib import sha256
from pathlib import Path
from typing import Callable, List, Optional, Union
from datetime import datetime

logger = logging.getLogger(__name__)

from domain.structure.story_node import StoryNode, NodeType, StoryTree, PlanningStatus, PlanningSource


class StoryNodeRepository:
    """故事结构节点仓储

    改进：接受 DatabaseConnection 实例，复用线程本地连接（WAL 模式 + busy_timeout），
    避免每个方法 connect→close 短连接模式。
    向后兼容：仍接受 db_path 字符串（与 `get_database(db_path)` 共用线程本地连接）。
    """

    def __init__(self, db: Union[str, "DatabaseConnection"]):
        # 延迟导入避免循环引用
        from infrastructure.persistence.database.connection import DatabaseConnection

        if isinstance(db, DatabaseConnection):
            self._db = db
            self.db_path = db.db_path
        elif isinstance(db, str):
            self._db = None
            self.db_path = db
        else:
            self._db = None
            self.db_path = str(db)

    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接（优先复用 DatabaseConnection 线程本地连接）。"""
        if self._db is not None:
            return self._db.get_connection()
        from infrastructure.persistence.database.connection import get_database

        return get_database(self.db_path).get_connection()

    def _should_close_after_use(self) -> bool:
        """不再在方法末尾 close：db_path 模式也走全局 DatabaseConnection，避免误关线程本地连接。"""
        return False

    @contextmanager
    def claim_act_planning(self, novel_id: str):
        """Reserve model work across processes without locking the manuscript database."""
        from domain.structure.narrative_progress import NarrativeProgressError

        directory = Path(self.db_path).resolve().parent / 'planning-locks'
        directory.mkdir(exist_ok=True)
        key = sha256((str(Path(self.db_path).resolve()) + '\0' + novel_id).encode()).hexdigest()
        # SQLite releases the OS lock even if the process exits during generation.
        with closing(sqlite3.connect(directory / (key + '.db'), timeout=0)) as lock:
            try:
                lock.execute('BEGIN IMMEDIATE')
            except sqlite3.OperationalError as exc:
                if exc.sqlite_errorcode in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
                    raise NarrativeProgressError('本书正在生成下一幕，请稍后重试') from exc
                raise
            yield

    def save_sync(self, node: StoryNode, *, validate: Optional[Callable[[], None]] = None) -> StoryNode:
        """同步保存（供 NovelService 等非 async 调用链使用）。"""
        conn = self._get_connection()
        try:
            if validate:
                conn.execute("BEGIN IMMEDIATE")
                validate()
            self._insert_node(conn, node)
            conn.commit()
            return node
        except Exception:
            conn.rollback()
            raise
        finally:
            if self._should_close_after_use():
                conn.close()

    @staticmethod
    def _insert_node(conn, node):
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO story_nodes (
                id, novel_id, parent_id, node_type, number, title, description, order_index,
                planning_status, planning_source,
                chapter_start, chapter_end, chapter_count, suggested_chapter_count,
                content, outline, word_count, status,
                themes, key_events, narrative_arc, conflicts,
                pov_character_id, timeline_start, timeline_end,
                metadata, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            node.id,
            node.novel_id,
            node.parent_id,
            node.node_type.value,
            node.number,
            node.title,
            node.description,
            node.order_index,
            node.planning_status.value,
            node.planning_source.value,
            node.chapter_start,
            node.chapter_end,
            node.chapter_count,
            node.suggested_chapter_count,
            node.content,
            node.outline,
            node.word_count,
            node.status,
            json.dumps(node.themes),
            json.dumps(node.key_events),
            node.narrative_arc,
            json.dumps(node.conflicts),
            node.pov_character_id,
            node.timeline_start,
            node.timeline_end,
            json.dumps(node.metadata),
            node.created_at.isoformat(),
            node.updated_at.isoformat(),
        ))

    def ensure_act_has_no_manuscript(self, act_id: str) -> None:
        from domain.structure.narrative_progress import NarrativeProgressError

        row = self._get_connection().execute("""
            SELECT n.number FROM story_nodes n LEFT JOIN chapters c ON c.novel_id=n.novel_id AND c.number=n.number
             WHERE n.parent_id=? AND n.node_type='chapter'
               AND (length(coalesce(c.content,''))>0 OR length(coalesce(n.content,''))>0)
             ORDER BY n.number LIMIT 1
        """, (act_id,)).fetchone()
        if row:
            raise NarrativeProgressError(f"本幕第{row[0]}章已有正文，整幕替换已停止。请在章节编辑器中调整现有章节的大纲。")

    def commit_act_chapters(self, act_id, nodes, elements, validate):
        """Replace only unfilled plans in this act, under a checked transaction."""
        conn = self._get_connection()
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            validate()
            conn.execute("""DELETE FROM chapters WHERE novel_id=? AND number IN
                            (SELECT number FROM story_nodes WHERE parent_id=? AND node_type='chapter')""",
                         (nodes[0].novel_id, act_id))
            conn.execute("DELETE FROM story_nodes WHERE parent_id=? AND node_type='chapter'", (act_id,))
            previous = conn.execute("""SELECT number FROM chapters WHERE novel_id=?
                       AND number BETWEEN ? AND ? ORDER BY number LIMIT 1""",
                       (nodes[0].novel_id, nodes[0].number, nodes[-1].number)).fetchone()
            if previous:
                from domain.structure.narrative_progress import NarrativeProgressError
                raise NarrativeProgressError(f"第{previous[0]}章已有书稿记录，请先核对目录和书稿")
            for node in nodes:
                self._insert_node(conn, node)
                conn.execute("""
                    INSERT INTO chapters(id, novel_id, number, title, content, outline, status)
                    VALUES (?, ?, ?, ?, '', ?, 'draft')
                """, (node.id, node.novel_id, node.number, node.title, node.outline))
            conn.executemany("""
                INSERT INTO chapter_elements(id, chapter_id, element_type, element_id, relation_type,
                        importance, appearance_order, notes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [(e.id, e.chapter_id, e.element_type.value, e.element_id, e.relation_type.value,
                   e.importance.value, e.appearance_order, e.notes, e.created_at.isoformat()) for e in elements])
            conn.execute("""
                UPDATE story_nodes SET chapter_start=?, chapter_end=?, chapter_count=?, updated_at=CURRENT_TIMESTAMP
                WHERE id=?
            """, (nodes[0].number, nodes[-1].number, len(nodes), act_id))

    async def save(self, node: StoryNode) -> StoryNode:
        """保存节点"""
        return self.save_sync(node)

    async def commit_narrative_review(self, novel_id: str, volume_id: str, contract: dict, expected: str) -> None:
        """Store only this review, against the exact plan and manuscripts the author saw."""
        from domain.structure.narrative_progress import NarrativeProgressPolicy, NarrativeReviewConflict
        from domain.structure.writing_target import plan_revision
        from infrastructure.persistence.database.sqlite_chapter_repository import read_completed_revisions

        conn = self._get_connection()
        nested = conn.in_transaction
        with nullcontext() if nested else conn:
            if not nested:
                conn.execute('BEGIN IMMEDIATE')
            book = conn.execute('SELECT target_chapters FROM novels WHERE id=?', (novel_id,)).fetchone()
            refs = read_completed_revisions(conn.execute, novel_id)
            if not book or plan_revision(NarrativeProgressPolicy(self.get_plan_nodes_sync(novel_id), book[0], refs)) != expected:
                raise NarrativeReviewConflict('书稿或大纲已变化，请重新核读后再提交验收')
            conn.execute(
                """UPDATE story_nodes SET metadata=json_set(coalesce(metadata,'{}'),'$.narrative_progress',json(?)),
                          updated_at=CURRENT_TIMESTAMP WHERE novel_id=? AND id=? AND node_type='volume'""",
                (json.dumps(contract, ensure_ascii=False), novel_id, volume_id),
            )

    def update_node_details(self, novel_id: str, node_id: str, title, description, number) -> StoryNode:
        conn = self._get_connection()
        with conn:
            cursor = conn.execute(
                """UPDATE story_nodes SET title=COALESCE(?,title), description=COALESCE(?,description),
                       number=COALESCE(?,number),updated_at=CURRENT_TIMESTAMP
                   WHERE novel_id=? AND id=? RETURNING *""",
                (title, description, number, novel_id, node_id),
            )
            row = cursor.fetchone()
            cursor.close()
            if row is None:
                raise ValueError(f"Node not found: {node_id}")
            return self._row_to_entity(row)

    async def update(self, node: StoryNode) -> StoryNode:
        """更新节点"""
        node.updated_at = datetime.now()
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE story_nodes SET
                    parent_id = ?,
                    node_type = ?,
                    number = ?,
                    title = ?,
                    description = ?,
                    order_index = ?,
                    planning_status = ?,
                    planning_source = ?,
                    chapter_start = ?,
                    chapter_end = ?,
                    chapter_count = ?,
                    suggested_chapter_count = ?,
                    content = ?,
                    outline = ?,
                    word_count = ?,
                    status = ?,
                    themes = ?,
                    key_events = ?,
                    narrative_arc = ?,
                    conflicts = ?,
                    pov_character_id = ?,
                    timeline_start = ?,
                    timeline_end = ?,
                    metadata = ?,
                    updated_at = ?
                WHERE id = ?
            """, (
                node.parent_id,
                node.node_type.value,
                node.number,
                node.title,
                node.description,
                node.order_index,
                node.planning_status.value,
                node.planning_source.value,
                node.chapter_start,
                node.chapter_end,
                node.chapter_count,
                node.suggested_chapter_count,
                node.content,
                node.outline,
                node.word_count,
                node.status,
                json.dumps(node.themes),
                json.dumps(node.key_events),
                node.narrative_arc,
                json.dumps(node.conflicts),
                node.pov_character_id,
                node.timeline_start,
                node.timeline_end,
                json.dumps(node.metadata),
                node.updated_at.isoformat(),
                node.id,
            ))
            conn.commit()
            return node
        finally:
            if self._should_close_after_use():
                conn.close()

    async def save_batch(self, nodes: List[StoryNode]) -> List[StoryNode]:
        """批量保存节点"""
        if not nodes:
            return nodes
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            for node in nodes:
                try:
                    cursor.execute("""
                        INSERT OR REPLACE INTO story_nodes (
                            id, novel_id, parent_id, node_type, number, title, description, order_index,
                            planning_status, planning_source,
                            chapter_start, chapter_end, chapter_count, suggested_chapter_count,
                            content, outline, word_count, status,
                            themes, key_events, narrative_arc, conflicts,
                            pov_character_id, timeline_start, timeline_end,
                            metadata, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        node.id,
                        node.novel_id,
                        node.parent_id,
                        node.node_type.value,
                        node.number,
                        node.title,
                        node.description,
                        node.order_index,
                        node.planning_status.value,
                        node.planning_source.value,
                        node.chapter_start,
                        node.chapter_end,
                        node.chapter_count,
                        node.suggested_chapter_count,
                        node.content,
                        node.outline,
                        node.word_count,
                        node.status,
                        json.dumps(node.themes),
                        json.dumps(node.key_events),
                        node.narrative_arc,
                        json.dumps(node.conflicts),
                        node.pov_character_id,
                        node.timeline_start,
                        node.timeline_end,
                        json.dumps(node.metadata),
                        node.created_at.isoformat(),
                        node.updated_at.isoformat(),
                    ))
                except sqlite3.IntegrityError as e:
                    if "FOREIGN KEY" in str(e):
                        if not self._novel_exists(cursor, node.novel_id):
                            logger.warning(
                                "save_batch: novel %s 已被删除，跳过 story_node %s 的写入",
                                node.novel_id, node.id,
                            )
                            continue
                    raise
            conn.commit()
            return nodes
        finally:
            if self._should_close_after_use():
                conn.close()

    @staticmethod
    def _novel_exists(cursor: sqlite3.Cursor, novel_id: str) -> bool:
        cursor.execute("SELECT 1 FROM novels WHERE id = ?", (novel_id,))
        return cursor.fetchone() is not None

    async def get_by_id(self, node_id: str) -> Optional[StoryNode]:
        """根据 ID 获取节点"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM story_nodes WHERE id = ?", (node_id,))
            row = cursor.fetchone()
            return self._row_to_entity(row) if row else None
        finally:
            if self._should_close_after_use():
                conn.close()

    def get_by_novel_sync(self, novel_id: str) -> List[StoryNode]:
        """同步列出某小说的全部结构节点。"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM story_nodes
                WHERE novel_id = ?
                ORDER BY order_index
            """, (novel_id,))
            rows = cursor.fetchall()
            return [self._row_to_entity(row) for row in rows]
        finally:
            if self._should_close_after_use():
                conn.close()

    async def get_by_novel(self, novel_id: str) -> List[StoryNode]:
        """获取小说的所有节点"""
        return self.get_by_novel_sync(novel_id)

    def get_plan_nodes_sync(self, novel_id: str) -> List[StoryNode]:
        """Read the outline tree without hydrating archived chapter prose."""
        rows = self._get_connection().execute(
            """SELECT id, novel_id, parent_id, node_type, number, title, description, order_index,
                      planning_status, planning_source, chapter_start, chapter_end, chapter_count,
                      suggested_chapter_count, NULL AS content, outline, word_count, status,
                      themes, key_events, narrative_arc, conflicts, pov_character_id, timeline_start,
                      timeline_end, metadata, created_at, updated_at
                 FROM story_nodes WHERE novel_id=? ORDER BY order_index""",
            (novel_id,),
        )
        return [self._row_to_entity(row) for row in rows]

    def get_tree_sync(self, novel_id: str) -> StoryTree:
        """同步获取结构树（供 NovelService 使用）。"""
        return StoryTree(novel_id=novel_id, nodes=self.get_by_novel_sync(novel_id))

    async def get_tree(self, novel_id: str) -> StoryTree:
        """获取小说的结构树"""
        return self.get_tree_sync(novel_id)

    def get_children_sync(self, parent_id: str) -> List[StoryNode]:
        """同步获取子节点。"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM story_nodes
                WHERE parent_id = ?
                ORDER BY order_index
            """, (parent_id,))
            rows = cursor.fetchall()
            return [self._row_to_entity(row) for row in rows]
        finally:
            if self._should_close_after_use():
                conn.close()

    async def get_children(self, parent_id: str) -> List[StoryNode]:
        """获取子节点"""
        return self.get_children_sync(parent_id)

    async def get_chapters_by_novel(self, novel_id: str) -> List[StoryNode]:
        """获取小说的所有章节"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM story_nodes
                WHERE novel_id = ? AND node_type = 'chapter'
                ORDER BY order_index
            """, (novel_id,))
            rows = cursor.fetchall()
            return [self._row_to_entity(row) for row in rows]
        finally:
            if self._should_close_after_use():
                conn.close()

    async def delete(self, node_id: str) -> bool:
        """删除节点（级联删除子节点）"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM story_nodes WHERE id = ?", (node_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            if self._should_close_after_use():
                conn.close()

    async def delete_by_novel(self, novel_id: str) -> int:
        """删除小说的所有节点"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM story_nodes WHERE novel_id = ?", (novel_id,))
            conn.commit()
            return cursor.rowcount
        finally:
            if self._should_close_after_use():
                conn.close()

    async def apply_merge_plan(self, creates: List[dict], updates: List[dict], deletes: List[str]) -> None:
        """应用宏观规划合并计划（原子性事务）

        Args:
            creates: 需要创建的节点字典列表
            updates: 需要更新的节点字典列表
            deletes: 需要删除的节点 ID 列表
        """
        conn = self._get_connection()
        try:
            conn.execute("BEGIN")
            cursor = conn.cursor()

            # 1. 批量删除
            if deletes:
                placeholders = ",".join(["?"] * len(deletes))
                cursor.execute(f"DELETE FROM story_nodes WHERE id IN ({placeholders})", deletes)

            # 2. 批量更新（只更新 title, description, order_index）
            if updates:
                for u in updates:
                    cursor.execute("""
                        UPDATE story_nodes
                        SET title=?, description=?, order_index=?, updated_at=?
                        WHERE id=?
                    """, (
                        u['title'],
                        u.get('description', ''),
                        u['order_index'],
                        datetime.now().isoformat(),
                        u['id']
                    ))

            # 3. 批量插入
            if creates:
                for c in creates:
                    cursor.execute("""
                        INSERT INTO story_nodes (
                            id, novel_id, parent_id, node_type, number, title, description, order_index,
                            planning_status, planning_source,
                            chapter_start, chapter_end, chapter_count, suggested_chapter_count,
                            content, outline, word_count, status,
                            themes, key_events, narrative_arc, conflicts,
                            pov_character_id, timeline_start, timeline_end,
                            metadata, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        c['id'],
                        c['novel_id'],
                        c.get('parent_id'),
                        c['node_type'],
                        c.get('number', 0),
                        c['title'],
                        c.get('description', ''),
                        c['order_index'],
                        c.get('planning_status', 'ai_generated'),
                        c.get('planning_source', 'ai_macro'),
                        c.get('chapter_start'),
                        c.get('chapter_end'),
                        c.get('chapter_count'),
                        c.get('suggested_chapter_count'),
                        c.get('content'),
                        c.get('outline'),
                        c.get('word_count', 0),
                        c.get('status', 'draft'),
                        json.dumps(c.get('themes', [])),
                        json.dumps(c.get('key_events', [])),
                        c.get('narrative_arc'),
                        json.dumps(c.get('conflicts', [])),
                        c.get('pov_character_id'),
                        c.get('timeline_start'),
                        c.get('timeline_end'),
                        json.dumps(c.get('metadata', {})),
                        datetime.now().isoformat(),
                        datetime.now().isoformat(),
                    ))

            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            if self._should_close_after_use():
                conn.close()

    def _row_to_entity(self, row: sqlite3.Row) -> StoryNode:
        """将数据库行转换为实体"""
        # sqlite3.Row 不支持 .get() 方法，需要先转换为字典
        row_dict = dict(row)

        return StoryNode(
            id=row_dict["id"],
            novel_id=row_dict["novel_id"],
            parent_id=row_dict["parent_id"],
            node_type=NodeType(row_dict["node_type"]),
            number=row_dict["number"],
            title=row_dict["title"],
            description=row_dict["description"],
            order_index=row_dict["order_index"],

            planning_status=PlanningStatus(row_dict.get("planning_status", "draft")),
            planning_source=PlanningSource(row_dict.get("planning_source", "manual")),

            chapter_start=row_dict["chapter_start"],
            chapter_end=row_dict["chapter_end"],
            chapter_count=row_dict["chapter_count"],
            suggested_chapter_count=row_dict.get("suggested_chapter_count"),

            content=row_dict["content"],
            outline=row_dict.get("outline"),
            word_count=row_dict["word_count"],
            status=row_dict["status"],

            themes=row_dict.get("themes", "[]"),
            key_events=row_dict.get("key_events", "[]"),
            narrative_arc=row_dict.get("narrative_arc"),
            conflicts=row_dict.get("conflicts", "[]"),

            pov_character_id=row_dict.get("pov_character_id"),
            timeline_start=row_dict.get("timeline_start"),
            timeline_end=row_dict.get("timeline_end"),

            metadata=row_dict.get("metadata", "{}"),

            created_at=datetime.fromisoformat(row_dict["created_at"]),
            updated_at=datetime.fromisoformat(row_dict["updated_at"]),
        )

    async def update_chapter_ranges(self, novel_id: str) -> None:
        """根据子节点的 chapter_start/chapter_end 更新父节点的章节范围"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, parent_id, chapter_start, chapter_end, node_type
                FROM story_nodes WHERE novel_id = ?
                ORDER BY order_index
            """, (novel_id,))
            rows = cursor.fetchall()

            nodes_by_parent = {}
            for row in rows:
                pid = row[1]
                if pid not in nodes_by_parent:
                    nodes_by_parent[pid] = []
                nodes_by_parent[pid].append(row)

            for parent_id, children in nodes_by_parent.items():
                if not children:
                    continue
                starts = [r[2] for r in children if r[2] is not None]
                ends = [r[3] for r in children if r[3] is not None]
                if starts and ends:
                    new_start = min(starts)
                    new_end = max(ends)
                    cursor.execute("""
                        UPDATE story_nodes
                        SET chapter_start = ?, chapter_end = ?, updated_at = ?
                        WHERE id = ?
                    """, (new_start, new_end, datetime.now().isoformat(), parent_id))

            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            if self._should_close_after_use():
                conn.close()

    def bulk_replace_text_sync(
        self,
        novel_id: str,
        old_name: str,
        new_name: str,
    ) -> int:
        """将 story_nodes 中 title / description / outline 字段里的 old_name 替换为 new_name。

        用于 Bible 改名后同步刷新结构大纲文本，避免大纲里遗留旧名导致正文生成使用旧名。
        通过 SQLite replace() 函数原地替换，不加载到 Python 层，效率高。

        Returns:
            受影响的行数。
        """
        if not old_name or old_name == new_name:
            return 0
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE story_nodes
                SET
                    title       = replace(title,       ?, ?),
                    description = replace(description, ?, ?),
                    outline     = replace(outline,     ?, ?)
                WHERE novel_id = ?
                  AND (
                      instr(title,       ?) > 0
                   OR instr(description, ?) > 0
                   OR instr(outline,     ?) > 0
                  )
                """,
                (
                    old_name, new_name,
                    old_name, new_name,
                    old_name, new_name,
                    novel_id,
                    old_name, old_name, old_name,
                ),
            )
            affected = cursor.rowcount
            conn.commit()
            return affected
        except Exception as e:
            raise e
        finally:
            if self._should_close_after_use():
                conn.close()
