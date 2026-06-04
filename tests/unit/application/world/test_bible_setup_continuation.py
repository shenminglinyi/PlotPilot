from application.ai_invocation.continuation import ContinuationContext
from application.ai_invocation.dtos import (
    AdoptionDecision,
    ContinuationRef,
    InvocationPolicy,
    InvocationSession,
    InvocationSessionStatus,
)
from application.world.services.bible_setup_continuation import (
    bible_characters_handler,
    bible_locations_handler,
    bible_worldbuilding_handler,
)


def _make_context(handler_key: str, content: str) -> ContinuationContext:
    session = InvocationSession(
        id="session-1",
        operation="bible.setup.worldbuilding",
        node_key="bible-worldbuilding",
        policy=InvocationPolicy.FULL_INTERACTIVE,
        status=InvocationSessionStatus.AWAITING_COMMIT,
        context={"novel_id": "novel-1"},
        continuation=ContinuationRef(handler_key=handler_key),
    )
    decision = AdoptionDecision(
        id="decision-1",
        session_id=session.id,
        attempt_id="attempt-1",
        accepted_content=content,
    )
    return ContinuationContext(session=session, decision=decision)


def test_worldbuilding_handler_accepts_top_level_split_fields():
    ctx = _make_context(
        "bible_worldbuilding",
        '{"style":"克制冷峻","core_rules":{"power_system":"体系A","physics_rules":"规则B","magic_tech":"机制C"},'
        '"geography":{"terrain":"地形A","climate":"气候B","resources":"资源C","ecology":"生态D"}}',
    )

    result = bible_worldbuilding_handler(ctx)

    assert result["novel_id"] == "novel-1"
    assert result["style"] == "克制冷峻"
    assert result["worldbuilding"]["core_rules"]["power_system"] == "体系A"
    assert result["core_rules"]["power_system"] == "体系A"
    assert result["geography"]["terrain"] == "地形A"
    assert "worldbuilding_full" not in result
    assert "core_rules_text" not in result
    assert "geography_text" not in result


def test_characters_handler_repairs_stringified_arrays():
    ctx = _make_context(
        "bible_characters",
        '{"characters":[{"name":"阿澄","description":"主角","relationships":"[{\\"target\\":\\"林墨\\",\\"relation\\":\\"师徒\\"}]","'
        'gender":"女","age":"19","appearance":"白发","personality":"冷静","background":"流亡者",'
        '"core_motivation":"找回故土","inner_lack":"学会信任同伴",'
        '"moral_taboos":"[\\"杀无辜\\"]","voice_profile":"{\\"style\\":\\"克制\\"}","active_wounds":"[{\\"description\\":\\"旧伤\\"}]"}]}',
    )

    result = bible_characters_handler(ctx)
    row = result["characters"][0]

    assert row["id"] == "novel-1-char-1"
    assert result["protagonist"]["name"] == "阿澄"
    assert row["relationships"][0]["target"] == "林墨"
    assert row["gender"] == "女"
    assert row["age"] == "19"
    assert row["appearance"] == "白发"
    assert row["personality"] == "冷静"
    assert row["background"] == "流亡者"
    assert row["core_motivation"] == "找回故土"
    assert row["inner_lack"] == "学会信任同伴"
    assert row["moral_taboos"] == ["杀无辜"]
    assert row["voice_profile"]["style"] == "克制"
    assert row["active_wounds"][0]["description"] == "旧伤"


def test_characters_handler_drops_truncated_tail_item():
    ctx = _make_context(
        "bible_characters",
        '{"characters":[{"name":"阿澄","description":"主角","relationships":[]},'
        '{"name":"林墨","description":"盟友","relationships":[]},'
        '{"name":"半截角色","description":"会被丢弃","relationships":[{"target":"未完","relation":"师徒"}',
    )

    result = bible_characters_handler(ctx)

    assert [item["name"] for item in result["characters"]] == ["阿澄", "林墨"]
    assert result["protagonist"]["name"] == "阿澄"


def test_characters_handler_keeps_existing_ids():
    ctx = _make_context(
        "bible_characters",
        '{"characters":[{"id":"novel-1-char-1","name":"新名","role":"主角","description":"新描述","relationships":[]}]}',
    )

    result = bible_characters_handler(ctx)

    assert result["characters"][0]["id"] == "novel-1-char-1"
    assert result["characters"][0]["name"] == "新名"
    assert result["characters"][0]["description"] == "新描述"


def test_locations_handler_repairs_stringified_arrays():
    ctx = _make_context(
        "bible_locations",
        '{"locations":[{"name":"天枢城","description":"主城","type":"城市","connections":"[{\\"target\\":\\"外城\\",\\"relation\\":\\"通往\\"}]"}]}',
    )

    result = bible_locations_handler(ctx)
    row = result["locations"][0]

    assert row["id"] == "novel-1-loc-1"
    assert result["existing_locations"][0]["name"] == "天枢城"
    assert row["connections"][0]["target"] == "外城"
