import sqlite3
from contextlib import contextmanager

from application.ai_invocation.dtos import (
    AdoptionDecision,
    ContinuationRef,
    InvocationPolicy,
    InvocationSession,
    InvocationSessionStatus,
    InvocationSpec,
    PromptSnapshot,
    VariableBinding,
    VariablePlan,
)
from application.ai_invocation.contracts.chapter_prose_generation import (
    CONTINUATION_HANDLER_KEY,
    OUTPUT_BINDING_SET_ID,
    NODE_KEY,
    _output_bindings,
    register_chapter_prose_generation_continuation,
    project_chapter_prose_to_chapters,
)
from application.ai_invocation.services import AdoptionCommitService
from application.ai_invocation.variable_hub import InMemoryVariableHubRepository, VariableWrite
from domain.ai.value_objects.prompt import Prompt
from application.ai_invocation.prompt_variables import (
    aliases_with_dotted_variables,
    prompt_declared_input_bindings,
)
from application.ai_invocation.input_materialization import materialize_input_variables
from application.ai_invocation.prompt_assembler import CPMSPromptAssembler
from infrastructure.ai.prompt_template_engine import PromptTemplateEngine


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
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(novel_id, number)
            );
            """
        )

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


def test_project_chapter_prose_updates_existing_chapter():
    db = _Db()
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO chapters (id, novel_id, number, title, content, status, word_count) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("chapter-1", "novel-1", 2, "旧章", "旧正文", "draft", 3),
        )

    result = project_chapter_prose_to_chapters(
        db,
        {
            "projection_key": "chapter_prose_to_chapters_v1",
            "adapter": "chapters_table",
            "novel_id": "novel-1",
            "chapter_number": 2,
            "content": "新的正文",
            "word_count": 4,
        },
    )

    row = db.fetch_one("SELECT content, status, word_count FROM chapters WHERE id = ?", ("chapter-1",))
    assert result["action"] == "updated"
    assert row == {"content": "新的正文", "status": "draft", "word_count": 4}


def test_project_chapter_prose_refuses_empty_overwrite():
    db = _Db()
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO chapters (id, novel_id, number, title, content, status, word_count) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("chapter-1", "novel-1", 2, "旧章", "旧正文", "draft", 3),
        )

    result = project_chapter_prose_to_chapters(
        db,
        {
            "adapter": "chapters_table",
            "novel_id": "novel-1",
            "chapter_number": 2,
            "content": " ",
        },
    )

    row = db.fetch_one("SELECT content FROM chapters WHERE id = ?", ("chapter-1",))
    assert result == {"blocked": True, "reason": "empty_content_refuses_overwrite"}
    assert row == {"content": "旧正文"}


def test_project_chapter_prose_inserts_missing_chapter():
    db = _Db()

    result = project_chapter_prose_to_chapters(
        db,
        {
            "adapter": "chapters_table",
            "novel_id": "novel-1",
            "chapter_number": 3,
            "content": "新章节正文",
            "word_count": 5,
        },
    )

    row = db.fetch_one("SELECT novel_id, number, content, status, word_count FROM chapters WHERE number = ?", (3,))
    assert result["action"] == "inserted"
    assert row == {
        "novel_id": "novel-1",
        "number": 3,
        "content": "新章节正文",
        "status": "draft",
        "word_count": 5,
    }


def test_chapter_prose_output_payload_writes_generated_and_accepted_variables():
    repo = InMemoryVariableHubRepository()
    repo.set_bindings(OUTPUT_BINDING_SET_ID, NODE_KEY, _output_bindings(), direction="output")
    session = InvocationSession(
        id="session-1",
        operation="chapter.generate.prose",
        node_key=NODE_KEY,
        policy=InvocationPolicy.FULL_INTERACTIVE,
        context={"novel_id": "novel-1", "chapter_number": 2},
        prompt_snapshot=PromptSnapshot(
            prompt=Prompt(system="s", user="u"),
            node_key=NODE_KEY,
            node_version_id="node-v1",
            output_binding_set_id=OUTPUT_BINDING_SET_ID,
            input_binding_set_id="chapter-prose-generation:input:v1",
            asset_link_set_id="",
            variable_snapshot_hash="vars",
            template_hash="template",
            composition_hash="composition",
            rendered_prompt_hash="rendered",
        ),
    )
    decision = AdoptionDecision(
        id="decision-1",
        session_id="session-1",
        attempt_id="attempt-1",
        accepted_content="正文",
    )

    result = AdoptionCommitService(variable_hub_repository=repo)._commit_variable_outputs(
        session=session,
        decision=decision,
        commit_id="commit-1",
        output_payload={"content": "正文", "accepted_content": "正文"},
    )

    assert not result.get("skipped")
    generated = repo.get_value("chapter.prose.generated", "novel_id:novel-1|chapter_number:2")
    accepted = repo.get_value("chapter.prose.accepted", "novel_id:novel-1|chapter_number:2")
    assert generated is not None and generated.value == "正文"
    assert accepted is not None and accepted.value == "正文"


def test_chapter_prose_commit_writes_outputs_and_projects_to_chapters(monkeypatch):
    db = _Db()
    repo = InMemoryVariableHubRepository()
    repo.set_bindings(OUTPUT_BINDING_SET_ID, NODE_KEY, _output_bindings(), direction="output")
    register_chapter_prose_generation_continuation()
    monkeypatch.setattr(
        "infrastructure.persistence.database.connection.get_database",
        lambda: db,
    )
    session = InvocationSession(
        id="session-1",
        operation="chapter.generate.prose",
        node_key=NODE_KEY,
        policy=InvocationPolicy.FULL_INTERACTIVE,
        status=InvocationSessionStatus.AWAITING_COMMIT,
        context={"novel_id": "novel-1", "chapter_number": 4},
        continuation=ContinuationRef(handler_key=CONTINUATION_HANDLER_KEY),
        prompt_snapshot=PromptSnapshot(
            prompt=Prompt(system="s", user="u"),
            node_key=NODE_KEY,
            node_version_id="node-v1",
            output_binding_set_id=OUTPUT_BINDING_SET_ID,
            input_binding_set_id="chapter-prose-generation:input:v1",
            asset_link_set_id="",
            variable_snapshot_hash="vars",
            template_hash="template",
            composition_hash="composition",
            rendered_prompt_hash="rendered",
        ),
    )
    decision = AdoptionDecision(
        id="decision-1",
        session_id="session-1",
        attempt_id="attempt-1",
        accepted_content="完整正文",
    )

    commit = AdoptionCommitService(variable_hub_repository=repo).commit(session=session, decision=decision)

    row = db.fetch_one("SELECT content, status, word_count FROM chapters WHERE novel_id = ? AND number = ?", ("novel-1", 4))
    generated = repo.get_value("chapter.prose.generated", "novel_id:novel-1|chapter_number:4")
    accepted = repo.get_value("chapter.prose.accepted", "novel_id:novel-1|chapter_number:4")
    assert commit.status.value == "succeeded"
    assert session.status == InvocationSessionStatus.COMPLETED
    assert row == {"content": "完整正文", "status": "draft", "word_count": 4}
    assert generated is not None and generated.value == "完整正文"
    assert accepted is not None and accepted.value == "完整正文"
    assert [step.name for step in commit.steps] == [
        "commit_content_patch",
        "commit_prompt_version",
        "continuation_handler",
        "commit_variable_outputs",
        "commit_projection",
    ]


def test_chapter_prose_inputs_are_materialized_to_variable_hub():
    repo = InMemoryVariableHubRepository()
    input_binding_set_id = "chapter-prose-generation:input:v1"
    repo.set_bindings(
        input_binding_set_id,
        NODE_KEY,
        [
            VariableBinding("novel_title", "novel.title", True, scope="novel", stage="setup"),
            VariableBinding("chapter_outline", "chapter.outline", True, scope="chapter", stage="writing"),
        ],
        direction="input",
    )
    spec = InvocationSpec(
        operation="chapter.generate.prose",
        node_key=NODE_KEY,
        input_binding_set_id=input_binding_set_id,
    )
    session = InvocationSession(
        id="session-1",
        operation="chapter.generate.prose",
        node_key=NODE_KEY,
        policy=InvocationPolicy.FULL_INTERACTIVE,
        context={"novel_id": "novel-1", "chapter_number": 2},
    )
    variable_plan = VariablePlan(aliases={"novel_title": "小说名", "chapter_outline": "章节大纲"})

    result = materialize_input_variables(
        variable_hub_repository=repo,
        session=session,
        spec=spec,
        variable_plan=variable_plan,
        updated_by="test",
    )

    title = repo.get_value("novel.title", "novel_id:novel-1|chapter_number:2")
    outline = repo.get_value("chapter.outline", "novel_id:novel-1|chapter_number:2")
    assert not result.get("skipped")
    assert title is not None and title.value == "小说名"
    assert outline is not None and outline.value == "章节大纲"
    assert session.metadata["input_variable_materialization"]["written"]


class _FakeNode:
    active_version_id = "node-v1"

    def get_active_system(self):
        return "要求：{{ chapter.special_requirement }}"

    def get_active_user_template(self):
        return "大纲：{chapter_outline}"


class _FakeRegistry:
    def get_node(self, node_key, use_cache=True):
        return _FakeNode()


def test_cpms_prompt_assembler_renders_dotted_variable_keys():
    spec = InvocationSpec(
        operation="chapter.generate.prose",
        node_key=NODE_KEY,
        prompt_node_version_id="node-v1",
    )
    variable_plan = VariablePlan(
        aliases={"chapter_outline": "追击"},
        snapshot_items=(
            {
                "key": "chapter_special_requirement",
                "variable_key": "chapter.special_requirement",
                "value": "雨夜压迫感",
            },
        ),
    )

    snapshot = CPMSPromptAssembler(
        registry=_FakeRegistry(),
        template_engine=PromptTemplateEngine(),
    ).compile(spec=spec, variable_plan=variable_plan)

    assert "雨夜压迫感" in snapshot.prompt.system
    assert "追击" in snapshot.prompt.user


def test_prompt_declared_dotted_variable_becomes_binding_and_render_alias():
    repo = InMemoryVariableHubRepository()
    spec = InvocationSpec(
        operation="chapter.generate.prose",
        node_key=NODE_KEY,
        input_binding_set_id="chapter-prose-generation:input:v1",
    )
    session = InvocationSession(
        id="session-1",
        operation="chapter.generate.prose",
        node_key=NODE_KEY,
        policy=InvocationPolicy.FULL_INTERACTIVE,
        context={"novel_id": "novel-1", "chapter_number": 2},
        variable_plan=VariablePlan(aliases={}),
    )

    bindings, added = prompt_declared_input_bindings(
        existing_bindings=[],
        system_template="",
        user_template="请注意 {{chapter.special_requirement}}",
    )
    repo.set_bindings("chapter-prose-generation:input:v1", NODE_KEY, bindings, direction="input")
    bindings = repo.get_bindings("chapter-prose-generation:input:v1", NODE_KEY)
    binding = next(item for item in bindings if item.variable_key == "chapter.special_requirement")

    repo.set_value(
        VariableWrite(
            key="chapter.special_requirement",
            value="雨夜压迫感",
            context_key="novel_id:novel-1|chapter_number:2",
            scope="chapter",
            stage="writing",
        )
    )
    render_vars = aliases_with_dotted_variables({
        binding.alias: "雨夜压迫感",
        binding.variable_key: "雨夜压迫感",
    })

    assert added == [{"alias": "chapter_special_requirement", "variable_key": "chapter.special_requirement"}]
    assert binding.alias == "chapter_special_requirement"
    assert binding.required is True
    assert render_vars["chapter"]["special_requirement"] == "雨夜压迫感"
