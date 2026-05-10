"""TracePort 实现 — SQLite 溯源落盘

引擎操作审计日志的持久化层。
"""
from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any

from engine.core.ports.ports import TracePort, TraceRecord

logger = logging.getLogger(__name__)


class SqliteTraceStore(TracePort):
    """溯源端口 SQLite 实现"""

    def __init__(self, db_pool):
        self._db_pool = db_pool
        self._ensure_tables()

    def _ensure_tables(self):
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
                conn.commit()
        except Exception as e:
            logger.error("Trace表创建失败: %s", e)

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
                        getattr(trace, 'novel_id', ''),
                        trace.node_type,
                        trace.operation,
                        trace.input_summary[:200] if trace.input_summary else '',
                        trace.output_summary[:200] if trace.output_summary else '',
                        trace.score,
                        json.dumps(trace.violations, ensure_ascii=False),
                        trace.duration_ms,
                        trace.timestamp or datetime.utcnow().isoformat(),
                    )
                )
                conn.commit()
        except Exception as e:
            logger.error("Trace记录失败: %s", e)

    async def query(
        self,
        novel_id: str,
        node_type: Optional[str] = None,
        operation: Optional[str] = None,
        limit: int = 100,
    ) -> List[TraceRecord]:
        try:
            with self._db_pool.get_connection() as conn:
                conn.row_factory = sqlite3.Row
                conditions = ["novel_id = ?"]
                params: list = [novel_id]

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

                results = []
                for row in rows:
                    data = dict(row)
                    results.append(TraceRecord(
                        trace_id=data["trace_id"],
                        node_type=data["node_type"],
                        operation=data["operation"],
                        input_summary=data.get("input_summary", ""),
                        output_summary=data.get("output_summary", ""),
                        score=data.get("score"),
                        violations=json.loads(data.get("violations", "[]")),
                        duration_ms=data.get("duration_ms", 0),
                        timestamp=data.get("timestamp", ""),
                    ))
                return results
        except Exception as e:
            logger.error("Trace查询失败: %s", e)
            return []
