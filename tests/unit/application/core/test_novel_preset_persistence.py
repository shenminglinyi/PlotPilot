from unittest.mock import Mock

from application.core.dtos.novel_dto import NovelDTO
from application.core.services.novel_service import NovelService
from domain.novel.entities.novel import Novel
from domain.novel.value_objects.generation_preferences import GenerationPreferences
from domain.novel.value_objects.novel_id import NovelId


def test_create_novel_persists_locked_genre_and_world_preset_in_generation_prefs():
    novel_repository = Mock()
    chapter_repository = Mock()
    service = NovelService(novel_repository, chapter_repository)

    dto = service.create_novel(
        novel_id="novel-1",
        title="测试小说",
        author="测试作者",
        target_chapters=100,
        premise="作者设定",
        genre="玄幻 / 东方玄幻",
        world_preset="高武末世",
    )

    saved_novel = novel_repository.save.call_args.args[0]
    assert saved_novel.generation_prefs.locked_genre == "玄幻 / 东方玄幻"
    assert saved_novel.generation_prefs.locked_world_preset == "高武末世"
    assert dto.locked_genre == "玄幻 / 东方玄幻"
    assert dto.locked_world_preset == "高武末世"


def test_novel_dto_prefers_generation_prefs_over_premise_parsing_for_locked_presets():
    novel = Novel(
        id=NovelId("novel-1"),
        title="测试小说",
        author="测试作者",
        target_chapters=100,
        premise="这里只保留作者正文，不包含类型前缀",
        generation_prefs=GenerationPreferences(
            locked_genre="仙侠 / 凡人流",
            locked_world_preset="宗门修真",
        ),
    )

    dto = NovelDTO.from_domain(novel)

    assert dto.locked_genre == "仙侠 / 凡人流"
    assert dto.locked_world_preset == "宗门修真"
