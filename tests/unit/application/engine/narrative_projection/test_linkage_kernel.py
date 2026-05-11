"""linkage_kernel — 默认 DAG 与注册表 CPMS 对齐"""
from application.engine.dag.models import get_default_dag
from application.engine.narrative_projection.linkage_kernel import (
    default_dag_linkage_nodes,
    default_pipeline_node_ids,
    linkage_bundle,
)


def test_pipeline_matches_default_dag_node_count():
    dag = get_default_dag()
    pipe = default_pipeline_node_ids()
    assert len(pipe) == len(dag.nodes)
    assert set(pipe) == {n.id for n in dag.nodes}


def test_each_default_node_has_registry_row():
    rows = default_dag_linkage_nodes()
    assert len(rows) == len(get_default_dag().nodes)
    for row in rows:
        assert row["node_id"]
        assert row["node_type"]
        # 默认 DAG 中类型均已注册，应有主 CPMS key
        assert row.get("cpms_node_key") is not None


def test_linkage_bundle_keys():
    b = linkage_bundle()
    assert "pipeline_node_ids" in b and "nodes" in b and "registry_cpms_by_type" in b
    assert len(b["registry_cpms_by_type"]) >= len(b["nodes"])
