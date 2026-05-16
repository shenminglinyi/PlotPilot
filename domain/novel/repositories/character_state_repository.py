"""人物可变状态仓储抽象接口"""
from abc import ABC, abstractmethod
from typing import List, Optional
from domain.novel.value_objects.character_state import CharacterState


class CharacterStateRepository(ABC):
    """人物可变状态仓储抽象接口"""

    @abstractmethod
    def save(self, state: CharacterState) -> None:
        """保存人物状态"""
        pass

    @abstractmethod
    def get(self, character_id: str, novel_id: str) -> Optional[CharacterState]:
        """获取指定角色在指定小说中的状态"""
        pass

    @abstractmethod
    def get_by_novel(self, novel_id: str) -> List[CharacterState]:
        """获取小说中所有角色状态"""
        pass

    @abstractmethod
    def get_characters_with_active_scars(self, novel_id: str) -> List[CharacterState]:
        """获取有活跃伤疤的角色（用于 T0 注入）"""
        pass

    @abstractmethod
    def delete(self, character_id: str, novel_id: str) -> bool:
        """删除角色状态"""
        pass
