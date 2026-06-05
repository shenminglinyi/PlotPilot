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
        story_structure="开篇从废柴开局切入，中段围绕升级夺宝推进，高潮落在跨阶反杀，结尾抛出更高位面冲突。",
        pacing_control="前三章给出金手指或首胜，中段每卷完成一次资源跃迁，卷末兑现身份揭露或境界突破。",
        writing_style="叙事强调强目标推进，环境描写突出压迫感与层级差，对话要带锋芒和势力博弈。",
        special_requirements="境界差必须可感；机缘要有代价；反派压迫要成体系；地图扩张要同步升级。",
    )

    saved_novel = novel_repository.save.call_args.args[0]
    assert saved_novel.generation_prefs.locked_genre == "玄幻 / 东方玄幻"
    assert saved_novel.generation_prefs.locked_world_preset == "高武末世"
    assert saved_novel.generation_prefs.locked_story_structure.startswith("开篇从废柴开局切入")
    assert saved_novel.generation_prefs.locked_pacing_control.startswith("前三章给出金手指或首胜")
    assert saved_novel.generation_prefs.locked_writing_style.startswith("叙事强调强目标推进")
    assert saved_novel.generation_prefs.locked_special_requirements.startswith("境界差必须可感")
    assert dto.locked_genre == "玄幻 / 东方玄幻"
    assert dto.locked_world_preset == "高武末世"
    assert dto.locked_story_structure.startswith("开篇从废柴开局切入")
    assert dto.locked_pacing_control.startswith("前三章给出金手指或首胜")
    assert dto.locked_writing_style.startswith("叙事强调强目标推进")
    assert dto.locked_special_requirements.startswith("境界差必须可感")


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
            locked_story_structure="从凡人入门写到宗门晋阶，再推向天道之争。",
            locked_pacing_control="修炼、历练、争夺循环，每卷必须有一次位阶兑现。",
            locked_writing_style="叙事克制但持续给压迫感，对话体现修行立场。",
            locked_special_requirements="资源、寿命、因果都要闭环。",
        ),
    )

    dto = NovelDTO.from_domain(novel)

    assert dto.locked_genre == "仙侠 / 凡人流"
    assert dto.locked_world_preset == "宗门修真"
    assert dto.locked_story_structure == "从凡人入门写到宗门晋阶，再推向天道之争。"
    assert dto.locked_pacing_control == "修炼、历练、争夺循环，每卷必须有一次位阶兑现。"
    assert dto.locked_writing_style == "叙事克制但持续给压迫感，对话体现修行立场。"
    assert dto.locked_special_requirements == "资源、寿命、因果都要闭环。"
