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


@pytest.mark.asyncio
async def test_stream_worldbuilding_full_emits_child_fields_before_dimension_done():
    class FakeLlm:
        async def stream_generate(self, _prompt, _config):
            text = (
                '{"worldbuilding":{"core_rules":{'
                '"power_system":"玩家以神经同步驱动剑气与身法，非传统打法能绕开标准职业模板",'
                '"physics_rules":"游戏时间流速和现实神经消耗分离，高倍速对战会放大反应误差",'
                '"magic_tech":"训练舱将肌肉记忆转译为角色动作，同步率越高越依赖昂贵监测设备"'
                '},"geography":{"terrain":"主城、赛场和训练基地围绕服务器节点分布，地下网吧藏在监管薄弱街区"}}}'
            )
            for idx in range(0, len(text), 23):
                yield text[idx:idx + 23]

    svc = AutoBibleGenerator(llm_service=FakeLlm(), bible_service=Mock())

    events = []
    async for item in svc._stream_worldbuilding_full("电竞剑仙", 100):
        if item.get("type") in {"dimension_start", "field", "dimension"}:
            events.append(item)

    core_events = [e for e in events if e.get("key") == "core_rules"]
    assert [e["type"] for e in core_events[:4]] == [
        "dimension_start",
        "field",
        "field",
        "field",
    ]
    assert [e.get("field") for e in core_events if e["type"] == "field"] == [
        "power_system",
        "physics_rules",
        "magic_tech",
    ]
    assert any(e["type"] == "dimension" and e["key"] == "core_rules" for e in events)


@pytest.mark.asyncio
async def test_stream_worldbuilding_full_generates_dimensions_in_linked_batches():
    payloads = [
        '{"worldbuilding":{"core_rules":{"power_system":"玩家通过神经同步驱动剑气与身法，非传统打法能绕开标准模板","physics_rules":"游戏时间流速和现实神经消耗分离，高倍速对战会放大反应误差","magic_tech":"训练舱将肌肉记忆转译为角色动作，同步率越高越依赖监测设备"}}}',
        '{"worldbuilding":{"geography":{"terrain":"主城、赛场和训练基地围绕服务器节点分布，地下网吧藏在旧城区","climate":"赛季天气由服务器动态渲染，雨战会放大身法误差，雪图压低视野","resources":"高阶材料集中在联赛副本和训练服隐藏节点，普通玩家只能兑换碎片","ecology":"野区机关与镜像怪会模拟职业队常用压迫路线，逼迫选手移动判断"}}}',
        '{"worldbuilding":{"society":{"politics":"联盟表面以公开赛规管理战队，实际席位掌握在平台和资本手里","economy":"顶级选手靠年薪直播和皮肤分成暴富，青训生要自费购买训练时长","class_system":"选手分传奇宗师职业青训路人五档，医疗和资源随等级急剧分化"}}}',
        '{"worldbuilding":{"culture":{"history":"职业联盟十年前建立神经健康标准，但俱乐部用外包青训规避监管","religion":"粉丝文化把冠军戒指视作圣物，退役名宿录像会被反复拆解","taboos":"公开操盘伤病隐瞒和盗用战术库是红线，触犯者会被永久除名"}}}',
        '{"worldbuilding":{"daily_life":{"food_clothing":"战队基地以营养餐和压缩睡眠为日常，青训生常在训练室过夜","language_slang":"圈内常说卡帧骗闪锁血和剑走偏锋，队友沟通追求短促明确","entertainment":"玩家靠直播二路竞猜和皮肤抽卡消遣，大赛夜网吧会爆满到凌晨"}}}',
    ]

    class FakeLlm:
        def __init__(self):
            self.calls = 0
            self.users = []

        async def stream_generate(self, prompt, _config):
            self.users.append(prompt.user)
            text = payloads[self.calls]
            self.calls += 1
            for idx in range(0, len(text), 29):
                yield text[idx:idx + 29]

    llm = FakeLlm()
    svc = AutoBibleGenerator(llm_service=llm, bible_service=Mock())

    dimensions = []
    async for item in svc._stream_worldbuilding_full("电竞剑仙", 100):
        if item.get("type") == "dimension":
            dimensions.append(item["key"])

    assert llm.calls == 5
    assert dimensions == ["core_rules", "geography", "society", "culture", "daily_life"]
    assert '"power_system"' in llm.users[1]
    assert '"terrain"' in llm.users[2]
