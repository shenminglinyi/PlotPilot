from types import SimpleNamespace

from application.engine.services.context_brief import (
    build_bridge_hint,
    build_character_state_hint,
    build_context_brief,
    build_debt_hint,
)


class FakeAssembler:
    def __init__(self, scars="", debt=""):
        self.scars = scars
        self.debt = debt

    def build_scars_and_motivations(self, _novel_id):
        return self.scars

    def build_debt_due_block(self, _novel_id, _chapter_number, _outline):
        return self.debt


def test_character_state_hint_filters_headers_and_caps_lines():
    hint = build_character_state_hint(
        FakeAssembler(
            scars="\n".join(
                [
                    "【角色状态】",
                    "═",
                    "林羽仍害怕失控。",
                    "他对师父有愧疚。",
                    "同伴关系进入试探期。",
                    "这一行不应进入简报。",
                ]
            )
        ),
        "novel-1",
    )

    assert hint == "角色状态：林羽仍害怕失控；他对师父有愧疚；同伴关系进入试探期。"


def test_debt_hint_keeps_only_first_two_bullets():
    hint = build_debt_hint(
        FakeAssembler(
            debt="\n".join(
                [
                    "【叙事债务】",
                    "- 玉佩发热尚未解释",
                    "• 黑衣人的身份需要推进",
                    "- 第三条暂缓",
                ]
            )
        ),
        "novel-1",
        12,
        "outline",
    )

    assert hint == "叙事备忘：玉佩发热尚未解释；黑衣人的身份需要推进。如果合适可以推进，不必强求回收。"


def test_context_brief_orders_author_bridge_character_and_debt():
    brief = build_context_brief(
        context_assembler=FakeAssembler(
            scars="林羽仍害怕失控。",
            debt="- 玉佩发热尚未解释",
        ),
        novel_id="novel-1",
        chapter_number=3,
        outline="outline",
        generation_hint_loader=lambda _novel_id, _chapter_number: "本章避免立刻揭底。",
        bridge_hint_builder=lambda _novel_id, _chapter_number: "衔接：上一章门外有人。",
    )

    assert brief.splitlines() == [
        "【编辑手记】",
        "【作者指令】本章避免立刻揭底。",
        "衔接：上一章门外有人。",
        "角色状态：林羽仍害怕失控。",
        "叙事备忘：玉佩发热尚未解释。如果合适可以推进，不必强求回收。",
    ]


def test_context_brief_skips_bridge_for_first_chapter():
    brief = build_context_brief(
        context_assembler=None,
        novel_id="novel-1",
        chapter_number=1,
        outline="outline",
        generation_hint_loader=lambda _novel_id, _chapter_number: "",
        bridge_hint_builder=lambda _novel_id, _chapter_number: "should not appear",
    )

    assert brief == ""


def test_build_bridge_hint_renders_available_fields(monkeypatch):
    bridge = SimpleNamespace(
        suspense_hook="井底传来敲击声",
        emotional_residue="强作镇定",
        scene_state="雨夜祠堂",
        unfinished_actions="还没点灯",
    )

    class FakeBridgeService:
        def __init__(self, db_path):
            self.db_path = db_path

        def get_prev_chapter_bridge(self, _novel_id, _chapter_number):
            return bridge

    monkeypatch.setattr(
        "application.engine.services.chapter_bridge_service.ChapterBridgeService",
        FakeBridgeService,
    )
    monkeypatch.setattr(
        "application.paths.get_db_path",
        lambda: "unused.db",
    )

    hint = build_bridge_hint("novel-1", 4)

    assert "上一章留了悬念：井底传来敲击声" in hint
    assert "主角情绪：强作镇定" in hint
    assert "你可以自然接续" in hint
