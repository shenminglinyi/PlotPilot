"""写作手法知识库提示词 overlay 测试。"""

from application.style_bible.services.style_prompt_overlay_service import (
    StylePromptOverlayService,
)
from domain.style_bible.entities import StyleProfile, StyleTechniqueCard
from infrastructure.persistence.database.connection import DatabaseConnection
from infrastructure.persistence.database.sqlite_style_bible_repository import (
    SqliteStyleBibleRepository,
)


def _repo(tmp_path):
    db = DatabaseConnection(str(tmp_path / "style-overlay.db"))
    return SqliteStyleBibleRepository(db)


def test_style_prompt_overlay_returns_empty_without_selected_profile(tmp_path):
    service = StylePromptOverlayService(_repo(tmp_path))

    overlay = service.build_overlay("novel-1", "")

    assert overlay.prompt == ""
    assert overlay.card_ids == []


def test_style_prompt_overlay_builds_compact_block(tmp_path):
    repo = _repo(tmp_path)
    profile = repo.save_profile(
        StyleProfile(
            name="克制悬疑",
            novel_id="novel-1",
            metrics={"avg_sentence_length": 13.4, "avg_paragraph_length": 88.0},
            forbidden_patterns=["五味杂陈"],
        )
    )
    repo.save_technique_cards(
        profile.id,
        [
            StyleTechniqueCard(
                profile_id=profile.id,
                title="节奏推进",
                category="pacing",
                rule_text="每段推进信息。",
                prompt_instruction="每 600-900 字出现一次信息变化。",
            )
        ],
    )

    overlay = StylePromptOverlayService(repo).build_overlay("novel-1", profile.id)

    assert "【写作手法库】" in overlay.prompt
    assert "克制悬疑" in overlay.prompt
    assert "每 600-900 字出现一次信息变化" in overlay.prompt
    assert "五味杂陈" in overlay.prompt
    assert "不复刻样本文字" in overlay.prompt


def test_style_prompt_overlay_excludes_disabled_cards(tmp_path):
    repo = _repo(tmp_path)
    profile = repo.save_profile(StyleProfile(name="档案", novel_id="novel-1"))
    repo.save_technique_cards(
        profile.id,
        [
            StyleTechniqueCard(
                profile_id=profile.id,
                title="启用卡",
                category="pacing",
                rule_text="启用",
                prompt_instruction="保留启用指令。",
            ),
            StyleTechniqueCard(
                profile_id=profile.id,
                title="禁用卡",
                category="dialogue",
                rule_text="禁用",
                prompt_instruction="不该出现的指令。",
                enabled=False,
            ),
        ],
    )

    overlay = StylePromptOverlayService(repo).build_overlay("novel-1", profile.id)

    assert "保留启用指令" in overlay.prompt
    assert "不该出现的指令" not in overlay.prompt


def test_style_prompt_overlay_ranks_scene_type_cards_first(tmp_path):
    repo = _repo(tmp_path)
    profile = repo.save_profile(StyleProfile(name="档案", novel_id="novel-1"))
    cards = repo.save_technique_cards(
        profile.id,
        [
            StyleTechniqueCard(
                profile_id=profile.id,
                title="高权重情感",
                category="emotion",
                scene_type="情感",
                rule_text="情感",
                prompt_instruction="先写情绪余波。",
                weight=1.0,
            ),
            StyleTechniqueCard(
                profile_id=profile.id,
                title="低权重悬疑",
                category="hook",
                scene_type="悬疑",
                rule_text="悬疑",
                prompt_instruction="先给异常细节。",
                weight=0.2,
            ),
        ],
    )

    overlay = StylePromptOverlayService(repo).build_overlay(
        "novel-1",
        profile.id,
        scene_type="悬疑",
    )

    assert overlay.card_ids[0] == cards[1].id
    assert overlay.prompt.index("先给异常细节") < overlay.prompt.index("先写情绪余波")
