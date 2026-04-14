from application.engine.services.context_budget_allocator import ContextBudgetAllocator


def test_allocate_without_triple_repository_does_not_raise():
    allocator = ContextBudgetAllocator()

    allocation = allocator.allocate(
        novel_id="novel-1",
        chapter_number=1,
        outline="主角第一次进入遗迹。",
        total_budget=2000,
    )

    assert "graph_subnetwork" in allocation.slots
    assert allocation.slots["graph_subnetwork"].content == ""
