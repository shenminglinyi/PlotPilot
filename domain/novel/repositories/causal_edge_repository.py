"""因果边仓储抽象接口"""
from abc import ABC, abstractmethod
from typing import List, Optional
from domain.novel.value_objects.causal_edge import CausalEdge


class CausalEdgeRepository(ABC):
    """因果边仓储抽象接口"""

    @abstractmethod
    def save(self, edge: CausalEdge) -> None:
        """保存因果边"""
        pass

    @abstractmethod
    def save_batch(self, edges: List[CausalEdge]) -> None:
        """批量保存因果边"""
        pass

    @abstractmethod
    def get_by_novel(self, novel_id: str) -> List[CausalEdge]:
        """获取小说的所有因果边"""
        pass

    @abstractmethod
    def get_unresolved(self, novel_id: str) -> List[CausalEdge]:
        """获取未闭环的因果边"""
        pass

    @abstractmethod
    def get_by_character(self, novel_id: str, character_id: str) -> List[CausalEdge]:
        """获取涉及指定角色的因果边"""
        pass

    @abstractmethod
    def get_chains_involving(self, novel_id: str, entity_name: str) -> List[CausalEdge]:
        """获取涉及指定实体名称的因果链

        用于 ACTIVE_ENTITY_MEMORY 槽位：
        当大纲提到某角色/势力时，查出所有相关因果边，
        注入到 T0 层，确保 AI 知道此实体的因果历史。
        """
        pass

    @abstractmethod
    def resolve(self, edge_id: str, chapter: int) -> None:
        """标记因果边已闭环"""
        pass

    @abstractmethod
    def get_high_strength_unresolved(self, novel_id: str, min_strength: float = 0.7) -> List[CausalEdge]:
        """获取高强度的未闭环因果边（用于叙事债务检测）"""
        pass

    @abstractmethod
    def delete(self, edge_id: str) -> bool:
        """删除因果边"""
        pass
