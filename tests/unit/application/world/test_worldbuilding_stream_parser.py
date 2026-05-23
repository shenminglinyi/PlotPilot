"""世界观单次流式增量解析器测试"""
import json

from application.world.services.worldbuilding_stream_parser import (
    WorldbuildingStreamIncrementalParser,
    _try_extract_dimension_object,
)


def test_try_extract_dimension_object_finds_complete_block():
    buf = json.dumps(
        {
            "worldbuilding": {
                "core_rules": {
                    "power_system": "灵气复苏后的异能体系以精神共鸣驱动职业分层",
                    "physics_rules": "常态物理仍然有效，但灵气浓度会改变战斗反馈",
                    "magic_tech": "训练舱会记录神经冲动并转译为角色动作，过载后必须停机校准",
                },
                "geography": {
                    "terrain": "群山环绕主城，灵脉沿断崖和峡谷集中分布",
                },
            }
        },
        ensure_ascii=False,
    )
    got = _try_extract_dimension_object(buf, "core_rules")
    assert got is not None
    fields, _, _ = got
    assert "灵气" in fields["power_system"]


def test_incremental_parser_emits_dimensions_in_order():
    parser = WorldbuildingStreamIncrementalParser()
    part1 = (
        '{"worldbuilding": {"core_rules": {'
        '"power_system": "玩家通过神经同步驱动剑气、身法与职业技能成长，非传统职业也能靠连招理解突破模板", '
        '"physics_rules": "游戏物理会计算现实反应延迟与肌肉记忆匹配度，零点零一秒的误差足以改写团战结果", '
        '"magic_tech": "训练舱用神经接口把操作意图转译为角色动作，同时记录疲劳阈值防止选手过载"}, '
    )
    part2 = (
        '"geography": {'
        '"terrain": "主城、赛场和训练基地围绕服务器节点分布，地下网吧藏在监管薄弱的旧城区", '
        '"climate": "赛季天气由服务器动态渲染，雨战会放大身法误差，雪图则压低远程视野", '
        '"resources": "高阶材料集中在联赛副本和训练服隐藏节点，普通玩家只能靠活动兑换碎片", '
        '"ecology": "野区机关与镜像怪会模拟职业队常用压迫路线，逼迫选手在移动中完成判断"}}}'
    )
    events = []
    events.extend(parser.feed(part1))
    events.extend(parser.feed(part2))
    keys = [e["key"] for e in events if e["type"] == "dimension"]
    assert "core_rules" in keys
    assert "geography" in keys


def test_parser_ignores_non_contract_keys():
    parser = WorldbuildingStreamIncrementalParser()
    chunk = (
        '{"worldbuilding": {"core_rules": {'
        '"power_system": "劫力体系按雷纹共鸣分层，修士需在实战中校准命格，失败者会被雷纹反噬", '
        '"physics_rules": "渡劫区会改变局部重力，普通人靠近后会失去方向感，法器也会短暂失灵", '
        '"magic_tech": "阵盘会记录雷纹误差并反向修正剑势，过载后需要闭关恢复神识稳定", '
        '"name": "自创字段"'
        "}}}"
    )
    events = parser.feed(chunk)
    fields = [e for e in events if e["type"] == "field"]
    field_names = {e["field"] for e in fields}
    assert "power_system" in field_names
    assert "physics_rules" in field_names
    assert "name" not in field_names
    dim = next(e for e in events if e["type"] == "dimension")
    assert "name" not in dim["content"]
    assert "劫力" in dim["content"]["power_system"]


def test_parser_emits_fields_after_complete_dimension_closes():
    parser = WorldbuildingStreamIncrementalParser()
    part1 = (
        '{"worldbuilding": {"core_rules": {'
        '"power_system": "劫力体系按雷纹共鸣分层，修士需在实战中校准命格，失误会留下雷痕伤", '
        '"physics_rules": "常态'
    )
    part2 = (
        '物理仍然有效，但灵气浓度会改变战斗反馈，重压区域会拖慢身法", '
        '"magic_tech": "阵盘会把雷纹共鸣转译为护体剑势，过载后需要静修校准经脉反馈"}}}'
    )
    events = []
    events.extend(parser.feed(part1))
    assert [e["type"] for e in events] == ["dimension_start"]
    assert events[0]["key"] == "core_rules"
    events.extend(parser.feed(part2))
    fields = [e for e in events if e["type"] == "field"]
    assert any(e["type"] == "field" and e["field"] == "power_system" for e in events)
    assert any(e["type"] == "field" and e["field"] == "physics_rules" for e in events)
    assert any(e["type"] == "field" and e["field"] == "magic_tech" for e in events)
    assert any(e["type"] == "dimension" for e in events)


def test_parser_does_not_push_items_before_dimension_closes():
    parser = WorldbuildingStreamIncrementalParser()
    events = []

    events.extend(parser.feed('{"worldbuilding": {"core_rules": {"power_system": "玩家通过'))
    assert [e["type"] for e in events] == ["dimension_start"]
    assert events[0]["key"] == "core_rules"

    later_events = parser.feed('神经同步驱动剑气与身法，依靠非标准连招绕开职业模板", "physics_rules": "游戏内时间流速')
    events.extend(later_events)
    assert later_events == []

    later_events = parser.feed('可调至现实的1.5倍，但玩家大脑仍按现实时间消耗能量", "magic_tech": "训练舱通过神经接口把操作意图转译为角色动作')
    events.extend(later_events)
    assert later_events == []

    events.extend(parser.feed('，同步率越高越容易留下认知错乱"}}}'))
    fields = [e for e in events if e["type"] == "field"]
    assert {e["field"]: e["value"] for e in fields} == {
        "power_system": "玩家通过神经同步驱动剑气与身法，依靠非标准连招绕开职业模板",
        "physics_rules": "游戏内时间流速可调至现实的1.5倍，但玩家大脑仍按现实时间消耗能量",
        "magic_tech": "训练舱通过神经接口把操作意图转译为角色动作，同步率越高越容易留下认知错乱",
    }


def test_parser_rejects_schema_incomplete_dimension():
    parser = WorldbuildingStreamIncrementalParser()
    events = []

    events.extend(parser.feed('{"worldbuilding": {"core_rules": {"power_system": "玩家通过", '))
    assert [e["type"] for e in events] == ["dimension_start"]

    events.extend(parser.feed('"physics_rules": "游戏内时间流速可调至现实的1.5倍，但玩家大脑仍按现实时间消耗能量"}}}'))
    fields = [e for e in events if e["type"] == "field"]
    assert fields == []
    assert not any(e["type"] == "dimension" for e in events)


def test_parser_ignores_invalid_dimension_string():
    parser = WorldbuildingStreamIncrementalParser()
    part1 = '{"worldbuilding": {"society": "剑修贵族垄断灵石矿'
    part2 = '，非剑修宗门需上缴七成收益才能获得庇护"}}'
    events = []
    events.extend(parser.feed(part1))
    assert events == []
    events.extend(parser.feed(part2))
    assert events == []


def test_parser_uses_closed_dimension_value_when_duplicate_keys_exist():
    parser = WorldbuildingStreamIncrementalParser()
    part1 = '{"worldbuilding": {"culture": {"history": "选手", '
    part2 = (
        '"history": "职业电竞联盟在十年前建立神经健康标准，但俱乐部用外包青训规避监管", '
        '"religion": "粉丝文化把冠军戒指视作圣物，退役名宿的操作录像会被反复拆解成仪式", '
        '"taboos": "公开操盘、伤病隐瞒和盗用战术库是职业圈红线，触犯者会被联盟永久除名"}}}'
    )

    events = []
    events.extend(parser.feed(part1))
    assert [e["type"] for e in events] == ["dimension_start"]

    events.extend(parser.feed(part2))
    history_fields = [
        e for e in events
        if e["type"] == "field" and e["key"] == "culture" and e["field"] == "history"
    ]
    assert history_fields[-1]["value"].startswith("职业电竞联盟")
    dim = next(e for e in events if e["type"] == "dimension" and e["key"] == "culture")
    assert dim["content"]["history"].startswith("职业电竞联盟")


def test_parser_flushes_previous_dimension_when_next_dimension_starts():
    parser = WorldbuildingStreamIncrementalParser()
    events = []

    events.extend(parser.feed(
        '{"worldbuilding": {"core_rules": {'
        '"power_system": "玩家以神经同步驱动剑气与身法，非传统打法能绕开标准职业模板", '
        '"physics_rules": "游戏时间流速和现实神经消耗分离，高倍速对战会放大反应误差", '
        '"magic_tech": "训练舱将肌肉记忆转译为角色动作，同步率越高越依赖昂贵监测设备"'
    ))
    assert [e["type"] for e in events] == ["dimension_start"]

    events.extend(parser.feed(', "geography": {'))
    assert events[-1] == {"type": "dimension_start", "key": "geography"}
