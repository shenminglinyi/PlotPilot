"""DAG 验证器测试"""
import pytest
from application.engine.dag.models import (
    DAGDefinition,
    EdgeCondition,
    EdgeDefinition,
    NodeDefinition,
    get_default_dag,
)
from application.engine.dag.validator import DAGValidator, ValidationResult


class TestDAGValidator:
    """DAG 验证器测试"""

    def _make_valid_dag(self) -> DAGDefinition:
        return DAGDefinition(
            id="dag_test",
            name="测试 DAG",
            nodes=[
                NodeDefinition(id="ctx_blueprint", type="ctx_blueprint", label="剧本基建"),
                NodeDefinition(id="exec_writer", type="exec_writer", label="写作引擎"),
                NodeDefinition(id="val_style", type="val_style", label="文风检查"),
            ],
            edges=[
                EdgeDefinition(id="edge_01", source="ctx_blueprint", target="exec_writer"),
                EdgeDefinition(id="edge_02", source="exec_writer", target="val_style"),
            ],
        )

    def test_valid_dag_passes(self):
        dag = self._make_valid_dag()
        validator = DAGValidator()
        result = validator.validate(dag)
        assert result.is_valid, f"有效 DAG 验证失败: {result.errors}"

    def test_empty_dag_fails(self):
        dag = DAGDefinition(id="dag_empty", name="空 DAG", nodes=[], edges=[])
        validator = DAGValidator()
        result = validator.validate(dag)
        assert not result.is_valid

    def test_duplicate_node_ids(self):
        dag = DAGDefinition(
            id="dag_dup",
            name="重复节点",
            nodes=[
                NodeDefinition(id="ctx_blueprint", type="ctx_blueprint"),
                NodeDefinition(id="ctx_blueprint", type="ctx_memory"),
            ],
            edges=[],
        )
        validator = DAGValidator()
        result = validator.validate(dag)
        assert any("不唯一" in e for e in result.errors)

    def test_self_loop_edge(self):
        dag = DAGDefinition(
            id="dag_self",
            name="自环",
            nodes=[NodeDefinition(id="exec_writer", type="exec_writer")],
            edges=[EdgeDefinition(id="edge_self", source="exec_writer", target="exec_writer")],
        )
        validator = DAGValidator()
        result = validator.validate(dag)
        assert any("自环" in e for e in result.errors)

    def test_cycle_detection(self):
        dag = DAGDefinition(
            id="dag_cycle",
            name="环路",
            nodes=[
                NodeDefinition(id="node_a", type="ctx_blueprint"),
                NodeDefinition(id="node_b", type="exec_writer"),
                NodeDefinition(id="node_c", type="val_style"),
            ],
            edges=[
                EdgeDefinition(id="edge_ab", source="node_a", target="node_b"),
                EdgeDefinition(id="edge_bc", source="node_b", target="node_c"),
                EdgeDefinition(id="edge_ca", source="node_c", target="node_a"),
            ],
        )
        validator = DAGValidator()
        result = validator.validate(dag)
        assert any("环" in e for e in result.errors)

    def test_isolated_node_warning(self):
        dag = DAGDefinition(
            id="dag_isolated",
            name="孤立节点",
            nodes=[
                NodeDefinition(id="ctx_blueprint", type="ctx_blueprint"),
                NodeDefinition(id="orphan", type="ctx_memory"),
            ],
            edges=[],
        )
        validator = DAGValidator()
        result = validator.validate(dag)
        assert any("孤立" in w for w in result.warnings)

    def test_default_dag_has_expected_structure(self):
        """默认 DAG 包含所有关键节点"""
        dag = get_default_dag()
        assert len(dag.nodes) > 0
        assert len(dag.edges) > 0
        # 验证没有自环
        for edge in dag.edges:
            assert edge.source != edge.target

    def test_edge_references_nonexistent_node(self):
        dag = DAGDefinition(
            id="dag_badref",
            name="引用错误",
            nodes=[NodeDefinition(id="ctx_blueprint", type="ctx_blueprint")],
            edges=[EdgeDefinition(id="edge_bad", source="ctx_blueprint", target="nonexistent")],
        )
        validator = DAGValidator()
        result = validator.validate(dag)
        assert any("不存在" in e for e in result.errors)

    def test_gateway_completeness(self):
        """熔断网关至少需要 2 条出边"""
        dag = DAGDefinition(
            id="dag_gw",
            name="网关测试",
            nodes=[
                NodeDefinition(id="val_style", type="val_style"),
                NodeDefinition(id="gw_circuit", type="gw_circuit"),
            ],
            edges=[
                EdgeDefinition(id="edge_to_gw", source="val_style", target="gw_circuit"),
            ],
        )
        validator = DAGValidator()
        result = validator.validate(dag)
        assert any("熔断网关" in e for e in result.errors)


class TestValidationResult:
    """验证结果模型测试"""

    def test_valid_no_warnings(self):
        result = ValidationResult(errors=[], warnings=[], is_valid=True)
        assert "✅" in result.summary

    def test_valid_with_warnings(self):
        result = ValidationResult(errors=[], warnings=["警告1"], is_valid=True)
        assert "⚠️" in result.summary

    def test_invalid(self):
        result = ValidationResult(errors=["错误1"], warnings=[], is_valid=False)
        assert "❌" in result.summary
