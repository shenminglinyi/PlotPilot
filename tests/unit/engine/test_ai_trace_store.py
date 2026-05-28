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
            "prompt_preview": {"user": "写第一章"},
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
