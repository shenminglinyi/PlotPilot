from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from application.workbench.services.sandbox_dialogue_service import SandboxDialogueService
from application.world.dtos.bible_dto import CharacterDTO
from domain.ai.services.llm_service import GenerationResult
from domain.ai.value_objects.token_usage import TokenUsage
from interfaces.api.dependencies import (
    get_bible_service,
    get_llm_service,
    get_sandbox_dialogue_service,
)
from interfaces.main import app


class FakeNarrativeEventRepository:
    def __init__(self, events):
        self._events = events

    def list_up_to_chapter(self, novel_id: str, max_chapter_inclusive: int):
        return list(self._events)


class FakeBibleService:
    def __init__(self):
        self._bible = SimpleNamespace(
            characters=[
                CharacterDTO(
                    id="shenji",
                    name="沈霁",
                    description="冷静克制的剑修",
                    relationships=[{"target_name": "柳月", "relation": "师徒"}],
                    public_profile="外冷内热，出手极稳",
                    mental_state="压着火气",
                    verbal_tic="少废话",
                    idle_behavior="指腹轻敲剑鞘",
                ),
                CharacterDTO(
                    id="liuyue",
                    name="柳月",
                    description="沈霁的师父，处事周全",
                    relationships=[],
                ),
                CharacterDTO(
                    id="guhan",
                    name="顾寒",
                    description="沈霁的旧敌",
                    relationships=[],
                ),
            ]
        )

    def get_bible_by_novel(self, novel_id: str):
        return self._bible


class FakeLLMService:
    def __init__(self):
        self.prompt = None
        self.config = None

    async def generate(self, prompt, config):
        self.prompt = prompt
        self.config = config
        return GenerationResult(
            content="沈霁：少废话，让柳月退后，这里轮不到顾寒逞强。",
            token_usage=TokenUsage(input_tokens=12, output_tokens=8),
        )


@pytest.fixture
def client():
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


def test_generate_dialogue_uses_grounded_prompt_and_strips_character_prefix(client):
    fake_llm = FakeLLMService()
    sandbox_service = SandboxDialogueService(
        FakeNarrativeEventRepository(
            [
                {
                    "event_id": "evt-1",
                    "chapter_number": 12,
                    "event_summary": "沈霁：我从不做没把握的事。",
                    "tags": ["对话:沈霁", "场景:祠堂夜谈"],
                },
                {
                    "event_id": "evt-2",
                    "chapter_number": 15,
                    "event_summary": "沈霁：柳月若插手，局势只会更乱。",
                    "tags": ["对白:沈霁", "场景:雨夜巷战"],
                },
            ]
        )
    )

    app.dependency_overrides[get_bible_service] = lambda: FakeBibleService()
    app.dependency_overrides[get_llm_service] = lambda: fake_llm
    app.dependency_overrides[get_sandbox_dialogue_service] = lambda: sandbox_service

    response = client.post(
        "/api/v1/novels/sandbox/generate-dialogue",
        json={
            "novel_id": "novel-1",
            "character_id": "shenji",
            "scene_prompt": "顾寒步步紧逼，柳月想上前挡在沈霁面前。",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "dialogue": "少废话，让柳月退后，这里轮不到顾寒逞强。",
        "character_name": "沈霁",
    }
    assert fake_llm.prompt is not None
    assert "历史对白样本" in fake_llm.prompt.user
    assert "第15章 / 雨夜巷战：柳月若插手，局势只会更乱。" in fake_llm.prompt.user
    assert "柳月：师徒" in fake_llm.prompt.user
    assert "顾寒" in fake_llm.prompt.user
    assert fake_llm.config.max_tokens == 240
