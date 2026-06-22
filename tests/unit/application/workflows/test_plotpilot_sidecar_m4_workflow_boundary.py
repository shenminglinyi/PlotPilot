from unittest.mock import Mock
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from application.workflows.auto_novel_generation_workflow import AutoNovelGenerationWorkflow
from domain.ai.value_objects.prompt import Prompt


@pytest.fixture
def workflow():
    return AutoNovelGenerationWorkflow(
        context_builder=Mock(),
        consistency_checker=Mock(),
        storyline_manager=Mock(),
        plot_arc_repository=Mock(),
        llm_service=Mock(),
    )


def test_build_prompt_applies_m4_adapter_before_return(workflow, monkeypatch):
    import application.workflows.auto_novel_generation_workflow as workflow_module

    calls = []

    def fake_enhance(prompt, **kwargs):
        calls.append(kwargs)
        node_type = "beat_prose" if kwargs["beat_mode"] else "chapter_prose"
        return (
            Prompt(
                system=prompt.system + f"\n\n【Sidecar M4 pre-generation】\nnode_type: {node_type}",
                user=prompt.user,
            ),
            {
                "enhancement_mode": "pre_generation",
                "node_type": node_type,
                "enhancement_applied": True,
                "sidecar_added_regeneration_count": 0,
                "native_call_boundary": kwargs["native_call_boundary"],
            },
        )

    monkeypatch.setattr(
        workflow_module,
        "enhance_prompt_for_plotpilot_m4",
        fake_enhance,
    )

    prompt = workflow._build_prompt(
        context="CTX",
        outline="OL",
        beat_prompt="第 1 节拍：进入现场。",
        beat_index=0,
        total_beats=3,
    )

    assert calls
    assert calls[0]["beat_mode"] is True
    assert calls[0]["beat_prompt"] == "第 1 节拍：进入现场。"
    assert calls[0]["native_call_boundary"]["source_function"] == (
        "AutoNovelGenerationWorkflow._build_prompt"
    )
    assert "【Sidecar M4 pre-generation】" in prompt.system
    assert "node_type: beat_prose" in prompt.system
    assert "【Sidecar M4 pre-generation】" not in prompt.user
    assert workflow._last_sidecar_trace["node_type"] == "beat_prose"
    assert workflow._sidecar_traces[-1]["node_type"] == "beat_prose"


@pytest.mark.asyncio
async def test_suggest_outline_applies_m4_adapter_before_llm(workflow, monkeypatch):
    import application.workflows.auto_novel_generation_workflow as workflow_module

    captured_prompts = []
    workflow.context_builder.build_context.return_value = "托管连写上下文"

    def fake_enhance(prompt, **kwargs):
        return (
            Prompt(
                system=prompt.system + "\n\n【Sidecar M4 pre-generation】\nnode_type: chapter_outline",
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

    async def fake_generate(prompt, _config):
        captured_prompts.append(prompt)
        return SimpleNamespace(content="1. 主角收到线索\n2. 代价升级")

    monkeypatch.setattr(workflow_module, "enhance_prompt_for_plotpilot_m4", fake_enhance)
    workflow.llm_service.generate = AsyncMock(side_effect=fake_generate)

    outline = await workflow.suggest_outline("novel-1", 4)

    assert "主角收到线索" in outline
    assert captured_prompts
    assert "【Sidecar M4 pre-generation】" in captured_prompts[0].system
    assert workflow._sidecar_traces[-1]["node_type"] == "chapter_outline"
    assert workflow._sidecar_traces[-1]["native_call_boundary"]["source_function"] == (
        "AutoNovelGenerationWorkflow.suggest_outline"
    )


@pytest.mark.asyncio
async def test_generate_prose_from_script_applies_m4_adapter_before_llm(workflow, monkeypatch):
    import application.workflows.auto_novel_generation_workflow as workflow_module

    captured_prompts = []

    class FakeGateway:
        def render(self, *_args, **_kwargs):
            return SimpleNamespace(prompt=Prompt(system="prose system", user="prose user"))

    def fake_enhance(prompt, **kwargs):
        return (
            Prompt(
                system=prompt.system + "\n\n【Sidecar M4 pre-generation】\nnode_type: chapter_prose",
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

    async def fake_generate(prompt, _config):
        captured_prompts.append(prompt)
        return SimpleNamespace(content="生成正文")

    monkeypatch.setattr(workflow_module, "get_prompt_gateway", lambda: FakeGateway())
    monkeypatch.setattr(workflow_module, "enhance_prompt_for_plotpilot_m4", fake_enhance)
    workflow.llm_service.generate = AsyncMock(side_effect=fake_generate)

    prose = await workflow._generate_prose_from_script(
        script="剧本",
        outline="大纲",
        target_words=1200,
        context="上下文",
    )

    assert prose == "生成正文"
    assert captured_prompts
    assert "【Sidecar M4 pre-generation】" in captured_prompts[0].system
    assert workflow._last_sidecar_trace["node_type"] == "chapter_prose"
    assert workflow._sidecar_traces[-1]["native_call_boundary"]["source_function"] == (
        "AutoNovelGenerationWorkflow._generate_prose_from_script"
    )


@pytest.mark.asyncio
async def test_generate_prose_from_script_records_output_evidence_on_sidecar_trace(
    workflow, monkeypatch
):
    import application.workflows.auto_novel_generation_workflow as workflow_module

    class FakeGateway:
        def render(self, *_args, **_kwargs):
            return SimpleNamespace(prompt=Prompt(system="prose system", user="prose user"))

    def fake_enhance(prompt, **kwargs):
        return (
            Prompt(
                system=prompt.system + "\n\n【Sidecar M4 pre-generation】\nnode_type: chapter_prose",
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

    async def fake_generate(_prompt, _config):
        return SimpleNamespace(content="窗外的雨线忽然停住，主角把钥匙攥进掌心。")

    monkeypatch.setattr(workflow_module, "get_prompt_gateway", lambda: FakeGateway())
    monkeypatch.setattr(workflow_module, "enhance_prompt_for_plotpilot_m4", fake_enhance)
    workflow.llm_service.generate = AsyncMock(side_effect=fake_generate)

    prose = await workflow._generate_prose_from_script(
        script="剧本",
        outline="大纲",
        target_words=1200,
    )

    trace = workflow._sidecar_traces[-1]
    assert prose == "窗外的雨线忽然停住，主角把钥匙攥进掌心。"
    assert trace["enhancement_applied"] is True
    assert trace["output_evidence"]["output_char_count"] == len(prose)
    assert len(trace["output_evidence"]["output_excerpt_hash"]) == 64
    assert trace["enhanced_before_native_call"] is True
