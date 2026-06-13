from types import SimpleNamespace

from application.blueprint.services.chapter_continuity_ledger import (
    ChapterContinuityLedgerService,
)


class _ChapterRepo:
    def __init__(self, chapters):
        self._chapters = chapters

    def list_by_novel(self, _novel_id):
        return self._chapters


class _StoryNodeRepo:
    def __init__(self, nodes):
        self._nodes = nodes

    def get_tree_sync(self, _novel_id):
        return SimpleNamespace(nodes=self._nodes)


def _chapter(number: int, *, outline: str = ""):
    return SimpleNamespace(
        number=number,
        title=f"第{number}章",
        outline=outline,
        content="",
    )


def _node(number: int, metadata):
    return SimpleNamespace(
        number=number,
        title=f"第{number}章",
        node_type=SimpleNamespace(value="chapter"),
        metadata=metadata,
        outline="",
        content="",
    )


def test_planning_context_prefers_lightweight_act_plan_over_tail_of_full_preplan():
    full_outline_tail = "六、爽点/反转设计：重复爽点总结\n七、主角状态变化：重复状态总结"
    service = ChapterContinuityLedgerService(
        chapter_repository=_ChapterRepo([_chapter(1, outline=full_outline_tail)]),
        story_node_repo=_StoryNodeRepo(
            [
                _node(
                    1,
                    {
                        "act_chapter_plan": {
                            "number": 1,
                            "title": "第1章",
                            "main_event": "苏念完成本章唯一主事件",
                            "handoff_from_previous": "本幕入口",
                            "handoff_to_next": "明确交给下一章的钩子",
                            "required_threads": ["主线"],
                        }
                    },
                )
            ]
        ),
    )

    text = service.build_for_chapter("novel-1", 2).to_planning_context_text()

    assert "最近3章承接摘要" in text
    assert "主事件：苏念完成本章唯一主事件" in text
    assert "交给下一章：明确交给下一章的钩子" in text
    assert "爽点/反转设计" not in text
    assert "主角状态变化" not in text
