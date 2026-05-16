"""DAG 版本管理器 -- 数据库存储版本

迁移自文件系统存储，使用 Repository 模式
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from application.engine.dag.models import DAGDefinition
from domain.engine.dag.repositories.dag_version_repository import DAGVersionRepository

logger = logging.getLogger(__name__)


class DAGVersionManager:
    """DAG 版本管理器（数据库存储）"""

    def __init__(self, repository: Optional[DAGVersionRepository] = None):
        """初始化版本管理器

        Args:
            repository: DAG 版本仓库（可选，默认使用 SQLite 实现）
        """
        if repository is None:
            from infrastructure.persistence.database.connection import get_database
            from infrastructure.persistence.database.sqlite_dag_version_repository import (
                SqliteDAGVersionRepository,
            )

            db = get_database()
            self._repo = SqliteDAGVersionRepository(db)
        else:
            self._repo = repository

    def load_latest(self, novel_id: str) -> Optional[DAGDefinition]:
        """加载最新版本"""
        return self._repo.get_latest(novel_id)

    def save_version(self, novel_id: str, dag: DAGDefinition) -> int:
        """保存新版本，自动递增版本号

        Returns:
            版本号（如果 fingerprint 未变化，返回当前版本号）
        """
        return self._repo.save(novel_id, dag)

    def list_versions(self, novel_id: str) -> List[Dict]:
        """列出所有版本"""
        return self._repo.list_versions(novel_id)

    def rollback(self, novel_id: str, target_version: int) -> DAGDefinition:
        """回滚到指定版本（创建新版本）"""
        # 1. 加载目标版本
        target_dag = self._repo.get_by_version(novel_id, target_version)
        if not target_dag:
            raise ValueError(f"版本 v{target_version} 不存在: novel={novel_id}")

        # 2. 创建新版本（内容为目标版本）
        new_version = self.save_version(novel_id, target_dag)
        logger.info(
            f"DAG 版本回滚: novel={novel_id}, target=v{target_version}, new_version=v{new_version}"
        )

        # 3. 返回最新版本
        return self.load_latest(novel_id)  # type: ignore

    def init_default_dag(self, novel_id: str) -> DAGDefinition:
        """初始化默认 DAG"""
        existing = self.load_latest(novel_id)
        if existing:
            return existing

        from application.engine.dag.models import get_default_dag

        dag = get_default_dag()
        dag.id = f"dag_{novel_id}"
        self.save_version(novel_id, dag)
        return dag

    def cleanup_old_versions(self, novel_id: str, keep_count: int = 10) -> int:
        """清理旧版本"""
        return self._repo.delete_old_versions(novel_id, keep_count)
