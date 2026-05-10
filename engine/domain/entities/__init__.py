"""领域实体 — Story聚合根、Character、Chapter、Foreshadow"""
from engine.domain.entities.story import Story, StoryId, StoryPhase
from engine.domain.entities.character import Character, CharacterId, VoiceStyle, Wound, CharacterPatch
from engine.domain.entities.chapter import Chapter, Paragraph, ChapterQualityScore
from engine.domain.entities.foreshadow import (
    Foreshadow, ForeshadowId, ForeshadowStatus, ForeshadowBinding,
)

__all__ = [
    "Story", "StoryId", "StoryPhase",
    "Character", "CharacterId", "VoiceStyle", "Wound", "CharacterPatch",
    "Chapter", "Paragraph", "ChapterQualityScore",
    "Foreshadow", "ForeshadowId", "ForeshadowStatus", "ForeshadowBinding",
]
