from types import SimpleNamespace

from application.ai_invocation.dtos import (
    AdoptionDecision,
    ContinuationRef,
    InvocationPolicy,
    InvocationSession,
    InvocationSessionStatus,
    PromptSnapshot,
)
from application.ai_invocation.continuation import register_continuation_handler
from application.ai_invocation.services import AdoptionCommitService
from application.ai_invocation.variable_hub import InMemoryVariableHubRepository
from domain.ai.value_objects.prompt import Prompt


class FakePromptManager:
    def __init__(self):
        self.update_calls = []
        self.node = SimpleNamespace(
            id="node-id-1",
            node_key="chapter-test",
            active_version_id="version-1",
        )

    def ensure_seeded(self):
        return True

    def get_node(self, node_key: str, by_key: bool = True):
        if node_key == "chapter-test" and by_key:
            return self.node
        return None

    def update_node(self, node_id: str, **kwargs):
        self.update_calls.append((node_id, kwargs))
        self.node = SimpleNamespace(
            id=node_id,
            node_key="chapter-test",
            active_version_id="version-2",
        )
        return self.node


def _session(*, draft_prompt: Prompt, template_prompt: Prompt) -> InvocationSession:
    return InvocationSession(
        id="session-1",
        operation="chapter.generate",
        node_key="chapter-test",
        policy=InvocationPolicy.FULL_INTERACTIVE,
        status=InvocationSessionStatus.AWAITING_COMMIT,
        prompt_snapshot=PromptSnapshot(
            prompt=Prompt(system="运行时系统", user="运行时用户"),
            node_key="chapter-test",
            node_version_id="version-1",
            asset_link_set_id="",
            input_binding_set_id="",
            output_binding_set_id="",
            variable_snapshot_hash="",
            template_hash="template-hash",
            composition_hash="composition-hash",
            rendered_prompt_hash="rendered-hash",
            template_prompt=template_prompt,
            draft_prompt=draft_prompt,
        ),
    )


def _decision() -> AdoptionDecision:
    return AdoptionDecision(
        id="decision-1",
        session_id="session-1",
        attempt_id="attempt-1",
        accepted_content="生成正文",
        accepted_by="user",
    )


def _worldbuilding_session() -> InvocationSession:
    return InvocationSession(
        id="session-1",
        operation="bible.setup.worldbuilding",
        node_key="bible-worldbuilding",
        policy=InvocationPolicy.FULL_INTERACTIVE,
        status=InvocationSessionStatus.AWAITING_COMMIT,
        context={"novel_id": "novel-1"},
        prompt_snapshot=PromptSnapshot(
            prompt=Prompt(system="系统提示词", user="用户提示词"),
            node_key="bible-worldbuilding",
            node_version_id="version-1",
            asset_link_set_id="",
            input_binding_set_id="bible-worldbuilding:input:v1",
            output_binding_set_id="bible-worldbuilding:output:v1",
            variable_snapshot_hash="",
            template_hash="template-hash",
            composition_hash="composition-hash",
            rendered_prompt_hash="rendered-hash",
            template_prompt=Prompt(system="系统提示词", user="用户提示词"),
        ),
    )


def test_commit_writes_edited_prompt_draft_back_to_cpms():
    mgr = FakePromptManager()
    service = AdoptionCommitService(prompt_manager=mgr)
    session = _session(
        template_prompt=Prompt(system="原系统提示词", user="原用户提示词"),
        draft_prompt=Prompt(system="改后系统提示词", user="改后用户提示词"),
    )

    commit = service.commit(session=session, decision=_decision())

    assert session.status == InvocationSessionStatus.COMPLETED
    assert mgr.update_calls == [
        (
            "node-id-1",
            {
                "system_prompt": "改后系统提示词",
                "user_template": "改后用户提示词",
                "change_summary": "AI Invocation 采纳写回: chapter.generate",
            },
        )
    ]
    step = next(item for item in commit.steps if item.name == "commit_prompt_version")
    assert step.result["skipped"] is False
    assert step.result["previous_version_id"] == "version-1"
    assert step.result["active_version_id"] == "version-2"
    assert commit.result["prompt_version"]["active_version_id"] == "version-2"
    assert session.prompt_snapshot is not None
    assert session.prompt_snapshot.template_prompt is not None
    assert session.prompt_snapshot.template_prompt.system == "改后系统提示词"
    assert session.prompt_snapshot.template_prompt.user == "改后用户提示词"
    assert session.prompt_snapshot.draft_prompt == session.prompt_snapshot.template_prompt


def test_commit_does_not_create_prompt_version_when_draft_is_unchanged():
    mgr = FakePromptManager()
    service = AdoptionCommitService(prompt_manager=mgr)
    prompt = Prompt(system="原系统提示词", user="原用户提示词")
    session = _session(template_prompt=prompt, draft_prompt=prompt)

    commit = service.commit(session=session, decision=_decision())

    assert mgr.update_calls == []
    step = next(item for item in commit.steps if item.name == "commit_prompt_version")
    assert step.result == {"skipped": True, "reason": "draft_unchanged"}
    assert "prompt_version" not in commit.result


def test_commit_variable_outputs_requires_declared_output_bindings():
    repo = InMemoryVariableHubRepository()
    service = AdoptionCommitService(prompt_manager=FakePromptManager(), variable_hub_repository=repo)
    session = _session(
        template_prompt=Prompt(system="原系统提示词", user="原用户提示词"),
        draft_prompt=Prompt(system="原系统提示词", user="原用户提示词"),
    )
    session.node_key = "bible-worldbuilding"

    commit = service.commit(session=session, decision=_decision())

    step = next(item for item in commit.steps if item.name == "commit_variable_outputs")
    assert step.result == {"skipped": True, "reason": "no_output_bindings"}
    assert repo.values == {}


def test_bible_worldbuilding_commit_registers_and_writes_variable_outputs():
    repo = InMemoryVariableHubRepository()
    service = AdoptionCommitService(prompt_manager=FakePromptManager(), variable_hub_repository=repo)
    session = _worldbuilding_session()
    register_continuation_handler(
        "test_bible_worldbuilding",
        lambda _ctx: {
            "worldbuilding": {
                "core_rules": {"power_system": "体系A"},
                "geography": {"terrain": "地形A"},
            },
            "worldbuilding_full": "核心法则：体系A\n地理生态：地形A",
            "core_rules": {"power_system": "体系A"},
            "geography": {"terrain": "地形A"},
            "style": "克制冷峻",
        },
    )
    session.continuation = ContinuationRef(handler_key="test_bible_worldbuilding")
    decision = AdoptionDecision(
        id="decision-1",
        session_id="session-1",
        attempt_id="attempt-1",
        accepted_content="{}",
        accepted_by="user",
    )

    commit = service.commit(session=session, decision=decision)

    step = next(item for item in commit.steps if item.name == "commit_variable_outputs")
    assert step.result["skipped"] is False
    assert repo.get_value("novel.worldbuilding.core_rules", "novel_id:novel-1").value["power_system"] == "体系A"
    assert repo.get_value("novel.worldbuilding.geography", "novel_id:novel-1").value["terrain"] == "地形A"
    assert "体系A" in repo.get_value("novel.worldbuilding.full", "novel_id:novel-1").value
    assert repo.get_value("novel.style.guide", "novel_id:novel-1").value == "克制冷峻"


def test_commit_blocks_when_continuation_contract_fails():
    service = AdoptionCommitService(prompt_manager=FakePromptManager(), variable_hub_repository=InMemoryVariableHubRepository())
    session = _worldbuilding_session()
    session.operation = "setup.main_plot_options"
    session.node_key = "planning-main-plot-option"
    session.continuation = ContinuationRef(handler_key="test_failing_continuation")
    register_continuation_handler(
        "test_failing_continuation",
        lambda _ctx: (_ for _ in ()).throw(ValueError("主线候选数量不足：需要至少 3 条有效方案")),
    )
    decision = AdoptionDecision(
        id="decision-1",
        session_id="session-1",
        attempt_id="attempt-1",
        accepted_content='{"plot_options":[{"id":"only_one"}',
        accepted_by="user",
    )

    commit = service.commit(session=session, decision=decision)

    assert session.status == InvocationSessionStatus.BLOCKED
    assert commit.status.value == "failed"
    step = next(item for item in commit.steps if item.name == "continuation_handler")
    assert step.status.value == "failed"
    assert "主线候选数量不足" in step.error
