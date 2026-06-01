from application.ai_invocation.autopilot.materializers import ChapterContextMaterializer
from application.ai_invocation.autopilot.policy import AutopilotInvocationPolicyResolver
from application.ai_invocation.contracts import InvocationContractRegistry
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
    assert resolver.resolve(operation="autopilot.prose.from_script", node_key="autopilot-stream-beat", novel=None) == InvocationPolicy.DIRECT
    assert resolver.resolve(operation="autopilot.chapter.audit", node_key="audit-node", novel=None) == InvocationPolicy.REVIEW_AFTER_CALL


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
