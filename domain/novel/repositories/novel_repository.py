from abc import ABC, abstractmethod
from typing import List, Optional
from domain.novel.entities.novel import Novel, AutopilotStatus
from domain.novel.value_objects.novel_id import NovelId


class NovelRepository(ABC):
    """小说仓储接口"""

    @abstractmethod
    def save(self, novel: Novel) -> None:
        """保存小说"""
        pass

    @abstractmethod
    def patch(self, novel_id: NovelId, **fields) -> None:
        """增量更新小说字段（只写传入的字段，减少锁竞争）"""
        pass

    @abstractmethod
    async def async_save(self, novel: Novel) -> None:
        """异步保存小说（守护进程使用）"""
        pass

    @abstractmethod
    def get_by_id(self, novel_id: NovelId) -> Optional[Novel]:
        """根据 ID 获取小说"""
        pass

    @abstractmethod
    def list_all(self) -> List[Novel]:
        """列出所有小说"""
        pass

    @abstractmethod
    def find_by_autopilot_status(self, status: AutopilotStatus) -> List[Novel]:
        """根据自动驾驶状态查询小说（守护进程使用）"""
        pass

    @abstractmethod
    def delete(self, novel_id: NovelId) -> None:
        """删除小说"""
        pass

    @abstractmethod
    def exists(self, novel_id: NovelId) -> bool:
        """检查小说是否存在"""
        pass
