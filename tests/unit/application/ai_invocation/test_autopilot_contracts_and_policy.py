from application.ai_invocation.autopilot.materializers import ChapterContextMaterializer
from application.ai_invocation.autopilot.policy import AutopilotInvocationPolicyResolver
from application.ai_invocation.contracts import InvocationContractRegistry
from application.ai_invocation.contracts.autopilot_planning import ensure_autopilot_macro_plan_contract
from application.ai_invocation.dtos import InvocationPolicy, InvocationSpec
from application.ai_invocation.variable_hub import InMemoryVariableHubRepository


def test_chapter_context_materializer_writes_variable_hub_payload():
    repo = InMemoryVariableHubRepository()
    materializer = ChapterContextMaterializer()

    payload = materializer.materialize(
        bundle={"voice_anchors": "冷峻克制"},
        outline="第一幕冲突",
        target_chapter_words=2400,
        repository=repo,
        context_key="novel_id:novel-1|chapter_number:1",
    )

    assert payload["chapter.outline"] == "第一幕冲突"
    assert repo.get_value("chapter.outline", "novel_id:novel-1|chapter_number:1").value == "第一幕冲突"
    assert repo.get_value("runtime.continuity_hint", "novel_id:novel-1|chapter_number:1").value == "冷峻克制"


def test_policy_resolver_prefers_auto_approve_and_defaults():
    resolver = AutopilotInvocationPolicyResolver()

    assert resolver.resolve(operation="autopilot.outline.partition", node_key="outline-beat-partition", novel=None) == InvocationPolicy.AUTOPILOT_PAUSE
    assert resolver.resolve(operation="autopilot.outline.partition", node_key="outline-beat-partition", novel=type("N", (), {"auto_approve_mode": True})()) == InvocationPolicy.DIRECT
    assert resolver.resolve(operation="autopilot.prose.from_script", node_key="autopilot-stream-beat", novel=None) == InvocationPolicy.AUTOPILOT_PAUSE
    assert resolver.resolve(operation="autopilot.prose.from_script", node_key="autopilot-stream-beat", novel=type("N", (), {"auto_approve_mode": True})()) == InvocationPolicy.DIRECT
    assert resolver.resolve(operation="autopilot.chapter.audit", node_key="audit-node", novel=None) == InvocationPolicy.DIRECT
    assert resolver.resolve(
        operation="autopilot.chapter.audit",
        node_key="audit-node",
        novel=None,
        context={"force_interactive": "true"},
    ) == InvocationPolicy.AUTOPILOT_PAUSE


def test_invocation_contract_registry_uses_autopilot_contract_entrypoint(monkeypatch):
    called = {}

    def fake_ensure(db):
        called["db"] = db

    class FakeSpecRepository:
        def __init__(self, db):
            self.db = db

        def get(self, operation, node_key):
            return InvocationSpec(operation=operation, node_key=node_key)

    monkeypatch.setattr(
        "application.ai_invocation.contracts.autopilot_planning.ensure_autopilot_outline_partition_contract",
        fake_ensure,
    )
    monkeypatch.setattr(
        "infrastructure.persistence.database.sqlite_ai_invocation_repository.SqliteInvocationSpecRepository",
        FakeSpecRepository,
    )
    db = object()
    registry = InvocationContractRegistry(db)

    spec = registry.ensure_published("autopilot.outline.partition", "outline-beat-partition")

    assert called["db"] is db
    assert spec.operation == "autopilot.outline.partition"
    assert spec.node_key == "outline-beat-partition"


def test_invocation_contract_registry_supports_autopilot_stream_beat(monkeypatch):
    called = {}

    def fake_ensure(db):
        called["db"] = db

    class FakeSpecRepository:
        def __init__(self, db):
            self.db = db

        def get(self, operation, node_key):
            return InvocationSpec(operation=operation, node_key=node_key)

    monkeypatch.setattr(
        "application.ai_invocation.contracts.autopilot_writing.ensure_autopilot_stream_beat_contract",
        fake_ensure,
    )
    monkeypatch.setattr(
        "infrastructure.persistence.database.sqlite_ai_invocation_repository.SqliteInvocationSpecRepository",
        FakeSpecRepository,
    )
    db = object()
    registry = InvocationContractRegistry(db)

    spec = registry.ensure_published("autopilot.prose.from_script", "autopilot-stream-beat")

    assert called["db"] is db
    assert spec.operation == "autopilot.prose.from_script"
    assert spec.node_key == "autopilot-stream-beat"


def test_invocation_contract_registry_supports_autopilot_macro_plan(monkeypatch):
    called = {}

    def fake_ensure(db):
        called["db"] = db

    class FakeSpecRepository:
        def __init__(self, db):
            self.db = db

        def get(self, operation, node_key):
            return InvocationSpec(operation=operation, node_key=node_key)

    monkeypatch.setattr(
        "application.ai_invocation.contracts.autopilot_planning.ensure_autopilot_macro_plan_contract",
        fake_ensure,
    )
    monkeypatch.setattr(
        "infrastructure.persistence.database.sqlite_ai_invocation_repository.SqliteInvocationSpecRepository",
        FakeSpecRepository,
    )
    db = object()
    registry = InvocationContractRegistry(db)

    spec = registry.ensure_published("autopilot.macro.plan", "planning-quick-macro")

    assert called["db"] is db
    assert spec.operation == "autopilot.macro.plan"
    assert spec.node_key == "planning-quick-macro"


def test_invocation_contract_registry_supports_autopilot_act_plan(monkeypatch):
    called = {}

    def fake_ensure(db):
        called["db"] = db

    class FakeSpecRepository:
        def __init__(self, db):
            self.db = db

        def get(self, operation, node_key):
            return InvocationSpec(operation=operation, node_key=node_key)

    monkeypatch.setattr(
        "application.ai_invocation.contracts.autopilot_planning.ensure_autopilot_act_plan_contract",
        fake_ensure,
    )
    monkeypatch.setattr(
        "infrastructure.persistence.database.sqlite_ai_invocation_repository.SqliteInvocationSpecRepository",
        FakeSpecRepository,
    )
    db = object()
    registry = InvocationContractRegistry(db)

    spec = registry.ensure_published("autopilot.act.plan", "planning-act")

    assert called["db"] is db
    assert spec.operation == "autopilot.act.plan"
    assert spec.node_key == "planning-act"


def test_autopilot_macro_plan_contract_uses_novel_scope_for_story_level_bindings(monkeypatch):
    captured = {}

    class FakeVariableRepo:
        def __init__(self, db):
            self.db = db

        def set_bindings(self, binding_set_id, node_key, bindings, *, direction="input"):
            captured[(binding_set_id, direction)] = list(bindings)

    class FakeSpecRepo:
        def __init__(self, db):
            self.db = db

        def upsert(self, spec, **kwargs):
            captured["spec"] = spec

    monkeypatch.setattr(
        "application.ai_invocation.contracts.autopilot_planning._template_aliases",
        lambda node_key, declared: [
            "premise",
            "target_chapters",
            "worldview",
            "characters",
            "genre_opening_profile",
        ],
    )
    monkeypatch.setattr(
        "application.ai_invocation.contracts.autopilot_planning._active_node_version",
        lambda node_key: "node-v1",
    )
    monkeypatch.setattr(
        "application.ai_invocation.contracts.autopilot_planning.SqliteVariableHubRepository",
        FakeVariableRepo,
    )
    monkeypatch.setattr(
        "application.ai_invocation.contracts.autopilot_planning.SqliteInvocationSpecRepository",
        FakeSpecRepo,
    )

    ensure_autopilot_macro_plan_contract(db=object())

    input_bindings = {
        binding.alias: binding
        for binding in captured[("planning-quick-macro:input:autopilot:v1", "input")]
    }
    output_bindings = {
        binding.alias: binding
        for binding in captured[("planning-quick-macro:output:autopilot:v1", "output")]
    }

    assert input_bindings["premise"].scope == "novel"
    assert input_bindings["premise"].stage == "setup"
    assert input_bindings["target_chapters"].scope == "novel"
    assert input_bindings["characters"].scope == "novel"
    assert input_bindings["genre_opening_profile"].scope == "novel"
    assert input_bindings["worldview"].scope == "novel"
    assert input_bindings["worldview"].stage == "planning"
    assert output_bindings["parts"].scope == "novel"
    assert output_bindings["parts"].stage == "planning"
