"""
故事结构节点 Repository
"""

import sqlite3
import json
from typing import List, Optional, Union
from datetime import datetime

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

    def save_sync(self, node: StoryNode) -> StoryNode:
        """同步保存（供 NovelService 等非 async 调用链使用）。"""
        conn = self._get_connection()
        try:
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
            conn.commit()
            return node
        finally:
            if self._should_close_after_use():
                conn.close()

    async def save(self, node: StoryNode) -> StoryNode:
        """保存节点"""
        return self.save_sync(node)

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
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            for node in nodes:
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
            conn.commit()
            return nodes
        finally:
            if self._should_close_after_use():
                conn.close()

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
