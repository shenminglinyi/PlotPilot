"""DAG 版本管理器测试"""
import pytest
from unittest.mock import Mock, MagicMock
from application.engine.dag.models import DAGDefinition, NodeDefinition, get_default_dag
from application.engine.dag.version_manager import DAGVersionManager
from domain.engine.dag.repositories.dag_version_repository import DAGVersionRepository


class TestDAGVersionManager:
    """DAG 版本管理器测试（数据库存储）"""

    def setup_method(self):
        """使用 Mock Repository"""
        self.mock_repo = Mock(spec=DAGVersionRepository)
        self._mgr = DAGVersionManager(repository=self.mock_repo)

    def test_load_latest_returns_none_when_not_exists(self):
        self.mock_repo.get_latest.return_value = None
        result = self._mgr.load_latest("novel_001")
        assert result is None
        self.mock_repo.get_latest.assert_called_once_with("novel_001")

    def test_init_default_dag(self):
        self.mock_repo.get_latest.return_value = None
        self.mock_repo.save.return_value = 1

        dag = self._mgr.init_default_dag("novel_001")
        assert dag is not None
        assert len(dag.nodes) > 0
        self.mock_repo.save.assert_called_once()

    def test_init_default_dag_idempotent(self):
        # 第一次创建
        existing_dag = get_default_dag()
        existing_dag.id = "dag_novel_001"
        existing_dag.version = 1

        self.mock_repo.get_latest.return_value = existing_dag

        # 第二次应返回已存在的
        dag = self._mgr.init_default_dag("novel_001")
        assert dag.version == 1
        # 不应该调用 save
        self.mock_repo.save.assert_not_called()

    def test_save_version(self):
        dag = get_default_dag()
        dag.id = "dag_novel_001"
        self.mock_repo.save.return_value = 2

        version = self._mgr.save_version("novel_001", dag)
        assert version == 2
        self.mock_repo.save.assert_called_once_with("novel_001", dag)

    def test_save_version_fingerprint_unchanged(self):
        dag = get_default_dag()
        dag.id = "dag_novel_001"
        dag.version = 1

        # Mock 返回当前版本（fingerprint 相同）
        self.mock_repo.get_latest.return_value = dag
        self.mock_repo.save.return_value = 1  # 返回当前版本号

        # 不修改结构，fingerprint 不变
        dag.name = "修改名称"
        version = self._mgr.save_version("novel_001", dag)

        # save 方法会被调用，但内部会检测 fingerprint 并返回当前版本
        assert version == 1

    def test_list_versions(self):
        self.mock_repo.list_versions.return_value = [
            {"version": 2, "name": "版本2", "updated_at": "2024-01-02", "node_count": 5, "edge_count": 4},
            {"version": 1, "name": "版本1", "updated_at": "2024-01-01", "node_count": 4, "edge_count": 3},
        ]

        versions = self._mgr.list_versions("novel_001")
        assert len(versions) == 2
        assert versions[0]["version"] == 2
        self.mock_repo.list_versions.assert_called_once_with("novel_001")

    def test_rollback(self):
        # Mock 目标版本
        target_dag = get_default_dag()
        target_dag.id = "dag_novel_001"
        target_dag.version = 1
        target_dag.name = "原始版本"

        self.mock_repo.get_by_version.return_value = target_dag
        self.mock_repo.save.return_value = 3

        # Mock 最新版本
        rolled_dag = get_default_dag()
        rolled_dag.version = 3
        rolled_dag.name = "原始版本"
        self.mock_repo.get_latest.return_value = rolled_dag

        rolled = self._mgr.rollback("novel_001", 1)
        assert rolled.name == "原始版本"
        self.mock_repo.get_by_version.assert_called_once_with("novel_001", 1)
        self.mock_repo.save.assert_called_once()

    def test_rollback_nonexistent_version(self):
        self.mock_repo.get_by_version.return_value = None
        with pytest.raises(ValueError, match="不存在"):
            self._mgr.rollback("novel_001", 999)

    def test_cleanup_old_versions(self):
        self.mock_repo.delete_old_versions.return_value = 10

        deleted = self._mgr.cleanup_old_versions("novel_001", keep_count=5)
        assert deleted == 10
        self.mock_repo.delete_old_versions.assert_called_once_with("novel_001", 5)
