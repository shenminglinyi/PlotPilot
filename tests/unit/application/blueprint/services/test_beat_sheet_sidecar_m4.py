from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from application.blueprint.services.beat_sheet_service import BeatSheetService
from domain.ai.value_objects.prompt import Prompt


@pytest.mark.asyncio
async def test_generate_beat_sheet_applies_m4_adapter_before_llm(monkeypatch):
    import application.blueprint.services.beat_sheet_service as beat_sheet_module
    import infrastructure.ai.prompt_utils as prompt_utils

    captured_prompts = []
    saved_sheets = []

    service = BeatSheetService(
        beat_sheet_repo=SimpleNamespace(save=AsyncMock(side_effect=saved_sheets.append)),
        chapter_repo=Mock(),
        storyline_repo=Mock(),
        llm_service=SimpleNamespace(),
        vector_store=None,
    )
    service._retrieve_relevant_context = AsyncMock(return_value={})

    def fake_render_required_prompt(_node_key, _variables):
        return Prompt(system="beat sheet system", user="beat sheet user")

    def fake_enhance(prompt, **kwargs):
        return (
            Prompt(
                system=prompt.system + "\n\n【Sidecar M4 pre-generation】\nnode_type: beat_sheet",
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
        return SimpleNamespace(
            content=(
                '{"scenes": [{"title": "追车", "goal": "逼迫主角选择", '
                '"pov_character": "阿澄", "estimated_words": 800}]}'
            )
        )

    monkeypatch.setattr(prompt_utils, "render_required_prompt", fake_render_required_prompt)
    monkeypatch.setattr(beat_sheet_module, "enhance_prompt_for_plotpilot_m4", fake_enhance, raising=False)
    service.llm_service.generate = fake_generate

    beat_sheet = await service.generate_beat_sheet("chapter-1", "主角追查线索。")

    assert beat_sheet.get_scene_count() == 1
    assert captured_prompts
    assert "【Sidecar M4 pre-generation】" in captured_prompts[0].system
