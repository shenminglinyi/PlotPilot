"""引擎溯源与 AI Trace Debug API。

旧接口继续查询 engine_traces；新增接口查询 AI 调用 timeline。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/novels", tags=["engine-trace"])


class TraceDTO(BaseModel):
    trace_id: str
    node_type: str
    operation: str
    input_summary: str = ""
    output_summary: str = ""
    score: Optional[float] = None
    violations: List[str] = Field(default_factory=list)
    duration_ms: int = 0
    timestamp: str = ""


class TraceListResponse(BaseModel):
    traces: List[TraceDTO] = Field(default_factory=list)
    total: int = 0


class TraceStatsDTO(BaseModel):
    total_traces: int = 0
    by_node_type: Dict[str, int] = Field(default_factory=dict)
    by_operation: Dict[str, int] = Field(default_factory=dict)
    avg_score: Optional[float] = None
    avg_duration_ms: float = 0.0


class AiTraceSummaryDTO(BaseModel):
    trace_id: str
    novel_id: str = ""
    operation: str = "ai_call"
    started_at: str = ""
    last_at: str = ""
    span_count: int = 0
    error_count: int = 0


class AiTraceListResponse(BaseModel):
    traces: List[AiTraceSummaryDTO] = Field(default_factory=list)
    total: int = 0


class AiTraceSpanDTO(BaseModel):
    trace_id: str
    span_id: str
    parent_span_id: Optional[str] = None
    novel_id: str = ""
    operation: str = "ai_call"
    phase: str
    node_id: Optional[str] = None
    node_type: Optional[str] = None
    contract_key: Optional[str] = None
    contract_version: Optional[str] = None
    source: Optional[str] = None
    model: Optional[str] = None
    generation_profile: Optional[str] = None
    variables_hash: Optional[str] = None
    variables_preview: Any = None
    variables_full: Any = None
    variable_sources: Any = None
    prompt_hash: Optional[str] = None
    prompt_preview: Any = None
    prompt_full: Any = None
    response_hash: Optional[str] = None
    response_preview: Any = None
    response_full: Any = None
    token_input: Optional[int] = None
    token_output: Optional[int] = None
    latency_ms: Optional[int] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = ""


class AiTraceTimelineResponse(BaseModel):
    trace_id: str
    spans: List[AiTraceSpanDTO] = Field(default_factory=list)
    total: int = 0


def _get_trace_store():
    """获取 TraceStore 实例。"""
    from engine.infrastructure.persistence.trace_store import SqliteTraceStore
    from interfaces.api.dependencies import get_database

    return SqliteTraceStore(get_database())


def _novel_exists(novel_id: str) -> bool:
    try:
        from interfaces.api.dependencies import get_novel_service

        novel = get_novel_service().get_novel(novel_id)
        return novel is not None
    except Exception:
        # 降级：无法检查小说时放行，避免调试接口被依赖初始化问题阻断。
        return True


@router.get("/{novel_id}/traces", response_model=TraceListResponse)
async def list_traces(
    novel_id: str,
    node_type: Optional[str] = Query(None, description="DAG 节点、Guardrail 或 Checkpoint"),
    operation: Optional[str] = Query(None, description="check/save/load/execute"),
    limit: int = Query(100, ge=1, le=500),
):
    """查询旧版引擎操作溯源记录。"""
    if not _novel_exists(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")

    store = _get_trace_store()
    try:
        records = await store.query(
            novel_id=novel_id,
            node_type=node_type,
            operation=operation,
            limit=limit,
        )
        return TraceListResponse(
            traces=[
                TraceDTO(
                    trace_id=r.trace_id,
                    node_type=r.node_type,
                    operation=r.operation,
                    input_summary=r.input_summary,
                    output_summary=r.output_summary,
                    score=r.score,
                    violations=r.violations,
                    duration_ms=r.duration_ms,
                    timestamp=r.timestamp,
                )
                for r in records
            ],
            total=len(records),
        )
    except Exception as exc:
        logger.error("查询 Trace 失败: %s", exc)
        return TraceListResponse()


@router.get("/{novel_id}/traces/stats", response_model=TraceStatsDTO)
async def trace_stats(novel_id: str):
    """获取旧版引擎溯源统计。"""
    if not _novel_exists(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")

    store = _get_trace_store()
    try:
        records = await store.query(novel_id=novel_id, limit=1000)
        if not records:
            return TraceStatsDTO()

        by_node_type: Dict[str, int] = {}
        by_operation: Dict[str, int] = {}
        scores = []
        durations = []

        for record in records:
            by_node_type[record.node_type] = by_node_type.get(record.node_type, 0) + 1
            by_operation[record.operation] = by_operation.get(record.operation, 0) + 1
            if record.score is not None:
                scores.append(record.score)
            durations.append(record.duration_ms)

        return TraceStatsDTO(
            total_traces=len(records),
            by_node_type=by_node_type,
            by_operation=by_operation,
            avg_score=sum(scores) / len(scores) if scores else None,
            avg_duration_ms=sum(durations) / len(durations) if durations else 0.0,
        )
    except Exception as exc:
        logger.error("Trace 统计失败: %s", exc)
        return TraceStatsDTO()


@router.get("/{novel_id}/ai-traces", response_model=AiTraceListResponse)
async def list_ai_traces(
    novel_id: str,
    limit: int = Query(100, ge=1, le=500),
):
    """查询 AI Trace 列表，用于定位可展开的 trace_id。"""
    if not _novel_exists(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")

    store = _get_trace_store()
    rows = store.list_ai_traces(novel_id=novel_id, limit=limit)
    traces = [AiTraceSummaryDTO(**row) for row in rows]
    return AiTraceListResponse(traces=traces, total=len(traces))


@router.get("/{novel_id}/traces/{trace_id}/timeline", response_model=AiTraceTimelineResponse)
async def ai_trace_timeline(novel_id: str, trace_id: str):
    """按 trace_id 查询 AI 调用 timeline。"""
    if not _novel_exists(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")

    store = _get_trace_store()
    rows = store.get_ai_timeline(trace_id=trace_id, novel_id=novel_id)
    spans = [AiTraceSpanDTO(**row) for row in rows]
    return AiTraceTimelineResponse(trace_id=trace_id, spans=spans, total=len(spans))
