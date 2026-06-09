import sqlite3

from application.engine.services.autopilot_recovery_policy import AutopilotRecoveryPolicy


class _Db:
    def __init__(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE novels (
                id TEXT PRIMARY KEY,
                current_stage TEXT DEFAULT 'writing',
                autopilot_status TEXT DEFAULT 'running'
            );
            CREATE TABLE chapters (
                id TEXT PRIMARY KEY,
                novel_id TEXT NOT NULL,
                number INTEGER NOT NULL,
                status TEXT DEFAULT 'draft',
                content TEXT DEFAULT '',
                UNIQUE(novel_id, number)
            );
            CREATE TABLE story_nodes (
                id TEXT PRIMARY KEY,
                novel_id TEXT NOT NULL,
                number INTEGER NOT NULL,
                node_type TEXT NOT NULL
            );
            CREATE TABLE ai_invocation_sessions (
                id TEXT PRIMARY KEY,
                operation TEXT,
                status TEXT,
                context_json TEXT DEFAULT '{}',
                metadata_json TEXT DEFAULT '{}',
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE ai_adoption_decisions (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                attempt_id TEXT DEFAULT '',
                decision TEXT DEFAULT 'accepted',
                accepted_by TEXT DEFAULT ''
            );
            """
        )

    def execute(self, sql, params=()):
        return self.conn.execute(sql, params)

    def fetch_one(self, sql, params=()):
        row = self.conn.execute(sql, params).fetchone()
        return dict(row) if row else None

    def fetch_all(self, sql, params=()):
        return [dict(row) for row in self.conn.execute(sql, params).fetchall()]

    def commit(self):
        self.conn.commit()


def test_recovery_policy_retries_writing_and_discards_transient_generation():
    db = _Db()
    db.execute("INSERT INTO novels (id, current_stage) VALUES ('novel-1', 'writing')")
    db.execute("INSERT INTO chapters (id, novel_id, number, status, content) VALUES ('c1', 'novel-1', 1, 'draft', '半章')")

    decision = AutopilotRecoveryPolicy(db).decide_on_start("novel-1")

    assert decision.next_stage == "writing"
    assert decision.chapter_number == 1
    assert decision.discard_transient_generation is True
    assert decision.reason == "retry_writing_step"


def test_recovery_policy_preserves_completed_chapter_for_auditing():
    db = _Db()
    db.execute("INSERT INTO novels (id, current_stage) VALUES ('novel-1', 'auditing')")
    db.execute("INSERT INTO chapters (id, novel_id, number, status, content) VALUES ('c1', 'novel-1', 2, 'completed', '完整正文')")

    decision = AutopilotRecoveryPolicy(db).decide_on_start("novel-1")

    assert decision.next_stage == "auditing"
    assert decision.chapter_number == 2
    assert decision.discard_transient_generation is False
    assert decision.reason == "completed_chapter_reaudit"


def test_recovery_policy_preserves_paused_review_gate():
    db = _Db()
    db.execute("INSERT INTO novels (id, current_stage) VALUES ('novel-1', 'paused_for_review')")

    decision = AutopilotRecoveryPolicy(db).decide_on_start("novel-1")

    assert decision.next_stage == "paused_for_review"
    assert decision.preserve_review_gate is True
    assert decision.clear_pending_invocation is False


def test_recovery_policy_preserves_legacy_writing_resume_semantics():
    db = _Db()
    db.execute("INSERT INTO novels (id, current_stage) VALUES ('novel-1', 'writing')")
    db.execute("INSERT INTO chapters (id, novel_id, number, status, content) VALUES ('c1', 'novel-1', 1, 'draft', '半章')")

    decision = AutopilotRecoveryPolicy(db, story_pipeline_writing_enabled=False).decide_on_start("novel-1")

    assert decision.next_stage == "writing"
    assert decision.chapter_number == 1
    assert decision.discard_transient_generation is False
    assert decision.reason == "resume_legacy_writing"


def test_recovery_cleanup_cancels_only_retryable_pending_invocations():
    db = _Db()
    db.execute("INSERT INTO novels (id, current_stage) VALUES ('novel-1', 'writing')")
    db.execute(
        """
        INSERT INTO ai_invocation_sessions (id, operation, status, context_json, metadata_json)
        VALUES
          ('s-retry', 'autopilot.chapter.prose', 'generating', '{"novel_id":"novel-1"}', '{"stage":"writing"}'),
          ('s-review', 'autopilot.chapter.review', 'awaiting_acceptance', '{"novel_id":"novel-1"}', '{"stage":"paused_for_review"}'),
          ('s-human', 'autopilot.chapter.prose', 'awaiting_acceptance', '{"novel_id":"novel-1"}', '{"stage":"writing"}')
        """
    )
    db.execute(
        "INSERT INTO ai_adoption_decisions (id, session_id, accepted_by) VALUES ('d1', 's-human', 'user')"
    )

    policy = AutopilotRecoveryPolicy(db)
    decision = policy.decide_on_start("novel-1")
    assert decision.clear_pending_invocation is True

    policy.apply_transient_cleanup(decision)

    statuses = {
        row["id"]: row["status"]
        for row in db.fetch_all("SELECT id, status FROM ai_invocation_sessions", ())
    }
    assert statuses["s-retry"] == "cancelled"
    assert statuses["s-review"] == "awaiting_acceptance"
    assert statuses["s-human"] == "awaiting_acceptance"
