"""角色状态抽取器测试。"""

from dataclasses import dataclass, field

from application.workflows.character_state_extractor import (
    extract_ability_tags,
    extract_bible_entity_states,
    extract_character_state,
)


@dataclass
class CharacterStub:
    id: str
    name: str
    description: str = ""
    public_profile: str = ""
    mental_state: str = "NORMAL"
    verbal_tic: str = ""
    idle_behavior: str = ""
    core_belief: str = ""
    moral_taboos: list[str] = field(default_factory=list)
    active_wounds: list[dict] = field(default_factory=list)
    voice_profile: dict = field(default_factory=dict)
    attributes: dict = field(default_factory=dict)


class BibleStub:
    def __init__(self, characters):
        self._characters = characters

    @property
    def characters(self):
        return list(self._characters)


def test_extract_ability_tags_without_topic_specific_allowlist():
    tags = extract_ability_tags("她擅长火系术法，也掌握精神魔法。")

    assert "火系" in tags
    assert "精神系" in tags


def test_extract_character_state_uses_structured_fields_and_public_text():
    character = CharacterStub(
        id="char-1",
        name="林舟",
        description="公开设定：擅长水魔法。",
        mental_state="警觉",
        verbal_tic="等一下",
        idle_behavior="转笔",
        core_belief="证据优先",
        moral_taboos=["背叛同伴"],
        voice_profile={"style": "短句"},
        attributes={"rank": "二阶"},
    )

    state = extract_character_state(character)

    assert state["rank"] == "二阶"
    assert state["mental_state"] == "警觉"
    assert state["verbal_tic"] == "等一下"
    assert state["idle_behavior"] == "转笔"
    assert state["core_belief"] == "证据优先"
    assert state["moral_taboos"] == ["背叛同伴"]
    assert state["voice_profile"] == {"style": "短句"}
    assert state["magic_type"] == "水系"
    assert "水系" in state["ability_tags"]


def test_extract_bible_entity_states_skips_empty_characters():
    bible = BibleStub([
        CharacterStub(id="char-1", name="林舟", description="擅长雷系追踪。"),
        CharacterStub(id="char-2", name="路人"),
    ])

    states = extract_bible_entity_states(bible)

    assert states["char-1"]["magic_type"] == "雷系"
    assert "char-2" not in states
