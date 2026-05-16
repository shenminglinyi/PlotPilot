"""SQLite 人物可变状态仓储实现"""
import json
import logging
from typing import List, Optional
from domain.novel.value_objects.character_state import CharacterState
from domain.novel.repositories.character_state_repository import CharacterStateRepository
from infrastructure.persistence.database.connection import DatabaseConnection

logger = logging.getLogger(__name__)


class SqliteCharacterStateRepository(CharacterStateRepository):
    """SQLite 人物可变状态仓储实现"""

    def __init__(self, db: DatabaseConnection):
        self.db = db

    def save(self, state: CharacterState) -> None:
        """保存人物状态"""
        self.db.execute("""
            INSERT OR REPLACE INTO character_states
            (character_id, novel_id, base_traits, scars, motivations, emotional_arc,
             current_state_summary, last_updated_chapter, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """, (
            state.character_id,
            state.novel_id,
            json.dumps(state.base_traits, ensure_ascii=False),
            json.dumps([s.to_dict() for s in state.scars], ensure_ascii=False),
            json.dumps([m.to_dict() for m in state.motivations], ensure_ascii=False),
            json.dumps([e.to_dict() for e in state.emotional_arc], ensure_ascii=False),
            state.current_state_summary,
            state.last_updated_chapter,
        ))
        self.db.get_connection().commit()

    def get(self, character_id: str, novel_id: str) -> Optional[CharacterState]:
        """获取指定角色在指定小说中的状态"""
        row = self.db.fetch_one(
            "SELECT * FROM character_states WHERE character_id = ? AND novel_id = ?",
            (character_id, novel_id),
        )
        if not row:
            return None
        return self._row_to_state(row)

    def get_by_novel(self, novel_id: str) -> List[CharacterState]:
        """获取小说中所有角色状态"""
        rows = self.db.fetch_all(
            "SELECT * FROM character_states WHERE novel_id = ? ORDER BY last_updated_chapter DESC",
            (novel_id,),
        )
        return [self._row_to_state(row) for row in rows]

    def get_characters_with_active_scars(self, novel_id: str) -> List[CharacterState]:
        """获取有活跃伤疤的角色"""
        all_states = self.get_by_novel(novel_id)
        return [s for s in all_states if s.get_active_scars()]

    def delete(self, character_id: str, novel_id: str) -> bool:
        cur = self.db.execute(
            "DELETE FROM character_states WHERE character_id = ? AND novel_id = ?",
            (character_id, novel_id),
        )
        self.db.get_connection().commit()
        return cur.rowcount > 0

    def _row_to_state(self, row) -> CharacterState:
        """将数据库行转换为 CharacterState 对象"""
        from domain.novel.value_objects.character_state import Scar, Motivation, EmotionalArcNode

        d = dict(row)
        scars_data = json.loads(d.get("scars", "[]"))
        motivations_data = json.loads(d.get("motivations", "[]"))
        arc_data = json.loads(d.get("emotional_arc", "[]"))

        return CharacterState(
            character_id=d["character_id"],
            novel_id=d["novel_id"],
            base_traits=json.loads(d.get("base_traits", "[]")),
            scars=[Scar.from_dict(s) for s in scars_data],
            motivations=[Motivation.from_dict(m) for m in motivations_data],
            emotional_arc=[EmotionalArcNode.from_dict(e) for e in arc_data],
            current_state_summary=d.get("current_state_summary", ""),
            last_updated_chapter=d.get("last_updated_chapter", 0),
        )
