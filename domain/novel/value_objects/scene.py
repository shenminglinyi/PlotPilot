"""场景值对象

场景是章节的基本组成单元，用于节拍表（Beat Sheet）
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Scene:
    """场景值对象

    表示章节内的单个场景，包含场景的基本信息和生成参数
    """
    title: str  # 场景标题
    goal: str  # 场景目标（这个场景要达成什么）
    pov_character: str  # POV 角色名称
    location: Optional[str]  # 地点（可选）
    tone: Optional[str]  # 情绪基调（例如：紧张、温馨、悲伤）
    estimated_words: int  # 预估字数
    order_index: int  # 场景顺序（从 0 开始）
    transition_from_prev: Optional[str] = None  # 🔗 从上一节拍如何过渡（对话延续/动作接续/情绪过渡/场景切换）

    def __post_init__(self):
        """验证场景数据"""
        if not self.title:
            raise ValueError("Scene title cannot be empty")
        if not self.goal:
            raise ValueError("Scene goal cannot be empty")
        if not self.pov_character:
            raise ValueError("Scene POV character cannot be empty")
        if self.estimated_words <= 0:
            raise ValueError("Estimated words must be positive")
        if self.order_index < 0:
            raise ValueError("Order index must be non-negative")
