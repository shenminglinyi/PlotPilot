from types import SimpleNamespace

import pytest

from application.ai_invocation.continuation import ContinuationContext
from application.ai_invocation.dtos import (
    AdoptionDecision,
    ContinuationRef,
    InvocationPolicy,
    InvocationSession,
    InvocationSessionStatus,
    VariableBinding,
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


@pytest.fixture(autouse=True)
def _stub_bible_services(monkeypatch):
    captured = {"worldbuilding_updates": []}

    class _FakeBibleService:
        def ensure_bible_for_novel(self, _novel_id):
            return SimpleNamespace(
                characters=[],
                world_settings=[],
                locations=[],
                timeline_notes=[],
                style_notes=[],
            )

        def update_bible(self, **_kwargs):
            return None

    class _FakeWorldbuildingService:
        def update_worldbuilding(self, **kwargs):
            captured["worldbuilding_updates"].append(kwargs)
            return None

    monkeypatch.setattr(
        "application.world.services.bible_setup_continuation._get_services",
        lambda _context: (_FakeBibleService(), _FakeWorldbuildingService()),
    )
    monkeypatch.setattr(
        "application.world.services.bible_setup_continuation._refresh_shared_state",
        lambda _novel_id: None,
    )
    return captured


def test_worldbuilding_handler_accepts_top_level_split_fields():
    ctx = _make_context(
        "bible_worldbuilding",
        '{"style":"克制冷峻","core_rules":{'
        '"power_system":"武道九品到一品层层递进，先天境需要名望、功德和战绩共同支撑。",'
        '"physics_rules":"经脉反噬会随掠夺次数加重，未调和时轻则失控，重则走火入魔。",'
        '"magic_tech":"血脉战体通过厮杀或机缘吸收武学精髓，但必须以药物和功德压住副作用。"},'
        '"geography":{'
        '"terrain":"中原九州被天堑山脉分割，宗门、府城和绿林寨各守险要节点。",'
        '"climate":"北地风沙影响马匪路线，江南雨季抬高漕运风险，山中雾障利于埋伏。",'
        '"resources":"名药、矿脉和秘籍残页分散在府库、黑市与宗门禁地，取用都需付代价。",'
        '"ecology":"山林毒虫、猛兽和隐秘药谷共同塑造行路风险，夜宿破庙也不算安全。"}}',
    )

    result = bible_worldbuilding_handler(ctx)

    assert result["novel_id"] == "novel-1"
    assert result["style"] == "克制冷峻"
    assert result["worldbuilding"]["core_rules"]["power_system"].startswith("武道九品")
    assert result["core_rules"]["power_system"].startswith("武道九品")
    assert result["geography"]["terrain"].startswith("中原九州")
    assert "worldbuilding_full" not in result
    assert "core_rules_text" not in result
    assert "geography_text" not in result


def test_worldbuilding_handler_uses_output_bindings_for_custom_paths(monkeypatch):
    ctx = _make_context(
        "bible_worldbuilding",
        '{"用户文风":"冷硬克制","用户世界":{"用户法则":{'
        '"power_system":"武道九品到一品层层递进，先天境需要名望、功德和战绩共同支撑。",'
        '"physics_rules":"经脉反噬会随掠夺次数加重，未调和时轻则失控，重则走火入魔。",'
        '"magic_tech":"血脉战体通过厮杀或机缘吸收武学精髓，但必须以药物和功德压住副作用。"}}}',
    )

    monkeypatch.setattr(
        "application.world.services.bible_setup_continuation.load_session_output_bindings",
        lambda _session: [
            VariableBinding(alias="style", variable_key="worldbuilding.style", source_path="用户文风"),
            VariableBinding(alias="worldbuilding", variable_key="worldbuilding.content", source_path="用户世界"),
            VariableBinding(alias="core_rules", variable_key="worldbuilding.core_rules", source_path="用户世界.用户法则"),
        ],
    )

    result = bible_worldbuilding_handler(ctx)

    assert result["style"] == "冷硬克制"
    assert result["worldbuilding"]["core_rules"]["power_system"].startswith("武道九品")


def test_worldbuilding_handler_rejects_string_dimension_blocks(_stub_bible_services):
    ctx = _make_context(
        "bible_worldbuilding",
        '{"style":"锋利但留白","worldbuilding":{'
        '"core_rules":"核心法则围绕代价交换展开，所有能力都会留下可追踪痕迹。",'
        '"geography":"地理生态由断裂群岛和潮汐废墟构成，资源随季风迁移。",'
        '"society":"社会结构由港盟、旧贵族和流亡工会共同制衡。",'
        '"culture":"历史文化重视誓言、航海纪年和禁忌姓名。",'
        '"daily_life":"沉浸感细节集中在盐雾、灯塔班表和夜市暗语。"}}',
    )

    result = bible_worldbuilding_handler(ctx)

    assert "worldbuilding" not in result
    assert _stub_bible_services["worldbuilding_updates"] == []


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


def test_characters_handler_uses_output_bindings_for_custom_paths(monkeypatch):
    ctx = _make_context(
        "bible_characters",
        '{"用户角色":[{"name":"阿澄","description":"主角","relationships":[]}]}',
    )

    monkeypatch.setattr(
        "application.world.services.bible_setup_continuation.load_session_output_bindings",
        lambda _session: [
            VariableBinding(alias="characters", variable_key="characters.list", source_path="用户角色"),
        ],
    )

    result = bible_characters_handler(ctx)

    assert result["characters"][0]["name"] == "阿澄"


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


def test_locations_handler_uses_output_bindings_for_custom_paths(monkeypatch):
    ctx = _make_context(
        "bible_locations",
        '{"用户地点":[{"name":"天枢城","description":"主城","connections":[]}]}',
    )

    monkeypatch.setattr(
        "application.world.services.bible_setup_continuation.load_session_output_bindings",
        lambda _session: [
            VariableBinding(alias="locations", variable_key="locations.list", source_path="用户地点"),
        ],
    )

    result = bible_locations_handler(ctx)

    assert result["locations"][0]["name"] == "天枢城"
