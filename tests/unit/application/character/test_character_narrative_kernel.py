from __future__ import annotations

from dataclasses import dataclass, field

from application.character.services.character_narrative_kernel import CharacterNarrativeKernel


@dataclass
class _CID:
    value: str


@dataclass
class _Char:
    id: str
    name: str
    description: str = ""
    importance: str = "supporting"
    mental_state: str = "NORMAL"
    mental_state_reason: str = ""
    core_belief: str = ""
    moral_taboos: list[str] = field(default_factory=list)
    active_wounds: list[dict] = field(default_factory=list)
    voice_profile: dict = field(default_factory=dict)
    public_profile: str = ""
    hidden_profile: str = ""
    reveal_chapter: int | None = None

    @property
    def character_id(self):
        return _CID(self.id)


@dataclass
class _Bible:
    characters: list[_Char]
    locations: list = field(default_factory=list)


class _BibleRepo:
    def __init__(self, chars):
        self.bible = _Bible(chars)

    def get_by_novel_id(self, _novel_id):
        return self.bible


class _StoryNodeRepo:
    def get_by_novel_sync(self, novel_id):
        return []


def test_plan_cast_prefers_outline_mentions_then_importance():
    kernel = CharacterNarrativeKernel(
        bible_repository=_BibleRepo([
            _Char("c1", "林风", importance="protagonist"),
            _Char("c2", "秦柔", importance="supporting"),
            _Char("c3", "路远", importance="minor"),
        ]),
        story_node_repository=_StoryNodeRepo(),
    )

    plan = kernel.plan_cast("n1", 3, "秦柔在雨夜发现线索。", max_characters=2)

    assert [s.name for s in plan.slots] == ["秦柔", "林风"]
    assert plan.slots[0].importance == "normal"
    assert plan.slots[1].importance == "major"


def test_new_character_candidates_classify_scene_director_as_create():
    kernel = CharacterNarrativeKernel(
        bible_repository=_BibleRepo([_Char("c1", "林风")]),
        story_node_repository=_StoryNodeRepo(),
    )

    candidates = kernel.detect_new_character_candidates(
        "n1",
        4,
        "林风遇见沈照。",
        [_Char("c1", "林风")],
        scene_director={"characters": ["沈照"]},
    )

    target = next(c for c in candidates if c.name == "沈照")
    assert target.recommendation == "create_bible_character"
    assert target.narrative_function == "explicit_scene_cast"


def test_build_context_locks_maps_importance_to_tiers():
    kernel = CharacterNarrativeKernel(
        bible_repository=_BibleRepo([
            _Char(
                "c1",
                "林风",
                importance="protagonist",
                core_belief="绝不背叛同伴",
                moral_taboos=["不杀无辜者"],
                mental_state="焦虑",
            ),
            _Char("c2", "秦柔", importance="supporting", mental_state="平静"),
            _Char("c3", "路远", importance="minor"),
        ]),
        story_node_repository=_StoryNodeRepo(),
    )

    plan = kernel.plan_cast("n1", 2, "林风与秦柔会面。", max_characters=3)
    locks = kernel.build_context_locks("n1", 2, plan=plan)

    assert "林风" in locks.t0
    assert "核心信念" in locks.t0
    assert "秦柔" in locks.t1
    assert "路远" in locks.t2
