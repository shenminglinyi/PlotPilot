"""触发词与 Bible 世界设定切片联动集成测试

验证 ContextBuilder._build_layer2_smart_retrieval 在 scene_director 含
trigger_keywords 时，能将 Bible world_settings 中匹配的条目注入 Layer2。
"""
import pytest
from unittest.mock import MagicMock, patch


def _make_scene_director(trigger_keywords):
    sd = MagicMock()
    sd.trigger_keywords = trigger_keywords
    sd.characters = None
    sd.locations = None
    return sd


def _make_world_setting(name, setting_type, description):
    ws = MagicMock()
    ws.name = name
    ws.setting_type = setting_type
    ws.description = description
    return ws


def _make_bible_dto(world_settings):
    dto = MagicMock()
    dto.characters = []
    dto.locations = []
    dto.style_notes = []
    dto.timeline_notes = []
    dto.world_settings = world_settings
    return dto


def _make_context_builder():
    """创建最小化 ContextBuilder（跳过真实依赖）"""
    from application.engine.services.context_builder import ContextBuilder
    cb = ContextBuilder.__new__(ContextBuilder)
    cb.bible_service = MagicMock()
    cb.storyline_manager = MagicMock()
    cb.relationship_engine = MagicMock()
    cb.vector_store = None
    cb.novel_repository = MagicMock()
    cb.chapter_repository = MagicMock()
    cb.plot_arc_repository = None
    cb.embedding_service = None
    cb.foreshadowing_repository = None
    cb.vector_facade = None
    return cb


def test_trigger_keywords_inject_matching_world_settings():
    """战斗触发词 -> 武器 -> 匹配名为「刃尘剑法」setting -> 注入 Layer2"""
    cb = _make_context_builder()

    sword_setting = _make_world_setting(
        name="刃尘剑法",
        setting_type="战斗技能",
        description="以气息凝刃，每式蕴含一种元素属性"
    )
    other_setting = _make_world_setting(
        name="皇都布局",
        setting_type="地点",
        description="帝国首都的建筑格局"
    )
    bible_dto = _make_bible_dto([sword_setting, other_setting])
    cb.bible_service.get_bible_by_novel.return_value = bible_dto

    scene_director = _make_scene_director(["战斗"])
    layer2 = cb._build_layer2_smart_retrieval(
        novel_id="novel-1",
        chapter_number=5,
        outline="主角与宿敌展开战斗",
        budget=50000,
        scene_director=scene_director,
    )

    assert "刃尘剑法" in layer2
    assert "Triggered World Settings" in layer2
    # 不相关的设定不应出现
    assert "皇都布局" not in layer2


def test_no_trigger_keywords_skips_linkage():
    """无 trigger_keywords 时不触发切片联动"""
    cb = _make_context_builder()
    sword_setting = _make_world_setting("刃尘剑法", "战斗技能", "气息凝刃")
    bible_dto = _make_bible_dto([sword_setting])
    cb.bible_service.get_bible_by_novel.return_value = bible_dto

    scene_director = _make_scene_director([])  # 空列表
    layer2 = cb._build_layer2_smart_retrieval(
        novel_id="novel-1",
        chapter_number=5,
        outline="主角与宿敌展开战斗",
        budget=50000,
        scene_director=scene_director,
    )

    assert "Triggered World Settings" not in layer2


def test_unknown_trigger_falls_back_and_matches_by_self():
    """未知触发词兜底为原词，能匹配 setting 中包含该词的条目"""
    cb = _make_context_builder()
    special_setting = _make_world_setting(
        name="神秘契约",
        setting_type="神秘契约",
        description="一种特殊的血脉盟约"
    )
    bible_dto = _make_bible_dto([special_setting])
    cb.bible_service.get_bible_by_novel.return_value = bible_dto

    scene_director = _make_scene_director(["神秘契约"])
    layer2 = cb._build_layer2_smart_retrieval(
        novel_id="novel-1",
        chapter_number=5,
        outline="签订神秘契约",
        budget=50000,
        scene_director=scene_director,
    )

    assert "神秘契约" in layer2
