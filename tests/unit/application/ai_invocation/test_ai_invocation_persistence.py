import sqlite3
from contextlib import contextmanager
from pathlib import Path

from application.ai_invocation.dtos import (
    InvocationAttempt,
    InvocationAttemptStatus,
    InvocationPolicy,
    InvocationSession,
    InvocationSessionStatus,
    InvocationSpec,
    PromptSnapshot,
    VariableBinding,
    VariablePlan,
)
from application.ai_invocation.variable_hub import VariableWrite
from domain.ai.value_objects.prompt import Prompt
from domain.ai.value_objects.token_usage import TokenUsage
from infrastructure.persistence.database.sqlite_ai_invocation_repository import (
    SqliteAdoptionRepository,
    SqliteInvocationAttemptRepository,
    SqliteInvocationSessionRepository,
    SqliteInvocationSpecRepository,
    SqliteVariableHubRepository,
)


class _Db:
    def __init__(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        migration = Path(
            "infrastructure/persistence/database/migrations/add_ai_invocation_variable_hub.sql"
        ).read_text(encoding="utf-8")
        self.conn.executescript(migration)

    @contextmanager
    def transaction(self):
        try:
            yield self.conn
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def fetch_one(self, sql, params=()):
        row = self.conn.execute(sql, params).fetchone()
        return dict(row) if row else None

    def fetch_all(self, sql, params=()):
        return [dict(row) for row in self.conn.execute(sql, params).fetchall()]


def _snapshot() -> PromptSnapshot:
    return PromptSnapshot(
        prompt=Prompt(system="系统提示词", user="用户提示词"),
        node_key="chapter-generation-main",
        node_version_id="node-v1",
        asset_link_set_id="asset-link-set-v1",
        input_binding_set_id="input-binding-v1",
        output_binding_set_id="output-binding-v1",
        variable_snapshot_hash="variable-hash",
        template_hash="template-hash",
        composition_hash="composition-hash",
        rendered_prompt_hash="rendered-hash",
        asset_version_ids=("asset-v1",),
    )


def test_sqlite_invocation_spec_repository_roundtrip():
    db = _Db()
    repo = SqliteInvocationSpecRepository(db)
    spec = InvocationSpec(
        operation="chapter.generate",
        node_key="chapter-generation-main",
        prompt_node_version_id="node-v1",
        asset_link_set_id="asset-link-set-v1",
        input_binding_set_id="input-binding-v1",
        output_binding_set_id="output-binding-v1",
        default_policy=InvocationPolicy.FULL_INTERACTIVE,
        supports_stream=True,
        metadata={"source": "test"},
    )

    repo.upsert(spec, spec_id="spec-1")

    loaded = repo.get("chapter.generate", "chapter-generation-main")
    assert loaded is not None
    assert loaded.default_policy == InvocationPolicy.FULL_INTERACTIVE
    assert loaded.asset_link_set_id == "asset-link-set-v1"
    assert loaded.metadata["source"] == "test"


def test_sqlite_invocation_session_attempt_adoption_roundtrip():
    db = _Db()
    session_repo = SqliteInvocationSessionRepository(db)
    attempt_repo = SqliteInvocationAttemptRepository(db)
    adoption_repo = SqliteAdoptionRepository(db)
    plan = VariablePlan(
        aliases={"novel_id": "novel-1"},
        bindings=(VariableBinding(alias="novel_id", variable_key="novel.id", required=True),),
        lineage={"novel_id": "explicit"},
        snapshot_hash="variable-hash",
    )
    session = InvocationSession(
        id="session-1",
        operation="chapter.generate",
        node_key="chapter-generation-main",
        policy=InvocationPolicy.REVIEW_AFTER_CALL,
        status=InvocationSessionStatus.AWAITING_ACCEPTANCE,
        context={"novel_id": "novel-1"},
        prompt_snapshot=_snapshot(),
        variable_plan=plan,
        attempts=["attempt-1"],
    )
    attempt = InvocationAttempt(
        id="attempt-1",
        session_id="session-1",
        status=InvocationAttemptStatus.SUCCEEDED,
        prompt_snapshot=_snapshot(),
        content="正文内容",
        token_usage=TokenUsage(input_tokens=10, output_tokens=20),
    )

    session_repo.save(session)
    attempt_repo.save(attempt)
    decision = adoption_repo.create_decision(
        session_id="session-1",
        attempt_id="attempt-1",
        accepted_content="正文内容",
    )
    commit = adoption_repo.create_commit(session_id="session-1", decision_id=decision.id)
    adoption_repo.upsert_step(
        commit_id=commit.id,
        step_name="commit_content_patch",
        status="succeeded",
        result={"content_saved": True},
    )

    loaded_session = session_repo.get("session-1")
    loaded_attempt = attempt_repo.get("attempt-1")
    assert loaded_session is not None
    assert loaded_session.prompt_snapshot is not None
    assert loaded_session.variable_plan is not None
    assert loaded_session.variable_plan.aliases["novel_id"] == "novel-1"
    assert loaded_attempt is not None
    assert loaded_attempt.content == "正文内容"
    assert loaded_attempt.token_usage is not None
    assert loaded_attempt.token_usage.total_tokens == 30
    assert db.fetch_one("SELECT status FROM ai_adoption_commit_steps WHERE commit_id = ?", (commit.id,))[
        "status"
    ] == "succeeded"


def test_sqlite_variable_hub_repository_resolves_bindings_and_current_value():
    db = _Db()
    with db.transaction() as conn:
        conn.execute(
            """
            INSERT INTO variable_definitions (
                id, variable_key, display_name, value_type, default_value_json, status
            ) VALUES ('var-def-1', 'novel.bible', '设定', 'string', '"默认设定"', 'active')
            """
        )
        conn.execute(
            """
            INSERT INTO variable_values (
                id, variable_key, scope_level, scope_key, value_json, value_hash, version_number, is_current
            ) VALUES ('var-value-1', 'novel.bible', 'novel', 'novel_id:novel-1', '"变量中心设定"', 'hash', 1, 1)
            """
        )
        conn.execute(
            """
            INSERT INTO cpms_variable_binding_sets (
                id, node_key, direction, version_number, status, is_active
            ) VALUES ('binding-set-1', 'chapter-test', 'input', 1, 'active', 1)
            """
        )
        conn.execute(
            """
            INSERT INTO cpms_variable_bindings (
                id, binding_set_id, node_key, direction, alias, variable_key, required, enabled
            ) VALUES ('binding-1', 'binding-set-1', 'chapter-test', 'input', 'bible', 'novel.bible', 1, 1)
            """
        )

    repo = SqliteVariableHubRepository(db)
    bindings = repo.get_bindings("binding-set-1", "chapter-test")
    value = repo.get_value("novel.bible", "novel_id:novel-1")
    definition = repo.get_definition("novel.bible")

    assert bindings[0].alias == "bible"
    assert bindings[0].required is True
    assert value is not None
    assert value.value == "变量中心设定"
    assert definition is not None
    assert definition.default == "默认设定"


def test_sqlite_variable_hub_repository_writes_current_value_and_lineage():
    db = _Db()
    repo = SqliteVariableHubRepository(db)

    first = repo.set_value(
        VariableWrite(
            key="novel.characters.list",
            value=[{"name": "阿澄"}],
            context_key="novel_id:novel-1",
            source_session_id="session-1",
            source_attempt_id="attempt-1",
            source_trace_id="trace-1",
            source_node_key="bible-characters",
            source_commit_id="commit-1",
            lineage={"alias": "characters"},
            value_type="list",
            display_name="角色列表",
            stage="characters",
        )
    )
    second = repo.set_value(
        VariableWrite(
            key="novel.characters.list",
            value=[{"name": "阿澄"}, {"name": "林墨"}],
            context_key="novel_id:novel-1",
            source_session_id="session-2",
            source_attempt_id="attempt-2",
            source_trace_id="trace-2",
            source_node_key="bible-characters",
            source_commit_id="commit-2",
            lineage={"alias": "characters"},
            value_type="list",
            display_name="角色列表",
            stage="characters",
        )
    )

    current = repo.get_value("novel.characters.list", "novel_id:novel-1")
    rows = db.fetch_all("SELECT version_number, is_current FROM variable_values WHERE variable_key = ? ORDER BY version_number", ("novel.characters.list",))
    lineage = db.fetch_one(
        "SELECT source_session_id, source_attempt_id, source_node_key FROM variable_lineage WHERE source_commit_id = ?",
        ("commit-2",),
    )

    assert first is not None and first.version_number == 1
    assert second is not None and second.version_number == 2
    assert current is not None
    assert current.value == [{"name": "阿澄"}, {"name": "林墨"}]
    assert rows == [{"version_number": 1, "is_current": 0}, {"version_number": 2, "is_current": 1}]
    assert lineage == {
        "source_session_id": "session-2",
        "source_attempt_id": "attempt-2",
        "source_node_key": "bible-characters",
    }
