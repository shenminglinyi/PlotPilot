from application.engine.services.context_budget_allocator import ContextBudgetAllocator
from domain.evolution.models import ChapterEvolutionSnapshot, EvolutionState


class Repo:
    def __init__(self):
        self.requested = None

    def get_latest_active_before(self, novel_id, branch_id, chapter_number):
        self.requested = (novel_id, branch_id, chapter_number)
        state = EvolutionState.empty()
        state.scene["location"] = "皇城东门"
        return ChapterEvolutionSnapshot(
            snapshot_id="s1",
            novel_id=novel_id,
            branch_id=branch_id,
            chapter_number=chapter_number - 1,
            ending_state=state,
        )


class Presenter:
    def present(self, state):
        return f"STATE:{state.scene['location']}"


def test_evolution_presenter_uses_snapshot_before_current_chapter():
    repo = Repo()
    allocator = ContextBudgetAllocator(evolution_presenter=Presenter(), evolution_repository=repo)

    text = allocator._build_evolution_presenter_slot("n1", 12)

    assert repo.requested == ("n1", "main", 12)
    assert text == "STATE:皇城东门"
