import sys

import pytest

from application.ai_invocation.autopilot.intents import AutopilotInvocationIntent
from application.ai_invocation.autopilot.orchestrator import AutopilotInvocationOrchestrator
from application.ai_invocation.autopilot.publisher import AutopilotSessionPublisher
from application.ai_invocation.dtos import InvocationPolicy, InvocationSpec, VariableBinding
from application.ai_invocation.prompt_assembler import CPMSPromptAssembler
from application.ai_invocation.services import AdoptionCommitService, AdoptionService, AttemptService, InvocationSessionService
from application.ai_invocation.spec_service import InMemoryInvocationSpecRepository, InvocationSpecService
from application.ai_invocation.variable_hub import InMemoryVariableHubRepository, VariableResolver
from domain.ai.services.llm_service import GenerationResult
from domain.ai.value_objects.token_usage import TokenUsage


class _Node:
    active_version_id = "node-v1"

    def get_active_system(self):
        return "system {{ role }}"

    def get_active_user_template(self):
        return "user {{ outline }}"


class _Registry:
    def get_node(self, node_key: str, use_cache: bool = True):
        return _Node()


class _TemplateEngine:
    def render(self, system_template: str, user_template: str, variables: dict, variable_schemas=None):
        class Result:
            system = system_template.replace("{{ role }}", str(variables.get("role", "")))
            user = user_template.replace("{{ outline }}", str(variables.get("outline", "")))
            warnings = []
            missing_variables = []

        return Result()


class _LLM:
    async def generate(self, prompt, config):
        return GenerationResult(
            content="generated",
            token_usage=TokenUsage(input_tokens=1, output_tokens=1),
        )

    async def stream_generate(self, prompt, config):
        yield "generated"


class _Publisher:
    def __init__(self):
        self.events = []

    def publish(self, novel_id, payload):
        self.events.append((novel_id, dict(payload)))


@pytest.mark.asyncio
async def test_autopilot_direct_request_publishes_active_session_before_completion():
    variable_repo = InMemoryVariableHubRepository()
    variable_repo.set_bindings(
        "input",
        "node",
        [
            VariableBinding(alias="outline", required=True),
            VariableBinding(alias="role", default="writer"),
        ],
    )
    publisher = _Publisher()
    orchestrator = AutopilotInvocationOrchestrator(
        spec_service=InvocationSpecService(
            InMemoryInvocationSpecRepository(
                [
                    InvocationSpec(
                        operation="autopilot.test",
                        node_key="node",
                        prompt_node_version_id="node-v1",
                        input_binding_set_id="input",
                        default_policy=InvocationPolicy.DIRECT,
                    )
                ]
            )
        ),
        variable_resolver=VariableResolver(variable_repo),
        prompt_assembler=CPMSPromptAssembler(registry=_Registry(), template_engine=_TemplateEngine()),
        llm_service=_LLM(),
        publisher=publisher,
        session_service=InvocationSessionService(),
        attempt_service=AttemptService(_LLM()),
        adoption_service=AdoptionService(),
        commit_service=AdoptionCommitService(variable_hub_repository=variable_repo),
    )

    outcome = await orchestrator.request(
        AutopilotInvocationIntent(
            novel_id="novel-1",
            stage="writing",
            operation="autopilot.test",
            node_key="node",
            explicit_variables={"outline": "outline"},
            policy_hint=InvocationPolicy.DIRECT,
        )
    )

    assert outcome.status == "completed"
    assert len(publisher.events) >= 2
    first_payload = publisher.events[0][1]
    last_payload = publisher.events[-1][1]
    assert first_payload["active_invocation_session_id"]
    assert first_payload["has_active_invocation"] is True
    assert first_payload["active_invocation_status"] == "prompt_compiled"
    assert last_payload["active_invocation_session_id"] == first_payload["active_invocation_session_id"]
    assert last_payload["has_active_invocation"] is False
    assert last_payload["active_invocation_status"] == "completed"


def test_autopilot_session_publisher_uses_shared_state_without_importing_interfaces_main(monkeypatch):
    shared = {}
    monkeypatch.setitem(sys.modules, "__shared_state", shared)

    publisher = AutopilotSessionPublisher()
    publisher.publish(
        "novel-1",
        {
            "active_invocation_session_id": "session-1",
            "active_invocation_status": "prompt_compiled",
            "has_active_invocation": True,
            "requires_ai_review": True,
        },
    )

    state = shared["novel:novel-1"]
    assert state["novel_id"] == "novel-1"
    assert state["active_invocation_session_id"] == "session-1"
    assert state["active_invocation_status"] == "prompt_compiled"
    assert state["has_active_invocation"] is True
    assert state["requires_ai_review"] is True
    assert "_daemon_heartbeat" in shared

    monkeypatch.delitem(sys.modules, "__shared_state", raising=False)


def test_autopilot_session_publisher_does_not_fallback_to_interfaces_main_in_daemon(monkeypatch):
    monkeypatch.delitem(sys.modules, "__shared_state", raising=False)
    monkeypatch.setattr("multiprocessing.current_process", lambda: type("P", (), {"daemon": True})())

    def fail_import(name, *args, **kwargs):
        if name == "interfaces.main":
            raise AssertionError("daemon publisher must not import interfaces.main")
        return real_import(name, *args, **kwargs)

    real_import = __import__
    monkeypatch.setattr("builtins.__import__", fail_import)

    AutopilotSessionPublisher().publish("novel-1", {"active_invocation_session_id": "session-1"})
