import asyncio
from types import SimpleNamespace
from typing import Optional

from application.blueprint.services.story_structure_service import StoryStructureService
from domain.novel.value_objects.chapter_id import ChapterId
from domain.structure.story_node import NodeType


class _FakeStoryRepo:
    def __init__(self, nodes):
        self._nodes = {node.id: node for node in nodes}
        self.deleted_ids = []

    async def get_by_id(self, node_id):
        return self._nodes.get(node_id)

    def get_by_novel_sync(self, novel_id):
        return [node for node in self._nodes.values() if node.novel_id == novel_id]

    async def delete(self, node_id):
        existed = node_id in self._nodes
        if existed:
            self.deleted_ids.append(node_id)
            del self._nodes[node_id]
        return existed


class _FakeChapterRepo:
    def __init__(self, chapters, on_delete=None):
        self._chapters = {number: chapter for number, chapter in chapters.items()}
        self.deleted_numbers = []
        self._on_delete = on_delete

    def get_by_novel_and_number(self, novel_id, chapter_number):
        return self._chapters.get(chapter_number)

    def delete(self, chapter_id: ChapterId):
        for number, chapter in list(self._chapters.items()):
            current_id = chapter.id.value if hasattr(chapter.id, "value") else chapter.id
            if current_id == chapter_id.value:
                self.deleted_numbers.append(number)
                del self._chapters[number]
                if self._on_delete is not None:
                    self._on_delete(chapter_id.value)
                return


class _FakeCoordinator:
    def __init__(self):
        self.calls = []

    def on_chapter_deleted(
        self,
        novel_id: str,
        deleted_chapter_number: int,
        deleted_chapter_id: Optional[str] = None,
    ) -> None:
        self.calls.append((novel_id, deleted_chapter_number, deleted_chapter_id))


def _node(node_id: str, node_type: NodeType, number: int, parent_id: Optional[str] = None):
    return SimpleNamespace(
        id=node_id,
        novel_id="novel-1",
        parent_id=parent_id,
        node_type=node_type,
        number=number,
    )


def _chapter(number: int):
    return SimpleNamespace(id=f"chapter-{number}", number=number)


def test_delete_node_removes_descendant_chapters_before_deleting_structure_node():
    repo = _FakeStoryRepo(
        [
            _node("act-1", NodeType.ACT, 1),
            _node("chapter-1", NodeType.CHAPTER, 1, parent_id="act-1"),
            _node("chapter-2", NodeType.CHAPTER, 2, parent_id="act-1"),
        ]
    )
    chapter_repo = _FakeChapterRepo({1: _chapter(1), 2: _chapter(2)})
    coordinator = _FakeCoordinator()
    service = StoryStructureService(
        repo,
        chapter_repository=chapter_repo,
        chapter_renumber_coordinator=coordinator,
    )

    result = asyncio.run(service.delete_node("act-1"))

    assert result is True
    assert chapter_repo.deleted_numbers == [2, 1]
    assert coordinator.calls == [
        ("novel-1", 2, "chapter-2"),
        ("novel-1", 1, "chapter-1"),
    ]
    assert repo.deleted_ids == ["act-1"]


def test_delete_node_returns_true_when_direct_chapter_delete_removes_story_node():
    repo = _FakeStoryRepo([_node("chapter-1", NodeType.CHAPTER, 1)])
    chapter_repo = _FakeChapterRepo(
        {1: _chapter(1)},
        on_delete=lambda chapter_id: repo._nodes.pop(chapter_id, None),
    )
    coordinator = _FakeCoordinator()
    service = StoryStructureService(
        repo,
        chapter_repository=chapter_repo,
        chapter_renumber_coordinator=coordinator,
    )

    result = asyncio.run(service.delete_node("chapter-1"))

    assert result is True
    assert chapter_repo.deleted_numbers == [1]
    assert coordinator.calls == [("novel-1", 1, "chapter-1")]
    assert asyncio.run(repo.get_by_id("chapter-1")) is None
    assert repo.deleted_ids == []


def test_delete_node_returns_false_when_structure_delete_fails_after_chapter_cleanup():
    class _FailingDeleteStoryRepo(_FakeStoryRepo):
        async def delete(self, node_id):
            return False

    repo = _FailingDeleteStoryRepo(
        [
            _node("act-1", NodeType.ACT, 1),
            _node("chapter-1", NodeType.CHAPTER, 1, parent_id="act-1"),
        ]
    )
    chapter_repo = _FakeChapterRepo({1: _chapter(1)})
    service = StoryStructureService(repo, chapter_repository=chapter_repo)

    result = asyncio.run(service.delete_node("act-1"))

    assert result is False
    assert chapter_repo.deleted_numbers == [1]
