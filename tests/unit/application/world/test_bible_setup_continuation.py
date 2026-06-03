from application.ai_invocation.dtos import AdoptionDecision, ContinuationRef, InvocationSession, InvocationSessionStatus, InvocationPolicy
from application.ai_invocation.continuation import ContinuationContext
from application.world.services.bible_setup_continuation import (
    bible_characters_handler,
    bible_locations_handler,
    bible_worldbuilding_handler,
)


class _FakeBibleService:
    def __init__(self):
        self.styles = []
        self.characters = []
        self.locations = []

    def add_style_note(self, **kwargs):
        self.styles.append(kwargs)

    def add_character(self, **kwargs):
        self.characters.append(kwargs)

    def upsert_character(self, **kwargs):
        for idx, character in enumerate(self.characters):
            if character["character_id"] == kwargs["character_id"]:
                self.characters[idx] = kwargs
                return
        self.characters.append(kwargs)

    def add_location(self, **kwargs):
        self.locations.append(kwargs)


class _FakeWorldbuildingService:
    def __init__(self):
        self.updated = []

    def update_worldbuilding(self, **kwargs):
        self.updated.append(kwargs)


def _make_context(content: str) -> ContinuationContext:
    session = InvocationSession(
        id="session-1",
        operation="bible.setup.worldbuilding",
        node_key="bible-worldbuilding",
        policy=InvocationPolicy.FULL_INTERACTIVE,
        status=InvocationSessionStatus.AWAITING_COMMIT,
        context={"novel_id": "novel-1"},
        continuation=ContinuationRef(handler_key="bible_worldbuilding"),
    )
    decision = AdoptionDecision(
        id="decision-1",
        session_id=session.id,
        attempt_id="attempt-1",
        accepted_content=content,
    )
    return ContinuationContext(session=session, decision=decision)


def test_worldbuilding_handler_accepts_top_level_split_fields(monkeypatch):
    bible_service = _FakeBibleService()
    worldbuilding_service = _FakeWorldbuildingService()
    monkeypatch.setattr(
        "application.world.services.bible_setup_continuation._get_services",
        lambda _ctx: (bible_service, worldbuilding_service),
    )

    ctx = _make_context(
        '{"style":"克制冷峻","core_rules":{"power_system":"体系A","physics_rules":"规则B","magic_tech":"机制C"},'
        '"geography":{"terrain":"地形A","climate":"气候B","resources":"资源C","ecology":"生态D"}}'
    )

    result = bible_worldbuilding_handler(ctx)

    assert result["style"] == "克制冷峻"
    assert result["worldbuilding"]["core_rules"]["power_system"] == "体系A"
    assert result["core_rules"]["power_system"] == "体系A"
    assert result["geography"]["terrain"] == "地形A"
    assert "worldbuilding_full" not in result
    assert "core_rules_text" not in result
    assert "geography_text" not in result
    assert bible_service.styles[0]["content"] == "克制冷峻"
    assert worldbuilding_service.updated


def test_characters_handler_repairs_stringified_arrays(monkeypatch):
    bible_service = _FakeBibleService()
    monkeypatch.setattr(
        "application.world.services.bible_setup_continuation._get_services",
        lambda _ctx: (bible_service, None),
    )

    ctx = _make_context(
        '{"characters":[{"name":"阿澄","description":"主角","relationships":"[{\\"target\\":\\"林墨\\",\\"relation\\":\\"师徒\\"}]","'
        'gender":"女","age":"19","appearance":"白发","personality":"冷静","background":"流亡者",'
        '"core_motivation":"找回故土","inner_lack":"学会信任同伴",'
        '"moral_taboos":"[\\"杀无辜\\"]","voice_profile":"{\\"style\\":\\"克制\\"}","active_wounds":"[{\\"description\\":\\"旧伤\\"}]"}]}'
    )

    result = bible_characters_handler(ctx)

    assert result["characters"][0]["id"] == "novel-1-char-1"
    assert result["protagonist"]["name"] == "阿澄"
    assert bible_service.characters[0]["relationships"][0]["target"] == "林墨"
    assert bible_service.characters[0]["gender"] == "女"
    assert bible_service.characters[0]["age"] == "19"
    assert bible_service.characters[0]["appearance"] == "白发"
    assert bible_service.characters[0]["personality"] == "冷静"
    assert bible_service.characters[0]["background"] == "流亡者"
    assert bible_service.characters[0]["core_motivation"] == "找回故土"
    assert bible_service.characters[0]["inner_lack"] == "学会信任同伴"
    assert bible_service.characters[0]["moral_taboos"] == ["杀无辜"]
    assert bible_service.characters[0]["voice_profile"]["style"] == "克制"
    assert bible_service.characters[0]["active_wounds"][0]["description"] == "旧伤"


def test_characters_handler_drops_truncated_tail_item(monkeypatch):
    bible_service = _FakeBibleService()
    monkeypatch.setattr(
        "application.world.services.bible_setup_continuation._get_services",
        lambda _ctx: (bible_service, None),
    )

    ctx = _make_context(
        '{"characters":[{"name":"阿澄","description":"主角","relationships":[]},'
        '{"name":"林墨","description":"盟友","relationships":[]},'
        '{"name":"半截角色","description":"会被丢弃","relationships":[{"target":"未完","relation":"师徒"}'
    )

    result = bible_characters_handler(ctx)

    assert [item["name"] for item in result["characters"]] == ["阿澄", "林墨"]
    assert [item["name"] for item in bible_service.characters] == ["阿澄", "林墨"]


def test_characters_handler_is_idempotent_for_existing_ids(monkeypatch):
    bible_service = _FakeBibleService()
    bible_service.characters.append(
        {
            "novel_id": "novel-1",
            "character_id": "novel-1-char-1",
            "name": "旧名",
            "description": "旧描述",
        }
    )
    monkeypatch.setattr(
        "application.world.services.bible_setup_continuation._get_services",
        lambda _ctx: (bible_service, None),
    )

    ctx = _make_context(
        '{"characters":[{"name":"新名","role":"主角","description":"新描述","relationships":[]}]}'
    )

    result = bible_characters_handler(ctx)

    assert result["characters"][0]["id"] == "novel-1-char-1"
    assert len(bible_service.characters) == 1
    assert bible_service.characters[0]["name"] == "新名"
    assert bible_service.characters[0]["description"] == "主角 - 新描述"


def test_locations_handler_repairs_stringified_arrays(monkeypatch):
    bible_service = _FakeBibleService()
    monkeypatch.setattr(
        "application.world.services.bible_setup_continuation._get_services",
        lambda _ctx: (bible_service, None),
    )

    ctx = _make_context(
        '{"locations":[{"name":"天枢城","description":"主城","type":"城市","connections":"[{\\"target\\":\\"外城\\",\\"relation\\":\\"通往\\"}]"}]}'
    )

    result = bible_locations_handler(ctx)

    assert result["locations"][0]["id"] == "novel-1-loc-1"
    assert result["existing_locations"][0]["name"] == "天枢城"
    assert bible_service.locations[0]["connections"][0]["target"] == "外城"
