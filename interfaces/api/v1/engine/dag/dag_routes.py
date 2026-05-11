"""DAG 管理 REST API — 纯展示层路由

设计原则：
- DAG 是纯展示层，不提供保存/校验/编辑接口
- 节点注册是代码行为，写一个节点就注册一个
- 执行权在全托管模式，DAG 只展示状态流转
- 暂时不走数据库

路由分组：
- 健康检查: GET /dag/health/dag
- 节点类型注册表: GET /dag/registry/types, /dag/registry/types/{node_type}
- SSE 事件流: GET /dag/events?novel_id=xxx
- DAG 定义（只读）: GET /dag/{novel_id}
- 节点详情（只读）: GET /dag/{novel_id}/nodes/{node_id}
- 节点启禁用: POST /dag/{novel_id}/nodes/{node_id}/toggle
- 运行状态: GET /dag/{novel_id}/status
- 提示词来源: GET /dag/{novel_id}/nodes/{node_id}/prompt-live

注意：静态路由（registry, health, events）必须定义在参数化路由（/{novel_id}）之前，
否则 FastAPI 会将 "registry", "health", "events" 当作 novel_id 参数匹配。
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from application.engine.dag.models import (
    DAGDefinition,
    NodeConfig,
    NodeDefinition,
    NodeMeta,
    NodeRunState,
    NodeStatus,
    get_default_dag,
)
from application.engine.dag.registry import NodeRegistry
from application.engine.narrative_projection.dag_runtime_projection import (
    node_states_to_sse_events,
    project_node_states,
    snapshot_from_shared,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dag", tags=["DAG 工作流"])

# ─── 全局单例 ───

# SSE 事件订阅者管理
_sse_subscribers: Dict[str, List[asyncio.Queue]] = {}  # novel_id -> [Queue]

# ★ DAG 定义内存缓存（暂时不走数据库）
_dag_cache: Dict[str, DAGDefinition] = {}


def _get_dag_for_novel(novel_id: str) -> DAGDefinition:
    """获取或初始化小说的 DAG 定义（内存缓存，不走数据库）"""
    if novel_id not in _dag_cache:
        _dag_cache[novel_id] = get_default_dag()
    return _dag_cache[novel_id]


def publish_sse_event(novel_id: str, event_data: dict):
    """向指定小说的 SSE 订阅者推送事件"""
    subscribers = _sse_subscribers.get(novel_id, [])
    dead_queues = []
    for queue in subscribers:
        try:
            queue.put_nowait(event_data)
        except asyncio.QueueFull:
            dead_queues.append(queue)
    # 清理满队列
    for q in dead_queues:
        subscribers.remove(q)


# ─── Request/Response Models ───


class DAGStatusResponse(BaseModel):
    """DAG 运行状态响应"""
    novel_id: str
    dag_enabled: bool
    current_version: int
    node_states: Dict[str, Dict[str, Any]]


# ═══════════════════════════════════════════════════════════════
# 静态路由 — 必须在 /{novel_id} 参数化路由之前定义
# ═══════════════════════════════════════════════════════════════


# ─── 健康检查 ───


@router.get("/health/dag")
async def dag_health_check():
    """DAG 引擎健康检查"""
    checks = {}

    # 节点注册表
    checks["node_registry"] = {
        "registered_types": len(NodeRegistry.all_types()),
        "types": sorted(NodeRegistry.all_types()),
    }

    # SSE 订阅者统计
    total_subscribers = sum(len(qs) for qs in _sse_subscribers.values())
    checks["sse"] = {
        "active_novels": len(_sse_subscribers),
        "total_subscribers": total_subscribers,
    }

    overall = "ok" if all(
        c.get("status") != "error" for c in checks.values()
    ) else "degraded"

    return {"status": overall, "checks": checks}


# ─── 节点类型注册表 ───


@router.get("/registry/types")
async def list_node_types():
    """获取所有已注册的节点类型"""
    metas = NodeRegistry.all_meta()
    return {
        "types": {
            node_type: meta.model_dump(mode="json")
            for node_type, meta in metas.items()
        }
    }


@router.get("/registry/types/{node_type}")
async def get_node_type_meta(node_type: str):
    """获取单个节点类型的元数据"""
    try:
        meta = NodeRegistry.get_meta(node_type)
        return meta.model_dump(mode="json")
    except KeyError:
        raise HTTPException(status_code=404, detail=f"节点类型 '{node_type}' 未注册")


# ─── SSE 事件流 ───


@router.get("/events")
async def dag_event_stream(novel_id: str = Query(..., description="小说 ID")):
    """SSE 事件流 — 前端实时接收节点状态变更"""
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)

    # 注册订阅者
    if novel_id not in _sse_subscribers:
        _sse_subscribers[novel_id] = []
    _sse_subscribers[novel_id].append(queue)

    async def event_generator():
        try:
            from interfaces.main import get_shared_novel_state

            # 发送初始连接确认
            yield f"event: connected\ndata: {json.dumps({'novel_id': novel_id, 'timestamp': time.time()})}\n\n"

            prev_proj: Dict[str, Dict[str, Any]] = {}
            projection_bootstrapped = False
            idle_ticks = 0

            while True:
                try:
                    event_data = await asyncio.wait_for(queue.get(), timeout=1.0)
                    idle_ticks = 0
                    event_type = event_data.get("type", "message")
                    yield f"event: {event_type}\ndata: {json.dumps(event_data, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    idle_ticks += 1
                    dag = _get_dag_for_novel(novel_id)
                    shared = get_shared_novel_state(novel_id)
                    snap = snapshot_from_shared(novel_id, shared)
                    node_ids = [(n.id, n.enabled) for n in dag.nodes]
                    new_proj = project_node_states(node_ids, snap)
                    if not projection_bootstrapped:
                        prev_proj = new_proj
                        projection_bootstrapped = True
                    else:
                        for ev in node_states_to_sse_events(novel_id, prev_proj, new_proj):
                            et = ev.get("type", "node_status_change")
                            yield f"event: {et}\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"
                        prev_proj = new_proj
                    if idle_ticks >= 30:
                        yield f"event: heartbeat\ndata: {json.dumps({'timestamp': time.time()})}\n\n"
                        idle_ticks = 0
        except asyncio.CancelledError:
            pass
        finally:
            if novel_id in _sse_subscribers:
                try:
                    _sse_subscribers[novel_id].remove(queue)
                    if not _sse_subscribers[novel_id]:
                        del _sse_subscribers[novel_id]
                except ValueError:
                    pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ═══════════════════════════════════════════════════════════════
# 参数化路由 — /{novel_id}
# ═══════════════════════════════════════════════════════════════


# ─── DAG 定义（只读） ───


@router.get("/{novel_id}")
async def get_dag(novel_id: str):
    """获取当前 DAG 定义（只读展示）"""
    dag = _get_dag_for_novel(novel_id)
    return dag.model_dump(mode="json")


# ─── 节点详情（只读） ───


@router.get("/{novel_id}/nodes/{node_id}")
async def get_node(novel_id: str, node_id: str):
    """获取节点详情（只读展示）"""
    dag = _get_dag_for_novel(novel_id)

    node = dag.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail=f"节点 '{node_id}' 不存在")

    # 附加节点元数据
    result = node.model_dump(mode="json")
    try:
        meta = NodeRegistry.get_meta(node.type)
        result["meta"] = meta.model_dump(mode="json")
    except KeyError:
        result["meta"] = None

    return result


# ─── 节点启禁用（唯一写操作） ───


@router.post("/{novel_id}/nodes/{node_id}/toggle")
async def toggle_node(novel_id: str, node_id: str):
    """切换启用/禁用"""
    dag = _get_dag_for_novel(novel_id)
    node = dag.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail=f"节点 '{node_id}' 不存在")

    # 检查是否允许禁用
    try:
        meta = NodeRegistry.get_meta(node.type)
        if not meta.can_disable and node.enabled:
            raise HTTPException(status_code=400, detail=f"节点 '{node_id}' 不允许禁用")
    except KeyError:
        pass

    node.enabled = not node.enabled
    return dag.model_dump(mode="json")


# ─── 运行状态（只读） ───


@router.get("/{novel_id}/status")
async def get_dag_status(novel_id: str):
    """获取运行状态（含所有节点状态）— 由全托管共享状态投影，与 DAG 定义节点 id 对齐。"""
    from interfaces.main import get_shared_novel_state

    dag = _get_dag_for_novel(novel_id)
    shared = get_shared_novel_state(novel_id)
    snap = snapshot_from_shared(novel_id, shared)
    node_ids = [(n.id, n.enabled) for n in dag.nodes]
    states = project_node_states(node_ids, snap)

    return DAGStatusResponse(
        novel_id=novel_id,
        dag_enabled=True,
        current_version=dag.version,
        node_states=states,
    )


# ─── 提示词来源（只读） ───


@router.get("/{novel_id}/nodes/{node_id}/prompt-live")
async def get_node_prompt_live(novel_id: str, node_id: str):
    """获取节点当前的实时提示词"""
    dag = _get_dag_for_novel(novel_id)

    node_def = next((n for n in dag.nodes if n.id == node_id), None)
    if not node_def:
        raise HTTPException(status_code=404, detail=f"节点 {node_id} 不存在")

    try:
        base_node = NodeRegistry.create_instance(node_def.type, config=node_def.config)
        prompt_dict = base_node.get_effective_prompt()

        cpms_node_key = ""
        if base_node.meta and base_node.meta.cpms_node_key:
            cpms_node_key = base_node.meta.cpms_node_key

        # 收集 CPMS 子注入点信息
        cpms_sub_keys = []
        if base_node.meta and base_node.meta.cpms_sub_keys:
            cpms_sub_keys = [
                {
                    "cpms_node_key": inj.cpms_node_key,
                    "target_variable": inj.target_variable,
                    "description": inj.description,
                    "required": inj.required,
                }
                for inj in base_node.meta.cpms_sub_keys
            ]

        prompt_mode = ""
        if base_node.meta and base_node.meta.prompt_mode:
            prompt_mode = base_node.meta.prompt_mode.value

        return {
            "node_id": node_id,
            "system": prompt_dict["system"],
            "user_template": prompt_dict["user_template"],
            "source": prompt_dict["source"],
            "cpms_node_key": cpms_node_key,
            "cpms_sub_keys": cpms_sub_keys,
            "prompt_mode": prompt_mode,
        }
    except KeyError:
        raise HTTPException(status_code=404, detail=f"节点类型 {node_def.type} 未注册")


# ─── 渲染后 Prompt（只读预览） ───


@router.get("/{novel_id}/nodes/{node_id}/prompt")
async def get_rendered_prompt(novel_id: str, node_id: str):
    """获取渲染后的 Prompt（预览）"""
    dag = _get_dag_for_novel(novel_id)

    node = dag.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail=f"节点 '{node_id}' 不存在")

    template = node.config.prompt_template or ""
    variables = node.config.prompt_variables or {}

    # 渲染模板
    rendered = template
    for key, value in variables.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", str(value))

    return {
        "node_id": node_id,
        "template": template,
        "variables": variables,
        "rendered": rendered,
    }


# ─── 节点配置更新（nodeEditorStore 使用） ───


class UpdateNodeConfigRequest(BaseModel):
    """更新节点配置请求"""
    prompt_template: Optional[str] = None
    prompt_variables: Optional[Dict[str, str]] = None
    thresholds: Optional[Dict[str, float]] = None
    model_override: Optional[str] = None
    max_retries: Optional[int] = Field(default=None, ge=0, le=5)
    timeout_seconds: Optional[int] = Field(default=None, ge=10, le=600)
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, ge=100, le=16000)


@router.put("/{novel_id}/nodes/{node_id}")
async def update_node_config(novel_id: str, node_id: str, request: UpdateNodeConfigRequest):
    """更新节点配置（运行参数）"""
    dag = _get_dag_for_novel(novel_id)
    node = dag.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail=f"节点 '{node_id}' 不存在")

    # 应用配置更新
    updates = request.model_dump(exclude_none=True)
    if "prompt_template" in updates:
        node.config.prompt_template = updates["prompt_template"]
    if "prompt_variables" in updates:
        node.config.prompt_variables = updates["prompt_variables"]
    if "thresholds" in updates:
        node.config.thresholds.update(updates["thresholds"])
    if "model_override" in updates:
        node.config.model_override = updates["model_override"]
    if "max_retries" in updates:
        node.config.max_retries = updates["max_retries"]
    if "timeout_seconds" in updates:
        node.config.timeout_seconds = updates["timeout_seconds"]
    if "temperature" in updates:
        node.config.temperature = updates["temperature"]
    if "max_tokens" in updates:
        node.config.max_tokens = updates["max_tokens"]

    return dag.model_dump(mode="json")


# ─── DAG 运行控制（dagRunStore 使用） ───


@router.post("/{novel_id}/run")
async def run_dag(novel_id: str):
    """启动 DAG 运行"""
    return {"status": "started", "novel_id": novel_id}


@router.post("/{novel_id}/stop")
async def stop_dag(novel_id: str):
    """停止 DAG 运行"""
    return {"status": "stopped", "novel_id": novel_id}
