"""
章节元素关联 Repository
"""

from typing import Dict, List, Optional, Union
from datetime import datetime

from domain.structure.chapter_element import ChapterElement, ElementType, RelationType, Importance


Row = Dict[str, object]


class ChapterElementRepository:
    """章节元素关联仓储"""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def _db(self):
        from infrastructure.persistence.database.connection import get_database

        return get_database(self.db_path)

    async def save(self, element: ChapterElement) -> ChapterElement:
        """保存章节元素关联"""
        db = self._db()
        db.execute(
            """
                INSERT INTO chapter_elements (
                    id, chapter_id, element_type, element_id,
                    relation_type, importance, appearance_order, notes,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                element.id,
                element.chapter_id,
                element.element_type.value,
                element.element_id,
                element.relation_type.value,
                element.importance.value,
                element.appearance_order,
                element.notes,
                element.created_at.isoformat(),
            ),
        )
        db.commit()
        return element

    async def save_batch(self, elements: List[ChapterElement]) -> List[ChapterElement]:
        """批量保存章节元素关联"""
        db = self._db()
        for element in elements:
            db.execute(
                """
                    INSERT OR REPLACE INTO chapter_elements (
                        id, chapter_id, element_type, element_id,
                        relation_type, importance, appearance_order, notes,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    element.id,
                    element.chapter_id,
                    element.element_type.value,
                    element.element_id,
                    element.relation_type.value,
                    element.importance.value,
                    element.appearance_order,
                    element.notes,
                    element.created_at.isoformat(),
                ),
            )
        db.commit()
        return elements

    async def get_by_chapter(self, chapter_id: str) -> List[ChapterElement]:
        """获取章节的所有元素关联"""
        rows = self._db().fetch_all(
            """
                SELECT * FROM chapter_elements
                WHERE chapter_id = ?
                ORDER BY appearance_order, created_at
            """,
            (chapter_id,),
        )
        return [self._row_to_entity(row) for row in rows]

    def get_by_chapter_sync(self, chapter_id: str) -> List[ChapterElement]:
        """同步获取章节的所有元素关联。"""
        rows = self._db().fetch_all(
            """
                SELECT * FROM chapter_elements
                WHERE chapter_id = ?
                ORDER BY appearance_order, created_at
            """,
            (chapter_id,),
        )
        return [self._row_to_entity(row) for row in rows]

    def get_by_chapter_and_type_sync(
        self,
        chapter_id: str,
        element_type: ElementType,
    ) -> List[ChapterElement]:
        """同步获取章节中某类型的所有元素。"""
        rows = self._db().fetch_all(
            """
                SELECT * FROM chapter_elements
                WHERE chapter_id = ? AND element_type = ?
                ORDER BY appearance_order, created_at
            """,
            (chapter_id, element_type.value),
        )
        return [self._row_to_entity(row) for row in rows]

    async def get_by_element(
        self,
        element_type: ElementType,
        element_id: str,
    ) -> List[ChapterElement]:
        """获取某个元素在哪些章节出现"""
        rows = self._db().fetch_all(
            """
                SELECT * FROM chapter_elements
                WHERE element_type = ? AND element_id = ?
                ORDER BY created_at
            """,
            (element_type.value, element_id),
        )
        return [self._row_to_entity(row) for row in rows]

    async def get_by_chapter_and_type(
        self,
        chapter_id: str,
        element_type: ElementType,
    ) -> List[ChapterElement]:
        """获取章节中某类型的所有元素"""
        rows = self._db().fetch_all(
            """
                SELECT * FROM chapter_elements
                WHERE chapter_id = ? AND element_type = ?
                ORDER BY appearance_order, created_at
            """,
            (chapter_id, element_type.value),
        )
        return [self._row_to_entity(row) for row in rows]

    async def delete(self, element_id: str) -> bool:
        """删除章节元素关联"""
        db = self._db()
        cur = db.execute("DELETE FROM chapter_elements WHERE id = ?", (element_id,))
        db.commit()
        return getattr(cur, "rowcount", 0) > 0

    async def delete_by_chapter(self, chapter_id: str) -> int:
        """删除章节的所有元素关联"""
        db = self._db()
        cur = db.execute("DELETE FROM chapter_elements WHERE chapter_id = ?", (chapter_id,))
        db.commit()
        return int(getattr(cur, "rowcount", 0) or 0)

    async def exists(
        self,
        chapter_id: str,
        element_type: ElementType,
        element_id: str,
        relation_type: RelationType,
    ) -> bool:
        """检查关联是否已存在"""
        row = self._db().fetch_one(
            """
                SELECT COUNT(*) AS c FROM chapter_elements
                WHERE chapter_id = ? AND element_type = ?
                AND element_id = ? AND relation_type = ?
            """,
            (chapter_id, element_type.value, element_id, relation_type.value),
        )
        return bool(row and int(row.get("c", 0) or 0) > 0)

    def get_planned_cast_sync(self, chapter_id: str) -> List[Dict]:
        """同步查询某章节的预规划角色列表（character 类型，按 importance 排序）"""
        rows = self._db().fetch_all(
            """
            SELECT id, element_id, importance, relation_type, appearance_order, notes
            FROM chapter_elements
            WHERE chapter_id = ? AND element_type = 'character'
            ORDER BY
                CASE importance WHEN 'major' THEN 0 WHEN 'normal' THEN 1 ELSE 2 END,
                appearance_order
            """,
            (chapter_id,),
        )
        return [
            {
                "id": r["id"],
                "element_id": r["element_id"],
                "importance": r["importance"],
                "relation_type": r["relation_type"],
                "appearance_order": r["appearance_order"],
                "notes": r["notes"],
            }
            for r in rows
        ]

    def upsert_cast_slot_sync(
        self,
        *,
        chapter_id: str,
        character_id: str,
        importance: str,
        relation_type: str = "appears",
        appearance_order: Optional[int] = None,
        notes: Optional[str] = None,
    ) -> Dict:
        """Insert/update a character cast slot without touching other chapter elements."""
        db = self._db()
        existing = db.fetch_one(
            """
            SELECT id FROM chapter_elements
            WHERE chapter_id = ? AND element_type = 'character' AND element_id = ?
            LIMIT 1
            """,
            (chapter_id, character_id),
        )
        now = datetime.now().isoformat()
        if existing:
            elem_id = existing["id"]
            db.execute(
                """
                UPDATE chapter_elements
                SET relation_type = ?, importance = ?, appearance_order = ?, notes = ?
                WHERE id = ?
                """,
                (relation_type, importance, appearance_order, notes, elem_id),
            )
        else:
            import uuid

            elem_id = f"elem-{uuid.uuid4().hex[:8]}"
            db.execute(
                """
                INSERT INTO chapter_elements (
                    id, chapter_id, element_type, element_id,
                    relation_type, importance, appearance_order, notes, created_at
                ) VALUES (?, ?, 'character', ?, ?, ?, ?, ?, ?)
                """,
                (
                    elem_id,
                    chapter_id,
                    character_id,
                    relation_type,
                    importance,
                    appearance_order,
                    notes,
                    now,
                ),
            )
        db.commit()
        return {
            "id": elem_id,
            "chapter_id": chapter_id,
            "element_type": "character",
            "element_id": character_id,
            "relation_type": relation_type,
            "importance": importance,
            "appearance_order": appearance_order,
            "notes": notes,
            "created_at": now,
        }

    def get_recent_char_activity_sync(
        self, novel_id: str, chapter_number: int, window: int = 5
    ) -> List[Dict]:
        """同步查询最近 window 章的角色出场统计，用于活跃度排序。"""
        rows = self._db().fetch_all(
            """
            SELECT ce.element_id,
                   COUNT(*)      AS count,
                   MAX(sn.number) AS last_chapter
            FROM chapter_elements ce
            JOIN story_nodes sn ON sn.id = ce.chapter_id
            WHERE sn.novel_id      = ?
              AND sn.node_type     = 'chapter'
              AND sn.number        >= ?
              AND sn.number        < ?
              AND ce.element_type  = 'character'
            GROUP BY ce.element_id
            """,
            (novel_id, chapter_number - window, chapter_number),
        )
        return [
            {
                "element_id": r["element_id"],
                "count": int(r["count"]),
                "last_chapter": int(r["last_chapter"]),
            }
            for r in rows
        ]

    def _row_to_entity(self, row: Union[Row, object]) -> ChapterElement:
        """将数据库行转换为实体"""
        return ChapterElement(
            id=row["id"],
            chapter_id=row["chapter_id"],
            element_type=ElementType(row["element_type"]),
            element_id=row["element_id"],
            relation_type=RelationType(row["relation_type"]),
            importance=Importance(row["importance"]),
            appearance_order=row["appearance_order"],
            notes=row["notes"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
