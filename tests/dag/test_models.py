"""DAG 核心模型测试"""
import pytest
from application.engine.dag.models import (
    DAGDefinition,
    EdgeCondition,
    EdgeDefinition,
    NodeCategory,
    NodeConfig,
    NodeDefinition,
    NodeMeta,
    NodePort,
    NodeStatus,
    PortDataType,
    get_default_dag,
)


class TestNodeDefinition:
    """节点定义模型测试"""

    def test_valid_node(self):
        node = NodeDefinition(id="ctx_blueprint", type="ctx_blueprint", label="剧本基建")
        assert node.id == "ctx_blueprint"
        assert node.type == "ctx_blueprint"
        assert node.enabled is True

    def test_invalid_node_type(self):
        with pytest.raises(ValueError, match="未知节点类型"):
            NodeDefinition(id="test", type="invalid_type")

    def test_invalid_node_id_format(self):
        with pytest.raises(ValueError):
            NodeDefinition(id="123bad", type="ctx_blueprint")

    def test_default_position(self):
        node = NodeDefinition(id="test_node", type="ctx_blueprint")
        assert node.position == {"x": 0.0, "y": 0.0}

    def test_custom_config(self):
        config = NodeConfig(
            temperature=0.5,
            max_retries=3,
            timeout_seconds=120,
            thresholds={"drift_warning": 0.5},
        )
        node = NodeDefinition(id="test_node", type="val_style", config=config)
        assert node.config.temperature == 0.5
        assert node.config.max_retries == 3


class TestEdgeDefinition:
    """边定义模型测试"""

    def test_valid_edge(self):
        edge = EdgeDefinition(
            id="edge_01",
            source="ctx_blueprint",
            target="exec_beat",
        )
        assert edge.condition == EdgeCondition.ALWAYS
        assert edge.animated is False

    def test_conditional_edge(self):
        edge = EdgeDefinition(
            id="edge_cond",
            source="val_style",
            target="gw_retry",
            condition=EdgeCondition.ON_DRIFT_ALERT,
            animated=True,
        )
        assert edge.condition == EdgeCondition.ON_DRIFT_ALERT
        assert edge.animated is True


class TestDAGDefinition:
    """DAG 定义模型测试"""

    def _make_simple_dag(self) -> DAGDefinition:
        return DAGDefinition(
            id="dag_test",
            name="测试 DAG",
            nodes=[
                NodeDefinition(id="ctx_blueprint", type="ctx_blueprint", label="剧本基建"),
                NodeDefinition(id="exec_writer", type="exec_writer", label="写作引擎"),
            ],
            edges=[
                EdgeDefinition(id="edge_01", source="ctx_blueprint", target="exec_writer"),
            ],
        )

    def test_get_node(self):
        dag = self._make_simple_dag()
        node = dag.get_node("ctx_blueprint")
        assert node is not None
        assert node.type == "ctx_blueprint"

    def test_get_node_not_found(self):
        dag = self._make_simple_dag()
        assert dag.get_node("nonexistent") is None

    def test_get_entry_nodes(self):
        dag = self._make_simple_dag()
        entries = dag.get_entry_nodes()
        assert len(entries) == 1
        assert entries[0].id == "ctx_blueprint"

    def test_get_successors(self):
        dag = self._make_simple_dag()
        succs = dag.get_successors("ctx_blueprint")
        assert succs == ["exec_writer"]

    def test_get_predecessors(self):
        dag = self._make_simple_dag()
        preds = dag.get_predecessors("exec_writer")
        assert preds == ["ctx_blueprint"]

    def test_fingerprint(self):
        dag1 = self._make_simple_dag()
        dag2 = self._make_simple_dag()
        assert dag1.fingerprint() == dag2.fingerprint()

    def test_fingerprint_changes_with_structure(self):
        dag1 = self._make_simple_dag()
        dag2 = self._make_simple_dag()
        dag2.nodes.append(
            NodeDefinition(id="val_style", type="val_style", label="文风检查")
        )
        assert dag1.fingerprint() != dag2.fingerprint()


class TestDefaultDAG:
    """默认 DAG 实例测试"""

    def test_default_dag_structure(self):
        dag = get_default_dag()
        assert dag.id == "dag_default_single_act"
        assert len(dag.nodes) > 0
        assert len(dag.edges) > 0

    def test_default_dag_has_all_categories(self):
        dag = get_default_dag()
        categories = set()
        for node in dag.nodes:
            # 从节点类型前缀推断类别
            if node.type.startswith("ctx_"):
                categories.add("context")
            elif node.type.startswith("exec_"):
                categories.add("execution")
            elif node.type.startswith("val_"):
                categories.add("validation")
            elif node.type.startswith("gw_"):
                categories.add("gateway")
        assert "context" in categories
        assert "execution" in categories
        assert "validation" in categories
        assert "gateway" in categories

    def test_default_dag_entry_nodes(self):
        dag = get_default_dag()
        entries = dag.get_entry_nodes()
        assert len(entries) > 0

    def test_default_dag_no_self_loops(self):
        dag = get_default_dag()
        for edge in dag.edges:
            assert edge.source != edge.target, f"自环边: {edge.id}"
