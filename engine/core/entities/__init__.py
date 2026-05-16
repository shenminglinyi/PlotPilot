"""引擎内核 — 实体层

统一入口：所有实体从此处导入
旧入口 engine.domain.entities.* 改为兼容层(re-export)
"""
from engine.core.entities.character import (
    Character, CharacterId, VoiceStyle, Wound, CharacterPatch,
)
from engine.core.entities.story import (
    Story, StoryId, StoryPhase,
)
from engine.core.entities.foreshadow import (
    Foreshadow, ForeshadowId, ForeshadowStatus, ForeshadowBinding,
)
from engine.core.entities.chapter import (
    Chapter, ChapterStatus, Paragraph, ChapterQualityScore,
)

__all__ = [
    "Character", "CharacterId", "VoiceStyle", "Wound", "CharacterPatch",
    "Story", "StoryId", "StoryPhase",
    "Foreshadow", "ForeshadowId", "ForeshadowStatus", "ForeshadowBinding",
    "Chapter", "ChapterStatus", "Paragraph", "ChapterQualityScore",
]
