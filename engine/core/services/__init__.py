"""引擎内核服务接口 — 依赖倒置的服务抽象层

统一入口：所有服务接口从此处导入
旧入口 engine.domain.services.* 改为兼容层(re-export)
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
