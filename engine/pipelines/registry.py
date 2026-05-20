"""PipelineRegistry — 题材 → BaseStoryPipeline 子类映射

Phase 3：新管线体系与 ThemeAgent 的正式接入点。
未注册题材降级为 ThemedStoryPipeline（自动注入 ThemeAgent）。
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Type

from engine.pipeline.base import BaseStoryPipeline
from engine.pipelines.themed_pipeline import ThemedStoryPipeline
from engine.pipelines.wuxia_pipeline import WuxiaPipeline

logger = logging.getLogger(__name__)

_PIPELINE_CLASSES: Dict[str, Type[BaseStoryPipeline]] = {
    "wuxia": WuxiaPipeline,
}


class PipelineRegistry:
    """题材 Pipeline 注册中心"""

    def __init__(self):
        self._pipelines: Dict[str, Type[BaseStoryPipeline]] = dict(_PIPELINE_CLASSES)

    def register(self, genre_key: str, pipeline_cls: Type[BaseStoryPipeline]) -> None:
        if genre_key in self._pipelines:
            logger.warning(
                "Pipeline 重复注册：%s (%s → %s)",
                genre_key,
                self._pipelines[genre_key].__name__,
                pipeline_cls.__name__,
            )
        self._pipelines[genre_key] = pipeline_cls
        logger.info("注册 Pipeline: %s → %s", genre_key, pipeline_cls.__name__)

    def get_pipeline_class(self, genre_key: str) -> Type[BaseStoryPipeline]:
        """获取题材 Pipeline 类；未知题材返回 ThemedStoryPipeline"""
        key = (genre_key or "").strip().lower()
        if key in self._pipelines:
            return self._pipelines[key]
        return ThemedStoryPipeline

    def create_pipeline(self, genre_key: str) -> BaseStoryPipeline:
        """实例化题材 Pipeline"""
        cls = self.get_pipeline_class(genre_key)
        if cls is ThemedStoryPipeline:
            return ThemedStoryPipeline(genre_key=(genre_key or "").strip().lower())
        return cls()

    def list_pipelines(self) -> List[Dict[str, str]]:
        return [
            {"genre_key": key, "pipeline_class": cls.__name__}
            for key, cls in sorted(self._pipelines.items())
        ]

    @property
    def registered_keys(self) -> List[str]:
        return list(self._pipelines.keys())


_default_registry: Optional[PipelineRegistry] = None


def get_pipeline_registry() -> PipelineRegistry:
    global _default_registry
    if _default_registry is None:
        _default_registry = PipelineRegistry()
    return _default_registry
