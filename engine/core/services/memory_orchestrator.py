"""MemoryOrchestrator抽象接口 — 记忆编排器

核心职责：
- assemble_context：组装写作上下文（三层记忆模型）
- update_emotion_ledger：更新情绪账本
- manage_foreshadow：管理伏笔生命周期

三层记忆模型（复刻人类作家）：
- T0 语义记忆(20%)：世界观设定、角色关系、伏笔状态
- T1 情景记忆(30%)：EmotionLedger（情绪账本替代摘要）
- T2 工作记忆(35%)：最近10-15章的完整内容
- T3 向量召回(15%)：早期原文片段
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional, Dict, Any

from engine.core.entities.story import StoryId
from engine.core.value_objects.emotion_ledger import EmotionLedger
from engine.core.entities.foreshadow import ForeshadowStatus


@dataclass
class TokenBudget:
    """Token预算"""
    total: int = 35000
    t0_max: int = 7000    # 语义记忆 ~20%
    t1_max: int = 10500   # 情景记忆 ~30%
    t2_max: int = 12250   # 工作记忆 ~35%
    t3_max: int = 5250    # 向量召回 ~15%


@dataclass
class ContextAssembly:
    """上下文组装结果"""
    t0_content: str = ""   # 语义记忆
    t1_content: str = ""   # 情景记忆
    t2_content: str = ""   # 工作记忆
    t3_content: str = ""   # 向量召回
    total_tokens: int = 0
    budget: Optional[TokenBudget] = None

    def get_final_context(self) -> str:
        """合并所有层级的上下文"""
        parts = []
        if self.t0_content:
            parts.append(f"=== 核心设定（T0 语义记忆）===\n{self.t0_content}")
        if self.t1_content:
            parts.append(f"=== 情绪账本（T1 情景记忆）===\n{self.t1_content}")
        if self.t2_content:
            parts.append(f"=== 近期章节（T2 工作记忆）===\n{self.t2_content}")
        if self.t3_content:
            parts.append(f"=== 往事回声（T3 向量召回）===\n{self.t3_content}")
        return "\n\n".join(parts)


class ForeshadowAction:
    """伏笔操作"""
    PLANT = "plant"           # 埋设
    REFERENCE = "reference"   # 引用
    AWAKEN = "awaken"         # 唤醒
    RESOLVE = "resolve"       # 回收
    ABANDON = "abandon"       # 放弃


class MemoryOrchestrator(ABC):
    """记忆编排器抽象接口

    核心职责：
    - 三层记忆模型的组装和挤压
    - EmotionLedger的更新
    - 伏笔生命周期的管理
    - 回声机制（向量召回早期原文）
    """

    @abstractmethod
    async def assemble_context(
        self,
        story_id: StoryId,
        chapter_number: int,
        budget: TokenBudget,
    ) -> ContextAssembly:
        """组装写作上下文（三层记忆模型）

        步骤：
        1. T0语义记忆：世界观、角色面具、伏笔状态
        2. T1情景记忆：EmotionLedger情绪账本
        3. T2工作记忆：最近10-15章完整内容
        4. T3向量召回：早期相关原文片段

        当Token预算紧张时：T3 → T2 → T1 逐层挤压，T0绝对保护

        Args:
            story_id: 故事ID
            chapter_number: 章节号
            budget: Token预算

        Returns:
            上下文组装结果
        """
        ...

    @abstractmethod
    async def update_emotion_ledger(
        self,
        story_id: StoryId,
        chapter_number: int,
        chapter_content: str,
    ) -> EmotionLedger:
        """更新情绪账本

        从章节内容中提取：
        - EmotionalWound：核心损失
        - EmotionalBoon：核心获得
        - PowerShift：势能转化
        - OpenLoop：未解悬念

        Args:
            story_id: 故事ID
            chapter_number: 章节号
            chapter_content: 章节内容

        Returns:
            更新后的情绪账本
        """
        ...

    @abstractmethod
    async def manage_foreshadow(
        self,
        story_id: StoryId,
        foreshadow_id: str,
        action: str,
        chapter_number: int = 0,
    ) -> None:
        """管理伏笔生命周期

        Args:
            story_id: 故事ID
            foreshadow_id: 伏笔ID
            action: 操作类型(plant/reference/awaken/resolve/abandon)
            chapter_number: 当前章节号
        """
        ...

    @abstractmethod
    async def restore_state(
        self,
        story_id: StoryId,
        character_masks: Dict[str, Any],
        emotion_ledger: Dict[str, Any],
        active_foreshadows: List[str],
        outline: str = "",
        recent_summary: str = "",
    ) -> None:
        """从 Checkpoint 恢复引擎状态（用于 checkout/rollback）

        Args:
            story_id: 故事ID
            character_masks: 角色面具字典
            emotion_ledger: 情绪账本字典
            active_foreshadows: 活跃伏笔 ID 列表
            outline: 大纲文本
            recent_summary: 近期摘要文本
        """
        ...
