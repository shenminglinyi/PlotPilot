"""Comprehensive unit tests for Phase A L3 Role-Based Smart Routing & Multi-Role Provider Cache:
- Unified vs Independent endpoint_mode routing across main / cheap / kg
- Prompt.node_key propagation from PromptRegistry & PromptGateway
- Explicit GenerationConfig(role_hint=...) & TraceContext.stage classification
- DAG NodeRegistry.create_executor & scoped_prompt_node_key ContextVar isolation (including exception safety)
- Multi-role warm provider pool lifecycle, targeted slot eviction, shared fallback reference safety, & aclose()
- Graceful fallback to main when cheap / kg profiles are missing or unconfigured
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, AsyncIterator
from unittest.mock import MagicMock

import pytest

from application.ai.llm_control_service import (
    LLMControlConfig,
    LLMControlService,
    LLMProfile,
)
from application.ai.trace_context import (
    TraceContext,
    get_scoped_prompt_node_key,
    reset_current_trace,
    scoped_prompt_node_key,
    set_current_trace,
)
from application.engine.dag.models import NodeCategory, NodeMeta, NodeResult, NodeStatus
from application.engine.dag.registry import BaseNode, NodeRegistry
from domain.ai.services.llm_service import GenerationConfig, GenerationResult, LLMService
from domain.ai.value_objects.prompt import Prompt
from domain.ai.value_objects.token_usage import TokenUsage
from infrastructure.ai.config.settings import Settings
from infrastructure.ai.prompt_gateway import PromptGateway
from infrastructure.ai.prompt_registry import PromptRegistry
from infrastructure.ai.prompt_template_engine import RenderResult
from infrastructure.ai.provider_factory import (
    DynamicLLMService,
    LLMProviderFactory,
    classify_llm_role,
)
from infrastructure.persistence.database.connection import DatabaseConnection


class _RecordingProvider(LLMService):
    def __init__(self, profile: LLMProfile) -> None:
        self.profile_id = profile.id
        self.settings = Settings(
            default_model=profile.model,
            default_temperature=profile.temperature,
            default_max_tokens=profile.max_tokens,
            api_key=profile.api_key,
            base_url=profile.base_url,
            provider_name=profile.name,
            protocol=profile.protocol,
        )
        self.calls: list[tuple[Prompt, GenerationConfig]] = []
        self.stream_calls: list[tuple[Prompt, GenerationConfig]] = []
        self.closed = False
        self.close_count = 0

    async def generate(self, prompt: Prompt, config: GenerationConfig) -> GenerationResult:
        self.calls.append((prompt, config))
        return GenerationResult(
            content=f"[{self.profile_id}:{config.model}] ok",
            token_usage=TokenUsage(input_tokens=10, output_tokens=5),
        )

    async def stream_generate(
        self, prompt: Prompt, config: GenerationConfig
    ) -> AsyncIterator[str]:
        self.stream_calls.append((prompt, config))
        yield f"[{self.profile_id}:{config.model}]"
        yield " stream-ok"

    async def aclose(self) -> None:
        self.closed = True
        self.close_count += 1


class _RecordingFactory(LLMProviderFactory):
    def __init__(self, control_service: LLMControlService) -> None:
        super().__init__(control_service)
        self.created_providers: list[_RecordingProvider] = []

    def create_from_profile(self, profile: LLMProfile | None) -> LLMService:
        if profile is None:
            return super().create_from_profile(None)
        resolved = self.control_service.resolve_profile(profile)
        if not resolved.api_key.strip() or not resolved.model.strip():
            return super().create_from_profile(profile)
        prov = _RecordingProvider(resolved)
        self.created_providers.append(prov)
        return prov


@pytest.fixture()
def routing_setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db = DatabaseConnection(str(tmp_path / "test_role_routing.db"))
    control = LLMControlService(db_provider=lambda: db)
    factory = _RecordingFactory(control)
    llm = DynamicLLMService(factory)

    recorded_spans: list[dict[str, Any]] = []

    class _FakeTraceRecorder:
        def record_span(self, **kwargs: Any) -> None:
            recorded_spans.append(kwargs)

    import infrastructure.ai.provider_factory as pf_module

    monkeypatch.setattr(pf_module, "get_trace_recorder", lambda: _FakeTraceRecorder())

    try:
        yield {
            "db": db,
            "control": control,
            "factory": factory,
            "llm": llm,
            "recorded_spans": recorded_spans,
        }
    finally:
        db.close_all(skip_checkpoint=True)


def _three_role_profiles() -> list[LLMProfile]:
    return [
        LLMProfile(
            id="role-main",
            name="主力模型",
            protocol="openai",
            base_url="http://127.0.0.1:3425/v1",
            model="claude/claude-opus-5-5",
            auth_mode="local_gateway",
        ),
        LLMProfile(
            id="role-cheap",
            name="经济模型",
            protocol="openai",
            base_url="http://127.0.0.1:3425/v1",
            model="workbuddy/deepseek-v4.1-flash",
            auth_mode="local_gateway",
        ),
        LLMProfile(
            id="role-kg",
            name="知识图谱模型",
            protocol="openai",
            base_url="http://127.0.0.1:3425/v1",
            model="antigravity/gemini-4-hydrogen",
            auth_mode="local_gateway",
        ),
    ]


# ── 1. Unified vs Independent Role Routing & Trace Metadata ─────────────


@pytest.mark.asyncio
async def test_unified_mode_routes_all_node_keys_to_main(routing_setup: dict[str, Any]):
    control: LLMControlService = routing_setup["control"]
    llm: DynamicLLMService = routing_setup["llm"]

    control.save_config(
        LLMControlConfig(
            active_profile_id="role-main",
            endpoint_mode="unified",
            role_bindings={
                "main": "role-main",
                "cheap": "role-cheap",
                "kg": "role-kg",
            },
            profiles=_three_role_profiles(),
        )
    )

    for nk in ("chapter-generation-main", "chapter-summarizer", "chapter-narrative-sync"):
        res = await llm.generate(
            Prompt(system="sys", user="usr", node_key=nk),
            GenerationConfig(),
        )
        assert res.content == "[role-main:claude/claude-opus-5-5] ok"

    await llm.aclose()


@pytest.mark.asyncio
async def test_independent_mode_routes_main_cheap_and_kg_accurately(
    routing_setup: dict[str, Any],
):
    control: LLMControlService = routing_setup["control"]
    llm: DynamicLLMService = routing_setup["llm"]
    spans: list[dict[str, Any]] = routing_setup["recorded_spans"]

    control.save_config(
        LLMControlConfig(
            active_profile_id="role-main",
            endpoint_mode="independent",
            role_bindings={
                "main": "role-main",
                "cheap": "role-cheap",
                "kg": "role-kg",
            },
            profiles=_three_role_profiles(),
        )
    )

    # Main nodes
    for nk in ("chapter-generation-main", "bible-all"):
        res = await llm.generate(
            Prompt(system="sys", user="usr", node_key=nk),
            GenerationConfig(),
        )
        assert res.content == "[role-main:claude/claude-opus-5-5] ok"

    # Cheap nodes
    for nk in ("chapter-summarizer", "tension-scoring", "review-character-consistency"):
        res = await llm.generate(
            Prompt(system="sys", user="usr", node_key=nk),
            GenerationConfig(),
        )
        assert res.content == "[role-cheap:workbuddy/deepseek-v4.1-flash] ok"

    # KG nodes (both generate and stream_generate)
    for nk in ("chapter-narrative-sync", "knowledge-initial", "memory-extraction"):
        res = await llm.generate(
            Prompt(system="sys", user="usr", node_key=nk),
            GenerationConfig(),
        )
        assert res.content == "[role-kg:antigravity/gemini-4-hydrogen] ok"

    chunks = [
        c
        async for c in llm.stream_generate(
            Prompt(system="sys", user="usr", node_key="kg-inference"),
            GenerationConfig(),
        )
    ]
    assert "".join(chunks) == "[role-kg:antigravity/gemini-4-hydrogen] stream-ok"

    # Explicit role_hint overrides node_key
    override_res = await llm.generate(
        Prompt(system="sys", user="usr", node_key="chapter-generation-main"),
        GenerationConfig(role_hint="cheap"),
    )
    assert override_res.content == "[role-cheap:workbuddy/deepseek-v4.1-flash] ok"

    # Trace spans record llm_role metadata
    recorded_roles = [
        s["metadata"]["llm_role"]
        for s in spans
        if s.get("phase") == "llm_response" and "metadata" in s
    ]
    assert "main" in recorded_roles
    assert "cheap" in recorded_roles
    assert "kg" in recorded_roles

    await llm.aclose()


def test_prompt_registry_gateway_and_trace_stage_classification():
    # PromptGateway._prompt_from_rendered preserves node_key
    gw_prompt = PromptGateway._prompt_from_rendered(
        node_key="chapter-summarizer",
        system="system instruction",
        user="user body",
    )
    assert gw_prompt.node_key == "chapter-summarizer"
    assert classify_llm_role(gw_prompt) == "cheap"

    # PromptRegistry.render_to_prompt preserves node_key
    fake_mgr = MagicMock()
    fake_node = MagicMock()
    fake_node.get_active_system.return_value = "sys"
    fake_node.get_active_user_template.return_value = "usr"
    fake_mgr.get_node.return_value = fake_node
    fake_engine = MagicMock()
    fake_engine.render.return_value = RenderResult(
        success=True,
        system="sys rendered",
        user="usr rendered",
    )
    reg = PromptRegistry(prompt_manager=fake_mgr, template_engine=fake_engine)
    reg_prompt = reg.render_to_prompt("knowledge-initial", {})
    assert reg_prompt is not None
    assert reg_prompt.node_key == "knowledge-initial"
    assert classify_llm_role(reg_prompt) == "kg"

    # Trace stage fallback when node_key is empty
    bare_prompt = Prompt(system="s", user="u")
    tok = set_current_trace(TraceContext.create(stage="knowledge.extract"))
    try:
        assert classify_llm_role(bare_prompt) == "kg"
    finally:
        reset_current_trace(tok)

    assert classify_llm_role(
        bare_prompt, trace=TraceContext.create(stage="summary.chapter")
    ) == "cheap"
    assert classify_llm_role(
        bare_prompt, trace=TraceContext.create(stage="analyst.tension.score")
    ) == "cheap"
    assert classify_llm_role(
        bare_prompt, trace=TraceContext.create(stage="audit.chapter.review.v1")
    ) == "cheap"
    assert classify_llm_role(bare_prompt) == "main"


# ── 2. DAG scoped_prompt_node_key Isolation & Leak-Free Reset ───────────


@pytest.mark.asyncio
async def test_dag_executor_scoped_prompt_node_key_routes_and_resets_without_leakage(
    routing_setup: dict[str, Any],
):
    control: LLMControlService = routing_setup["control"]
    llm: DynamicLLMService = routing_setup["llm"]

    control.save_config(
        LLMControlConfig(
            active_profile_id="role-main",
            endpoint_mode="independent",
            role_bindings={
                "main": "role-main",
                "cheap": "role-cheap",
                "kg": "role-kg",
            },
            profiles=_three_role_profiles(),
        )
    )

    test_node_type = "_test_dag_kg_sync_node"

    @NodeRegistry.register(test_node_type)
    class _TestKGDAGNode(BaseNode):
        meta = NodeMeta(
            node_type=test_node_type,
            display_name="Test KG Sync Node",
            category=NodeCategory.EXECUTION,
            description="Test node",
            cpms_node_key="chapter-narrative-sync",
        )

        def validate_inputs(self, inputs: dict[str, Any]) -> bool:
            return True

        async def execute(
            self, inputs: dict[str, Any], context: dict[str, Any]
        ) -> NodeResult:
            if context.get("shared_state", {}).get("raise_boom"):
                raise RuntimeError("simulated DAG node failure")
            # Bare Prompt without explicit node_key inside DAG node!
            gen = await llm.generate(Prompt(system="sys", user="usr"), GenerationConfig())
            return NodeResult(status=NodeStatus.SUCCESS, outputs={"out": gen.content})

    try:
        executor = NodeRegistry.create_executor(test_node_type, "node_kg_1")
        out = await executor({})
        assert out["out"] == "[role-kg:antigravity/gemini-4-hydrogen] ok"
        assert get_scoped_prompt_node_key() == ""

        # Subsequent bare Prompt outside DAG MUST route back to main!
        after = await llm.generate(Prompt(system="sys", user="usr"), GenerationConfig())
        assert after.content == "[role-main:claude/claude-opus-5-5] ok"

        # Even if DAG node raises an exception, finally block resets ContextVar cleanly!
        with pytest.raises(RuntimeError, match="simulated DAG node failure"):
            await executor({"raise_boom": True})
        assert get_scoped_prompt_node_key() == ""

        after_err = await llm.generate(
            Prompt(system="sys", user="usr"), GenerationConfig()
        )
        assert after_err.content == "[role-main:claude/claude-opus-5-5] ok"
    finally:
        NodeRegistry._registry.pop(test_node_type, None)
        NodeRegistry._meta_registry.pop(test_node_type, None)
        await llm.aclose()


# ── 3. Multi-Role Provider Cache Lifecycle & Graceful Fallback ──────────


@pytest.mark.asyncio
async def test_multi_role_cache_keeps_three_slots_warm_evicts_changed_slot_and_closes_all(
    routing_setup: dict[str, Any],
):
    control: LLMControlService = routing_setup["control"]
    factory: _RecordingFactory = routing_setup["factory"]
    llm: DynamicLLMService = routing_setup["llm"]

    profiles = _three_role_profiles()
    control.save_config(
        LLMControlConfig(
            active_profile_id="role-main",
            endpoint_mode="independent",
            role_bindings={
                "main": "role-main",
                "cheap": "role-cheap",
                "kg": "role-kg",
            },
            profiles=profiles,
        )
    )

    # Alternate across main -> cheap -> kg twice: only 3 providers created, ZERO closed!
    for _ in range(2):
        await llm.generate(
            Prompt(system="s", user="u", node_key="chapter-generation-main"),
            GenerationConfig(),
        )
        await llm.generate(
            Prompt(system="s", user="u", node_key="chapter-summarizer"),
            GenerationConfig(),
        )
        await llm.generate(
            Prompt(system="s", user="u", node_key="knowledge-initial"),
            GenerationConfig(),
        )

    assert len(factory.created_providers) == 3
    p_main, p_cheap_v1, p_kg = factory.created_providers
    assert p_main.closed is False
    assert p_cheap_v1.closed is False
    assert p_kg.closed is False

    # Update ONLY cheap profile's model -> evicts & closes p_cheap_v1, keeps p_main and p_kg open!
    profiles[1] = profiles[1].model_copy(update={"model": "claude/claude-haiku-5-5"})
    control.save_config(
        LLMControlConfig(
            active_profile_id="role-main",
            endpoint_mode="independent",
            role_bindings={
                "main": "role-main",
                "cheap": "role-cheap",
                "kg": "role-kg",
            },
            profiles=profiles,
        )
    )

    res_cheap_v2 = await llm.generate(
        Prompt(system="s", user="u", node_key="chapter-summarizer"),
        GenerationConfig(),
    )
    assert res_cheap_v2.content == "[role-cheap:claude/claude-haiku-5-5] ok"
    assert len(factory.created_providers) == 4
    p_cheap_v2 = factory.created_providers[3]
    assert p_cheap_v1.closed is True
    assert p_cheap_v1.close_count == 1
    assert p_main.closed is False
    assert p_kg.closed is False
    assert p_cheap_v2.closed is False

    # aclose() closes all remaining warm providers once
    await llm.aclose()
    assert p_main.closed is True and p_main.close_count == 1
    assert p_cheap_v2.closed is True and p_cheap_v2.close_count == 1
    assert p_kg.closed is True and p_kg.close_count == 1


@pytest.mark.asyncio
async def test_graceful_fallback_to_main_when_secondary_profiles_missing_or_incomplete(
    routing_setup: dict[str, Any],
):
    control: LLMControlService = routing_setup["control"]
    factory: _RecordingFactory = routing_setup["factory"]
    llm: DynamicLLMService = routing_setup["llm"]

    main_only = LLMProfile(
        id="role-main",
        name="主力模型",
        protocol="openai",
        base_url="http://127.0.0.1:3425/v1",
        model="claude/claude-opus-5-5",
        auth_mode="local_gateway",
    )
    incomplete_cheap = LLMProfile(
        id="role-cheap",
        name="经济模型",
        protocol="openai",
        base_url="https://api.openai.com/v1",
        api_key="",  # Missing API key!
        model="gpt-4o-mini",
        auth_mode="api_key",
    )
    empty_model_kg = LLMProfile(
        id="role-kg",
        name="知识图谱模型",
        protocol="openai",
        base_url="http://127.0.0.1:3425/v1",
        model="",  # Missing model!
        auth_mode="local_gateway",
    )

    control.save_config(
        LLMControlConfig(
            active_profile_id="role-main",
            endpoint_mode="independent",
            role_bindings={
                "main": "role-main",
                "cheap": "role-cheap",
                "kg": "role-kg",
            },
            profiles=[main_only, incomplete_cheap, empty_model_kg],
        )
    )

    r_main = await llm.generate(
        Prompt(system="s", user="u", node_key="chapter-generation-main"),
        GenerationConfig(),
    )
    r_cheap = await llm.generate(
        Prompt(system="s", user="u", node_key="chapter-summarizer"),
        GenerationConfig(),
    )
    r_kg = await llm.generate(
        Prompt(system="s", user="u", node_key="knowledge-initial"),
        GenerationConfig(),
    )
    assert r_main.content == "[role-main:claude/claude-opus-5-5] ok"
    assert r_cheap.content == "[role-main:claude/claude-opus-5-5] ok"
    assert r_kg.content == "[role-main:claude/claude-opus-5-5] ok"

    # Shared provider pool reused across fallback slots
    assert len(factory.created_providers) == 1
    shared_main_prov = factory.created_providers[0]
    assert shared_main_prov.closed is False

    # Now configure cheap properly: switching cheap away from shared_main_prov MUST NOT close shared_main_prov!
    configured_cheap = incomplete_cheap.model_copy(update={"api_key": "sk-valid-cheap"})
    control.save_config(
        LLMControlConfig(
            active_profile_id="role-main",
            endpoint_mode="independent",
            role_bindings={
                "main": "role-main",
                "cheap": "role-cheap",
                "kg": "role-kg",
            },
            profiles=[main_only, configured_cheap, empty_model_kg],
        )
    )

    r_cheap_now = await llm.generate(
        Prompt(system="s", user="u", node_key="chapter-summarizer"),
        GenerationConfig(),
    )
    assert r_cheap_now.content == "[role-cheap:gpt-4o-mini] ok"
    assert shared_main_prov.closed is False

    # And aclose() closes each unique provider instance once (never double-closing shared_main_prov!)
    await llm.aclose()
    assert shared_main_prov.close_count == 1


@pytest.mark.asyncio
async def test_round3_whitespace_prompt_node_key_falls_back_to_scoped_key():
    """L3-003: Whitespace-only Prompt.node_key normalizes to empty and respects scoped_prompt_node_key."""
    from application.ai.trace_context import TraceContext, scoped_prompt_node_key

    blank_prompt = Prompt(system="sys", user="usr", node_key="   \t  ")
    assert blank_prompt.node_key == ""

    conflicting_trace = TraceContext(trace_id="t-r3", operation="test", stage="knowledge.extract")
    with scoped_prompt_node_key("chapter-summarizer"):
        assert classify_llm_role(blank_prompt, GenerationConfig(), conflicting_trace) == "cheap"
        # Even a duck-typed prompt bypassing Prompt.__post_init__ with whitespace node_key respects scoped key!
        duck_prompt = type("_DuckPrompt", (), {"node_key": "   "})()
        assert classify_llm_role(duck_prompt, GenerationConfig(), conflicting_trace) == "cheap"


@pytest.mark.asyncio
async def test_round3_active_stream_lease_survives_slot_eviction_and_concurrent_aclose():
    """L3-001: Shared provider P remains open while an active stream holds a lease across slot replacement and concurrent aclose()."""
    import asyncio

    stream_entered = asyncio.Event()
    release_stream = asyncio.Event()

    class _StreamingProvider(LLMService):
        def __init__(self, profile: LLMProfile):
            self.profile = profile
            self.closed = False
            self.close_count = 0

        async def generate(self, prompt: Prompt, config: GenerationConfig) -> GenerationResult:
            if self.closed:
                raise RuntimeError("provider closed underneath active request")
            return GenerationResult(
                content=f"[{self.profile.id}:{config.model}] ok",
                token_usage=TokenUsage(input_tokens=4, output_tokens=2),
            )

        async def stream_generate(self, prompt: Prompt, config: GenerationConfig):
            stream_entered.set()
            yield "chunk-1:"
            await release_stream.wait()
            if self.closed:
                raise RuntimeError("provider closed while stream still active!")
            yield f"{self.profile.id}"

        async def aclose(self) -> None:
            self.closed = True
            self.close_count += 1

    class _SimpleCtrl:
        def __init__(self):
            self.shared = LLMProfile(
                id="p-shared", name="Shared", protocol="openai", api_key="k1", model="m-shared"
            )
            self.next_main = LLMProfile(
                id="p-main-2", name="Main2", protocol="openai", api_key="k2", model="m-main-2"
            )
            self.next_cheap = LLMProfile(
                id="p-cheap-2", name="Cheap2", protocol="openai", api_key="k3", model="m-cheap-2"
            )
            self.mapping = {"main": self.shared, "cheap": self.shared, "kg": self.shared}

        async def resolve_role_profile_async(self, role: str) -> LLMProfile:
            return self.mapping[role]

    class _StreamingFactory:
        def __init__(self, ctrl: _SimpleCtrl):
            self.control_service = ctrl
            self.created: list[_StreamingProvider] = []

        def create_from_profile(self, profile: LLMProfile) -> _StreamingProvider:
            inst = _StreamingProvider(profile)
            self.created.append(inst)
            return inst

    ctrl = _SimpleCtrl()
    factory = _StreamingFactory(ctrl)
    service = DynamicLLMService(factory)  # type: ignore[arg-type]

    # Warm both main and cheap with shared provider P
    await service.generate(Prompt(system="s", user="u"), GenerationConfig())

    collected: list[str] = []

    async def _run_cheap_stream():
        async for part in service.stream_generate(
            Prompt(system="s", user="u", node_key="chapter-summarizer"),
            GenerationConfig(),
        ):
            collected.append(part)

    stream_task = asyncio.create_task(_run_cheap_stream())
    await stream_entered.wait()

    shared_p = factory.created[0]
    assert shared_p.closed is False

    # Replace main slot AND cheap slot AND kg slot while stream_task is suspended on shared_p!
    ctrl.mapping["main"] = ctrl.next_main
    ctrl.mapping["cheap"] = ctrl.next_cheap
    ctrl.mapping["kg"] = ctrl.next_main
    await service.generate(Prompt(system="s", user="u"), GenerationConfig())
    await service.generate(
        Prompt(system="s", user="u", node_key="chapter-summarizer"),
        GenerationConfig(),
    )

    # All cache slots for shared_p are gone, YET shared_p MUST NOT be closed while stream_task holds lease!
    assert shared_p.closed is False

    # Start concurrent shutdown aclose() while stream_task is still active!
    shutdown_task = asyncio.create_task(service.aclose())
    await asyncio.sleep(0)
    assert shared_p.closed is False
    assert not shutdown_task.done()

    # New requests after shutdown begins are deterministically rejected
    with pytest.raises(RuntimeError):
        await service.generate(Prompt(system="s", user="u"), GenerationConfig())

    # Let the in-flight stream finish -> completes without closed-client error, then shared_p & shutdown finish!
    release_stream.set()
    await stream_task
    await shutdown_task

    assert "".join(collected) == "chunk-1:p-shared"
    assert shared_p.closed is True
    assert shared_p.close_count == 1
    for p in factory.created:
        assert p.closed is True
        assert p.close_count == 1


@pytest.mark.asyncio
async def test_round3_cancelled_aclose_does_not_abandon_remaining_provider_cleanup():
    """L3-002: Cancelling aclose() while P.aclose() is suspended still closes Q and R and allows retry aclose() to await P."""
    import asyncio

    p_close_started = asyncio.Event()
    allow_p_close = asyncio.Event()

    class _SlowCloseProvider(LLMService):
        def __init__(self, pid: str, block_close: bool = False):
            self.pid = pid
            self.block_close = block_close
            self.closed = False
            self.close_count = 0

        async def generate(self, prompt: Prompt, config: GenerationConfig) -> GenerationResult:
            return GenerationResult(
                content=self.pid,
                token_usage=TokenUsage(input_tokens=4, output_tokens=2),
            )

        async def stream_generate(self, prompt: Prompt, config: GenerationConfig):
            yield self.pid

        async def aclose(self) -> None:
            if self.block_close:
                p_close_started.set()
                await allow_p_close.wait()
            self.closed = True
            self.close_count += 1

    class _ThreeCtrl:
        def __init__(self):
            self.by_role = {
                "main": LLMProfile(id="P", name="P", protocol="openai", api_key="k1", model="m1"),
                "cheap": LLMProfile(id="Q", name="Q", protocol="openai", api_key="k2", model="m2"),
                "kg": LLMProfile(id="R", name="R", protocol="openai", api_key="k3", model="m3"),
            }

        async def resolve_role_profile_async(self, role: str) -> LLMProfile:
            return self.by_role[role]

    class _ThreeFactory:
        def __init__(self):
            self.control_service = _ThreeCtrl()
            self.instances: dict[str, _SlowCloseProvider] = {}

        def create_from_profile(self, profile: LLMProfile) -> _SlowCloseProvider:
            inst = _SlowCloseProvider(profile.id, block_close=(profile.id == "P"))
            self.instances[profile.id] = inst
            return inst

    factory = _ThreeFactory()
    service = DynamicLLMService(factory)  # type: ignore[arg-type]

    await service.generate(Prompt(system="s", user="u"), GenerationConfig())
    await service.generate(Prompt(system="s", user="u", node_key="chapter-summarizer"), GenerationConfig())
    await service.generate(Prompt(system="s", user="u", node_key="knowledge-initial"), GenerationConfig())

    first_close = asyncio.create_task(service.aclose())
    await p_close_started.wait()

    # Cancel the caller of aclose() while P.aclose() is suspended!
    first_close.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first_close

    # Q and R were NOT abandoned — their independent cleanup tasks complete promptly!
    await asyncio.sleep(0)
    assert factory.instances["Q"].closed is True
    assert factory.instances["R"].closed is True
    assert factory.instances["P"].closed is False

    # A subsequent aclose() still tracks P and awaits its completion once unblocked!
    second_close = asyncio.create_task(service.aclose())
    await asyncio.sleep(0)
    assert not second_close.done()

    allow_p_close.set()
    await second_close
    assert factory.instances["P"].closed is True
    assert factory.instances["P"].close_count == 1
    assert factory.instances["Q"].close_count == 1
    assert factory.instances["R"].close_count == 1


@pytest.mark.asyncio
async def test_round4_anthropic_stream_early_aclose_awaits_inner_generator_cleanup():
    """R3-L3-01: Early consumer break / aclose() on AnthropicProvider.stream_generate awaits inner generator cleanup in both httpx and SDK modes."""
    import asyncio
    from contextlib import aclosing
    from infrastructure.ai.providers.anthropic_provider import AnthropicProvider, Settings

    for use_oauth_flag, mode_name in [(True, "httpx"), (False, "sdk")]:
        inner_cleanup_finished = False

        settings = Settings(
            api_key="sk-ant-test-token",
            base_url="https://api.anthropic.com",
            default_model="claude-sonnet-4-5",
            use_oauth_bearer=use_oauth_flag,
        )
        provider = AnthropicProvider(settings=settings)

        async def _fake_inner_stream(*args, **kwargs):
            nonlocal inner_cleanup_finished
            try:
                yield "first-delta"
                yield "second-delta"
            finally:
                await asyncio.sleep(0)
                inner_cleanup_finished = True

        if mode_name == "httpx":
            provider._stream_via_httpx = _fake_inner_stream  # type: ignore[method-assign]
        else:
            provider._stream_via_sdk = _fake_inner_stream  # type: ignore[method-assign]

        seen: list[str] = []
        async with aclosing(
            provider.stream_generate(Prompt(system="s", user="u"), GenerationConfig())
        ) as gen:
            async for delta in gen:
                seen.append(delta)
                break

        assert seen == ["first-delta"], f"{mode_name} should yield first delta"
        assert inner_cleanup_finished is True, f"{mode_name} inner generator finally must complete before outer aclose returns"
        await provider.aclose()


@pytest.mark.asyncio
async def test_round4_dynamic_llm_service_rejects_cross_loop_access_without_mutating_leases():
    """R3-L3-02: Accessing DynamicLLMService from a second event loop while bound loop is open or leases/providers remain raises RuntimeError without erasing state."""
    import asyncio
    import threading

    stream_ready = asyncio.Event()
    release_stream = asyncio.Event()

    class _LoopBoundProvider(LLMService):
        def __init__(self):
            self.closed = False

        async def generate(self, prompt: Prompt, config: GenerationConfig) -> GenerationResult:
            return GenerationResult(
                content="ok",
                token_usage=TokenUsage(input_tokens=1, output_tokens=1),
            )

        async def stream_generate(self, prompt: Prompt, config: GenerationConfig):
            stream_ready.set()
            yield "part1"
            await release_stream.wait()
            if self.closed:
                raise RuntimeError("provider closed prematurely")
            yield "part2"

        async def aclose(self) -> None:
            self.closed = True

    class _Ctrl:
        async def resolve_role_profile_async(self, role: str) -> LLMProfile:
            return LLMProfile(id="p1", name="P1", protocol="openai", api_key="k1", model="m1")

    class _Fac:
        def __init__(self):
            self.control_service = _Ctrl()
            self.prov = _LoopBoundProvider()

        def create_from_profile(self, profile: LLMProfile) -> _LoopBoundProvider:
            return self.prov

    fac = _Fac()
    service = DynamicLLMService(fac)  # type: ignore[arg-type]

    chunks: list[str] = []

    async def _consume():
        async for ch in service.stream_generate(Prompt(system="s", user="u"), GenerationConfig()):
            chunks.append(ch)

    task = asyncio.create_task(_consume())
    await stream_ready.wait()
    assert service._active_leases.get(id(fac.prov)) == 1

    cross_loop_errors: list[Exception] = []

    def _other_thread_loop():
        loop2 = asyncio.new_event_loop()
        try:
            loop2.run_until_complete(
                service.generate(Prompt(system="s", user="u"), GenerationConfig())
            )
        except Exception as exc:
            cross_loop_errors.append(exc)
        finally:
            loop2.close()

    t = threading.Thread(target=_other_thread_loop)
    t.start()
    t.join(timeout=5.0)

    assert len(cross_loop_errors) == 1
    assert isinstance(cross_loop_errors[0], RuntimeError)
    # Active lease and cached provider on loop 1 MUST remain completely intact!
    assert service._active_leases.get(id(fac.prov)) == 1
    assert fac.prov.closed is False

    release_stream.set()
    await task
    assert chunks == ["part1", "part2"]
    await service.aclose()
    assert fac.prov.closed is True


@pytest.mark.asyncio
async def test_round5_anthropic_partial_stream_failure_propagates_and_split_crlf_parses():
    """R4-L3-01 & R4-L3-02: AnthropicProvider propagates mid-stream failures after partial output without SDK replay, raises on SSE error events, and parses split CRLF across chunk boundaries."""
    import httpx
    from infrastructure.ai.providers.anthropic_provider import AnthropicProvider, Settings

    # 1. R4-L3-01: Error after partial output MUST raise and MUST NOT call _stream_via_sdk
    provider = AnthropicProvider(
        settings=Settings(
            api_key="sk-ant-test",
            base_url="https://api.anthropic.com",
            default_model="claude-sonnet-4-5",
        )
    )
    sdk_called = False

    async def _partial_then_fail(*args, **kwargs):
        yield "partial-chunk"
        raise RuntimeError("network reset mid-stream")

    async def _should_not_run_sdk(*args, **kwargs):
        nonlocal sdk_called
        sdk_called = True
        yield "sdk-fallback"

    provider._stream_via_httpx = _partial_then_fail  # type: ignore[method-assign]
    provider._stream_via_sdk = _should_not_run_sdk  # type: ignore[method-assign]
    try:
        got: list[str] = []
        with pytest.raises(RuntimeError, match="Stream interrupted after partial output"):
            async for delta in provider.stream_generate(
                Prompt(system="s", user="u"), GenerationConfig()
            ):
                got.append(delta)
        assert got == ["partial-chunk"]
        assert sdk_called is False
    finally:
        await provider.aclose()

    # 2. R4-L3-02 + SSE error event: Split CRLF across chunks + SSE error detection
    split_chunks = [
        'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"松烟"}}\r',
        "\n\r",
        '\ndata: {"type":"content_block_delta","delta":{"type":"text_delta","text":"入墨"}}\r',
        "\n\r",
        '\nevent: message_stop\r\ndata: {"type":"message_stop"}\r',
        "\n\r",
        "\n",
    ]

    class _SplitStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            for c in split_chunks:
                yield c.encode("utf-8")

        async def aclose(self) -> None:
            pass

    mock_http = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda req: httpx.Response(
                200,
                headers={"Content-Type": "text/event-stream"},
                stream=_SplitStream(),
            )
        )
    )
    provider2 = AnthropicProvider(
        settings=Settings(
            api_key="sk-ant-test",
            base_url="https://api.anthropic.com",
            default_model="claude-sonnet-4-5",
        )
    )
    old_stream_client = provider2._stream_http_client
    provider2._stream_http_client = mock_http
    try:
        out: list[str] = []
        async for delta in provider2.stream_generate(
            Prompt(system="s", user="u"), GenerationConfig()
        ):
            out.append(delta)
        assert "".join(out) == "松烟入墨"

        with pytest.raises(RuntimeError, match="Upstream SSE error"):
            provider2._parse_sse_event(
                'event: error\ndata: {"type":"error","error":{"type":"overloaded_error","message":"busy"}}'
            )
    finally:
        await old_stream_client.aclose()
        await provider2.aclose()


@pytest.mark.asyncio
async def test_round6_anthropic_sse_error_variants_and_premature_eof():
    """R5-L3-01 & R5-L3-02: Explicit SSE error events of any payload shape and clean EOF before message_stop/[DONE] must raise without SDK replay."""
    import httpx
    from infrastructure.ai.config.settings import Settings
    from infrastructure.ai.providers.anthropic_provider import AnthropicProvider

    class _SeqStream(httpx.AsyncByteStream):
        def __init__(self, payloads: list[str]) -> None:
            self._payloads = payloads

        async def __aiter__(self):
            for item in self._payloads:
                yield item.encode("utf-8")

        async def aclose(self) -> None:
            pass

    async def _run_case(payloads: list[str]) -> tuple[list[str], bool, Exception | None]:
        sdk_called = False
        mock_http = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda req: httpx.Response(
                    200,
                    headers={"Content-Type": "text/event-stream"},
                    stream=_SeqStream(payloads),
                )
            )
        )
        prov = AnthropicProvider(
            settings=Settings(
                api_key="sk-ant-r6",
                base_url="https://api.anthropic.com",
                default_model="claude-sonnet-4-5",
            )
        )
        old_client = prov._stream_http_client
        prov._stream_http_client = mock_http

        async def _no_sdk(*args, **kwargs):
            nonlocal sdk_called
            sdk_called = True
            yield "sdk-should-not-run"

        prov._stream_via_sdk = _no_sdk  # type: ignore[method-assign]
        collected: list[str] = []
        caught: Exception | None = None
        try:
            async for delta in prov.stream_generate(
                Prompt(system="s", user="u"), GenerationConfig()
            ):
                collected.append(delta)
        except Exception as exc:
            caught = exc
        finally:
            await old_client.aclose()
            await prov.aclose()
        return collected, sdk_called, caught

    delta_frame = 'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"半截正文"}}\n\n'

    # 1. R5-L3-01: Scalar/null/empty/[DONE] SSE error payloads after partial output
    for error_frame in [
        "event: error\ndata: null\n\n",
        "event: error\ndata: [DONE]\n\n",
        "event: error\ndata:\n\n",
        'event: error\ndata: "overloaded"\n\n',
        "event: error\ndata: []\n\n",
    ]:
        got, sdk_used, err = await _run_case([delta_frame, error_frame])
        assert got == ["半截正文"]
        assert sdk_used is False
        assert isinstance(err, RuntimeError)
        assert "Stream interrupted after partial output" in str(err)

    # 2. R5-L3-02: Native Anthropic stream ending cleanly without message_stop (or with [DONE] instead of message_stop)
    for incomplete_tail in ["", "data: [DONE]\n\n"]:
        frames = [delta_frame] + ([incomplete_tail] if incomplete_tail else [])
        got, sdk_used, err = await _run_case(frames)
        assert got == ["半截正文"]
        assert sdk_used is False
        assert isinstance(err, RuntimeError)
        assert "ended prematurely" in str(err)

    # 3. Compatibility OpenAI-style SSE requires [DONE]
    compat_delta = 'data: {"choices":[{"delta":{"content":"兼容输出"}}]}\n\n'
    got_ok, sdk_ok, err_ok = await _run_case([compat_delta, "data: [DONE]\n\n"])
    assert err_ok is None
    assert sdk_ok is False
    assert got_ok == ["兼容输出"]

    got_trunc, sdk_trunc, err_trunc = await _run_case([compat_delta])
    assert got_trunc == ["兼容输出"]
    assert sdk_trunc is False
    assert isinstance(err_trunc, RuntimeError)
    assert "ended prematurely" in str(err_trunc)



