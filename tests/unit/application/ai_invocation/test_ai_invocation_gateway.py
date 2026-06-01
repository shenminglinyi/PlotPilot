from types import SimpleNamespace

import pytest

from application.ai_invocation.dtos import (
    InvocationPolicy,
    InvocationRequest,
    InvocationSessionStatus,
    InvocationSpec,
    VariableBinding,
)
from application.ai_invocation.continuation import register_continuation_handler
from application.ai_invocation.gateway import AIInvocationGateway
from application.ai_invocation.prompt_assembler import CPMSPromptAssembler, PromptAssemblyError
from application.ai_invocation.services import InvocationSessionService
from application.ai_invocation.services import AttemptService
from application.ai_invocation.dtos import InvocationSession
from application.ai_invocation.spec_service import InMemoryInvocationSpecRepository, InvocationSpecService
from application.ai_invocation.variable_hub import (
    InMemoryVariableHubRepository,
    VariableDefinition,
    VariableResolver,
    VariableWrite,
    VariableValue,
)
from domain.ai.services.llm_service import GenerationResult
from domain.ai.value_objects.token_usage import TokenUsage


class FakeNode:
    active_version_id = "node-version-1"

    def __init__(self):
        self.node_key = "chapter-test"

    def get_active_system(self):
        return "你是{{ role }}。"

    def get_active_user_template(self):
        return "写：{{ outline }} / {{ bible }}"


_DEFAULT_NODE = object()


class FakeRegistry:
    def __init__(self, node=_DEFAULT_NODE):
        self.node = FakeNode() if node is _DEFAULT_NODE else node

    def get_node(self, node_key: str, use_cache: bool = True):
        if node_key == "chapter-test":
            return self.node
        return None


class FakeLLM:
    def __init__(self):
        self.calls = []

    async def generate(self, prompt, config):
        self.calls.append((prompt, config))
        return GenerationResult(
            content="生成正文",
            token_usage=TokenUsage(input_tokens=3, output_tokens=4),
        )

    async def stream_generate(self, prompt, config):
        yield "生成正文"


class FakeStreamingLLM:
    async def generate(self, prompt, config):
        return GenerationResult(
            content="生成正文",
            token_usage=TokenUsage(input_tokens=3, output_tokens=4),
        )

    async def stream_generate(self, prompt, config):
        yield "第一段"
        yield "第二段"


def _spec(policy=InvocationPolicy.DIRECT):
    return InvocationSpec(
        operation="chapter.generate",
        node_key="chapter-test",
        prompt_node_version_id="node-version-1",
        asset_link_set_id="asset-set-1",
        input_binding_set_id="binding-set-1",
        output_binding_set_id="output-set-1",
        default_policy=policy,
        metadata={"asset_version_ids": ["asset-v1"]},
    )


def _resolver():
    repo = InMemoryVariableHubRepository()
    repo.add_definition(VariableDefinition(key="novel.bible", default="默认设定"))
    repo.set_value(VariableValue(key="novel.bible", value="变量中心设定", context_key="novel_id:novel-1"))
    repo.set_bindings(
        "binding-set-1",
        "chapter-test",
        [
            VariableBinding(alias="outline", required=True),
            VariableBinding(alias="bible", variable_key="novel.bible", required=True),
            VariableBinding(alias="role", default="专业小说家"),
        ],
    )
    return VariableResolver(repo)


def test_variable_resolver_context_key_includes_beat_index():
    repo = InMemoryVariableHubRepository()
    repo.set_bindings(
        "binding-set-1",
        "chapter-test",
        [
            VariableBinding(alias="outline", required=True),
        ],
    )
    plan = VariableResolver(repo).resolve(
        spec=InvocationSpec(operation="autopilot.prose.from_script", node_key="chapter-test", input_binding_set_id="binding-set-1"),
        explicit_variables={"outline": "第一拍"},
        context={"novel_id": "novel-1", "chapter_number": 2, "beat_index": 3},
    )
    assert plan.ok
    assert plan.snapshot_hash


def test_variable_resolver_uses_explicit_then_hub_then_default():
    plan = _resolver().resolve(
        spec=_spec(),
        explicit_variables={"outline": "第一幕冲突"},
        context={"novel_id": "novel-1"},
    )

    assert plan.ok
    assert plan.aliases["outline"] == "第一幕冲突"
    assert plan.aliases["bible"] == "变量中心设定"
    assert plan.aliases["role"] == "专业小说家"
    assert plan.lineage["outline"] == "explicit"
    assert plan.snapshot_hash


def test_variable_resolver_reports_required_missing():
    plan = _resolver().resolve(
        spec=_spec(),
        explicit_variables={},
        context={"novel_id": "novel-1"},
    )

    assert not plan.ok
    assert plan.required_missing == ("outline",)
    assert "必填变量缺失: outline" in plan.diagnostics


def test_variable_resolver_materializes_main_plot_context_blob():
    repo = InMemoryVariableHubRepository()
    repo.set_bindings(
        "plot-input",
        "planning-main-plot-option",
        [
            VariableBinding(alias="premise", variable_key="novel.setup.premise", required=True),
            VariableBinding(alias="worldbuilding_full", variable_key="novel.worldbuilding.full", required=False),
            VariableBinding(alias="protagonist", variable_key="novel.characters.protagonist", required=False),
        ],
    )
    repo.set_value(VariableWrite(key="novel.setup.premise", value="旧城少年破局", context_key="novel_id:novel-1"))
    repo.set_value(VariableWrite(key="novel.worldbuilding.full", value="旧城由债务法则统治", context_key="novel_id:novel-1"))
    repo.set_value(VariableWrite(key="novel.characters.protagonist", value={"name": "阿澄"}, context_key="novel_id:novel-1"))

    plan = VariableResolver(repo).resolve(
        spec=InvocationSpec(
            operation="setup.main_plot_options",
            node_key="planning-main-plot-option",
            input_binding_set_id="plot-input",
        ),
        explicit_variables={},
        context={"novel_id": "novel-1"},
    )

    assert plan.ok
    assert "setup_main_plot_options_v1" in plan.aliases["context_blob"]
    assert "旧城少年破局" in plan.aliases["context_blob"]
    assert plan.lineage["context_blob"] == "materialized:materialized.setup.main_plot_context"


def test_prompt_assembler_freezes_snapshot_without_package_fallback():
    plan = _resolver().resolve(
        spec=_spec(),
        explicit_variables={"outline": "第一幕冲突"},
        context={"novel_id": "novel-1"},
    )
    snapshot = CPMSPromptAssembler(registry=FakeRegistry()).compile(spec=_spec(), variable_plan=plan)

    assert snapshot.prompt.system == "你是专业小说家。"
    assert "第一幕冲突" in snapshot.prompt.user
    assert snapshot.node_version_id == "node-version-1"
    assert snapshot.asset_version_ids == ("asset-v1",)
    assert snapshot.variable_snapshot_hash == plan.snapshot_hash
    assert snapshot.rendered_prompt_hash


def test_prompt_assembler_fast_fails_when_node_not_published():
    plan = _resolver().resolve(
        spec=_spec(),
        explicit_variables={"outline": "第一幕冲突"},
        context={"novel_id": "novel-1"},
    )
    assembler = CPMSPromptAssembler(registry=FakeRegistry(node=None))

    with pytest.raises(PromptAssemblyError, match="CPMS 节点未发布"):
        assembler.compile(
            spec=InvocationSpec(operation="x", node_key="missing", prompt_node_version_id="v"),
            variable_plan=plan,
        )


@pytest.mark.asyncio
async def test_gateway_direct_runs_common_prefix_and_attempt():
    llm = FakeLLM()
    repo = InMemoryInvocationSpecRepository([_spec(InvocationPolicy.DIRECT)])
    gateway = AIInvocationGateway(
        spec_service=InvocationSpecService(repo),
        variable_resolver=_resolver(),
        prompt_assembler=CPMSPromptAssembler(registry=FakeRegistry()),
        llm_service=llm,
        session_service=InvocationSessionService(),
    )

    result = await gateway.invoke(
        InvocationRequest(
            operation="chapter.generate",
            node_key="chapter-test",
            variables={"outline": "第一幕冲突"},
            context={"novel_id": "novel-1"},
        )
    )

    assert result.session.status == InvocationSessionStatus.COMPLETED
    assert result.attempt is not None
    assert result.decision is not None
    assert result.commit is not None
    assert result.attempt.content == "生成正文"
    assert result.decision.accepted_content == "生成正文"
    assert result.commit.steps[0].name == "commit_content_patch"
    assert len(llm.calls) == 1
    assert llm.calls[0][0] == result.prompt_snapshot.prompt


@pytest.mark.asyncio
async def test_gateway_review_after_call_waits_for_acceptance():
    llm = FakeLLM()
    repo = InMemoryInvocationSpecRepository([_spec(InvocationPolicy.REVIEW_AFTER_CALL)])
    gateway = AIInvocationGateway(
        spec_service=InvocationSpecService(repo),
        variable_resolver=_resolver(),
        prompt_assembler=CPMSPromptAssembler(registry=FakeRegistry()),
        llm_service=llm,
    )

    result = await gateway.invoke(
        InvocationRequest(
            operation="chapter.generate",
            node_key="chapter-test",
            variables={"outline": "第一幕冲突"},
            context={"novel_id": "novel-1"},
        )
    )

    assert result.session.status == InvocationSessionStatus.AWAITING_ACCEPTANCE
    assert result.attempt is not None


@pytest.mark.asyncio
async def test_attempt_service_streaming_stop_marks_attempt_cancelled_context():
    service = AttemptService(FakeStreamingLLM())
    session = InvocationSession(
        id="session-1",
        operation="autopilot.prose.from_script",
        node_key="autopilot-stream-beat",
        policy=InvocationPolicy.DIRECT,
    )
    snapshot = CPMSPromptAssembler(registry=FakeRegistry()).compile(spec=_spec(), variable_plan=_resolver().resolve(
        spec=_spec(),
        explicit_variables={"outline": "第一幕冲突"},
        context={"novel_id": "novel-1"},
    ))

    attempt = await service.generate_streaming(
        session=session,
        prompt_snapshot=snapshot,
        on_chunk=lambda chunk, content: False,
    )

    assert attempt.status.value == "failed"
    assert session.status == InvocationSessionStatus.CANCELLED
    assert attempt.content == "第一段"
    assert result.decision is None
    assert result.commit is None


@pytest.mark.asyncio
async def test_gateway_interactive_stops_before_llm():
    llm = FakeLLM()
    repo = InMemoryInvocationSpecRepository([_spec(InvocationPolicy.FULL_INTERACTIVE)])
    gateway = AIInvocationGateway(
        spec_service=InvocationSpecService(repo),
        variable_resolver=_resolver(),
        prompt_assembler=CPMSPromptAssembler(registry=FakeRegistry()),
        llm_service=llm,
    )

    result = await gateway.invoke(
        InvocationRequest(
            operation="chapter.generate",
            node_key="chapter-test",
            variables={"outline": "第一幕冲突"},
            context={"novel_id": "novel-1"},
        )
    )

    assert result.session.status == InvocationSessionStatus.AWAITING_PRE_CALL_REVIEW
    assert result.attempt is None
    assert len(llm.calls) == 0


@pytest.mark.asyncio
async def test_gateway_full_interactive_attaches_continuation_key():
    llm = FakeLLM()
    repo = InMemoryInvocationSpecRepository(
        [
            InvocationSpec(
                operation="setup.main_plot_options",
                node_key="chapter-test",
                prompt_node_version_id="node-version-1",
                asset_link_set_id="asset-set-1",
                input_binding_set_id="binding-set-1",
                output_binding_set_id="output-set-1",
                default_policy=InvocationPolicy.FULL_INTERACTIVE,
                continuation_handler_key="setup_main_plot_options",
            )
        ]
    )
    gateway = AIInvocationGateway(
        spec_service=InvocationSpecService(repo),
        variable_resolver=_resolver(),
        prompt_assembler=CPMSPromptAssembler(registry=FakeRegistry()),
        llm_service=llm,
    )

    result = await gateway.invoke(
        InvocationRequest(
            operation="setup.main_plot_options",
            node_key="chapter-test",
            variables={"outline": "第一幕冲突"},
            context={"novel_id": "novel-1"},
        )
    )

    assert result.session.status == InvocationSessionStatus.AWAITING_PRE_CALL_REVIEW
    assert result.session.continuation is not None
    assert result.session.continuation.handler_key == "setup_main_plot_options"


@pytest.mark.asyncio
async def test_gateway_review_after_call_produces_attempt_for_acceptance():
    llm = FakeLLM()
    repo = InMemoryInvocationSpecRepository([_spec(InvocationPolicy.REVIEW_AFTER_CALL)])
    gateway = AIInvocationGateway(
        spec_service=InvocationSpecService(repo),
        variable_resolver=_resolver(),
        prompt_assembler=CPMSPromptAssembler(registry=FakeRegistry()),
        llm_service=llm,
    )

    result = await gateway.invoke(
        InvocationRequest(
            operation="chapter.generate",
            node_key="chapter-test",
            variables={"outline": "第一幕冲突"},
            context={"novel_id": "novel-1"},
        )
    )

    assert result.session.status == InvocationSessionStatus.AWAITING_ACCEPTANCE
    assert result.attempt is not None
    assert result.decision is None
    assert result.commit is None
