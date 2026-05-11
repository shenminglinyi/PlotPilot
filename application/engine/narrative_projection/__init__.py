"""叙事引擎运行时 → DAG 画布投影（只读、可扩展）

全托管真实状态 lives in 共享内存；DAG 画布节点 ID 与 ``get_default_dag()`` 对齐。
本包提供单一投影入口，避免在 FastAPI 路由里散落 if/else。
"""

from application.engine.narrative_projection.dag_runtime_projection import (
    NarrativeRuntimeSnapshot,
    fingerprint,
    node_states_to_sse_events,
    project_node_states,
    snapshot_from_shared,
)

__all__ = [
    "NarrativeRuntimeSnapshot",
    "fingerprint",
    "node_states_to_sse_events",
    "project_node_states",
    "snapshot_from_shared",
]
