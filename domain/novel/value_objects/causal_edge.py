"""因果边值对象 - 超越静态关系三元组，追踪事件的因果链

核心设计理念：
  传统知识图谱：(主角)-[属于]->(宗门)  —— 静态关系，不懂"因果"
  因果图谱：     (宗门被灭)-[导致]->(仇恨值MAX)-[目标]->(复仇)  —— 因果链

因果边是长篇小说连贯性的核心基础设施：
  - AI 写第 80 章时，能查到"上次主角与该反派见面是在第 10 章，主角战败并立下三年之约"
  - 情感不会断档：因果边记录了 state_change（状态变化），AI 知道角色从什么状态变成了什么状态
  - 因果闭环检测：未闭环的因果边会转化为叙事债务，前置注入 MUST_RESOLVE 块
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List
from uuid import uuid4


class CausalType(str, Enum):
    """因果类型"""
    CAUSES = "causes"           # 导致：A 导致 B 发生
    MOTIVATES = "motivates"     # 驱动：A 成为 B 的动机
    TRIGGERS = "triggers"       # 触发：A 触发 B 的状态变化
    PREVENTS = "prevents"       # 阻止：A 阻止 B 发生
    RESOLVES = "resolves"       # 解决：A 解决了 B


@dataclass(frozen=True)
class CausalEdge:
    """因果边值对象

    表示两个叙事事件/状态之间的因果关系。

    与 KnowledgeTriple 的区别：
    - KnowledgeTriple: 静态关系 (主角)-[属于]->(宗门)
    - CausalEdge: 动态因果 (宗门被灭)-[导致]->(主角仇恨值MAX)

    Attributes:
        id: 唯一标识
        novel_id: 小说 ID
        source_event_summary: 源事件摘要，例："宗门被灭"
        source_chapter: 源事件发生的章节
        causal_type: 因果类型
        target_event_summary: 目标事件/状态摘要，例："主角仇恨值MAX"
        target_chapter: 目标事件章节（可能尚未发生，None 表示"未来"）
        strength: 因果强度 0-1，越高越强
        confidence: LLM 置信度 0-1
        state_change: 状态变化描述，告诉 AI 角色的内在状态如何变化
        involved_characters: 关联角色 ID 列表
        is_resolved: 因果链是否已闭环
        resolved_chapter: 闭环章节（None 表示未闭环）
    """
    id: str = field(default_factory=lambda: str(uuid4()))
    novel_id: str = ""
    source_event_summary: str = ""
    source_chapter: int = 0
    causal_type: CausalType = CausalType.CAUSES
    target_event_summary: str = ""
    target_chapter: Optional[int] = None
    strength: float = 0.8
    confidence: float = 0.7
    state_change: str = ""
    involved_characters: List[str] = field(default_factory=list)
    is_resolved: bool = False
    resolved_chapter: Optional[int] = None

    def __post_init__(self):
        if self.source_chapter < 0:
            raise ValueError("source_chapter must be >= 0")
        if not 0 <= self.strength <= 1:
            raise ValueError("strength must be between 0 and 1")
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        if self.is_resolved and self.resolved_chapter is None:
            raise ValueError("resolved edge must have resolved_chapter")

    def to_dict(self) -> dict:
        """序列化为字典"""
        return {
            "id": self.id,
            "novel_id": self.novel_id,
            "source_event_summary": self.source_event_summary,
            "source_chapter": self.source_chapter,
            "causal_type": self.causal_type.value,
            "target_event_summary": self.target_event_summary,
            "target_chapter": self.target_chapter,
            "strength": self.strength,
            "confidence": self.confidence,
            "state_change": self.state_change,
            "involved_characters": self.involved_characters,
            "is_resolved": self.is_resolved,
            "resolved_chapter": self.resolved_chapter,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CausalEdge":
        """从字典反序列化"""
        causal_type = data.get("causal_type", "causes")
        if isinstance(causal_type, str):
            causal_type = CausalType(causal_type)

        return cls(
            id=data.get("id", str(uuid4())),
            novel_id=data.get("novel_id", ""),
            source_event_summary=data.get("source_event_summary", ""),
            source_chapter=data.get("source_chapter", 0),
            causal_type=causal_type,
            target_event_summary=data.get("target_event_summary", ""),
            target_chapter=data.get("target_chapter"),
            strength=data.get("strength", 0.8),
            confidence=data.get("confidence", 0.7),
            state_change=data.get("state_change", ""),
            involved_characters=data.get("involved_characters", []),
            is_resolved=bool(data.get("is_resolved", False)),
            resolved_chapter=data.get("resolved_chapter"),
        )

    def resolve(self, chapter: int) -> "CausalEdge":
        """标记因果边已闭环"""
        return CausalEdge(
            id=self.id,
            novel_id=self.novel_id,
            source_event_summary=self.source_event_summary,
            source_chapter=self.source_chapter,
            causal_type=self.causal_type,
            target_event_summary=self.target_event_summary,
            target_chapter=self.target_chapter,
            strength=self.strength,
            confidence=self.confidence,
            state_change=self.state_change,
            involved_characters=self.involved_characters,
            is_resolved=True,
            resolved_chapter=chapter,
        )

    @property
    def is_high_strength(self) -> bool:
        """是否为高强度因果边"""
        return self.strength >= 0.7

    @property
    def display_label(self) -> str:
        """用于上下文注入的显示标签"""
        type_labels = {
            CausalType.CAUSES: "→导致→",
            CausalType.MOTIVATES: "→驱动→",
            CausalType.TRIGGERS: "→触发→",
            CausalType.PREVENTS: "→阻止→",
            CausalType.RESOLVES: "→解决→",
        }
        return type_labels.get(self.causal_type, "→")
