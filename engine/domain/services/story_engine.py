"""StoryEngine抽象接口 — 剧情引擎内核

核心职责：
- create_story：创建故事
- advance_plot：推进剧情（生成新Checkpoint）
- rollback：回滚到历史Checkpoint
- build_context：构建写作上下文

质量守门人集成：
- advance_plot中必须通过QualityGuardrail检查
- 不达标则返回修正建议，要求重写
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from engine.core.entities.story import Story, StoryId, StoryPhase
from engine.core.value_objects.checkpoint import CheckpointId


class StoryEngine(ABC):
    """剧情引擎抽象接口

    设计原则：
    - 依赖倒置：上层依赖抽象接口，不依赖具体实现
    - 质量守门：advance_plot必须通过质量检查
    - Checkpoint驱动：每次推进都生成新Checkpoint
    """

    @abstractmethod
    async def create_story(self, title: str, premise: str, target_chapters: int = 0) -> Story:
        """创建故事"""
        ...

    @abstractmethod
    async def advance_plot(self, story_id: StoryId, event: dict) -> CheckpointId:
        """推进剧情（生成新Checkpoint）

        流程：
        1. 生成章节内容
        2. 质量守门人检查
        3. 通过 → 创建Checkpoint
        4. 不通过 → 返回修正建议，要求重写

        Args:
            story_id: 故事ID
            event: 剧情事件

        Returns:
            新创建的Checkpoint ID
        """
        ...

    @abstractmethod
    async def rollback(self, story_id: StoryId, checkpoint_id: CheckpointId) -> None:
        """回滚到历史Checkpoint（拨回HEAD指针）

        Args:
            story_id: 故事ID
            checkpoint_id: 目标Checkpoint ID
        """
        ...

    @abstractmethod
    async def build_context(self, story_id: StoryId, chapter_number: int) -> str:
        """构建写作上下文（洋葱模型）

        Args:
            story_id: 故事ID
            chapter_number: 章节号

        Returns:
            组装好的上下文字符串
        """
        ...

    @abstractmethod
    async def get_current_checkpoint(self, story_id: StoryId) -> Optional[CheckpointId]:
        """获取当前HEAD指针"""
        ...
