import pytest

from domain.ai.value_objects.prompt import Prompt


class _FakeStreamLLM:
    def __init__(self):
        self.prompts = []

    async def stream_generate(self, prompt, _config):
        self.prompts.append(prompt)
        yield '{"atoms": [{"id": "b1", "intent": "主角被迫作出选择", "weight": 1}]}'


@pytest.mark.asyncio
async def test_llm_decompose_outline_applies_m4_adapter_before_stream(monkeypatch):
    import application.engine.dag.plan.outline_beat_planner as planner

    llm = _FakeStreamLLM()

    def fake_enhance(prompt, **kwargs):
        return (
            Prompt(
                system=prompt.system + "\n\n【Sidecar M4 pre-generation】\nnode_type: outline_partition",
                user=prompt.user,
            ),
            {
                "enhancement_mode": "pre_generation",
                "node_type": kwargs["node_type"],
                "enhancement_applied": True,
                "sidecar_added_regeneration_count": 0,
                "native_call_boundary": kwargs["native_call_boundary"],
            },
        )

    monkeypatch.setattr(planner, "enhance_prompt_for_plotpilot_m4", fake_enhance, raising=False)

    atoms = await planner.llm_decompose_outline(
        "主角进入废弃车站。",
        1200,
        system="partition system",
        user="partition user",
        llm_service=llm,
    )

    assert atoms
    assert llm.prompts
    assert "【Sidecar M4 pre-generation】" in llm.prompts[0].system


@pytest.mark.asyncio
async def test_build_chapter_execution_plan_keeps_outline_partition_sidecar_trace(monkeypatch):
    import application.engine.dag.plan.outline_beat_planner as planner

    llm = _FakeStreamLLM()

    def fake_enhance(prompt, **kwargs):
        return (
            Prompt(
                system=prompt.system + "\n\n【Sidecar M4 pre-generation】\nnode_type: outline_partition",
                user=prompt.user,
            ),
            {
                "enhancement_mode": "pre_generation",
                "node_type": kwargs["node_type"],
                "enhancement_applied": True,
                "sidecar_added_regeneration_count": 0,
                "native_call_boundary": kwargs["native_call_boundary"],
            },
        )

    monkeypatch.setattr(planner, "enhance_prompt_for_plotpilot_m4", fake_enhance, raising=False)

    plan = await planner.build_chapter_execution_plan_async(
        "主角进入废弃车站。",
        target_chapter_words=1200,
        llm_system="partition system",
        llm_user="partition user",
        llm_service=llm,
    )

    assert plan.atoms
    assert plan.provenance["sidecar_traces"][0]["node_type"] == "outline_partition"
    assert plan.provenance["sidecar_traces"][0]["native_call_boundary"]["source_function"] == (
        "outline_beat_planner.llm_decompose_outline"
    )
