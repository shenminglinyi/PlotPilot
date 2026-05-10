"""兼容层 — domain.novel.value_objects.story_phase

⚠️ StoryPhase 统一定义在 engine.core.entities.story.StoryPhase
此文件保留兼容，从统一模型 re-export。
"""
from engine.core.entities.story import StoryPhase

__all__ = ["StoryPhase"]
