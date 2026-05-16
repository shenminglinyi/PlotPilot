"""叙事债务值对象 - V9 减法改革：从"强制收束"到"温和提醒"

核心设计理念（V9 改革前）：
  每一个未闭环的伏笔、每一个未结算的因果边、每一个支线任务，都是系统的"叙事债务"。
  在生成前组装 Prompt 时，从库中查出"即将到期的债务"，放入 [MUST_RESOLVE] 块，
  强迫大模型在本章或本幕中填坑。

V9 改革后：
  填坑的强迫症正在杀死叙事心流。许多伏笔是随着剧情自然流变的，有些坑甚至会永远留白。
  《红楼梦》里还有几十个伏笔永远没有收束——那不叫"欠债"，那叫"文学"。

  改革内容：
  - TTL(due_chapter) 从"到期必须回收"变为"提醒作者关注"
  - is_overdue 从"违约"变为"已提醒"
  - 增加 abandoned 状态：允许作者主动放弃债务（永远留白也是一种文学选择）
  - debt_type 新增 GRACEFUL_ABANDON：允许伏笔自然消解

债务类型：
  - foreshadowing: 伏笔债务（挖了坑没填）
  - causal_chain: 因果债务（因果链未闭环）
  - storyline: 故事线债务（支线未完结）
  - character_arc: 角色弧债务（角色发展未收束）
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List
from uuid import uuid4


class DebtType(str, Enum):
    """叙事债务类型"""
    FORESHADOWING = "foreshadowing"       # 伏笔债务
    CAUSAL_CHAIN = "causal_chain"         # 因果债务
    STORYLINE = "storyline"               # 故事线债务
    CHARACTER_ARC = "character_arc"       # 角色弧债务


@dataclass(frozen=True)
class NarrativeDebt:
    """叙事债务值对象

    核心属性：
    - debt_type: 债务类型
    - description: 债务描述（AI 必须读这个来知道该填什么坑）
    - planted_chapter: 债务产生章节
    - due_chapter: 预期偿还章节（TTL 机制）
    - importance: 重要性 1-4（1=低，4=关键）
    - is_overdue: 是否已逾期
    - involved_entities: 涉及的实体（角色/势力/地点）
    - context: 为什么这笔债重要（给 AI 的提示）

    生命周期：
      created → overdue → resolved/abandoned
    """
    id: str = field(default_factory=lambda: str(uuid4()))
    novel_id: str = ""
    debt_type: DebtType = DebtType.FORESHADOWING
    description: str = ""
    planted_chapter: int = 0
    due_chapter: Optional[int] = None
    importance: int = 2
    is_overdue: bool = False
    resolved_chapter: Optional[int] = None
    involved_entities: List[str] = field(default_factory=list)
    context: str = ""

    def __post_init__(self):
        if self.planted_chapter < 1:
            raise ValueError("planted_chapter must be >= 1")
        if not 1 <= self.importance <= 4:
            raise ValueError("importance must be between 1 and 4")
        if self.resolved_chapter is not None and self.resolved_chapter < self.planted_chapter:
            raise ValueError("resolved_chapter must be >= planted_chapter")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "novel_id": self.novel_id,
            "debt_type": self.debt_type.value,
            "description": self.description,
            "planted_chapter": self.planted_chapter,
            "due_chapter": self.due_chapter,
            "importance": self.importance,
            "is_overdue": self.is_overdue,
            "resolved_chapter": self.resolved_chapter,
            "involved_entities": self.involved_entities,
            "context": self.context,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "NarrativeDebt":
        debt_type = data.get("debt_type", "foreshadowing")
        if isinstance(debt_type, str):
            debt_type = DebtType(debt_type)

        return cls(
            id=data.get("id", str(uuid4())),
            novel_id=data.get("novel_id", ""),
            debt_type=debt_type,
            description=data.get("description", ""),
            planted_chapter=data.get("planted_chapter", 0),
            due_chapter=data.get("due_chapter"),
            importance=data.get("importance", 2),
            is_overdue=data.get("is_overdue", False),
            resolved_chapter=data.get("resolved_chapter"),
            involved_entities=data.get("involved_entities", []),
            context=data.get("context", ""),
        )

    def mark_overdue(self) -> "NarrativeDebt":
        """标记为逾期"""
        return NarrativeDebt(
            id=self.id,
            novel_id=self.novel_id,
            debt_type=self.debt_type,
            description=self.description,
            planted_chapter=self.planted_chapter,
            due_chapter=self.due_chapter,
            importance=self.importance,
            is_overdue=True,
            resolved_chapter=self.resolved_chapter,
            involved_entities=self.involved_entities,
            context=self.context,
        )

    def resolve(self, chapter: int) -> "NarrativeDebt":
        """结算债务"""
        return NarrativeDebt(
            id=self.id,
            novel_id=self.novel_id,
            debt_type=self.debt_type,
            description=self.description,
            planted_chapter=self.planted_chapter,
            due_chapter=self.due_chapter,
            importance=self.importance,
            is_overdue=False,
            resolved_chapter=chapter,
            involved_entities=self.involved_entities,
            context=self.context,
        )

    def abandon(self) -> "NarrativeDebt":
        """V9: 放弃债务（永远留白）

        永远留白也是一种文学选择。《红楼梦》里有大量伏笔从未收束。
        这不是"欠债不还"，而是"这个故事选择不回答这个问题"。
        """
        return NarrativeDebt(
            id=self.id,
            novel_id=self.novel_id,
            debt_type=self.debt_type,
            description=self.description,
            planted_chapter=self.planted_chapter,
            due_chapter=self.due_chapter,
            importance=1,  # V9: 放弃后降为最低优先级
            is_overdue=False,
            resolved_chapter=-1,  # V9: -1 表示主动放弃（区别于 None=未结算 和 正数=已结算）
            involved_entities=self.involved_entities,
            context=self.context,
        )

    @property
    def is_resolved(self) -> bool:
        return self.resolved_chapter is not None and self.resolved_chapter > 0

    @property
    def is_abandoned(self) -> bool:
        """V9: 是否已被主动放弃（留白）"""
        return self.resolved_chapter == -1

    @property
    def age(self) -> Optional[int]:
        """债务年龄（从产生到现在）- 需要外部传入 current_chapter"""
        return None  # 需要运行时计算

    def age_at(self, current_chapter: int) -> int:
        """计算在指定章节的债务年龄"""
        return current_chapter - self.planted_chapter

    @property
    def importance_label(self) -> str:
        """重要性标签"""
        labels = {1: "次要", 2: "一般", 3: "重要", 4: "关键"}
        return labels.get(self.importance, "一般")

    @property
    def debt_type_label(self) -> str:
        """债务类型标签"""
        labels = {
            DebtType.FORESHADOWING: "伏笔",
            DebtType.CAUSAL_CHAIN: "因果链",
            DebtType.STORYLINE: "故事线",
            DebtType.CHARACTER_ARC: "角色弧",
        }
        return labels.get(self.debt_type, "未知")
