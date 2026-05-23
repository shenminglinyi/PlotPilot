from application.engine.services.context_budget_allocator import (
    BudgetAllocation,
    ContextSlot,
    PriorityTier,
)


def test_context_slot_mandatory_tracks_t0_tier():
    assert ContextSlot(name="lock", tier=PriorityTier.T0_CRITICAL).is_mandatory
    assert not ContextSlot(name="recent", tier=PriorityTier.T2_DYNAMIC).is_mandatory


def test_budget_allocation_final_context_orders_by_tier_and_priority():
    allocation = BudgetAllocation(
        slots={
            "recent": ContextSlot(
                name="recent chapters",
                tier=PriorityTier.T2_DYNAMIC,
                content="recent",
                priority=10,
            ),
            "anchor": ContextSlot(
                name="anchor",
                tier=PriorityTier.T0_CRITICAL,
                content="anchor",
                priority=10,
            ),
            "promise": ContextSlot(
                name="promise",
                tier=PriorityTier.T0_CRITICAL,
                content="promise",
                priority=20,
            ),
        }
    )

    final_context = allocation.get_final_context()

    assert final_context.index("PROMISE") < final_context.index("ANCHOR")
    assert final_context.index("ANCHOR") < final_context.index("RECENT CHAPTERS")
