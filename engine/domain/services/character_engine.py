"""CharacterEngine抽象接口 — 角色引擎

核心职责：
- apply_trauma：应用创伤事件（追加地质叠层）
- compute_current_mask：计算当前面具（折叠所有Patch）
- recall_echo：倒影召回（向量查询早期发言）
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from engine.domain.entities.character import CharacterId, CharacterPatch
from engine.domain.value_objects.character_mask import CharacterMask


class TraumaticEvent:
    """创伤事件"""
    def __init__(
        self,
        character_id: CharacterId,
        trigger_chapter: int,
        trigger_event: str,
        new_belief: Optional[str] = None,
        new_taboo: Optional[str] = None,
        new_wound: Optional[dict] = None,
        voice_change: Optional[dict] = None,
    ):
        self.character_id = character_id
        self.trigger_chapter = trigger_chapter
        self.trigger_event = trigger_event
        self.new_belief = new_belief
        self.new_taboo = new_taboo
        self.new_wound = new_wound
        self.voice_change = voice_change


class SceneContext:
    """场景上下文（用于倒影召回）"""
    def __init__(
        self,
        scene_type: str = "default",
        emotional_tone: str = "",
        characters_present: list = None,
        key_events: list = None,
    ):
        self.scene_type = scene_type
        self.emotional_tone = emotional_tone
        self.characters_present = characters_present or []
        self.key_events = key_events or []


class CharacterEngine(ABC):
    """角色引擎抽象接口

    核心职责：
    - 管理角色四维动态模型
    - 处理创伤事件（地质叠层）
    - 计算当前面具（T0层注入）
    - 倒影召回（早期发言向量检索）
    """

    @abstractmethod
    async def apply_trauma(self, event: TraumaticEvent) -> CharacterPatch:
        """应用创伤事件（追加地质叠层）

        Args:
            event: 创伤事件

        Returns:
            生成的Patch对象
        """
        ...

    @abstractmethod
    async def compute_current_mask(
        self,
        character_id: CharacterId,
        chapter_number: int,
    ) -> CharacterMask:
        """计算当前面具（折叠所有Patch）

        步骤：
        1. 扫描所有Patch（指定章节之前）
        2. 折叠计算当前面具
        3. 注入T0层作为Fact Lock

        Args:
            character_id: 角色ID
            chapter_number: 当前章节号

        Returns:
            角色当前面具快照
        """
        ...

    @abstractmethod
    async def recall_echo(
        self,
        character_id: CharacterId,
        context: SceneContext,
    ) -> Optional[str]:
        """倒影召回（向量检索早期发言）

        场景：第50章，林羽遇到天真少年
        1. T3向量查询：召回林羽第1章的发言片段
        2. T0追加指令："让林羽内心闪过自己当年的影子"

        Args:
            character_id: 角色ID
            context: 场景上下文

        Returns:
            召回的早期发言片段（None表示无匹配）
        """
        ...
