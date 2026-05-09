"""DAG 版本管理器测试"""
import json
import os
import tempfile
import pytest
from application.engine.dag.models import DAGDefinition, NodeDefinition, EdgeDefinition, get_default_dag
from application.engine.dag.version_manager import DAGVersionManager


class TestDAGVersionManager:
    """DAG 版本管理器测试"""

    def setup_method(self):
        """使用临时目录作为数据根"""
        self._tmpdir = tempfile.mkdtemp()
        self._mgr = DAGVersionManager(data_root=self._tmpdir)

    def test_init_creates_dirs(self):
        assert os.path.exists(os.path.join(self._tmpdir, "dag_definitions"))
        assert os.path.exists(os.path.join(self._tmpdir, "dag_versions"))

    def test_load_latest_returns_none_when_not_exists(self):
        result = self._mgr.load_latest("novel_001")
        assert result is None

    def test_init_default_dag(self):
        dag = self._mgr.init_default_dag("novel_001")
        assert dag is not None
        assert len(dag.nodes) > 0

    def test_init_default_dag_idempotent(self):
        dag1 = self._mgr.init_default_dag("novel_001")
        dag2 = self._mgr.init_default_dag("novel_001")
        # 第二次应返回已存在的，不创建新版本
        assert dag1.version == dag2.version

    def test_save_version(self):
        dag = self._mgr.init_default_dag("novel_001")
        version = self._mgr.save_version("novel_001", dag)
        assert version >= 1

    def test_save_version_increments(self):
        dag = self._mgr.init_default_dag("novel_001")
        v1 = dag.version
        # 修改结构后保存（fingerprint 变化才会触发版本递增）
        dag.name = "修改后"
        # 需要同时修改节点/边结构以改变 fingerprint
        dag.nodes.append(
            NodeDefinition(id="val_narrative", type="val_narrative", label="叙事同步")
        )
        v2 = self._mgr.save_version("novel_001", dag)
        assert v2 > v1

    def test_list_versions(self):
        dag = self._mgr.init_default_dag("novel_001")
        versions = self._mgr.list_versions("novel_001")
        assert len(versions) >= 1
        assert versions[0]["version"] >= 1

    def test_rollback(self):
        dag = self._mgr.init_default_dag("novel_001")
        original_name = dag.name

        # 修改并保存
        dag.name = "修改后"
        self._mgr.save_version("novel_001", dag)

        # 回滚到 v1
        rolled = self._mgr.rollback("novel_001", 1)
        assert rolled.name == original_name

    def test_rollback_nonexistent_version(self):
        self._mgr.init_default_dag("novel_001")
        with pytest.raises(ValueError, match="不存在"):
            self._mgr.rollback("novel_001", 999)

    def test_cleanup_old_versions(self):
        dag = self._mgr.init_default_dag("novel_001")

        # 创建多个版本（需要改变结构才能创建新版本）
        for i in range(15):
            dag.name = f"版本_{i}"
            # 修改结构以改变 fingerprint
            if i % 2 == 0 and len(dag.edges) > 0:
                # 移除最后一条边再添加回来（改变 fingerprint）
                last_edge = dag.edges.pop()
                last_edge.id = f"edge_modified_{i}"
                dag.edges.append(last_edge)
            self._mgr.save_version("novel_001", dag)

        # 清理，保留最近 5 个
        deleted = self._mgr.cleanup_old_versions("novel_001", keep_count=5)
        assert deleted > 0

        # 验证只剩 5 个版本文件
        versions = self._mgr.list_versions("novel_001")
        assert len(versions) <= 5
