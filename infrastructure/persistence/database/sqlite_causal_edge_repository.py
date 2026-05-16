"""SQLite 因果边仓储实现"""
import json
import logging
from typing import List, Optional
from domain.novel.value_objects.causal_edge import CausalEdge, CausalType
from domain.novel.repositories.causal_edge_repository import CausalEdgeRepository
from infrastructure.persistence.database.connection import DatabaseConnection

logger = logging.getLogger(__name__)


class SqliteCausalEdgeRepository(CausalEdgeRepository):
    """SQLite 因果边仓储实现"""

    def __init__(self, db: DatabaseConnection):
        self.db = db

    def save(self, edge: CausalEdge) -> None:
        """保存因果边"""
        self.db.execute("""
            INSERT OR REPLACE INTO causal_edges
            (id, novel_id, source_event_summary, source_chapter, causal_type,
             target_event_summary, target_chapter, strength, confidence,
             state_change, involved_characters, is_resolved, resolved_chapter,
             created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    COALESCE((SELECT created_at FROM causal_edges WHERE id = ?), datetime('now')),
                    datetime('now'))
        """, (
            edge.id, edge.novel_id,
            edge.source_event_summary, edge.source_chapter,
            edge.causal_type.value,
            edge.target_event_summary, edge.target_chapter,
            edge.strength, edge.confidence,
            edge.state_change,
            json.dumps(edge.involved_characters, ensure_ascii=False),
            int(edge.is_resolved), edge.resolved_chapter,
            edge.id,
        ))
        self.db.get_connection().commit()

    def save_batch(self, edges: List[CausalEdge]) -> None:
        """批量保存因果边"""
        for edge in edges:
            self.save(edge)

    def get_by_novel(self, novel_id: str) -> List[CausalEdge]:
        """获取小说的所有因果边"""
        rows = self.db.fetch_all(
            "SELECT * FROM causal_edges WHERE novel_id = ? ORDER BY source_chapter ASC",
            (novel_id,),
        )
        return [self._row_to_edge(row) for row in rows]

    def get_unresolved(self, novel_id: str) -> List[CausalEdge]:
        """获取未闭环的因果边"""
        rows = self.db.fetch_all(
            "SELECT * FROM causal_edges WHERE novel_id = ? AND is_resolved = 0 ORDER BY source_chapter ASC",
            (novel_id,),
        )
        return [self._row_to_edge(row) for row in rows]

    def get_by_character(self, novel_id: str, character_id: str) -> List[CausalEdge]:
        """获取涉及指定角色的因果边"""
        rows = self.db.fetch_all(
            "SELECT * FROM causal_edges WHERE novel_id = ? AND involved_characters LIKE ? ORDER BY source_chapter ASC",
            (novel_id, f'%"{character_id}"%'),
        )
        return [self._row_to_edge(row) for row in rows]

    def get_chains_involving(self, novel_id: str, entity_name: str) -> List[CausalEdge]:
        """获取涉及指定实体名称的因果链

        搜索范围：source_event_summary, target_event_summary, involved_characters
        """
        pattern = f'%{entity_name}%'
        rows = self.db.fetch_all(
            """SELECT * FROM causal_edges WHERE novel_id = ?
               AND (source_event_summary LIKE ? OR target_event_summary LIKE ?
                    OR involved_characters LIKE ?)
               ORDER BY source_chapter ASC""",
            (novel_id, pattern, pattern, pattern),
        )
        return [self._row_to_edge(row) for row in rows]

    def resolve(self, edge_id: str, chapter: int) -> None:
        """标记因果边已闭环"""
        self.db.execute(
            """UPDATE causal_edges SET is_resolved = 1, resolved_chapter = ?, updated_at = datetime('now')
               WHERE id = ?""",
            (chapter, edge_id),
        )
        self.db.get_connection().commit()

    def get_high_strength_unresolved(self, novel_id: str, min_strength: float = 0.7) -> List[CausalEdge]:
        """获取高强度的未闭环因果边"""
        rows = self.db.fetch_all(
            "SELECT * FROM causal_edges WHERE novel_id = ? AND is_resolved = 0 AND strength >= ? ORDER BY strength DESC",
            (novel_id, min_strength),
        )
        return [self._row_to_edge(row) for row in rows]

    def delete(self, edge_id: str) -> bool:
        cur = self.db.execute("DELETE FROM causal_edges WHERE id = ?", (edge_id,))
        self.db.get_connection().commit()
        return cur.rowcount > 0

    def _row_to_edge(self, row) -> CausalEdge:
        """将数据库行转换为 CausalEdge 对象"""
        d = dict(row)
        return CausalEdge(
            id=d["id"],
            novel_id=d["novel_id"],
            source_event_summary=d["source_event_summary"],
            source_chapter=d["source_chapter"],
            causal_type=CausalType(d.get("causal_type", "causes")),
            target_event_summary=d["target_event_summary"],
            target_chapter=d.get("target_chapter"),
            strength=d.get("strength", 0.8),
            confidence=d.get("confidence", 0.7),
            state_change=d.get("state_change", ""),
            involved_characters=json.loads(d.get("involved_characters", "[]")),
            is_resolved=bool(d.get("is_resolved", 0)),
            resolved_chapter=d.get("resolved_chapter"),
        )
