"""DAG 版本仓库接口"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from application.engine.dag.models import DAGDefinition


class DAGVersionRepository(ABC):
    """DAG 版本仓库接口"""

    @abstractmethod
    def get_latest(self, novel_id: str) -> Optional[DAGDefinition]:
        """获取最新版本

        Args:
            novel_id: 小说 ID

        Returns:
            最新版本的 DAG 定义，如果不存在则返回 None
        """
        pass

    @abstractmethod
    def get_by_version(self, novel_id: str, version: int) -> Optional[DAGDefinition]:
        """获取指定版本

        Args:
            novel_id: 小说 ID
            version: 版本号

        Returns:
            指定版本的 DAG 定义，如果不存在则返回 None
        """
        pass

    @abstractmethod
    def save(self, novel_id: str, dag: DAGDefinition) -> int:
        """保存新版本

        自动递增版本号，如果 fingerprint 未变化则不创建新版本

        Args:
            novel_id: 小说 ID
            dag: DAG 定义

        Returns:
            版本号（如果 fingerprint 未变化，返回当前版本号）
        """
        pass

    @abstractmethod
    def list_versions(self, novel_id: str) -> List[Dict]:
        """列出所有版本摘要

        Args:
            novel_id: 小说 ID

        Returns:
            版本摘要列表（按版本号降序）
        """
        pass

    @abstractmethod
    def delete_old_versions(self, novel_id: str, keep_count: int) -> int:
        """删除旧版本

        保留最新的 keep_count 个版本

        Args:
            novel_id: 小说 ID
            keep_count: 保留的版本数

        Returns:
            删除的版本数
        """
        pass

    @abstractmethod
    def get_version_count(self, novel_id: str) -> int:
        """获取版本总数

        Args:
            novel_id: 小说 ID

        Returns:
            版本总数
        """
        pass
