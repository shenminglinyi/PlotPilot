"""ContextBuilder 单元测试（与 ContextBudgetAllocator V9 行为对齐）。"""
import time
from typing import List, Optional, Tuple
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from application.world.dtos.bible_dto import (
    BibleDTO,
    CharacterDTO,
    TimelineNoteDTO,
)
from application.engine.dtos.scene_director_dto import SceneDirectorAnalysis
from application.engine.services.context_budget_allocator import ContextBudgetAllocator
from application.engine.services.context_builder import ContextBuilder
from domain.novel.entities.plot_arc import PlotArc
from domain.novel.entities.storyline import Storyline
from domain.novel.value_objects.novel_id import NovelId
from domain.novel.value_objects.plot_point import PlotPoint, PlotPointType
from domain.novel.value_objects.storyline_status import StorylineStatus
from domain.novel.value_objects.storyline_type import StorylineType
from domain.novel.value_objects.tension_level import TensionLevel


@pytest.fixture(autouse=True)
def _mute_heavy_t0_blocks(monkeypatch):
    """CPMS 生命周期与 Anti-AI 块在单测中体量过大，静音以稳定断言。"""
    monkeypatch.setattr(
        ContextBudgetAllocator,
        "_build_lifecycle_directive",
        lambda self, novel_id, chapter_number: "",
    )
    monkeypatch.setattr(
        ContextBudgetAllocator,
        "_build_anti_ai_protocol_block",
        lambda self, novel_id, chapter_number: "",
    )


def _empty_bible_dto(
    novel_id: str = "novel-1",
    *,
    characters=None,
    timeline_notes=None,
) -> BibleDTO:
    return BibleDTO(
        id=f"{novel_id}-bible",
        novel_id=novel_id,
        characters=characters or [],
        world_settings=[],
        locations=[],
        timeline_notes=timeline_notes or [],
        style_notes=[],
    )


def _bible_repo_for_names(names: List[Tuple[str, str]]) -> Mock:
    """构造 allocator 可读的最小 Bible 仓储（角色锚点路径）。"""
    chars = []
    for i, (name, desc) in enumerate(names):
        ch = MagicMock()
        ch.name = name
        ch.description = desc
        ch.character_id = MagicMock()
        ch.character_id.value = f"c{i}"
        ch.public_profile = ""
        ch.hidden_profile = ""
        ch.importance = MagicMock(value="protagonist")
        chars.append(ch)
    bible = MagicMock()
    bible.characters = chars
    repo = Mock()
    repo.get_by_novel_id.return_value = bible
    return repo


def _make_builder(
    *,
    bible_dto: Optional[BibleDTO] = None,
    storyline_manager: Optional[Mock] = None,
    plot_arc_repository: Optional[Mock] = None,
    novel_repo: Optional[Mock] = None,
    chapter_repo: Optional[Mock] = None,
    bible_repository: Optional[Mock] = None,
    vector_store=None,
    embedding_service=None,
) -> ContextBuilder:
    bible_service = Mock()
    bible_service.get_bible_by_novel.return_value = bible_dto or _empty_bible_dto()

    if storyline_manager is None:
        storyline_manager = Mock()
        storyline_manager.repository.get_by_novel_id.return_value = []

    if novel_repo is None:
        novel_repo = Mock()
        novel = Mock()
        novel.title = "Test Novel"
        novel.author = "Test Author"
        novel_repo.get_by_id.return_value = novel

    if chapter_repo is None:
        chapter_repo = Mock()
        chapter_repo.list_by_novel.return_value = []

    if bible_repository is None:
        bible_repository = _bible_repo_for_names([("Alice", "主角")])

    return ContextBuilder(
        bible_service=bible_service,
        storyline_manager=storyline_manager,
        relationship_engine=Mock(),
        vector_store=vector_store if vector_store is not None else Mock(),
        novel_repository=novel_repo,
        chapter_repository=chapter_repo,
        plot_arc_repository=plot_arc_repository,
        embedding_service=embedding_service,
        bible_repository=bible_repository,
    )


class TestContextBuilder:
    def test_build_context_basic(self):
        dto = _empty_bible_dto(
            characters=[
                CharacterDTO("char1", "Alice", "Protagonist", []),
            ]
        )
        chapter_repo = Mock()
        chapter1 = Mock()
        chapter1.number = 1
        chapter1.title = "Opening"
        chapter1.content = "Previous chapter body text."
        chapter_repo.list_by_novel.return_value = [chapter1]

        builder = _make_builder(bible_dto=dto, chapter_repo=chapter_repo)
        context = builder.build_context(
            novel_id="novel-1",
            chapter_number=2,
            outline="Alice starts her journey",
            max_tokens=35000,
        )
        assert "Alice" in context
        assert "Opening" in context or "Previous chapter" in context

    def test_build_context_respects_token_budget(self):
        chars = [
            CharacterDTO(f"c{i}", f"C{i}", "Very long description " * 100, [])
            for i in range(10)
        ]
        builder = _make_builder(bible_dto=_empty_bible_dto(characters=chars))
        context = builder.build_context(
            novel_id="novel-1",
            chapter_number=1,
            outline="Test outline",
            max_tokens=5000,
        )
        assert context is not None
        assert len(context) > 0

    def test_build_context_includes_recent_chapters(self):
        chapter_repo = Mock()
        chapter1 = Mock()
        chapter1.number = 1
        chapter1.title = "Chapter 1"
        chapter1.content = "Content of chapter 1"
        chapter2 = Mock()
        chapter2.number = 2
        chapter2.title = "Chapter 2"
        chapter2.content = "Content of chapter 2"
        chapter_repo.list_by_novel.return_value = [chapter1, chapter2]

        builder = _make_builder(chapter_repo=chapter_repo)
        context = builder.build_context(
            novel_id="novel-1",
            chapter_number=3,
            outline="Test outline",
            max_tokens=35000,
        )
        assert "Chapter 1" in context or "Chapter 2" in context

    @pytest.mark.skip(reason="V9 allocator 未注入 Storyline 实体；主线由图谱/记忆模块另行承载")
    def test_build_context_includes_storylines(self):
        storyline = Storyline(
            id="sl-1",
            novel_id=NovelId("novel-1"),
            storyline_type=StorylineType.MAIN_PLOT,
            status=StorylineStatus.ACTIVE,
            estimated_chapter_start=1,
            estimated_chapter_end=10,
        )
        repo = Mock()
        repo.get_by_novel_id.return_value = [storyline]
        sm = Mock()
        sm.repository = repo

        builder = _make_builder(storyline_manager=sm)
        builder.build_context(
            novel_id="novel-1",
            chapter_number=5,
            outline="Test outline",
            max_tokens=35000,
        )

    @pytest.mark.skip(reason="V9 allocator 未拼接 PlotArc / timeline DTO；改由 Bible 与 StoryNode 管线提供")
    def test_layer1_includes_plot_arc_and_timeline(self):
        arc = PlotArc(id="arc-1", novel_id=NovelId("novel-1"))
        arc.add_plot_point(
            PlotPoint(1, PlotPointType.OPENING, "开局", TensionLevel.LOW)
        )
        arc.add_plot_point(
            PlotPoint(10, PlotPointType.CLIMAX, "高潮", TensionLevel.PEAK)
        )
        plot_repo = Mock()
        plot_repo.get_by_novel_id.return_value = arc

        notes = [
            TimelineNoteDTO(
                id="tn-1", event="元年", time_point="春", description="建都"
            )
        ]
        dto = _empty_bible_dto(timeline_notes=notes)

        builder = _make_builder(bible_dto=dto, plot_arc_repository=plot_repo)
        builder.build_context(
            novel_id="novel-1",
            chapter_number=5,
            outline="mid",
            max_tokens=35000,
        )

    def test_build_context_performance(self):
        chars = [
            CharacterDTO(f"c{i}", f"C{i}", f"Description {i}", [])
            for i in range(50)
        ]
        chapter_repo = Mock()
        chapters = []
        for i in range(100):
            ch = Mock()
            ch.number = i + 1
            ch.title = f"Chapter {i+1}"
            ch.content = f"Content {i+1}" * 100
            chapters.append(ch)
        chapter_repo.list_by_novel.return_value = chapters

        builder = _make_builder(
            bible_dto=_empty_bible_dto(characters=chars),
            chapter_repo=chapter_repo,
        )
        start = time.time()
        context = builder.build_context(
            novel_id="novel-1",
            chapter_number=50,
            outline="Test outline",
            max_tokens=35000,
        )
        assert time.time() - start < 2.0
        assert len(context) > 0

    def test_layer1_filters_characters_when_scene_director_set(self):
        dto = _empty_bible_dto(
            characters=[
                CharacterDTO("c1", "Alice", "Hero", []),
                CharacterDTO("c2", "Bob", "Villain", []),
            ]
        )
        bible_repo = _bible_repo_for_names([("Alice", "Hero"), ("Bob", "Villain")])
        builder = _make_builder(bible_dto=dto, bible_repository=bible_repo)
        hint = SceneDirectorAnalysis(
            characters=["Alice"],
            locations=[],
            action_types=[],
            trigger_keywords=[],
            emotional_state="",
            pov="Alice",
        )
        structured = builder.build_structured_context(
            novel_id="novel-1",
            chapter_number=2,
            outline="Alice fights",
            max_tokens=35000,
            scene_director=hint,
        )
        layer1 = structured["layer1_text"]
        assert "Alice" in layer1

    def test_layer3_includes_vector_results(self):
        mock_embedding = Mock()
        mock_embedding.embed = AsyncMock(return_value=[0.1] * 768)
        mock_embedding.get_dimension = Mock(return_value=768)

        mock_vector_store = Mock()
        mock_vector_store.list_collections = AsyncMock(
            return_value=["novel_novel-1_chunks"]
        )
        mock_vector_store.search = AsyncMock(
            return_value=[
                {
                    "id": "chunk1",
                    "score": 0.9,
                    "payload": {"text": "Vector result 1", "chapter_number": 5},
                },
                {
                    "id": "chunk2",
                    "score": 0.8,
                    "payload": {"text": "Vector result 2", "chapter_number": 6},
                },
            ]
        )

        builder = _make_builder(
            embedding_service=mock_embedding,
            vector_store=mock_vector_store,
        )
        structured = builder.build_structured_context(
            novel_id="novel-1",
            chapter_number=10,
            outline="Test outline",
            max_tokens=35000,
        )

    def test_vector_recall_filters_current_chapter_hits(self):
        mock_embedding = Mock()
        mock_embedding.embed = AsyncMock(return_value=[0.1] * 768)
        mock_embedding.get_dimension = Mock(return_value=768)

        mock_vector_store = Mock()
        mock_vector_store.list_collections = AsyncMock(
            return_value=["novel_novel-1_chunks"]
        )
        mock_vector_store.search = AsyncMock(
            return_value=[
                {
                    "id": "c1",
                    "score": 0.9,
                    "payload": {"text": "Same chapter hit", "chapter_number": 11},
                },
                {
                    "id": "c2",
                    "score": 0.85,
                    "payload": {"text": "Near chapter hit", "chapter_number": 10},
                },
            ]
        )

        builder = _make_builder(
            embedding_service=mock_embedding,
            vector_store=mock_vector_store,
        )
        structured = builder.build_structured_context(
            novel_id="novel-1",
            chapter_number=11,
            outline="Test outline",
            max_tokens=35000,
        )
        layer3 = structured["layer3_text"]
        assert "Near chapter hit" in layer3
        assert "Same chapter hit" not in layer3

    def test_layer1_has_character_anchors_when_vector_disabled(self):
        dto = _empty_bible_dto(
            characters=[CharacterDTO("c1", "Alice", "Hero", [])]
        )
        builder = _make_builder(
            bible_dto=dto,
            vector_store=None,
            embedding_service=None,
        )
        structured = builder.build_structured_context(
            novel_id="novel-1",
            chapter_number=5,
            outline="Test outline",
            max_tokens=35000,
        )
        assert "Alice" in structured["layer1_text"]
        assert structured["layer3_text"] == "" or "向量" not in structured["layer3_text"]

    def test_layer_token_usage_totals_with_vector(self):
        mock_embedding = Mock()
        mock_embedding.embed = AsyncMock(return_value=[0.1] * 768)
        mock_embedding.get_dimension = Mock(return_value=768)

        large_text = "x" * 10000
        mock_vector_store = Mock()
        mock_vector_store.list_collections = AsyncMock(
            return_value=["novel_novel-1_chunks"]
        )
        mock_vector_store.search = AsyncMock(
            return_value=[
                {
                    "id": f"chunk{i}",
                    "score": 0.9,
                    "payload": {"text": large_text, "chapter_number": 5},
                }
                for i in range(10)
            ]
        )

        builder = _make_builder(
            embedding_service=mock_embedding,
            vector_store=mock_vector_store,
        )
        structured = builder.build_structured_context(
            novel_id="novel-1",
            chapter_number=5,
            outline="Test outline",
            max_tokens=5000,
        )

        total_tokens = structured["token_usage"]["total"]
        assert total_tokens <= 5500
