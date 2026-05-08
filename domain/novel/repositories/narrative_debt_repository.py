"""叙事债务仓储抽象接口"""
from abc import ABC, abstractmethod
from typing import List, Optional
from domain.novel.value_objects.narrative_debt import NarrativeDebt, DebtType


class NarrativeDebtRepository(ABC):
    """叙事债务仓储抽象接口"""

    @abstractmethod
    def save(self, debt: NarrativeDebt) -> None:
        """保存叙事债务"""
        pass

    @abstractmethod
    def save_batch(self, debts: List[NarrativeDebt]) -> None:
        """批量保存叙事债务"""
        pass

    @abstractmethod
    def get_by_novel(self, novel_id: str) -> List[NarrativeDebt]:
        """获取小说的所有叙事债务"""
        pass

    @abstractmethod
    def get_unresolved(self, novel_id: str) -> List[NarrativeDebt]:
        """获取未结算的叙事债务"""
        pass

    @abstractmethod
    def get_overdue(self, novel_id: str) -> List[NarrativeDebt]:
        """获取逾期债务"""
        pass

    @abstractmethod
    def get_due_soon(self, novel_id: str, current_chapter: int, window: int = 3) -> List[NarrativeDebt]:
        """获取即将到期的债务"""
        pass

    @abstractmethod
    def get_by_type(self, novel_id: str, debt_type: DebtType) -> List[NarrativeDebt]:
        """按类型获取债务"""
        pass

    @abstractmethod
    def get_by_entity(self, novel_id: str, entity_name: str) -> List[NarrativeDebt]:
        """获取涉及指定实体的债务"""
        pass

    @abstractmethod
    def resolve(self, debt_id: str, chapter: int) -> None:
        """结算债务"""
        pass

    @abstractmethod
    def mark_overdue_batch(self, novel_id: str, current_chapter: int) -> int:
        """批量标记逾期债务"""
        pass

    @abstractmethod
    def delete(self, debt_id: str) -> bool:
        """删除债务"""
        pass
