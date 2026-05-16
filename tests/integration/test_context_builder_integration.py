"""ContextBuilder 集成测试（与 Bible DTO / 故事线 协作）。"""
from unittest.mock import MagicMock, Mock

from application.dtos.bible_dto import BibleDTO, CharacterDTO
from application.engine.services.context_builder import ContextBuilder
from domain.bible.entities.character import Character
from domain.bible.value_objects.character_id import CharacterId
from domain.bible.value_objects.character_importance import CharacterImportance
from domain.bible.services.appearance_scheduler import AppearanceScheduler
from domain.bible.services.relationship_engine import RelationshipEngine
from domain.bible.value_objects.activity_metrics import ActivityMetrics
from domain.bible.value_objects.relationship_graph import RelationshipGraph
from domain.novel.entities.storyline import Storyline
from domain.novel.value_objects.novel_id import NovelId
from domain.novel.value_objects.storyline_status import StorylineStatus
from domain.novel.value_objects.storyline_type import StorylineType


def _bible_repository_stub(names: list[tuple[str, str]]) -> Mock:
    """ allocator 角色锚点所需的最小 Bible 仓储。"""
    chars = []
    for i, (name, desc) in enumerate(names):
        ch = MagicMock()
        ch.name = name
        ch.description = desc
        ch.character_id = MagicMock()
        ch.character_id.value = f"id-{i}"
        ch.public_profile = ""
        ch.hidden_profile = ""
        ch.importance = MagicMock(value="protagonist")
        chars.append(ch)
    bible = MagicMock()
    bible.characters = chars
    repo = Mock()
    repo.get_by_novel_id.return_value = bible
    return repo


class TestContextBuilderIntegration:
    def test_full_context_building_workflow(self):
        protagonist = Character(
            CharacterId("char-1"),
            "Alice",
            "A brave warrior seeking revenge for her family",
        )
        major_support = Character(
            CharacterId("char-2"),
            "Bob",
            "Alice's loyal companion and strategist",
        )
        minor_char = Character(
            CharacterId("char-3"),
            "Charlie",
            "A merchant who provides information",
        )

        bible_dto = BibleDTO(
            id="novel-1-bible",
            novel_id="novel-1",
            characters=[
                CharacterDTO(
                    protagonist.character_id.value,
                    protagonist.name,
                    protagonist.description,
                    [],
                ),
                CharacterDTO(
                    major_support.character_id.value,
                    major_support.name,
                    major_support.description,
                    [],
                ),
                CharacterDTO(
                    minor_char.character_id.value,
                    minor_char.name,
                    minor_char.description,
                    [],
                ),
            ],
            world_settings=[],
            locations=[],
            timeline_notes=[],
            style_notes=[],
        )

        bible_service = Mock()
        bible_service.get_bible_by_novel.return_value = bible_dto

        relationship_engine = RelationshipEngine(RelationshipGraph())

        storyline_repo = Mock()
        storyline = Storyline(
            id="storyline-1",
            novel_id=NovelId("novel-1"),
            storyline_type=StorylineType.MAIN_PLOT,
            status=StorylineStatus.ACTIVE,
            estimated_chapter_start=1,
            estimated_chapter_end=20,
        )
        storyline_repo.get_by_novel_id.return_value = [storyline]
        storyline_manager = Mock()
        storyline_manager.repository = storyline_repo

        vector_store = Mock()
        novel_repo = Mock()
        chapter_repo = Mock()

        novel = Mock()
        novel.title = "The Quest for Vengeance"
        novel.author = "Test Author"
        novel_repo.get_by_id.return_value = novel

        prev_chapter = Mock()
        prev_chapter.number = 5
        prev_chapter.title = "The Betrayal"
        prev_chapter.content = (
            "Alice discovered the truth about her family's death..."
        )
        chapter_repo.list_by_novel.return_value = [prev_chapter]

        context_builder = ContextBuilder(
            bible_service=bible_service,
            storyline_manager=storyline_manager,
            relationship_engine=relationship_engine,
            vector_store=vector_store,
            novel_repository=novel_repo,
            chapter_repository=chapter_repo,
            bible_repository=_bible_repository_stub(
                [
                    ("Alice", protagonist.description),
                    ("Bob", major_support.description),
                    ("Charlie", minor_char.description),
                ]
            ),
        )

        outline = "Alice and Bob plan their next move against the enemy"
        context = context_builder.build_context(
            novel_id="novel-1",
            chapter_number=6,
            outline=outline,
            max_tokens=35000,
        )

        assert "Alice" in context
        assert "Bob" in context
        assert "The Betrayal" in context

        tokens = context_builder.estimate_tokens(context)
        assert tokens <= 35000

        # build_context 走洋葱槽位拼接（生命周期沙漏 + 角色锚点 + 最近章节等）
        assert "===" in context

    def test_appearance_scheduler_integration(self):
        char1 = Character(CharacterId("char1"), "Alice", "Protagonist")
        char2 = Character(CharacterId("char2"), "Bob", "Supporting")
        char3 = Character(CharacterId("char3"), "Charlie", "Minor")

        metrics1 = ActivityMetrics()
        metrics1.update_activity(10, 5)

        metrics2 = ActivityMetrics()
        metrics2.update_activity(8, 3)

        metrics3 = ActivityMetrics()
        metrics3.update_activity(2, 1)

        available = [
            (char1, CharacterImportance.PROTAGONIST, metrics1),
            (char2, CharacterImportance.MAJOR_SUPPORTING, metrics2),
            (char3, CharacterImportance.MINOR, metrics3),
        ]

        scheduler = AppearanceScheduler()
        outline = "Alice and Bob discuss their strategy"
        selected = scheduler.schedule_appearances(outline, available, max_characters=2)

        assert len(selected) == 2
        assert char1 in selected
        assert char2 in selected
        assert char3 not in selected

    def test_context_builder_with_large_cast(self):
        characters = [
            CharacterDTO("char-0", "Hero", "The main character", []),
        ]
        for i in range(1, 11):
            characters.append(
                CharacterDTO(f"char-{i}", f"Support{i}", f"Supporting {i}", [])
            )
        for i in range(11, 61):
            characters.append(
                CharacterDTO(f"char-{i}", f"Minor{i}", f"Minor {i}", [])
            )

        bible_dto = BibleDTO(
            id="novel-1-bible",
            novel_id="novel-1",
            characters=characters,
            world_settings=[],
            locations=[],
            timeline_notes=[],
            style_notes=[],
        )
        bible_service = Mock()
        bible_service.get_bible_by_novel.return_value = bible_dto

        relationship_engine = RelationshipEngine(RelationshipGraph())

        storyline_manager = Mock()
        storyline_manager.repository.get_by_novel_id.return_value = []

        novel_repo = Mock()
        novel = Mock()
        novel.title = "Epic Tale"
        novel.author = "Author"
        novel_repo.get_by_id.return_value = novel

        chapter_repo = Mock()
        chapter_repo.list_by_novel.return_value = []

        context_builder = ContextBuilder(
            bible_service=bible_service,
            storyline_manager=storyline_manager,
            relationship_engine=relationship_engine,
            vector_store=Mock(),
            novel_repository=novel_repo,
            chapter_repository=chapter_repo,
            bible_repository=_bible_repository_stub(
                [(c.name, c.description or "") for c in characters]
            ),
        )

        context = context_builder.build_context(
            novel_id="novel-1",
            chapter_number=1,
            outline="Hero begins the journey",
            max_tokens=10000,
        )

        tokens = context_builder.estimate_tokens(context)
        assert tokens <= 11000
        assert "Hero" in context
