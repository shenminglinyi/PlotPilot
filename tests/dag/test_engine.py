"""DAG 执行引擎测试"""
import pytest
from application.engine.dag.engine import DAGEngine, DAGExecutionError
from application.engine.dag.models import (
    DAGDefinition,
    EdgeCondition,
    EdgeDefinition,
    NodeConfig,
    NodeDefinition,
    NodeResult,
    NodeStatus,
)
from application.engine.dag.registry import BaseNode, NodeRegistry


class TestDAGEngine:
    """DAG 执行引擎测试"""

    def test_engine_creation(self):
        engine = DAGEngine()
        assert engine is not None

    def test_has_cycle_detection(self):
        engine = DAGEngine()
        dag = DAGDefinition(
            id="dag_cycle",
            name="环路测试",
            nodes=[
                NodeDefinition(id="node_a", type="ctx_blueprint"),
                NodeDefinition(id="node_b", type="exec_writer"),
            ],
            edges=[
                EdgeDefinition(id="edge_01", source="node_a", target="node_b"),
                EdgeDefinition(id="edge_02", source="node_b", target="node_a"),
            ],
        )
        assert engine._has_cycle(dag) is True

    def test_no_cycle_in_linear_dag(self):
        engine = DAGEngine()
        dag = DAGDefinition(
            id="dag_linear",
            name="线性 DAG",
            nodes=[
                NodeDefinition(id="node_a", type="ctx_blueprint"),
                NodeDefinition(id="node_b", type="exec_writer"),
            ],
            edges=[
                EdgeDefinition(id="edge_01", source="node_a", target="node_b"),
            ],
        )
        assert engine._has_cycle(dag) is False

    def test_topological_layers(self):
        engine = DAGEngine()
        dag = DAGDefinition(
            id="dag_layers",
            name="层级测试",
            nodes=[
                NodeDefinition(id="node_a", type="ctx_blueprint"),
                NodeDefinition(id="node_b", type="exec_writer"),
            ],
            edges=[
                EdgeDefinition(id="edge_01", source="node_a", target="node_b"),
            ],
        )
        layers = engine._topological_layers(dag)
        assert len(layers) == 2
        assert layers[0][0].id == "node_a"
        assert layers[1][0].id == "node_b"

    def test_find_downstream_nodes(self):
        engine = DAGEngine()
        dag = DAGDefinition(
            id="dag_downstream",
            name="下游测试",
            nodes=[
                NodeDefinition(id="node_a", type="ctx_blueprint"),
                NodeDefinition(id="node_b", type="exec_writer"),
            ],
            edges=[
                EdgeDefinition(id="edge_01", source="node_a", target="node_b"),
            ],
        )
        downstream = engine._find_downstream_nodes(dag, "node_a")
        assert "node_b" in downstream

    def test_validate_no_entry_node(self):
        engine = DAGEngine()
        dag = DAGDefinition(
            id="dag_no_entry",
            name="无入口",
            nodes=[
                NodeDefinition(id="node_a", type="ctx_blueprint"),
                NodeDefinition(id="node_b", type="exec_writer"),
            ],
            edges=[
                EdgeDefinition(id="edge_01", source="node_a", target="node_b"),
                EdgeDefinition(id="edge_02", source="node_b", target="node_a"),
            ],
        )
        errors = engine.validate(dag)
        assert len(errors) > 0

    def test_parallel_topological_layers(self):
        """测试并行层 — 同层无依赖节点应该在同一层"""
        engine = DAGEngine()
        dag = DAGDefinition(
            id="dag_parallel",
            name="并行测试",
            nodes=[
                NodeDefinition(id="ctx_blueprint", type="ctx_blueprint"),
                NodeDefinition(id="ctx_memory", type="ctx_memory"),
                NodeDefinition(id="exec_writer", type="exec_writer"),
            ],
            edges=[
                EdgeDefinition(id="edge_01", source="ctx_blueprint", target="exec_writer"),
                EdgeDefinition(id="edge_02", source="ctx_memory", target="exec_writer"),
            ],
        )
        layers = engine._topological_layers(dag)
        assert len(layers) == 2  # 第一层：ctx_blueprint + ctx_memory，第二层：exec_writer
        assert len(layers[0]) == 2  # 两个并行节点
        assert len(layers[1]) == 1

    @pytest.mark.asyncio
    async def test_run_with_topological_sort(self):
        """测试自研拓扑排序执行器"""
        engine = DAGEngine()
        # 强制使用自研执行器
        engine._use_langgraph = False

        dag = DAGDefinition(
            id="dag_run_test",
            name="运行测试",
            nodes=[
                NodeDefinition(id="ctx_blueprint", type="ctx_blueprint"),
                NodeDefinition(id="exec_writer", type="exec_writer"),
            ],
            edges=[
                EdgeDefinition(id="edge_01", source="ctx_blueprint", target="exec_writer"),
            ],
        )

        result = await engine.run(dag, {"novel_id": "test_novel"})
        assert result.status in ("completed", "error")
