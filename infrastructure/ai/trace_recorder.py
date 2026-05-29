"""AI Trace 记录器。

调用方只需要提供 phase 与少量元数据；记录器负责补齐 trace_id、span_id、
时间戳，并以失败静默降级的方式写入 SQLite。
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from application.ai.trace_context import TraceContext, ensure_trace, get_current_trace

logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


@dataclass(slots=True)
class AiTraceSpan:
    trace_id: str
    span_id: str
    phase: str
    parent_span_id: str | None = None
    novel_id: str = ""
    operation: str = "ai_call"
    node_id: str | None = None
    node_type: str | None = None
    contract_key: str | None = None
    contract_version: str | None = None
    source: str | None = None
    model: str | None = None
    generation_profile: str | None = None
    variables_hash: str | None = None
    variables_preview: Any = None
    variables_full: Any = None
    variable_sources: Any = None
    prompt_hash: str | None = None
    prompt_preview: Any = None
    prompt_full: Any = None
    response_hash: str | None = None
    response_preview: Any = None
    response_full: Any = None
    token_input: int | None = None
    token_output: int | None = None
    latency_ms: int | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_utc_now)

    def to_record(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "novel_id": self.novel_id,
            "operation": self.operation,
            "phase": self.phase,
            "node_id": self.node_id,
            "node_type": self.node_type,
            "contract_key": self.contract_key,
            "contract_version": self.contract_version,
            "source": self.source,
            "model": self.model,
            "generation_profile": self.generation_profile,
            "variables_hash": self.variables_hash,
            "variables_preview": self.variables_preview,
            "variables_full": self.variables_full,
            "variable_sources": self.variable_sources,
            "prompt_hash": self.prompt_hash,
            "prompt_preview": self.prompt_preview,
            "prompt_full": self.prompt_full,
            "response_hash": self.response_hash,
            "response_preview": self.response_preview,
            "response_full": self.response_full,
            "token_input": self.token_input,
            "token_output": self.token_output,
            "latency_ms": self.latency_ms,
            "error": self.error,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }


class TraceRecorder:
    """轻量 Trace 写入门面。"""

    def __init__(self, *, enabled: bool | None = None):
        if enabled is None:
            enabled = os.getenv("AI_TRACE_ENABLED", "true").strip().lower() not in {
                "0",
                "false",
                "off",
                "no",
            }
        self.enabled = enabled

    def record_span(
        self,
        *,
        phase: str,
        trace_context: TraceContext | None = None,
        span_id: str | None = None,
        parent_span_id: str | None = None,
        novel_id: str | None = None,
        operation: str | None = None,
        **fields: Any,
    ) -> AiTraceSpan | None:
        if not self.enabled:
            return None

        ctx = trace_context or get_current_trace() or ensure_trace(
            novel_id=novel_id,
            operation=operation or "ai_call",
        )
        if novel_id and not ctx.novel_id:
            ctx.novel_id = novel_id
        if operation and ctx.operation == "ai_call":
            ctx.operation = operation

        span = AiTraceSpan(
            trace_id=ctx.trace_id,
            span_id=span_id or ctx.new_span_id(phase),
            parent_span_id=parent_span_id or ctx.parent_span_id,
            novel_id=ctx.novel_id,
            operation=ctx.operation,
            phase=phase,
            **fields,
        )
        try:
            self._store().record_ai_span(span.to_record())
        except Exception as exc:
            logger.debug("AI Trace 写入失败，已忽略: %s", exc)
        return span

    @staticmethod
    def _store():
        from engine.infrastructure.persistence.trace_store import SqliteTraceStore
        from interfaces.api.dependencies import get_database

        return SqliteTraceStore(get_database())


_RECORDER: TraceRecorder | None = None


def get_trace_recorder() -> TraceRecorder:
    global _RECORDER
    if _RECORDER is None:
        _RECORDER = TraceRecorder()
    return _RECORDER


def record_ai_span(phase: str, **fields: Any) -> AiTraceSpan | None:
    return get_trace_recorder().record_span(phase=phase, **fields)
