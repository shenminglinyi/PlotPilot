"""兼容层：character_soul → character_psyche

旧代码 `from engine.infrastructure.memory.character_soul import CharacterSoulEngine` 仍然可用。
新代码请使用 `from engine.infrastructure.memory.character_psyche import CharacterPsycheEngine`。

此文件将在 v4.0 移除。
"""
from engine.infrastructure.memory.character_psyche import CharacterPsycheEngine

# ─── 向后兼容别名 ───
CharacterSoulEngine = CharacterPsycheEngine

__all__ = ["CharacterSoulEngine", "CharacterPsycheEngine"]
