"""SQLite DAG 版本仓库集成测试"""
import tempfile
from pathlib import Path
import pytest
from application.engine.dag.models import DAGDefinition, NodeDefinition, get_default_dag
from infrastructure.persistence.database.connection import DatabaseConnection
from infrastructure.persistence.database.sqlite_dag_version_repository import (
    SqliteDAGVersionRepository,
)


class TestSqliteDAGVersionRepository:
    """SQLite DAG 版本仓库集成测试"""

    @pytest.fixture
    def db(self):
        """创建临时数据库"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = DatabaseConnection(str(db_path))

            # 创建测试小说记录（满足外键约束）
            db.execute("""
                INSERT OR IGNORE INTO novels (id, title, slug, target_chapters)
                VALUES ('novel_001', '测试小说', 'test-novel', 10)
            """)
            db.execute("""
                INSERT OR IGNORE INTO novels (id, title, slug, target_chapters)
                VALUES ('novel_new', '新小说', 'new-novel', 10)
            """)
            db.commit()

            yield db
            db.close()

    @pytest.fixture
    def repo(self, db):
        """创建 Repository 实例"""
        return SqliteDAGVersionRepository(db)

    def test_save_and_load_latest(self, repo):
        dag = get_default_dag()
        dag.id = "dag_novel_001"

        version = repo.save("novel_001", dag)
        assert version == 1

        loaded = repo.get_latest("novel_001")
        assert loaded is not None
        assert loaded.id == dag.id
        assert loaded.version == 1
        assert len(loaded.nodes) == len(dag.nodes)

    def test_fingerprint_unchanged_no_new_version(self, repo):
        dag = get_default_dag()
        dag.id = "dag_novel_001"

        v1 = repo.save("novel_001", dag)
        assert v1 == 1

        # 修改非结构字段，fingerprint 不变
        dag.name = "Modified Name"
        v2 = repo.save("novel_001", dag)
        assert v2 == 1  # 版本号不变

        count = repo.get_version_count("novel_001")
        assert count == 1

    def test_fingerprint_changed_creates_new_version(self, repo):
        dag = get_default_dag()
        dag.id = "dag_novel_001"

        v1 = repo.save("novel_001", dag)
        assert v1 == 1

        # 修改结构，fingerprint 变化
        dag.nodes.append(
            NodeDefinition(
                id="new_node", type="ctx_blueprint", label="新节点", enabled=True
            )
        )
        v2 = repo.save("novel_001", dag)
        assert v2 == 2

        count = repo.get_version_count("novel_001")
        assert count == 2

    def test_get_by_version(self, repo):
        dag = get_default_dag()
        dag.id = "dag_novel_001"
        dag.name = "Version 1"

        repo.save("novel_001", dag)

        # 修改并保存新版本
        dag.name = "Version 2"
        dag.nodes.append(
            NodeDefinition(
                id="new_node", type="ctx_blueprint", label="新节点", enabled=True
            )
        )
        repo.save("novel_001", dag)

        # 加载第一个版本
        v1 = repo.get_by_version("novel_001", 1)
        assert v1 is not None
        assert v1.name == "Version 1"

        # 加载第二个版本
        v2 = repo.get_by_version("novel_001", 2)
        assert v2 is not None
        assert v2.name == "Version 2"

    def test_list_versions(self, repo):
        dag = get_default_dag()
        dag.id = "dag_novel_001"

        # 创建多个版本
        for i in range(3):
            dag.name = f"Version {i+1}"
            if i > 0:
                dag.nodes.append(
                    NodeDefinition(
                        id=f"node_{i}",
                        type="ctx_blueprint",
                        label=f"节点 {i}",
                        enabled=True,
                    )
                )
            repo.save("novel_001", dag)

        versions = repo.list_versions("novel_001")
        assert len(versions) == 3
        assert versions[0]["version"] == 3  # 最新版本在前
        assert versions[0]["node_count"] > versions[2]["node_count"]

    def test_delete_old_versions(self, repo):
        dag = get_default_dag()
        dag.id = "dag_novel_001"

        # 创建 15 个版本
        for i in range(15):
            dag.name = f"Version {i+1}"
            dag.nodes.append(
                NodeDefinition(
                    id=f"node_{i}",
                    type="ctx_blueprint",
                    label=f"节点 {i}",
                    enabled=True,
                )
            )
            repo.save("novel_001", dag)

        # 清理，保留 5 个
        deleted = repo.delete_old_versions("novel_001", keep_count=5)
        assert deleted == 10

        count = repo.get_version_count("novel_001")
        assert count == 5

        # 验证保留的是最新版本
        versions = repo.list_versions("novel_001")
        assert len(versions) == 5
        assert versions[0]["version"] == 15  # 最新版本
        assert versions[4]["version"] == 11  # 第 11 个版本（保留了 11-15）

    def test_get_version_count(self, repo):
        dag = get_default_dag()
        dag.id = "dag_novel_001"

        # 初始为 0
        count = repo.get_version_count("novel_001")
        assert count == 0

        # 创建一个版本
        repo.save("novel_001", dag)
        count = repo.get_version_count("novel_001")
        assert count == 1

        # 创建更多版本
        for i in range(5):
            dag.nodes.append(
                NodeDefinition(
                    id=f"node_{i}",
                    type="ctx_blueprint",
                    label=f"节点 {i}",
                    enabled=True,
                )
            )
            repo.save("novel_001", dag)

        count = repo.get_version_count("novel_001")
        assert count == 6

    def test_save_without_initial_version(self, repo):
        """测试从零开始创建版本"""
        dag = get_default_dag()
        dag.id = "dag_novel_new"

        # 第一个版本应该是 1
        version = repo.save("novel_new", dag)
        assert version == 1

        # 可以正常加载
        loaded = repo.get_latest("novel_new")
        assert loaded is not None
        assert loaded.version == 1
