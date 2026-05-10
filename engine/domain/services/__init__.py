"""兼容层 — engine.domain.services

⚠️ 已废弃，请使用: from engine.core.services import ...
"""
from engine.core.services.story_engine import StoryEngine
from engine.core.services.character_engine import CharacterEngine, TraumaticEvent, SceneContext
from engine.core.services.memory_orchestrator import (
    MemoryOrchestrator, TokenBudget, ContextAssembly, ForeshadowAction,
)

__all__ = [
    "StoryEngine",
    "CharacterEngine", "TraumaticEvent", "SceneContext",
    "MemoryOrchestrator", "TokenBudget", "ContextAssembly", "ForeshadowAction",
]
