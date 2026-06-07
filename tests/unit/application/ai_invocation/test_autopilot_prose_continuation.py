import sqlite3

from application.ai_invocation.autopilot.continuations import register_autopilot_continuations
from application.ai_invocation.continuation import ContinuationContext, execute_continuation
from application.ai_invocation.dtos import (
    AdoptionDecision,
    ContinuationRef,
    InvocationPolicy,
    InvocationSession,
    InvocationSessionStatus,
)


class _Db:
    def __init__(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE chapters (
                id TEXT PRIMARY KEY,
                novel_id TEXT NOT NULL,
                number INTEGER NOT NULL,
                title TEXT,
                content TEXT,
                outline TEXT,
                status TEXT DEFAULT 'draft',
                word_count INTEGER DEFAULT 0,
                tension_score REAL DEFAULT 0,
                plot_tension REAL DEFAULT 0,
                emotional_tension REAL DEFAULT 0,
                pacing_tension REAL DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(novel_id, number)
            );
            CREATE TABLE novels (
                id TEXT PRIMARY KEY,
                autopilot_status TEXT DEFAULT 'running',
                current_stage TEXT DEFAULT 'writing',
                current_auto_chapters INTEGER DEFAULT 0,
                current_chapter_in_act INTEGER DEFAULT 0,
                current_beat_index INTEGER DEFAULT 0,
                beats_completed INTEGER DEFAULT 0,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO novels (id) VALUES ('novel-1');
            """
        )

    def execute(self, sql, params=()):
        return self.conn.execute(sql, params)

    def commit(self):
        self.conn.commit()

    def fetch_one(self, sql, params=()):
        row = self.conn.execute(sql, params).fetchone()
        return dict(row) if row else None


def _patch_db(monkeypatch, db):
    import application.paths
    import infrastructure.persistence.database.connection

    monkeypatch.setattr(application.paths, "get_db_path", lambda: "")
    monkeypatch.setattr(infrastructure.persistence.database.connection, "get_database", lambda *_args, **_kwargs: db)


def test_autopilot_beat_prose_commit_is_idempotent(monkeypatch):
    db = _Db()
    _patch_db(monkeypatch, db)
    register_autopilot_continuations()
    session = InvocationSession(
        id="session-1",
        operation="autopilot.prose.from_script",
        node_key="autopilot-stream-beat",
        policy=InvocationPolicy.AUTOPILOT_PAUSE,
        status=InvocationSessionStatus.AWAITING_COMMIT,
        context={"novel_id": "novel-1", "chapter_number": 1, "beat_index": 0},
        continuation=ContinuationRef(handler_key="autopilot_prose_generation"),
    )
    decision = AdoptionDecision(
        id="decision-1",
        session_id="session-1",
        attempt_id="attempt-1",
        accepted_content="第一段正文。",
    )

    execute_continuation(ContinuationContext(session=session, decision=decision))
    execute_continuation(ContinuationContext(session=session, decision=decision))

    chapter = db.fetch_one("SELECT content, status, word_count FROM chapters WHERE novel_id = ? AND number = ?", ("novel-1", 1))
    novel = db.fetch_one("SELECT current_stage, current_beat_index FROM novels WHERE id = ?", ("novel-1",))
    assert chapter == {"content": "第一段正文。", "status": "draft", "word_count": 6}
    assert novel == {"current_stage": "writing", "current_beat_index": 1}


def test_autopilot_full_chapter_accept_completes_once_and_moves_to_audit(monkeypatch):
    db = _Db()
    _patch_db(monkeypatch, db)
    register_autopilot_continuations()
    session = InvocationSession(
        id="session-2",
        operation="autopilot.chapter.prose",
        node_key="chapter-prose-generation",
        policy=InvocationPolicy.AUTOPILOT_PAUSE,
        status=InvocationSessionStatus.AWAITING_COMMIT,
        context={"novel_id": "novel-1", "chapter_number": 2, "beat_index": 0},
        continuation=ContinuationRef(handler_key="autopilot_prose_generation"),
    )
    decision = AdoptionDecision(
        id="decision-2",
        session_id="session-2",
        attempt_id="attempt-2",
        accepted_content="完整章节正文。",
    )

    execute_continuation(ContinuationContext(session=session, decision=decision))
    execute_continuation(ContinuationContext(session=session, decision=decision))

    chapter = db.fetch_one("SELECT content, status, word_count FROM chapters WHERE novel_id = ? AND number = ?", ("novel-1", 2))
    novel = db.fetch_one(
        """
        SELECT current_stage, current_auto_chapters, current_chapter_in_act, current_beat_index
        FROM novels WHERE id = ?
        """,
        ("novel-1",),
    )
    assert chapter == {"content": "完整章节正文。", "status": "completed", "word_count": 7}
    assert novel == {
        "current_stage": "auditing",
        "current_auto_chapters": 1,
        "current_chapter_in_act": 1,
        "current_beat_index": 0,
    }
