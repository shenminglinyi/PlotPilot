"""兼容层 — engine.domain.entities.story

⚠️ 已废弃，请使用: from engine.core.entities.story import ...
"""
from engine.core.entities.story import (
    Story, StoryId, StoryPhase,
)

__all__ = ["Story", "StoryId", "StoryPhase"]
