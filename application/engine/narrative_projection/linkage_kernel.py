"""DAG ↔ 全托管 ↔ 提示词广场 — 联动内核（单一数据源）

职责：
1. **默认 DAG 管线顺序**：与 ``get_default_dag().nodes`` 列表顺序一致，供运行时投影
   ``project_node_states`` 使用，避免多处手写节点 id 列表漂移。
2. **默认 DAG 一一对应表**：每个画布节点 → ``node_type``、``cpms_node_key``、子注入点，
   全部来自 ``NodeRegistry`` 元数据；修改 CPMS 关联只改节点注册处即可。
3. **全类型 CPMS 索引**：供管理端 / 前端兜底同步（体量 = 已注册节点类型数）。

禁止在此模块 import FastAPI。
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict, List, Tuple

from application.engine.dag.models import get_default_dag
from application.engine.dag.registry import NodeRegistry


def _ensure_nodes_registered() -> None:
    """侧载节点实现模块，保证 ``NodeRegistry`` 已填充（单测与脚本 import 顺序安全）。"""
    import application.engine.dag.nodes  # noqa: F401


@lru_cache
def default_pipeline_node_ids() -> Tuple[str, ...]:
    """默认 DAG 画布节点 id 顺序（与 ``get_default_dag`` 中 ``nodes`` 声明顺序一致）。"""
    return tuple(n.id for n in get_default_dag().nodes)


def default_dag_linkage_nodes() -> List[Dict[str, Any]]:
    """默认 DAG 上每个节点的联动规格（与画布一一对应）。"""
    _ensure_nodes_registered()
    dag = get_default_dag()
    rows: List[Dict[str, Any]] = []
    for n in dag.nodes:
        try:
            meta = NodeRegistry.get_meta(n.type)
            sub = [
                {
                    "cpms_node_key": inj.cpms_node_key,
                    "target_variable": inj.target_variable,
                    "description": inj.description,
                    "required": inj.required,
                }
                for inj in (meta.cpms_sub_keys or [])
            ]
            rows.append(
                {
                    "node_id": n.id,
                    "node_type": n.type,
                    "label": n.label,
                    "enabled_default": n.enabled,
                    "cpms_node_key": meta.cpms_node_key or "",
                    "cpms_sub_keys": sub,
                    "prompt_mode": meta.prompt_mode.value if meta.prompt_mode else "",
                    "category": meta.category.value if hasattr(meta.category, "value") else str(meta.category),
                    "display_name": meta.display_name,
                }
            )
        except KeyError:
            rows.append(
                {
                    "node_id": n.id,
                    "node_type": n.type,
                    "label": n.label,
                    "enabled_default": n.enabled,
                    "cpms_node_key": "",
                    "cpms_sub_keys": [],
                    "prompt_mode": "",
                    "category": "",
                    "display_name": n.label,
                }
            )
    return rows


def registry_cpms_by_type() -> Dict[str, Dict[str, Any]]:
    """已注册节点类型 → CPMS 主键与子注入（可修改映射的权威来源在各类 Node 的 meta）。"""
    _ensure_nodes_registered()
    out: Dict[str, Dict[str, Any]] = {}
    for node_type, meta in NodeRegistry.all_meta().items():
        sub = [
            {
                "cpms_node_key": inj.cpms_node_key,
                "target_variable": inj.target_variable,
                "description": inj.description,
                "required": inj.required,
            }
            for inj in (meta.cpms_sub_keys or [])
        ]
        out[node_type] = {
            "cpms_node_key": meta.cpms_node_key or "",
            "cpms_sub_keys": sub,
            "prompt_mode": meta.prompt_mode.value if meta.prompt_mode else "",
            "category": meta.category.value if hasattr(meta.category, "value") else str(meta.category),
            "display_name": meta.display_name,
        }
    return out


def default_dag_registry_gaps() -> Dict[str, Any]:
    """默认 DAG 中是否存在未在 ``NodeRegistry`` 注册的类型（应始终为空）。"""
    _ensure_nodes_registered()
    dag = get_default_dag()
    missing = [{"node_id": n.id, "node_type": n.type} for n in dag.nodes if not NodeRegistry.has(n.type)]
    return {"complete": len(missing) == 0, "missing": missing}


def linkage_bundle() -> Dict[str, Any]:
    """供 ``GET /dag/registry/linkage`` 一次性返回。"""
    return {
        "pipeline_node_ids": list(default_pipeline_node_ids()),
        "nodes": default_dag_linkage_nodes(),
        "registry_cpms_by_type": registry_cpms_by_type(),
        "registry_gaps": default_dag_registry_gaps(),
    }
