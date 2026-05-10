"""兼容层 — engine.domain.entities.character

⚠️ 已废弃，请使用: from engine.core.entities.character import ...
"""
from engine.core.entities.character import (
    Character, CharacterId, VoiceStyle, Wound, CharacterPatch,
)

__all__ = ["Character", "CharacterId", "VoiceStyle", "Wound", "CharacterPatch"]
