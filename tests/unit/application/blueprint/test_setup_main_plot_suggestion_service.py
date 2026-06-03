from types import SimpleNamespace

from application.blueprint.services.setup_main_plot_suggestion_service import SetupMainPlotSuggestionService


class _FakeNovelService:
    def __init__(self, novel):
        self._novel = novel

    def get_novel(self, novel_id):
        return self._novel


class _FakeBibleService:
    def get_bible_by_novel(self, novel_id):
        return SimpleNamespace(
            characters=[
                SimpleNamespace(name="旧主角", role="主角", description="业务表主角"),
            ],
            locations=[
                SimpleNamespace(name="旧地点", location_type="城市", description="业务表地点"),
            ],
            world_settings=[
                SimpleNamespace(name="旧世界观", description="业务表世界观"),
            ],
            style_notes=[
                SimpleNamespace(category="文风公约", content="业务表风格"),
            ],
        )


def test_build_context_prefers_variable_hub_over_business_tables(monkeypatch):
    service = SetupMainPlotSuggestionService(
        llm_service=None,
        bible_service=_FakeBibleService(),
        novel_service=_FakeNovelService(
            SimpleNamespace(
                title="业务标题",
                premise="业务设定",
                target_chapters=120,
                genre_label="玄幻 / 赛博",
                world_preset="业务基调",
                secondary_theme_keys=[],
            )
        ),
    )

    monkeypatch.setattr(
        service,
        "_load_variable_context",
        lambda novel_id: {
            "novel_title": "变量标题",
            "premise": "变量设定",
            "target_chapters": 66,
            "target_words_per_chapter": 3500,
            "theme_metadata": {"genre_label": "修仙 / 悬疑", "world_preset": "变量基调"},
            "fusion_contract": "变量合同",
            "protagonist": {"name": "阿澄"},
            "other_characters": [{"name": "林墨"}],
            "locations": [{"name": "天枢城"}],
            "worldview_summary": ["变量世界观"],
            "style_hint": "变量风格",
            "core_rules": {"power_system": "体系A"},
            "geography": {"terrain": "地形A"},
            "society": {"politics": "政体A"},
            "culture": {"history": "历史A"},
            "daily_life": {"food_clothing": "衣食住行A"},
        },
    )

    ctx = service.build_context("novel-1")

    assert ctx["novel_title"] == "变量标题"
    assert ctx["premise"] == "变量设定"
    assert ctx["target_chapters"] == 66
    assert ctx["theme_metadata"]["genre_label"] == "修仙 / 悬疑"
    assert ctx["fusion_contract"] == "变量合同"
    assert ctx["protagonist"]["name"] == "阿澄"
    assert ctx["locations"][0]["name"] == "天枢城"
    assert "worldbuilding_full" not in ctx
    assert ctx["style_hint"] == "变量风格"
    assert ctx["core_rules"]["power_system"] == "体系A"
