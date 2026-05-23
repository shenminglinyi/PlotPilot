import sqlite3
from types import SimpleNamespace

from application.engine.services.context_slot_providers import (
    build_immersion_details_slot_content,
    build_key_props_slot_content,
    build_narrative_promise_slot_content,
    build_storyline_slot_content,
    build_worldbuilding_core_slot_content,
)
from domain.novel.value_objects.novel_id import NovelId
from domain.novel.value_objects.storyline_role import StorylineRole


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


class FakeStorylineRepository:
    def __init__(self, storylines):
        self.storylines = storylines
        self.requested_id = None

    def get_by_novel_id(self, novel_id):
        self.requested_id = novel_id
        return self.storylines


class FakeConfluenceRepository:
    def __init__(self, confluences):
        self.confluences = confluences
        self.requested_id = None

    def get_by_novel_id(self, novel_id):
        self.requested_id = novel_id
        return self.confluences


def _storyline(role, weight=1.0):
    return SimpleNamespace(
        id=f"sl-{role.value}",
        name="",
        role=role,
        estimated_chapter_start=1,
        estimated_chapter_end=30,
        chapter_weight=weight,
        progress_summary="推进中",
        get_current_milestone=lambda: None,
    )


def test_storyline_provider_filters_and_orders_active_lines():
    main = _storyline(StorylineRole.MAIN)
    sub = _storyline(StorylineRole.SUB)
    low_weight = _storyline(StorylineRole.DARK, weight=0.01)
    storyline_repo = FakeStorylineRepository([sub, low_weight, main])
    confluence_repo = FakeConfluenceRepository([])

    block = build_storyline_slot_content(storyline_repo, confluence_repo, "novel-1", 8)

    assert storyline_repo.requested_id == NovelId("novel-1")
    assert confluence_repo.requested_id == "novel-1"
    assert "故事线上下文" in block
    assert block.index("[主线]") < block.index("[支线]")
    assert "暗线" not in block


def test_storyline_provider_keeps_dark_line_hidden_before_reveal():
    dark = _storyline(StorylineRole.DARK)
    confluence = SimpleNamespace(
        source_storyline_id=dark.id,
        resolved=False,
        target_chapter=20,
        merge_type="reveal",
        context_summary="幕后身份曝光",
        pre_reveal_hint="只留下违和感",
        behavior_guards=["不要点名幕后身份"],
    )

    block = build_storyline_slot_content(
        FakeStorylineRepository([dark]),
        FakeConfluenceRepository([confluence]),
        "novel-1",
        8,
    )

    assert "只留下违和感" in block
    assert "不要点名幕后身份" in block
    assert "幕后身份曝光" not in block


class FakeWorldbuildingRepository:
    def __init__(self, worldbuilding):
        self.worldbuilding = worldbuilding

    def get_by_novel_id(self, novel_id):
        return self.worldbuilding


def test_worldbuilding_providers_render_core_and_immersion_slots():
    worldbuilding = SimpleNamespace(
        power_system="灵根决定修行上限",
        physics_rules="飞行需要灵压支撑",
        magic_tech="符术可以存储一次性术式",
        food_clothing="矿工穿耐火麻衣",
        language_slang="称执法堂为铁门",
        entertainment="斗符夜市",
    )
    repo = FakeWorldbuildingRepository(worldbuilding)

    core = build_worldbuilding_core_slot_content(repo, "novel-1")
    immersion = build_immersion_details_slot_content(repo, "novel-1")

    assert "世界规则" in core
    assert "灵根决定修行上限" in core
    assert "世界沉浸感细节" in immersion
    assert "斗符夜市" in immersion


def test_key_props_provider_reads_sqlite_rows(tmp_path):
    db_path = tmp_path / "plotpilot.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE bible_props (novel_id TEXT, name TEXT, description TEXT, is_key INTEGER)"
    )
    conn.execute(
        "INSERT INTO bible_props VALUES (?, ?, ?, ?)",
        ("novel-1", "断剑", "剑身有旧血纹", 1),
    )
    conn.execute(
        "INSERT INTO bible_props VALUES (?, ?, ?, ?)",
        ("novel-1", "普通杯子", "无关", 0),
    )
    conn.commit()
    conn.close()

    block = build_key_props_slot_content("novel-1", db_path_provider=lambda: db_path)

    assert "本章关键道具" in block
    assert "断剑" in block
    assert "剑身有旧血纹" in block
    assert "普通杯子" not in block
