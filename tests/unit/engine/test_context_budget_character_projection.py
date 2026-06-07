from types import SimpleNamespace

from application.engine.services.context_budget_allocator import ContextBudgetAllocator


class FakeProjectionService:
    def __init__(self, projections):
        self.projections = projections

    def get_projection(self, novel_id, character_id):
        return self.projections.get(character_id, {})


def test_projection_locks_for_plan_prefers_major_t0_locks():
    allocator = ContextBudgetAllocator(
        character_projection_service=FakeProjectionService(
            {
                "hero": {"context_locks": {"t0": "英雄状态锁"}},
                "support": {"context_locks": {"t0": "配角状态锁"}},
            }
        )
    )
    plan = SimpleNamespace(
        slots=[
            SimpleNamespace(character_id="support", importance="normal"),
            SimpleNamespace(character_id="hero", importance="major"),
        ]
    )

    locks = allocator._projection_locks_for_plan("novel-1", plan, tier="t0")

    assert locks == "英雄状态锁"


def test_projection_locks_for_plan_maps_support_tiers():
    allocator = ContextBudgetAllocator(
        character_projection_service=FakeProjectionService(
            {
                "normal": {"context_locks": {"t1": "常规角色锁"}},
                "minor": {"context_locks": {"t2": "过场角色锁"}},
            }
        )
    )
    plan = SimpleNamespace(
        slots=[
            SimpleNamespace(character_id="normal", importance="normal"),
            SimpleNamespace(character_id="minor", importance="minor"),
        ]
    )

    locks = allocator._projection_locks_for_plan("novel-1", plan, tier="support")

    assert locks.splitlines() == ["常规角色锁", "过场角色锁"]
