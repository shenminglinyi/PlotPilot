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
            CREATE TABLE variable_values (
                id TEXT PRIMARY KEY,
                variable_key TEXT NOT NULL,
                scope_level TEXT NOT NULL DEFAULT 'global',
                scope_key TEXT NOT NULL DEFAULT 'global',
                value_json TEXT NOT NULL,
                value_hash TEXT NOT NULL DEFAULT '',
                version_number INTEGER NOT NULL DEFAULT 1,
                is_current INTEGER NOT NULL DEFAULT 1,
                source_session_id TEXT NOT NULL DEFAULT '',
                source_attempt_id TEXT NOT NULL DEFAULT '',
                source_trace_id TEXT NOT NULL DEFAULT '',
                source_node_key TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                metadata_json TEXT NOT NULL DEFAULT '{}'
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
    assert decision.discard_transient_invocations is False


def test_recovery_policy_discards_stopped_paused_prose_review_gate():
    db = _Db()
    db.execute(
        "INSERT INTO novels (id, current_stage, autopilot_status) VALUES ('novel-1', 'paused_for_review', 'stopped')"
    )
    db.execute(
        "INSERT INTO chapters (id, novel_id, number, status, content) VALUES ('c1', 'novel-1', 1, 'draft', '')"
    )
    db.execute(
        """
        INSERT INTO ai_invocation_sessions (id, operation, status, context_json, metadata_json)
        VALUES (
          's-prose',
          'autopilot.chapter.prose',
          'completed',
          '{"novel_id":"novel-1","chapter_number":1}',
          '{"stage":"writing","commit_owner":"story_pipeline_save_step"}'
        )
        """
    )
    db.execute(
        """
        INSERT INTO variable_values
          (id, variable_key, scope_level, scope_key, value_json, is_current, source_session_id)
        VALUES
          ('v1', 'chapter.prose.draft', 'novel', 'novel_id:novel-1|chapter_number:1', '"旧正文"', 1, 's-prose')
        """
    )

    policy = AutopilotRecoveryPolicy(db)
    decision = policy.decide_on_start("novel-1")

    assert decision.next_stage == "writing"
    assert decision.preserve_review_gate is False
    assert decision.discard_transient_generation is True
    assert decision.discard_transient_invocations is True
    assert decision.reason == "discard_interrupted_review_gate"

    policy.apply_transient_cleanup(decision)

    assert db.fetch_one("SELECT status FROM ai_invocation_sessions WHERE id = 's-prose'")["status"] == "cancelled"
    assert db.fetch_one("SELECT is_current FROM variable_values WHERE id = 'v1'")["is_current"] == 0


def test_recovery_policy_discards_stopped_paused_macro_review_gate_before_structure_applied():
    db = _Db()
    db.execute(
        "INSERT INTO novels (id, current_stage, autopilot_status) VALUES ('novel-1', 'paused_for_review', 'stopped')"
    )
    db.execute(
        """
        INSERT INTO ai_invocation_sessions (id, operation, status, context_json, metadata_json)
        VALUES (
          's-macro',
          'autopilot.macro.plan',
          'completed',
          '{"novel_id":"novel-1"}',
          '{"stage":"planning"}'
        )
        """
    )
    db.execute(
        """
        INSERT INTO variable_values
          (id, variable_key, scope_level, scope_key, value_json, is_current, source_session_id)
        VALUES
          ('v1', 'novel.planning.macro.parts', 'novel', 'novel_id:novel-1', '[]', 1, 's-macro')
        """
    )

    policy = AutopilotRecoveryPolicy(db)
    decision = policy.decide_on_start("novel-1")

    assert decision.next_stage == "macro_planning"
    assert decision.discard_transient_invocations is True

    policy.apply_transient_cleanup(decision)

    assert db.fetch_one("SELECT status FROM ai_invocation_sessions WHERE id = 's-macro'")["status"] == "cancelled"
    assert db.fetch_one("SELECT is_current FROM variable_values WHERE id = 'v1'")["is_current"] == 0


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
