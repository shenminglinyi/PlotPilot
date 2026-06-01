from types import SimpleNamespace

from application.ai_invocation.dtos import (
    AdoptionDecision,
    InvocationPolicy,
    InvocationSession,
    InvocationSessionStatus,
    PromptSnapshot,
)
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
