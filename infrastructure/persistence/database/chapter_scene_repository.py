"""
章节场景 Repository
"""

import json
from typing import Dict, List, Optional, Union
from datetime import datetime

from domain.structure.chapter_scene import ChapterScene


Row = Dict[str, object]


class ChapterSceneRepository:
    """章节场景仓储"""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def _db(self):
        from infrastructure.persistence.database.connection import get_database

        return get_database(self.db_path)

    async def save(self, scene: ChapterScene) -> ChapterScene:
        """保存章节场景"""
        db = self._db()
        db.execute(
            """
                INSERT INTO chapter_scenes (
                    id, chapter_id, scene_number, order_index,
                    location_id, timeline, summary, purpose,
                    content, word_count, characters,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                scene.id,
                scene.chapter_id,
                scene.scene_number,
                scene.order_index,
                scene.location_id,
                scene.timeline,
                scene.summary,
                scene.purpose,
                scene.content,
                scene.word_count,
                json.dumps(scene.characters),
                scene.created_at.isoformat(),
                scene.updated_at.isoformat(),
            ),
        )
        db.commit()
        return scene

    async def update(self, scene: ChapterScene) -> ChapterScene:
        """更新章节场景"""
        scene.updated_at = datetime.now()
        db = self._db()
        db.execute(
            """
                UPDATE chapter_scenes SET
                    scene_number = ?,
                    order_index = ?,
                    location_id = ?,
                    timeline = ?,
                    summary = ?,
                    purpose = ?,
                    content = ?,
                    word_count = ?,
                    characters = ?,
                    updated_at = ?
                WHERE id = ?
            """,
            (
                scene.scene_number,
                scene.order_index,
                scene.location_id,
                scene.timeline,
                scene.summary,
                scene.purpose,
                scene.content,
                scene.word_count,
                json.dumps(scene.characters),
                scene.updated_at.isoformat(),
                scene.id,
            ),
        )
        db.commit()
        return scene

    async def save_batch(self, scenes: List[ChapterScene]) -> List[ChapterScene]:
        """批量保存章节场景"""
        db = self._db()
        for scene in scenes:
            db.execute(
                """
                    INSERT OR REPLACE INTO chapter_scenes (
                        id, chapter_id, scene_number, order_index,
                        location_id, timeline, summary, purpose,
                        content, word_count, characters,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    scene.id,
                    scene.chapter_id,
                    scene.scene_number,
                    scene.order_index,
                    scene.location_id,
                    scene.timeline,
                    scene.summary,
                    scene.purpose,
                    scene.content,
                    scene.word_count,
                    json.dumps(scene.characters),
                    scene.created_at.isoformat(),
                    scene.updated_at.isoformat(),
                ),
            )
        db.commit()
        return scenes

    async def get_by_id(self, scene_id: str) -> Optional[ChapterScene]:
        """根据 ID 获取场景"""
        row = self._db().fetch_one("SELECT * FROM chapter_scenes WHERE id = ?", (scene_id,))
        return self._row_to_entity(row) if row else None

    async def get_by_chapter(self, chapter_id: str) -> List[ChapterScene]:
        """获取章节的所有场景"""
        rows = self._db().fetch_all(
            """
                SELECT * FROM chapter_scenes
                WHERE chapter_id = ?
                ORDER BY order_index, scene_number
            """,
            (chapter_id,),
        )
        return [self._row_to_entity(row) for row in rows]

    async def delete(self, scene_id: str) -> bool:
        """删除场景"""
        db = self._db()
        cur = db.execute("DELETE FROM chapter_scenes WHERE id = ?", (scene_id,))
        db.commit()
        return getattr(cur, "rowcount", 0) > 0

    async def delete_by_chapter(self, chapter_id: str) -> int:
        """删除章节的所有场景"""
        db = self._db()
        cur = db.execute("DELETE FROM chapter_scenes WHERE chapter_id = ?", (chapter_id,))
        db.commit()
        return int(getattr(cur, "rowcount", 0) or 0)

    def _row_to_entity(self, row: Union[Row, object]) -> ChapterScene:
        """将数据库行转换为实体"""
        return ChapterScene(
            id=row["id"],
            chapter_id=row["chapter_id"],
            scene_number=row["scene_number"],
            order_index=row["order_index"],
            location_id=row["location_id"],
            timeline=row["timeline"],
            summary=row["summary"],
            purpose=row["purpose"],
            content=row["content"],
            word_count=row["word_count"],
            characters=json.loads(row["characters"]) if row["characters"] else [],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
