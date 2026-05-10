"""兼容层 — engine.domain.entities

⚠️ 已废弃，请使用: from engine.core.entities import ...
"""
from engine.core.entities import (
    Character, CharacterId, VoiceStyle, Wound, CharacterPatch,
    Story, StoryId, StoryPhase,
    Foreshadow, ForeshadowId, ForeshadowStatus, ForeshadowBinding,
    Chapter, ChapterStatus, Paragraph, ChapterQualityScore,
)

__all__ = [
    "Character", "CharacterId", "VoiceStyle", "Wound", "CharacterPatch",
    "Story", "StoryId", "StoryPhase",
    "Foreshadow", "ForeshadowId", "ForeshadowStatus", "ForeshadowBinding",
    "Chapter", "ChapterStatus", "Paragraph", "ChapterQualityScore",
]
