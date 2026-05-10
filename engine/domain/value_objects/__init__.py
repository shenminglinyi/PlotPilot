"""兼容层 — engine.domain.value_objects

⚠️ 已废弃，请使用: from engine.core.value_objects import ...
"""
from engine.core.value_objects.checkpoint import Checkpoint, CheckpointId, CheckpointType
from engine.core.value_objects.emotion_ledger import (
    EmotionLedger, EmotionalWound, EmotionalBoon, PowerShift, OpenLoop,
)
from engine.core.value_objects.character_mask import CharacterMask

__all__ = [
    "Checkpoint", "CheckpointId", "CheckpointType",
    "EmotionLedger", "EmotionalWound", "EmotionalBoon", "PowerShift", "OpenLoop",
    "CharacterMask",
]
