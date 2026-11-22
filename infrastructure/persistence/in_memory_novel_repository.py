"""内存版小说仓储实现（用于测试守护进程）

注意：这是临时实现，生产环境需要替换为真正的数据库实现
"""
import threading
from typing import Any, List, Optional, Dict, Sequence, Tuple
from domain.novel.entities.novel import Novel, AutopilotStatus
from domain.novel.value_objects.novel_id import NovelId
from domain.novel.repositories.novel_repository import NovelRepository


class InMemoryNovelRepository(NovelRepository):
    """内存版小说仓储（用于测试）"""

    def __init__(self):
        self._storage: Dict[str, Novel] = {}
        self._setup_variables: Dict[Tuple[str, str], Any] = {}
        self._lock = threading.RLock()

    def save(self, novel: Novel) -> None:
        """保存小说"""
        with self._lock:
            self._storage[novel.novel_id.value] = novel

    def create_if_absent(self, novel: Novel) -> Tuple[Novel, bool]:
        """原子创建小说；若同 ID 已存在则不覆盖并返回 (existing, False)。"""
        with self._lock:
            existing = self._storage.get(novel.novel_id.value)
            if existing is not None:
                return existing, False
            self._storage[novel.novel_id.value] = novel
            return novel, True

    def init_setup_variables_if_absent(
        self,
        novel_id: str,
        entries: Sequence[Tuple[str, Any, str, str]],
    ) -> int:
        """原子补齐缺失的内存态 setup 变量，绝不覆盖已有键值。"""
        inserted = 0
        with self._lock:
            for raw_key, raw_value, _value_type, _display_name in entries:
                key = str(raw_key or "").strip()
                if not key or raw_value in ("", None):
                    continue
                slot = (novel_id, key)
                if slot not in self._setup_variables:
                    self._setup_variables[slot] = raw_value
                    inserted += 1
        return inserted

    def patch(self, novel_id: NovelId, **fields) -> None:
        """增量更新小说字段"""
        with self._lock:
            existing = self._storage.get(novel_id.value)
            if existing is None:
                return
            for key, value in fields.items():
                if hasattr(existing, key):
                    setattr(existing, key, value)

    async def async_save(self, novel: Novel) -> None:
        """异步保存小说"""
        self.save(novel)

    def get_by_id(self, novel_id: NovelId) -> Optional[Novel]:
        """根据 ID 获取小说"""
        return self._storage.get(novel_id.value)

    def list_all(self) -> List[Novel]:
        """列出所有小说"""
        return list(self._storage.values())

    def find_by_autopilot_status(self, status: AutopilotStatus) -> List[Novel]:
        """根据自动驾驶状态查询小说"""
        return [
            novel for novel in self._storage.values()
            if novel.autopilot_status == status
        ]

    def delete(self, novel_id: NovelId) -> None:
        """删除小说"""
        if novel_id.value in self._storage:
            del self._storage[novel_id.value]

    def exists(self, novel_id: NovelId) -> bool:
        """检查小说是否存在"""
        return novel_id.value in self._storage
