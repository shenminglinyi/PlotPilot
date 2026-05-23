from types import SimpleNamespace

from application.engine.services.context_slot_providers import (
    build_narrative_promise_slot_content,
)
from domain.novel.value_objects.novel_id import NovelId


class FakeNovelRepository:
    def __init__(self, novel=None, fail=False):
        self.novel = novel
        self.fail = fail
        self.requested_id = None

    def get_by_id(self, novel_id):
        self.requested_id = novel_id
        if self.fail:
            raise RuntimeError("database unavailable")
        return self.novel


def test_narrative_promise_provider_returns_empty_without_repository():
    assert build_narrative_promise_slot_content(None, "novel-1", 3) == ""


def test_narrative_promise_provider_renders_from_novel_repository():
    novel = SimpleNamespace(
        title="我不是剑仙",
        premise="核心冲突：无根仙体挑战灵根枷锁\n开篇钩子：矿洞中发现天道骗局",
    )
    repo = FakeNovelRepository(novel)

    block = build_narrative_promise_slot_content(repo, "novel-1", 8)

    assert repo.requested_id == NovelId("novel-1")
    assert "叙事承诺锁" in block
    assert "无根仙体" in block
    assert "前12章" in block


def test_narrative_promise_provider_fails_closed():
    repo = FakeNovelRepository(fail=True)

    assert build_narrative_promise_slot_content(repo, "novel-1", 8) == ""
