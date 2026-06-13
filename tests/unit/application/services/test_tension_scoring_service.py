from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from application.analyst.services.tension_scoring_service import TensionScoringService
from domain.ai.value_objects.prompt import Prompt
from domain.novel.value_objects.tension_dimensions import UNEVALUATED


class _Gateway:
    def render(self, contract, variables):
        return SimpleNamespace(prompt=Prompt(system="score tension", user=variables["content"]))


@pytest.mark.asyncio
async def test_tension_scoring_parse_failure_uses_neutral_score(monkeypatch):
    monkeypatch.setattr(
        "application.analyst.services.tension_scoring_service.get_prompt_gateway",
        lambda: _Gateway(),
    )
    llm = SimpleNamespace(generate=AsyncMock(return_value=SimpleNamespace(content="不是 JSON")))

    dims = await TensionScoringService(llm).score_chapter(
        chapter_content="这一章有足够正文用于评分。",
        chapter_number=3,
    )

    assert dims.composite_score == 50.0


@pytest.mark.asyncio
async def test_tension_scoring_llm_failure_stays_unevaluated(monkeypatch):
    monkeypatch.setattr(
        "application.analyst.services.tension_scoring_service.get_prompt_gateway",
        lambda: _Gateway(),
    )
    llm = SimpleNamespace(generate=AsyncMock(side_effect=RuntimeError("provider down")))

    dims = await TensionScoringService(llm).score_chapter(
        chapter_content="这一章有足够正文用于评分。",
        chapter_number=3,
    )

    assert dims.composite_score == UNEVALUATED
