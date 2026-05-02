import pytest
import json
from unittest.mock import AsyncMock, Mock

from application.world.services.auto_bible_generator import AutoBibleGenerator
from domain.ai.services.llm_service import GenerationResult
from domain.ai.value_objects.token_usage import TokenUsage
from infrastructure.ai.providers.mock_provider import MockProvider


@pytest.mark.asyncio
async def test_mock_provider_character_stage_returns_characters_when_prompt_mentions_worldbuilding():
    """人物阶段 prompt 会带已有世界观，MockProvider 仍应返回 characters。"""
    svc = AutoBibleGenerator(llm_service=MockProvider(), bible_service=Mock())

    result = await svc._generate_characters(
        "测试故事",
        100,
        {"society": {"class_system": "都市阶层"}},
    )

    assert result["characters"]
    assert result["characters"][0]["name"] == "张三"


@pytest.mark.asyncio
async def test_call_llm_and_parse_repairs_truncated_locations_json():
    llm = Mock()
    llm.generate = AsyncMock(
        return_value=GenerationResult(
            content="""```json
{
  "locations": [
    {
      "id": "location_imperial_capital",
      "name": "应天府",
      "type": "城市",
      "description": "大明王朝皇都",
      "parent_id": null,
      "connections": [
        {
          "target": "location_taoyuan_paradise",
          "relation": "统辖",
          "description": "皇室共管洞天"
        }
      ]
    }
  ]
""",
            token_usage=TokenUsage(input_tokens=1, output_tokens=1),
        )
    )
    svc = AutoBibleGenerator(llm_service=llm, bible_service=Mock())

    result = await svc._call_llm_and_parse("system", "user")

    assert result["locations"][0]["id"] == "location_imperial_capital"
    assert result["locations"][0]["connections"][0]["relation"] == "统辖"
    _, config = llm.generate.await_args.args
    assert config.max_tokens == 4096


@pytest.mark.asyncio
async def test_call_llm_and_parse_raises_when_content_is_unrecoverable():
    llm = Mock()
    llm.generate = AsyncMock(
        return_value=GenerationResult(
            content="not json at all",
            token_usage=TokenUsage(input_tokens=1, output_tokens=1),
        )
    )
    svc = AutoBibleGenerator(llm_service=llm, bible_service=Mock())

    with pytest.raises(json.JSONDecodeError):
        await svc._call_llm_and_parse("system", "user")


@pytest.mark.asyncio
async def test_generate_bible_data_uses_hardened_parser_path():
    llm = Mock()
    llm.generate = AsyncMock(
        return_value=GenerationResult(
            content='{"characters":[],"locations":[],"style":"s","worldbuilding":{}}',
            token_usage=TokenUsage(input_tokens=1, output_tokens=1),
        )
    )
    svc = AutoBibleGenerator(llm_service=llm, bible_service=Mock())

    result = await svc._generate_bible_data("premise", 10)

    assert result["style"] == "s"
    _, config = llm.generate.await_args.args
    assert config.max_tokens == 4096


def test_prepare_locations_for_save_orders_parents_first_and_downgrades_missing_parent():
    svc = AutoBibleGenerator(llm_service=Mock(), bible_service=Mock())

    prepared = svc._prepare_locations_for_save(
        "novel-1",
        [
            {
                "id": "loc_chaoyang",
                "name": "朝阳区",
                "type": "区域",
                "description": "城区",
                "parent_id": "loc_beijing",
            },
            {
                "id": "loc_orphan",
                "name": "孤立地点",
                "type": "建筑",
                "description": "无父节点",
                "parent_id": "loc_missing",
            },
            {
                "id": "loc_beijing",
                "name": "北京",
                "type": "城市",
                "description": "首都",
                "parent_id": None,
            },
        ],
    )

    ids = [item["location_id"] for item in prepared]
    by_id = {item["location_id"]: item for item in prepared}

    assert ids.index("loc_beijing") < ids.index("loc_chaoyang")
    assert by_id["loc_beijing"]["parent_id"] is None
    assert by_id["loc_orphan"]["parent_id"] is None
    assert by_id["loc_chaoyang"]["parent_id"] == "loc_beijing"
