import json

import pytest

from domain.ai.services.llm_service import GenerationConfig
from domain.ai.value_objects.prompt import Prompt
from infrastructure.ai.providers.mock_provider import MockProvider


async def _generate(user: str, system: str = "测试系统") -> str:
    provider = MockProvider()
    result = await provider.generate(Prompt(system=system, user=user), GenerationConfig())
    return result.content


def _loads(content: str) -> dict:
    return json.loads(content)


@pytest.mark.asyncio
async def test_mock_provider_macro_plan_returns_contract_shape():
    data = _loads(await _generate('请生成宏观结构，输出 "parts" 的部-卷-幕 JSON。'))

    parts = data["parts"]
    assert parts and parts[0]["volumes"]
    first_act = parts[0]["volumes"][0]["acts"][0]
    assert {"number", "title", "description", "key_events", "conflicts"} <= set(first_act)


@pytest.mark.asyncio
async def test_mock_provider_worldbuilding_returns_five_dimensions():
    data = _loads(await _generate("请生成世界观 worldbuilding 和核心法则。"))

    worldbuilding = data["worldbuilding"]
    assert {"core_rules", "geography", "society", "culture", "daily_life"} <= set(worldbuilding)
    assert data["style"]


@pytest.mark.asyncio
async def test_mock_provider_characters_and_locations_return_expected_arrays():
    characters = _loads(await _generate("请生成 characters 人物角色。"))["characters"]
    locations = _loads(await _generate("请生成 locations 地点地图。"))["locations"]

    assert len(characters) >= 3
    assert {"name", "role", "description", "voice_profile", "relationships"} <= set(characters[0])
    assert len(locations) >= 3
    assert {"id", "name", "type", "description", "connections"} <= set(locations[0])


@pytest.mark.asyncio
async def test_mock_provider_main_plot_options_return_three_options():
    data = _loads(await _generate("setup_main_plot_options_v1，请输出 plot_options。"))

    options = data["plot_options"]
    assert len(options) == 3
    assert {"id", "type", "title", "logline", "core_conflict", "starting_hook"} <= set(options[0])


@pytest.mark.asyncio
async def test_mock_provider_chapter_review_returns_review_contract():
    data = _loads(await _generate('章节 AI 审阅，请输出 "score" 和 "issues"。'))

    assert data["status"] in {"draft", "reviewed", "approved"}
    assert isinstance(data["score"], int)
    assert isinstance(data["suggestions"], list)


@pytest.mark.asyncio
async def test_mock_provider_does_not_emit_fixed_story_bias_terms():
    provider = MockProvider()
    prompts = [
        "请生成宏观结构，输出部-卷-幕 JSON。",
        "请生成世界观 worldbuilding。",
        "请生成 characters 人物角色。",
        "请生成 locations 地点地图。",
        "setup_main_plot_options_v1，请输出 plot_options。",
    ]
    forbidden_terms = [
        "修仙",
        "灵气",
        "穿越",
        "宗门",
        "学院",
        "无法修炼",
        "科学修仙",
    ]

    outputs = []
    for user in prompts:
        result = await provider.generate(Prompt(system="测试系统", user=user), GenerationConfig())
        outputs.append(result.content)

    joined = "\n".join(outputs)
    assert "?" * 4 not in joined
    assert chr(0xFFFD) not in joined
    for term in forbidden_terms:
        assert term not in joined


@pytest.mark.asyncio
async def test_mock_provider_stream_matches_generate_content():
    provider = MockProvider()
    prompt = Prompt(system="测试系统", user="请生成世界观 worldbuilding。")

    direct = await provider.generate(prompt, GenerationConfig())
    streamed = "".join([chunk async for chunk in provider.stream_generate(prompt, GenerationConfig())])

    assert streamed == direct.content
