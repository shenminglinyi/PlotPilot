"""叙事引擎运行时 → DAG 画布投影（只读、可扩展）

全托管真实状态 lives in 共享内存；DAG 画布节点 ID 与 ``get_default_dag()`` 对齐。
本包提供单一投影入口，避免在 FastAPI 路由里散落 if/else。
"""

from application.engine.narrative_projection.dag_runtime_projection import (
    fingerprint,
    node_states_to_sse_events,
    project_node_states,
    snapshot_from_shared,
)
from application.engine.narrative_projection.primary_node_policy import (
    DEFAULT_SEMANTICS,
    ProjectionSemantics,
    clear_policy_hooks_for_tests,
    register_policy_hook,
    resolve_primary_node_type,
)
from application.engine.narrative_projection.runtime_snapshot import NarrativeRuntimeSnapshot
from application.engine.narrative_projection.linkage_kernel import (
    default_dag_linkage_nodes,
    default_pipeline_node_ids,
    linkage_bundle,
    registry_cpms_by_type,
)

__all__ = [
    "DEFAULT_SEMANTICS",
    "NarrativeRuntimeSnapshot",
    "ProjectionSemantics",
    "clear_policy_hooks_for_tests",
    "default_dag_linkage_nodes",
    "default_pipeline_node_ids",
    "fingerprint",
    "linkage_bundle",
    "node_states_to_sse_events",
    "project_node_states",
    "register_policy_hook",
    "registry_cpms_by_type",
    "resolve_primary_node_type",
    "snapshot_from_shared",
]
