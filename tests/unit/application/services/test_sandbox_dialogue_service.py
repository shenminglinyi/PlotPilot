from application.workbench.dtos.sandbox_dto import DialogueEntry
from application.workbench.services.sandbox_dialogue_service import SandboxDialogueService
from application.world.dtos.bible_dto import CharacterDTO


class FakeNarrativeEventRepository:
    def __init__(self, events):
        self._events = events

    def list_up_to_chapter(self, novel_id: str, max_chapter_inclusive: int):
        return list(self._events)


def test_get_recent_character_dialogues_extracts_content_and_scene_context():
    repo = FakeNarrativeEventRepository(
        [
            {
                "event_id": "evt-1",
                "chapter_number": 2,
                "event_summary": "沈霁：我从不做没把握的事。",
                "tags": ["对话:沈霁", "场景:祠堂夜谈"],
            },
            {
                "event_id": "evt-2",
                "chapter_number": 5,
                "event_summary": "沈霁: 柳月若插手，局势只会更乱。",
                "tags": ["对白:沈霁", "场景:雨夜巷战"],
            },
            {
                "event_id": "evt-3",
                "chapter_number": 6,
                "event_summary": "顾寒：你还是一样嘴硬。",
                "tags": ["对话:顾寒", "场景:城门对峙"],
            },
        ]
    )
    service = SandboxDialogueService(repo)

    dialogues = service.get_recent_character_dialogues("novel-1", "沈霁", limit=2)

    assert [item.chapter for item in dialogues] == [5, 2]
    assert dialogues[0].content == "柳月若插手，局势只会更乱。"
    assert dialogues[0].context == "雨夜巷战"
    assert dialogues[1].content == "我从不做没把握的事。"


def test_build_dialogue_generation_prompt_includes_relationships_history_and_scene_characters():
    service = SandboxDialogueService(FakeNarrativeEventRepository([]))
    character = CharacterDTO(
        id="shenji",
        name="沈霁",
        description="冷静克制的剑修",
        relationships=[{"target_name": "柳月", "relation": "师徒"}],
        public_profile="行事果决，不喜废话",
        mental_state="压着火气",
        verbal_tic="少废话",
        idle_behavior="指腹轻敲剑鞘",
    )
    other_character = CharacterDTO(
        id="liuyue",
        name="柳月",
        description="沈霁的师父，处事周全",
        relationships=[],
    )
    prompt = service.build_dialogue_generation_prompt(
        character=character,
        scene_prompt="顾寒逼近时，柳月想上前阻止。",
        mental_state="压着火气",
        verbal_tic="少废话",
        idle_behavior="指腹轻敲剑鞘",
        all_characters=[character, other_character],
        recent_dialogues=[
            DialogueEntry(
                dialogue_id="evt-1",
                chapter=8,
                speaker="沈霁",
                content="我说过，别替我做决定。",
                context="山门争执",
                tags=["对话:沈霁"],
            )
        ],
    )

    assert "角色关系" in prompt.user
    assert "柳月：师徒" in prompt.user
    assert "历史对白样本" in prompt.user
    assert "第8章 / 山门争执：我说过，别替我做决定。" in prompt.user
    assert "场景点名的相关角色" in prompt.user
    assert "柳月" in prompt.user
    assert "少废话" in prompt.user


def test_clean_generated_dialogue_strips_prefix_and_wrapping_quotes():
    service = SandboxDialogueService(FakeNarrativeEventRepository([]))

    cleaned = service.clean_generated_dialogue("沈霁：“少废话，退后。”", "沈霁")

    assert cleaned == "少废话，退后。"
