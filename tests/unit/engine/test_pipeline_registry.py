"""PipelineRegistry 与题材管线测试"""
from engine.pipeline.base import BaseStoryPipeline
from engine.pipelines.registry import get_pipeline_registry, PipelineRegistry
from engine.pipelines.themed_pipeline import ThemedStoryPipeline
from engine.pipelines.wuxia_pipeline import WuxiaPipeline
from engine.examples import WuxiaPipeline as ExampleWuxiaPipeline
from application.engine.theme.theme_registry import ThemeAgentRegistry, normalize_genre_key


def test_wuxia_pipeline_registered():
    registry = get_pipeline_registry()
    assert registry.get_pipeline_class("wuxia") is WuxiaPipeline


def test_unknown_genre_falls_back_to_themed_pipeline():
    registry = get_pipeline_registry()
    pipeline = registry.create_pipeline("xuanhuan")
    assert isinstance(pipeline, ThemedStoryPipeline)
    assert pipeline.genre_key == "xuanhuan"


def test_wuxia_pipeline_is_example_reexport():
    assert ExampleWuxiaPipeline is WuxiaPipeline


def test_theme_registry_create_pipeline():
    theme_registry = ThemeAgentRegistry()
    pipeline = theme_registry.create_pipeline("wuxia")
    assert isinstance(pipeline, WuxiaPipeline)


def test_custom_pipeline_registration():
    registry = PipelineRegistry()

    class CustomPipeline(BaseStoryPipeline):
        pass

    registry.register("custom", CustomPipeline)
    assert registry.get_pipeline_class("custom") is CustomPipeline


def test_theme_registry_normalizes_cn_market_genre_labels():
    assert normalize_genre_key("玄幻 / 高武世界") == "xuanhuan"
    assert normalize_genre_key("武侠 / 高武武侠") == "wuxia"
    assert normalize_genre_key("科幻 / 赛博朋克") == "scifi"
