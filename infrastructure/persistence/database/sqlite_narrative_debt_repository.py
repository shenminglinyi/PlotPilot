"""SQLite 叙事债务仓储实现"""
import json
import logging
from typing import List, Optional
from domain.novel.value_objects.narrative_debt import NarrativeDebt, DebtType
from domain.novel.repositories.narrative_debt_repository import NarrativeDebtRepository
from infrastructure.persistence.database.connection import DatabaseConnection

logger = logging.getLogger(__name__)


class SqliteNarrativeDebtRepository(NarrativeDebtRepository):
    """SQLite 叙事债务仓储实现"""

    def __init__(self, db: DatabaseConnection):
        self.db = db

    def save(self, debt: NarrativeDebt) -> None:
        """保存叙事债务"""
        self.db.execute("""
            INSERT OR REPLACE INTO narrative_debts
            (id, novel_id, debt_type, description, planted_chapter, due_chapter,
             importance, is_overdue, resolved_chapter, involved_entities, context,
             created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    COALESCE((SELECT created_at FROM narrative_debts WHERE id = ?), datetime('now')),
                    datetime('now'))
        """, (
            debt.id, debt.novel_id,
            debt.debt_type.value,
            debt.description,
            debt.planted_chapter, debt.due_chapter,
            debt.importance,
            int(debt.is_overdue),
            debt.resolved_chapter,
            json.dumps(debt.involved_entities, ensure_ascii=False),
            debt.context,
            debt.id,
        ))
        self.db.get_connection().commit()

    def save_batch(self, debts: List[NarrativeDebt]) -> None:
        for debt in debts:
            self.save(debt)

    def get_by_novel(self, novel_id: str) -> List[NarrativeDebt]:
        rows = self.db.fetch_all(
            "SELECT * FROM narrative_debts WHERE novel_id = ? ORDER BY importance DESC, planted_chapter ASC",
            (novel_id,),
        )
        return [self._row_to_debt(row) for row in rows]

    def get_unresolved(self, novel_id: str) -> List[NarrativeDebt]:
        rows = self.db.fetch_all(
            "SELECT * FROM narrative_debts WHERE novel_id = ? AND resolved_chapter IS NULL ORDER BY importance DESC",
            (novel_id,),
        )
        return [self._row_to_debt(row) for row in rows]

    def get_overdue(self, novel_id: str) -> List[NarrativeDebt]:
        rows = self.db.fetch_all(
            "SELECT * FROM narrative_debts WHERE novel_id = ? AND is_overdue = 1 AND resolved_chapter IS NULL ORDER BY importance DESC",
            (novel_id,),
        )
        return [self._row_to_debt(row) for row in rows]

    def get_due_soon(self, novel_id: str, current_chapter: int, window: int = 3) -> List[NarrativeDebt]:
        """获取即将到期的债务"""
        rows = self.db.fetch_all(
            """SELECT * FROM narrative_debts
               WHERE novel_id = ? AND resolved_chapter IS NULL
               AND due_chapter IS NOT NULL AND due_chapter <= ?
               ORDER BY importance DESC""",
            (novel_id, current_chapter + window),
        )
        return [self._row_to_debt(row) for row in rows]

    def get_by_type(self, novel_id: str, debt_type: DebtType) -> List[NarrativeDebt]:
        rows = self.db.fetch_all(
            "SELECT * FROM narrative_debts WHERE novel_id = ? AND debt_type = ? AND resolved_chapter IS NULL ORDER BY importance DESC",
            (novel_id, debt_type.value),
        )
        return [self._row_to_debt(row) for row in rows]

    def get_by_entity(self, novel_id: str, entity_name: str) -> List[NarrativeDebt]:
        """获取涉及指定实体的债务"""
        pattern = f'%"{entity_name}"%'
        rows = self.db.fetch_all(
            "SELECT * FROM narrative_debts WHERE novel_id = ? AND involved_entities LIKE ? AND resolved_chapter IS NULL",
            (novel_id, pattern),
        )
        return [self._row_to_debt(row) for row in rows]

    def resolve(self, debt_id: str, chapter: int) -> None:
        self.db.execute(
            "UPDATE narrative_debts SET resolved_chapter = ?, is_overdue = 0, updated_at = datetime('now') WHERE id = ?",
            (chapter, debt_id),
        )
        self.db.get_connection().commit()

    def mark_overdue_batch(self, novel_id: str, current_chapter: int) -> int:
        """批量标记逾期债务"""
        cur = self.db.execute(
            """UPDATE narrative_debts SET is_overdue = 1, updated_at = datetime('now')
               WHERE novel_id = ? AND is_overdue = 0 AND resolved_chapter IS NULL
               AND due_chapter IS NOT NULL AND due_chapter < ?""",
            (novel_id, current_chapter),
        )
        self.db.get_connection().commit()
        return cur.rowcount

    def delete(self, debt_id: str) -> bool:
        cur = self.db.execute("DELETE FROM narrative_debts WHERE id = ?", (debt_id,))
        self.db.get_connection().commit()
        return cur.rowcount > 0

    def _row_to_debt(self, row) -> NarrativeDebt:
        d = dict(row)
        return NarrativeDebt(
            id=d["id"],
            novel_id=d["novel_id"],
            debt_type=DebtType(d.get("debt_type", "foreshadowing")),
            description=d["description"],
            planted_chapter=d["planted_chapter"],
            due_chapter=d.get("due_chapter"),
            importance=d.get("importance", 2),
            is_overdue=bool(d.get("is_overdue", 0)),
            resolved_chapter=d.get("resolved_chapter"),
            involved_entities=json.loads(d.get("involved_entities", "[]")),
            context=d.get("context", ""),
        )
