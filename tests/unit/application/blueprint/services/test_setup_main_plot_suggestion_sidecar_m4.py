from types import SimpleNamespace

import pytest

from application.blueprint.services.setup_main_plot_suggestion_service import (
    SetupMainPlotSuggestionService,
)
from domain.ai.services.llm_service import GenerationConfig
from domain.ai.value_objects.prompt import Prompt


@pytest.mark.asyncio
async def test_suggest_options_applies_m4_adapter_before_llm(monkeypatch):
    import application.blueprint.services.setup_main_plot_suggestion_service as main_plot_module

    captured_prompts = []

    class FakeLLM:
        async def generate(self, prompt, _config):
            captured_prompts.append(prompt)
            return SimpleNamespace(
                content="""
                {
                  "plot_options": [
                    {"id": "option_a", "title": "A", "logline": "log", "core_conflict": "conflict", "starting_hook": "hook"},
                    {"id": "option_b", "title": "B", "logline": "log", "core_conflict": "conflict", "starting_hook": "hook"},
                    {"id": "option_c", "title": "C", "logline": "log", "core_conflict": "conflict", "starting_hook": "hook"}
                  ]
                }
                """
            )

    service = SetupMainPlotSuggestionService.__new__(SetupMainPlotSuggestionService)
    service._llm = FakeLLM()
    service._build_prompt_and_config = lambda _novel_id: (
        {"target_chapters": 60},
        Prompt(system="main plot system", user="main plot user"),
        GenerationConfig(),
    )

    def fake_enhance(prompt, **kwargs):
        return (
            Prompt(
                system=prompt.system + "\n\n【Sidecar M4 pre-generation】\nnode_type: main_plot",
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

    monkeypatch.setattr(main_plot_module, "enhance_prompt_for_plotpilot_m4", fake_enhance, raising=False)

    options = await service.suggest_options("novel-1")

    assert len(options) == 3
    assert captured_prompts
    assert "【Sidecar M4 pre-generation】" in captured_prompts[0].system
