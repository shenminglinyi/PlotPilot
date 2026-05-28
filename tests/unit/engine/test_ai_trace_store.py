import sqlite3
from pathlib import Path

from engine.infrastructure.persistence.trace_store import SqliteTraceStore


class _Pool:
    def __init__(self, path: Path):
        self.path = path

    def get_connection(self):
        return sqlite3.connect(self.path)


def test_ai_trace_store_records_timeline(tmp_path):
    store = SqliteTraceStore(_Pool(tmp_path / "trace.db"))

    store.record_ai_span(
        {
            "trace_id": "trace-1",
            "span_id": "span-1",
            "novel_id": "novel-1",
            "operation": "chapter_generation",
            "phase": "prompt_rendered",
            "contract_key": "chapter-generation-main",
            "variables_preview": {"novel_id": "novel-1"},
            "variables_full": {"novel_id": "novel-1", "chapter_content": "完整正文"},
            "variable_sources": [{"name": "novel_id", "source": "prompt:chapter-generation-main"}],
            "prompt_preview": {"user": "写第一章"},
            "prompt_full": {"system": "系统全文", "user": "用户全文"},
            "metadata": {"fallback_used": False},
            "created_at": "2026-05-28T00:00:00.000+00:00",
        }
    )
    store.record_ai_span(
        {
            "trace_id": "trace-1",
            "span_id": "span-2",
            "parent_span_id": "span-1",
            "novel_id": "novel-1",
            "operation": "chapter_generation",
            "phase": "llm_response",
            "response_preview": "预览输出",
            "response_full": "完整输出全文",
            "token_input": 10,
            "token_output": 20,
            "created_at": "2026-05-28T00:00:01.000+00:00",
        }
    )

    summaries = store.list_ai_traces("novel-1")
    assert summaries[0]["trace_id"] == "trace-1"
    assert summaries[0]["span_count"] == 2

    timeline = store.get_ai_timeline("trace-1", "novel-1")
    assert [item["phase"] for item in timeline] == ["prompt_rendered", "llm_response"]
    assert timeline[0]["prompt_preview"] == {"user": "写第一章"}
    assert timeline[0]["variables_full"]["chapter_content"] == "完整正文"
    assert timeline[0]["variable_sources"][0]["source"] == "prompt:chapter-generation-main"
    assert timeline[0]["prompt_full"]["system"] == "系统全文"
    assert timeline[1]["response_full"] == "完整输出全文"


def test_ai_trace_store_auto_migrates_new_fulltext_columns(tmp_path):
    db_path = tmp_path / "trace_migrate.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE ai_trace_spans (
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
        """
    )
    conn.commit()
    conn.close()

    store = SqliteTraceStore(_Pool(db_path))
    timeline_columns = {
        row[1]
        for row in sqlite3.connect(db_path).execute("PRAGMA table_info(ai_trace_spans)").fetchall()
    }
    assert "variables_full" in timeline_columns
    assert "variable_sources" in timeline_columns
    assert "prompt_full" in timeline_columns
    assert "response_full" in timeline_columns
