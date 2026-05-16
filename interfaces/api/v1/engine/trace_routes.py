"""引擎溯源 API — TraceRecord 查询

路由：
- GET /novels/{novel_id}/traces         → 查询溯源记录
- GET /novels/{novel_id}/traces/stats   → 溯源统计
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/novels", tags=["engine-trace"])


# ─── DTOs ────────────────────────────────────────────────────────

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


# ─── 依赖 ────────────────────────────────────────────────────────

def _get_trace_store():
    """获取 TraceStore 实例"""
    from interfaces.api.dependencies import get_database
    from engine.infrastructure.persistence.trace_store import SqliteTraceStore
    return SqliteTraceStore(get_database())


def _novel_exists(novel_id: str) -> bool:
    try:
        from interfaces.api.dependencies import get_novel_service
        novel = get_novel_service().get_novel(novel_id)
        return novel is not None
    except Exception:
        return True  # 降级：无法检查时放行


# ─── Endpoints ───────────────────────────────────────────────────

@router.get("/{novel_id}/traces", response_model=TraceListResponse)
async def list_traces(
    novel_id: str,
    node_type: Optional[str] = Query(None, description="DAG节点/Guardrail/Checkpoint"),
    operation: Optional[str] = Query(None, description="check/save/load/execute"),
    limit: int = Query(100, ge=1, le=500),
):
    """查询引擎操作溯源记录"""
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
    except Exception as e:
        logger.error("查询Trace失败: %s", e)
        return TraceListResponse()


@router.get("/{novel_id}/traces/stats", response_model=TraceStatsDTO)
async def trace_stats(novel_id: str):
    """获取溯源统计"""
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

        for r in records:
            by_node_type[r.node_type] = by_node_type.get(r.node_type, 0) + 1
            by_operation[r.operation] = by_operation.get(r.operation, 0) + 1
            if r.score is not None:
                scores.append(r.score)
            durations.append(r.duration_ms)

        return TraceStatsDTO(
            total_traces=len(records),
            by_node_type=by_node_type,
            by_operation=by_operation,
            avg_score=sum(scores) / len(scores) if scores else None,
            avg_duration_ms=sum(durations) / len(durations) if durations else 0.0,
        )
    except Exception as e:
        logger.error("Trace统计失败: %s", e)
        return TraceStatsDTO()
