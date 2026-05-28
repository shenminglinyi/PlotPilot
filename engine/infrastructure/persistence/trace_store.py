"""TracePort 的 SQLite 实现。

兼容旧的 engine_traces 审计表，并为 AI Trace Debug Layer 增加
ai_trace_spans / ai_trace_artifacts 两张表。主表只保存 metadata、hash、preview，
避免默认写入完整提示词和正文。
"""
from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from engine.core.ports.ports import TracePort, TraceRecord

logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _json_dump(value: Any, default: Any) -> str:
    if value is None:
        value = default
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        return json.dumps(default, ensure_ascii=False)


def _json_load(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


class SqliteTraceStore(TracePort):
    """溯源端口 SQLite 实现。"""

    def __init__(self, db_pool):
        self._db_pool = db_pool
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        try:
            with self._db_pool.get_connection() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS engine_traces (
                        trace_id TEXT PRIMARY KEY,
                        novel_id TEXT NOT NULL,
                        node_type TEXT NOT NULL,
                        operation TEXT NOT NULL,
                        input_summary TEXT NOT NULL DEFAULT '',
                        output_summary TEXT NOT NULL DEFAULT '',
                        score REAL,
                        violations TEXT NOT NULL DEFAULT '[]',
                        duration_ms INTEGER NOT NULL DEFAULT 0,
                        timestamp TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_traces_novel_id
                    ON engine_traces(novel_id, created_at DESC)
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_traces_node_type
                    ON engine_traces(novel_id, node_type)
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS ai_trace_spans (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        trace_id TEXT NOT NULL,
                        span_id TEXT NOT NULL,
                        parent_span_id TEXT,
                        novel_id TEXT NOT NULL DEFAULT '',
                        operation TEXT NOT NULL DEFAULT 'ai_call',
                        phase TEXT NOT NULL,
                        node_id TEXT,
                        node_type TEXT,
                        contract_key TEXT,
                        contract_version TEXT,
                        source TEXT,
                        model TEXT,
                        generation_profile TEXT,
                        variables_hash TEXT,
                        variables_preview TEXT,
                        prompt_hash TEXT,
                        prompt_preview TEXT,
                        response_hash TEXT,
                        response_preview TEXT,
                        token_input INTEGER,
                        token_output INTEGER,
                        latency_ms INTEGER,
                        error TEXT,
                        metadata TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL
                    )
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_ai_trace_spans_novel
                    ON ai_trace_spans(novel_id, created_at DESC)
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_ai_trace_spans_trace
                    ON ai_trace_spans(trace_id, created_at ASC)
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_ai_trace_spans_contract
                    ON ai_trace_spans(contract_key, created_at DESC)
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS ai_trace_artifacts (
                        artifact_id TEXT PRIMARY KEY,
                        trace_id TEXT NOT NULL,
                        span_id TEXT NOT NULL,
                        novel_id TEXT NOT NULL DEFAULT '',
                        kind TEXT NOT NULL,
                        content_hash TEXT NOT NULL,
                        content_preview TEXT,
                        content_text TEXT,
                        metadata TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL
                    )
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_ai_trace_artifacts_trace
                    ON ai_trace_artifacts(trace_id, span_id)
                """)
                conn.commit()
        except Exception as exc:
            logger.error("Trace 表创建失败: %s", exc)

    async def record(self, trace: TraceRecord) -> None:
        try:
            with self._db_pool.get_connection() as conn:
                conn.execute(
                    """INSERT INTO engine_traces
                       (trace_id, novel_id, node_type, operation,
                        input_summary, output_summary, score, violations,
                        duration_ms, timestamp)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        trace.trace_id or str(uuid.uuid4()),
                        getattr(trace, "novel_id", ""),
                        trace.node_type,
                        trace.operation,
                        trace.input_summary[:200] if trace.input_summary else "",
                        trace.output_summary[:200] if trace.output_summary else "",
                        trace.score,
                        json.dumps(trace.violations, ensure_ascii=False),
                        trace.duration_ms,
                        trace.timestamp or _utc_now(),
                    ),
                )
                conn.commit()
        except Exception as exc:
            logger.error("Trace 记录失败: %s", exc)

    async def query(
        self,
        novel_id: str,
        node_type: Optional[str] = None,
        operation: Optional[str] = None,
        limit: int = 100,
    ) -> list[TraceRecord]:
        try:
            with self._db_pool.get_connection() as conn:
                conn.row_factory = sqlite3.Row
                conditions = ["novel_id = ?"]
                params: list[Any] = [novel_id]

                if node_type:
                    conditions.append("node_type = ?")
                    params.append(node_type)
                if operation:
                    conditions.append("operation = ?")
                    params.append(operation)

                where = " AND ".join(conditions)
                params.append(limit)

                rows = conn.execute(
                    f"""SELECT * FROM engine_traces
                        WHERE {where}
                        ORDER BY created_at DESC LIMIT ?""",
                    params,
                ).fetchall()

                results: list[TraceRecord] = []
                for row in rows:
                    data = dict(row)
                    results.append(
                        TraceRecord(
                            trace_id=data["trace_id"],
                            node_type=data["node_type"],
                            operation=data["operation"],
                            input_summary=data.get("input_summary", ""),
                            output_summary=data.get("output_summary", ""),
                            score=data.get("score"),
                            violations=json.loads(data.get("violations", "[]")),
                            duration_ms=data.get("duration_ms", 0),
                            timestamp=data.get("timestamp", ""),
                            novel_id=data.get("novel_id", ""),
                        )
                    )
                return results
        except Exception as exc:
            logger.error("Trace 查询失败: %s", exc)
            return []

    def record_ai_span(self, span: Mapping[str, Any]) -> None:
        """写入 AI Trace span。调用方传 dict，避免跨层类型耦合。"""
        try:
            with self._db_pool.get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO ai_trace_spans (
                        trace_id, span_id, parent_span_id, novel_id, operation, phase,
                        node_id, node_type, contract_key, contract_version, source,
                        model, generation_profile, variables_hash, variables_preview,
                        prompt_hash, prompt_preview, response_hash, response_preview,
                        token_input, token_output, latency_ms, error, metadata, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        span.get("trace_id") or str(uuid.uuid4()),
                        span.get("span_id") or str(uuid.uuid4()),
                        span.get("parent_span_id"),
                        span.get("novel_id") or "",
                        span.get("operation") or "ai_call",
                        span.get("phase") or "event",
                        span.get("node_id"),
                        span.get("node_type"),
                        span.get("contract_key"),
                        span.get("contract_version"),
                        span.get("source"),
                        span.get("model"),
                        span.get("generation_profile"),
                        span.get("variables_hash"),
                        _json_dump(span.get("variables_preview"), None),
                        span.get("prompt_hash"),
                        _json_dump(span.get("prompt_preview"), None),
                        span.get("response_hash"),
                        _json_dump(span.get("response_preview"), None),
                        span.get("token_input"),
                        span.get("token_output"),
                        span.get("latency_ms"),
                        span.get("error"),
                        _json_dump(span.get("metadata"), {}),
                        span.get("created_at") or _utc_now(),
                    ),
                )
                conn.commit()
        except Exception as exc:
            logger.debug("AI Trace span 写入失败: %s", exc)

    def record_ai_artifact(self, artifact: Mapping[str, Any]) -> None:
        try:
            with self._db_pool.get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO ai_trace_artifacts (
                        artifact_id, trace_id, span_id, novel_id, kind, content_hash,
                        content_preview, content_text, metadata, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        artifact.get("artifact_id") or str(uuid.uuid4()),
                        artifact.get("trace_id") or "",
                        artifact.get("span_id") or "",
                        artifact.get("novel_id") or "",
                        artifact.get("kind") or "text",
                        artifact.get("content_hash") or "",
                        artifact.get("content_preview"),
                        artifact.get("content_text"),
                        _json_dump(artifact.get("metadata"), {}),
                        artifact.get("created_at") or _utc_now(),
                    ),
                )
                conn.commit()
        except Exception as exc:
            logger.debug("AI Trace artifact 写入失败: %s", exc)

    def list_ai_traces(self, novel_id: str, limit: int = 100) -> list[dict[str, Any]]:
        try:
            with self._db_pool.get_connection() as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """
                    SELECT
                        trace_id,
                        novel_id,
                        COALESCE(NULLIF(operation, ''), 'ai_call') AS operation,
                        MIN(created_at) AS started_at,
                        MAX(created_at) AS last_at,
                        COUNT(*) AS span_count,
                        SUM(CASE WHEN phase = 'error' OR COALESCE(error, '') <> '' THEN 1 ELSE 0 END) AS error_count
                    FROM ai_trace_spans
                    WHERE novel_id = ?
                    GROUP BY trace_id, novel_id, operation
                    ORDER BY last_at DESC
                    LIMIT ?
                    """,
                    (novel_id, limit),
                ).fetchall()
                return [dict(row) for row in rows]
        except Exception as exc:
            logger.error("AI Trace 列表查询失败: %s", exc)
            return []

    def get_ai_timeline(self, trace_id: str, novel_id: str | None = None) -> list[dict[str, Any]]:
        try:
            with self._db_pool.get_connection() as conn:
                conn.row_factory = sqlite3.Row
                conditions = ["trace_id = ?"]
                params: list[Any] = [trace_id]
                if novel_id:
                    conditions.append("novel_id = ?")
                    params.append(novel_id)
                rows = conn.execute(
                    f"""
                    SELECT * FROM ai_trace_spans
                    WHERE {' AND '.join(conditions)}
                    ORDER BY created_at ASC, id ASC
                    """,
                    params,
                ).fetchall()
                return [self._row_to_ai_span(dict(row)) for row in rows]
        except Exception as exc:
            logger.error("AI Trace timeline 查询失败: %s", exc)
            return []

    @staticmethod
    def _row_to_ai_span(data: dict[str, Any]) -> dict[str, Any]:
        data["variables_preview"] = _json_load(data.get("variables_preview"), None)
        data["prompt_preview"] = _json_load(data.get("prompt_preview"), None)
        data["response_preview"] = _json_load(data.get("response_preview"), None)
        data["metadata"] = _json_load(data.get("metadata"), {})
        return data
