from application.evolution.services.context_presenter import ContextPresenter
from application.evolution.services.gate_service import EvolutionGateService
from domain.evolution.models import EvolutionState


def test_gate_blocks_dead_character_reappearance():
    state = EvolutionState.empty()
    state.characters["顾言之"] = {"status": "dead", "location": "悬崖底", "inventory": []}

    report = EvolutionGateService().check(
        novel_id="n1",
        chapter_number=2,
        outline_content="顾言之在客栈醒来。",
        state=state,
    )

    assert report.is_pass is False
    assert report.violations[0].type == "DEAD_CHARACTER_REAPPEARS"


def test_gate_does_not_block_ambiguous_character():
    state = EvolutionState.empty()
    state.characters["顾言之"] = {"status": "ambiguous", "location": "", "inventory": []}

    report = EvolutionGateService().check(
        novel_id="n1",
        chapter_number=2,
        outline_content="顾言之在雨夜归来。",
        state=state,
    )

    assert report.is_pass is True


def test_timeskip_downgrades_unresolved_action():
    state = EvolutionState.empty()
    state.scene["unresolved_actions"] = ["顾言之拔剑指向黑衣人"]

    report = EvolutionGateService().check(
        novel_id="n1",
        chapter_number=2,
        outline_content="[TimeSkip: 3 years] 顾言之在田里种地。",
        state=state,
    )

    assert report.is_pass is True
    assert report.violations[0].level == "info"


def test_presenter_hydrates_without_raw_json():
    state = EvolutionState.empty()
    state.characters["顾言之"] = {"status": "dead", "location": "皇城", "inventory": ["密道钥匙"]}
    state.scene["emotional_residue"] = "顾言之对乔知诺极度不信任。"

    text = ContextPresenter().present(state)

    assert "硬法则" in text
    assert "情绪余波" in text
    assert "{" not in text


def test_gate_matches_unified_character_name():
    class CharId:
        value = "char-001"

    class Character:
        id = CharId()
        name = "顾言之"

    class Repo:
        def list_by_novel(self, novel_id):
            return [Character()]

    state = EvolutionState.empty()
    state.characters["char-001"] = {"status": "dead", "location": "", "inventory": []}

    report = EvolutionGateService(character_repository=Repo()).check(
        novel_id="n1",
        chapter_number=2,
        outline_content="顾言之在客栈醒来。",
        state=state,
    )

    assert report.is_pass is False
    assert report.violations[0].type == "DEAD_CHARACTER_REAPPEARS"
