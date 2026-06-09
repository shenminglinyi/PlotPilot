from types import SimpleNamespace

from application.engine.services.context_budget_allocator import ContextBudgetAllocator


class _BibleRepo:
    def get_by_novel_id(self, novel_id):
        return SimpleNamespace(characters=[], locations=[])


class _Kernel:
    def plan_cast(self, novel_id, chapter_number, outline, scene_director=None):
        return SimpleNamespace()

    def apply_cast_plan(self, plan):
        return None

    def build_context_locks(self, novel_id, chapter_number, plan=None):
        return SimpleNamespace(t0="角色锁定：阿止必须保持警觉。")


def test_character_anchors_kernel_branch_uses_module_novel_id(monkeypatch):
    allocator = ContextBudgetAllocator(
        bible_repository=_BibleRepo(),
        character_narrative_kernel=_Kernel(),
    )
    monkeypatch.setattr(
        allocator,
        "_projection_locks_for_plan",
        lambda novel_id, plan, tier: "",
    )

    anchors = allocator._get_character_anchors("novel-1", 3, outline="阿止入场")

    assert "角色锁定：阿止必须保持警觉。" in anchors
