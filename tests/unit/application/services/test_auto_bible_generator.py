import pytest
from unittest.mock import AsyncMock, Mock

from application.world.services.auto_bible_generator import AutoBibleGenerator
from domain.ai.services.llm_service import GenerationResult
from domain.ai.value_objects.token_usage import TokenUsage


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
async def test_call_llm_and_parse_returns_empty_dict_when_content_is_unrecoverable():
    llm = Mock()
    llm.generate = AsyncMock(
        return_value=GenerationResult(
            content="not json at all",
            token_usage=TokenUsage(input_tokens=1, output_tokens=1),
        )
    )
    svc = AutoBibleGenerator(llm_service=llm, bible_service=Mock())

    result = await svc._call_llm_and_parse("system", "user")

    assert result == {}
