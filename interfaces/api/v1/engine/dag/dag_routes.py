"""DAG 管理 REST API -- 完整的 CRUD + 运行控制 + SSE 增强路由

路由分组：
- 健康检查: GET /dag/health/dag
- 节点类型注册表: GET /dag/registry/types, /dag/registry/types/{node_type}
- SSE 事件流: GET /dag/events?novel_id=xxx
- DAG 定义管理: GET/PUT /dag/{novel_id}, POST /dag/{novel_id}/validate
- 节点操作: GET/PUT /dag/{novel_id}/nodes/{node_id}, POST toggle/rerun
- DAG 运行: POST /dag/{novel_id}/run, /stop, GET /status
- 版本管理: GET /versions, POST /rollback

注意：静态路由（registry, health, events）必须定义在参数化路由（/{novel_id}）之前，
否则 FastAPI 会将 "registry", "health", "events" 当作 novel_id 参数匹配。
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from application.engine.dag.daemon_runner import DAGDaemonRunner, EngineSelector
from application.engine.dag.models import (
    DAGDefinition,
    NodeConfig,
    NodeDefinition,
    NodeMeta,
    NodeRunState,
    NodeStatus,
    get_default_dag,
)
from application.engine.dag.prompt_validator import PromptTemplateValidator
from application.engine.dag.registry import NodeRegistry
from application.engine.dag.validator import DAGValidator, ValidationResult
from application.engine.dag.version_manager import DAGVersionManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dag", tags=["DAG 工作流"])

# ─── 全局单例 ───

_version_mgr: Optional[DAGVersionManager] = None
_daemon_runner: Optional[DAGDaemonRunner] = None
_engine_selector: Optional[EngineSelector] = None

# SSE 事件订阅者管理
_sse_subscribers: Dict[str, List[asyncio.Queue]] = {}  # novel_id -> [Queue]


def _get_version_mgr() -> DAGVersionManager:
    global _version_mgr
    if _version_mgr is None:
        _version_mgr = DAGVersionManager()
    return _version_mgr


def _get_daemon_runner() -> DAGDaemonRunner:
    global _daemon_runner
    if _daemon_runner is None:
        _daemon_runner = DAGDaemonRunner()
    return _daemon_runner


def _get_engine_selector() -> EngineSelector:
    global _engine_selector
    if _engine_selector is None:
        _engine_selector = EngineSelector()
    return _engine_selector


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


class UpdateDAGRequest(BaseModel):
    """更新 DAG 定义请求"""
    name: Optional[str] = None
    description: Optional[str] = None
    nodes: Optional[List[Dict[str, Any]]] = None
    edges: Optional[List[Dict[str, Any]]] = None


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


class DAGRunRequest(BaseModel):
    """DAG 运行请求"""
    novel_id: str
    config_overrides: Dict[str, Dict[str, Any]] = Field(default_factory=dict)


class ValidationResponse(BaseModel):
    """验证结果响应"""
    errors: List[str]
    warnings: List[str]
    is_valid: bool
    summary: str


class NodeMetaResponse(BaseModel):
    """节点元数据响应"""
    node_type: str
    display_name: str
    category: str
    icon: str
    color: str
    input_ports: List[Dict[str, Any]]
    output_ports: List[Dict[str, Any]]
    prompt_template: str
    prompt_variables: List[str]
    is_configurable: bool
    can_disable: bool


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

    # DAG 引擎状态
    selector = _get_engine_selector()
    checks["dag_engine"] = {
        "enabled": selector.dag_enabled,
    }

    # 版本管理器
    try:
        mgr = _get_version_mgr()
        checks["version_manager"] = {"status": "ok"}
    except Exception as e:
        checks["version_manager"] = {"status": "error", "message": str(e)}

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
    """SSE 事件流 — 前端实时接收节点状态变更

    事件类型：
    - node_status_change: 节点状态变更
    - node_output: 节点输出
    - edge_data_flow: 边数据流动
    - dag_run_complete: DAG 运行完成
    """
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)

    # 注册订阅者
    if novel_id not in _sse_subscribers:
        _sse_subscribers[novel_id] = []
    _sse_subscribers[novel_id].append(queue)

    async def event_generator():
        try:
            # 发送初始连接确认
            yield f"event: connected\ndata: {json.dumps({'novel_id': novel_id, 'timestamp': time.time()})}\n\n"

            while True:
                try:
                    # 等待事件，超时 30 秒发送心跳
                    event_data = await asyncio.wait_for(queue.get(), timeout=30.0)
                    event_type = event_data.get("type", "message")
                    yield f"event: {event_type}\ndata: {json.dumps(event_data, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    # 心跳保活
                    yield f"event: heartbeat\ndata: {json.dumps({'timestamp': time.time()})}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            # 清理订阅者
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


# ─── DAG 定义管理 ───


@router.get("/{novel_id}")
async def get_dag(novel_id: str):
    """获取当前 DAG 定义"""
    mgr = _get_version_mgr()
    dag = mgr.load_latest(novel_id)
    if not dag:
        # 自动初始化默认 DAG
        dag = mgr.init_default_dag(novel_id)
    return dag.model_dump(mode="json")


@router.put("/{novel_id}")
async def update_dag(novel_id: str, request: UpdateDAGRequest):
    """更新 DAG 定义（节点位置/连线/配置）"""
    mgr = _get_version_mgr()
    dag = mgr.load_latest(novel_id)
    if not dag:
        dag = mgr.init_default_dag(novel_id)

    # 应用更新
    if request.name is not None:
        dag.name = request.name
    if request.description is not None:
        dag.description = request.description
    if request.nodes is not None:
        dag.nodes = [NodeDefinition(**n) for n in request.nodes]
    if request.edges is not None:
        from application.engine.dag.models import EdgeDefinition
        dag.edges = [EdgeDefinition(**e) for e in request.edges]

    # 验证
    validator = DAGValidator()
    result = validator.validate(dag)
    if not result.is_valid:
        raise HTTPException(status_code=400, detail={"errors": result.errors, "warnings": result.warnings})

    # 保存
    version = mgr.save_version(novel_id, dag)
    return {"version": version, "dag": dag.model_dump(mode="json")}


@router.post("/{novel_id}/validate")
async def validate_dag(novel_id: str):
    """校验 DAG 有效性"""
    mgr = _get_version_mgr()
    dag = mgr.load_latest(novel_id)
    if not dag:
        raise HTTPException(status_code=404, detail="DAG 定义不存在")

    validator = DAGValidator()
    result = validator.validate(dag)
    return ValidationResponse(
        errors=result.errors,
        warnings=result.warnings,
        is_valid=result.is_valid,
        summary=result.summary,
    )


# ─── 节点操作 ───


@router.get("/{novel_id}/nodes/{node_id}")
async def get_node(novel_id: str, node_id: str):
    """获取节点详情（含 Prompt 模板）"""
    mgr = _get_version_mgr()
    dag = mgr.load_latest(novel_id)
    if not dag:
        raise HTTPException(status_code=404, detail="DAG 定义不存在")

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


@router.put("/{novel_id}/nodes/{node_id}")
async def update_node_config(novel_id: str, node_id: str, request: UpdateNodeConfigRequest):
    """更新节点配置（Prompt/阈值/变量）"""
    # Prompt 安全校验
    if request.prompt_template:
        prompt_validator = PromptTemplateValidator()
        # 先获取节点类型
        mgr = _get_version_mgr()
        dag = mgr.load_latest(novel_id)
        if not dag:
            raise HTTPException(status_code=404, detail="DAG 定义不存在")
        node = dag.get_node(node_id)
        if not node:
            raise HTTPException(status_code=404, detail=f"节点 '{node_id}' 不存在")

        result = prompt_validator.validate(node.type, request.prompt_template)
        if not result.is_valid:
            raise HTTPException(status_code=400, detail={"errors": result.errors})

    runner = _get_daemon_runner()
    try:
        dag = await runner.update_node_config(novel_id, node_id, request.model_dump(exclude_none=True))
        return dag.model_dump(mode="json")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{novel_id}/nodes/{node_id}/toggle")
async def toggle_node(novel_id: str, node_id: str):
    """切换启用/禁用"""
    runner = _get_daemon_runner()
    try:
        dag = await runner.toggle_node(novel_id, node_id)
        return dag.model_dump(mode="json")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{novel_id}/nodes/{node_id}/rerun")
async def rerun_from_node(novel_id: str, node_id: str):
    """从该节点重新执行"""
    selector = _get_engine_selector()
    if not selector.should_use_dag(novel_id):
        raise HTTPException(status_code=400, detail="DAG 引擎未启用")

    # TODO: 实现从指定节点重跑逻辑
    return {"status": "rerun_started", "node_id": node_id}


@router.get("/{novel_id}/nodes/{node_id}/prompt")
async def get_rendered_prompt(novel_id: str, node_id: str):
    """获取渲染后的 Prompt（预览）"""
    mgr = _get_version_mgr()
    dag = mgr.load_latest(novel_id)
    if not dag:
        raise HTTPException(status_code=404, detail="DAG 定义不存在")

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


# ─── DAG 运行 ───


@router.post("/{novel_id}/run")
async def run_dag(novel_id: str):
    """启动 DAG 运行"""
    selector = _get_engine_selector()
    if not selector.should_use_dag(novel_id):
        raise HTTPException(status_code=400, detail="DAG 引擎未启用 (ENABLE_DAG_ENGINE)")

    runner = _get_daemon_runner()

    # 异步启动 DAG 运行
    task = asyncio.create_task(runner.run_novel(novel_id))

    return {"status": "started", "novel_id": novel_id}


@router.post("/{novel_id}/stop")
async def stop_dag(novel_id: str):
    """停止 DAG 运行"""
    # TODO: 实现停止逻辑（取消 asyncio.Task）
    return {"status": "stopped", "novel_id": novel_id}


@router.get("/{novel_id}/status")
async def get_dag_status(novel_id: str):
    """获取运行状态（含所有节点状态）"""
    mgr = _get_version_mgr()
    dag = mgr.load_latest(novel_id)
    selector = _get_engine_selector()

    return DAGStatusResponse(
        novel_id=novel_id,
        dag_enabled=selector.should_use_dag(novel_id),
        current_version=dag.version if dag else 0,
        node_states={
            n.id: {"status": "idle", "enabled": n.enabled}
            for n in (dag.nodes if dag else [])
        },
    )


@router.get("/{novel_id}/runs")
async def list_dag_runs(novel_id: str):
    """运行历史列表"""
    # TODO: 实现运行历史查询
    return {"runs": [], "novel_id": novel_id}


@router.get("/{novel_id}/runs/{run_id}")
async def get_dag_run(novel_id: str, run_id: str):
    """单次运行详情"""
    # TODO: 实现单次运行详情查询
    return {"run_id": run_id, "novel_id": novel_id, "status": "unknown"}


# ─── 版本管理 ───


@router.get("/{novel_id}/versions")
async def list_dag_versions(novel_id: str):
    """DAG 版本列表"""
    mgr = _get_version_mgr()
    versions = mgr.list_versions(novel_id)
    return {"novel_id": novel_id, "versions": versions}


@router.post("/{novel_id}/versions/{version}/rollback")
async def rollback_dag_version(novel_id: str, version: int):
    """回滚到指定版本"""
    mgr = _get_version_mgr()
    try:
        dag = mgr.rollback(novel_id, version)
        return {"status": "rolled_back", "version": dag.version, "dag": dag.model_dump(mode="json")}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
