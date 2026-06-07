"""Engine Pipelines — 题材专属 BaseStoryPipeline 子类"""
from engine.pipelines.themed_pipeline import ThemedStoryPipeline
from engine.pipelines.wuxia_pipeline import WuxiaPipeline
from engine.pipelines.registry import PipelineRegistry, get_pipeline_registry

__all__ = [
    "ThemedStoryPipeline",
    "WuxiaPipeline",
    "PipelineRegistry",
    "get_pipeline_registry",
]
