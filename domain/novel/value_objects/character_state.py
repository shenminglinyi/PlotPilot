"""人物可变状态值对象 - Scars / Motivations / Emotional Arc

V9 减法改革：角色不是状态机

核心设计理念（V9 改革前）：
  传统人设：Character.traits = ["冷酷", "理性"]  —— 静态标签，永不改变
  人物状态机：CharacterState.scars + motivations  —— 动态状态，随剧情演进

V9 改革后：
  把角色定义为 伤疤(8/10) + 执念(P9) 会让角色退化成触发式 NPC。
  AI 为了完成"不 OOC"的指令，会机械地在每一章复读这些伤疤，导致"角色弧光冻结"。

  新增遗忘曲线：
  - Scar 的 intensity 会随章节自然衰减（时间是最好的解药）
  - Motivation 可以被 resolve（执念是可以放下的）或 dissolve（自然消解）
  - get_active_scars() 现在考虑衰减后的有效强度

三大连贯性问题的解决方案：
  1. 情感失忆症：Scars 记录"伤疤"，AI 不会忘记主角经历过什么
  2. 因果链条断裂：Motivations 记录"执念"，AI 知道角色当前的驱动力
  3. 人物弧光冻结：Emotional Arc 追踪情感变化，MacroDiagnosis 能区分 OOC 和 Breakout
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List
from uuid import uuid4


@dataclass(frozen=True)
class Scar:
    """伤疤（心理阴影/创伤记忆）

    记录角色经历的重大创伤及其对心理状态的持续影响。
    伤疤是 MacroDiagnosis 判定 OOC vs Character Breakout 的关键依据。

    例：
      Scar(
          source_event="挚友赵宇在眼前被杀",
          source_chapter=20,
          impact="对'信任他人'极度恐惧",
          sensitivity_tags=["信任", "背叛", "生死"],
          intensity=9
      )

    当系统检测到角色在第 50 章因为"信任"问题而做出"冲动"行为时，
    不再判定为 OOC，而是判定为 Scar 触发——这是高光时刻。
    """
    id: str = field(default_factory=lambda: str(uuid4()))
    source_event: str = ""
    source_chapter: int = 0
    impact: str = ""
    sensitivity_tags: List[str] = field(default_factory=list)
    intensity: int = 7
    is_active: bool = True
    faded_chapter: Optional[int] = None

    def __post_init__(self):
        if not 1 <= self.intensity <= 10:
            raise ValueError("intensity must be between 1 and 10")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source_event": self.source_event,
            "source_chapter": self.source_chapter,
            "impact": self.impact,
            "sensitivity_tags": self.sensitivity_tags,
            "intensity": self.intensity,
            "is_active": self.is_active,
            "faded_chapter": self.faded_chapter,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Scar":
        return cls(
            id=data.get("id", str(uuid4())),
            source_event=data.get("source_event", ""),
            source_chapter=data.get("source_chapter", 0),
            impact=data.get("impact", ""),
            sensitivity_tags=data.get("sensitivity_tags", []),
            intensity=data.get("intensity", 7),
            is_active=data.get("is_active", True),
            faded_chapter=data.get("faded_chapter"),
        )

    def fade(self, chapter: int) -> "Scar":
        return Scar(
            id=self.id,
            source_event=self.source_event,
            source_chapter=self.source_chapter,
            impact=self.impact,
            sensitivity_tags=self.sensitivity_tags,
            intensity=self.intensity,
            is_active=True,
            faded_chapter=chapter,
        )

    def effective_intensity(self, current_chapter: int) -> int:
        """V9: 计算衰减后的有效强度

        遗忘曲线：intensity 每经过 10 章衰减 1 点（最低 1）。
        这不是"忘记"，而是"不再主动影响行为"——
        伤疤永远存在，但它对角色行为的驱动力会随时间自然减弱。

        例：intensity=9 的伤疤，经过 30 章后，有效强度为 6。
        """
        if not self.is_active:
            return 0
        chapters_elapsed = current_chapter - self.source_chapter
        decay = max(0, chapters_elapsed // 10)
        return max(1, self.intensity - decay)

    def deactivate(self) -> "Scar":
        return Scar(
            id=self.id,
            source_event=self.source_event,
            source_chapter=self.source_chapter,
            impact=self.impact,
            sensitivity_tags=self.sensitivity_tags,
            intensity=self.intensity,
            is_active=False,
            faded_chapter=self.faded_chapter,
        )

    def matches_sensitivity(self, tags: List[str]) -> bool:
        """检查给定标签是否触发了此伤疤的敏感点"""
        return bool(set(tags) & set(self.sensitivity_tags))


@dataclass(frozen=True)
class Motivation:
    """执念（当前驱动角色的核心目标）

    记录角色当前的核心驱动力。与 Scar 不同，
    Motivation 是"向前看"的（我要做什么），而 Scar 是"向后看"的（我经历了什么）。

    例：
      Motivation(
          description="为赵宇复仇",
          source_event="赵宇之死",
          source_chapter=20,
          priority=10
      )
    """
    id: str = field(default_factory=lambda: str(uuid4()))
    description: str = ""
    source_event: str = ""
    source_chapter: int = 0
    priority: int = 5
    is_active: bool = True
    resolved_chapter: Optional[int] = None

    def __post_init__(self):
        if not 1 <= self.priority <= 10:
            raise ValueError("priority must be between 1 and 10")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "description": self.description,
            "source_event": self.source_event,
            "source_chapter": self.source_chapter,
            "priority": self.priority,
            "is_active": self.is_active,
            "resolved_chapter": self.resolved_chapter,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Motivation":
        return cls(
            id=data.get("id", str(uuid4())),
            description=data.get("description", ""),
            source_event=data.get("source_event", ""),
            source_chapter=data.get("source_chapter", 0),
            priority=data.get("priority", 5),
            is_active=data.get("is_active", True),
            resolved_chapter=data.get("resolved_chapter"),
        )

    def resolve(self, chapter: int) -> "Motivation":
        return Motivation(
            id=self.id,
            description=self.description,
            source_event=self.source_event,
            source_chapter=self.source_chapter,
            priority=self.priority,
            is_active=False,
            resolved_chapter=chapter,
        )

    def dissolve(self) -> "Motivation":
        """V9: 执念自然消解（不是被完成，而是被时间或新事物冲淡）

        与 resolve 不同：resolve 意味着目标达成，dissolve 意味着不再在乎。
        例："为赵宇复仇"的执念，在角色找到新的人生意义后自然消解。
        """
        return Motivation(
            id=self.id,
            description=self.description,
            source_event=self.source_event,
            source_chapter=self.source_chapter,
            priority=1,  # V9: 降到最低
            is_active=False,
            resolved_chapter=-1,  # -1 表示自然消解（区别于 None=未结算）
        )


@dataclass(frozen=True)
class EmotionalArcNode:
    """情感弧线节点

    追踪角色的情感变化轨迹，用于：
    1. 宏观诊断判定 OOC vs Breakout
    2. 上下文注入：告诉 AI 角色当前的情绪状态
    3. 张力评分：情感转折点的数量和强度
    """
    chapter: int
    emotion: str
    trigger: str
    intensity: int
    is_breakout: bool = False

    def __post_init__(self):
        if self.chapter < 1:
            raise ValueError("chapter must be >= 1")
        if not 1 <= self.intensity <= 10:
            raise ValueError("intensity must be between 1 and 10")

    def to_dict(self) -> dict:
        return {
            "chapter": self.chapter,
            "emotion": self.emotion,
            "trigger": self.trigger,
            "intensity": self.intensity,
            "is_breakout": self.is_breakout,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EmotionalArcNode":
        return cls(
            chapter=data.get("chapter", 1),
            emotion=data.get("emotion", ""),
            trigger=data.get("trigger", ""),
            intensity=data.get("intensity", 5),
            is_breakout=data.get("is_breakout", False),
        )


class BreakpointType(str, Enum):
    """诊断断点类型

    核心区分：
    - OOC: 真正的人设崩塌（无合理原因的偏离）
    - BREAKOUT: 人物突破/高光时刻（有触发原因的偏离，不应阻断）
    - SCAR_TRIGGERED: 伤疤触发后的应激反应（应延续情绪而非阻断）
    """
    OOC = "ooc"
    CHARACTER_BREAKOUT = "breakout"
    SCAR_TRIGGERED = "scar_triggered"


@dataclass
class CharacterState:
    """人物可变状态

    与 Character 实体正交：Character 存储静态设定，CharacterState 存储动态状态。

    核心价值：
    1. 解决"情感失忆症"：Scars 让 AI 记得角色经历过什么
    2. 解决"人物弧光冻结"：MacroDiagnosis 能区分 OOC 和 Breakout
    3. 提供上下文注入素材：Scars + Motivations -> T0 槽位

    持久化到 character_states 表。
    """
    character_id: str
    novel_id: str

    base_traits: List[str] = field(default_factory=list)

    scars: List[Scar] = field(default_factory=list)
    motivations: List[Motivation] = field(default_factory=list)
    emotional_arc: List[EmotionalArcNode] = field(default_factory=list)

    current_state_summary: str = ""
    last_updated_chapter: int = 0

    def add_scar(self, scar: Scar) -> None:
        self.scars.append(scar)

    def add_motivation(self, motivation: Motivation) -> None:
        self.motivations.append(motivation)

    def add_emotional_arc_node(self, node: EmotionalArcNode) -> None:
        self.emotional_arc.append(node)

    def get_active_scars(self, current_chapter: int = 0) -> List[Scar]:
        """V9: 获取活跃伤疤，考虑遗忘曲线衰减。

        只有有效强度 >= 2 的伤疤才视为"活跃"。
        有效强度为 1 的伤疤虽未 deactivate，但已不再主动影响角色行为。
        """
        active = [s for s in self.scars if s.is_active]
        if current_chapter <= 0:
            return active
        # V9: 过滤掉有效强度低于 2 的伤疤（它们已经"愈合"了）
        return [s for s in active if s.effective_intensity(current_chapter) >= 2]

    def get_active_motivations(self) -> List[Motivation]:
        return [m for m in self.motivations if m.is_active]

    def get_top_motivations(self, limit: int = 3) -> List[Motivation]:
        active = self.get_active_motivations()
        return sorted(active, key=lambda m: m.priority, reverse=True)[:limit]

    def check_scar_trigger(self, tags: List[str]) -> List[Scar]:
        """检查给定标签是否触发了活跃伤疤"""
        return [s for s in self.get_active_scars() if s.matches_sensitivity(tags)]

    def is_character_breakout(
        self,
        conflict_tags: List[str],
        chapter_events: str = "",
    ) -> BreakpointType:
        """判定人设偏离是 OOC 还是 Character Breakout

        判定逻辑：
        1. 检查是否有活跃伤疤被触发 -> SCAR_TRIGGERED
        2. 检查是否有高优先级执念 -> CHARACTER_BREAKOUT
        3. 无合理原因 -> OOC
        """
        # 1. 检查伤疤触发
        triggered_scars = self.check_scar_trigger(conflict_tags)
        if triggered_scars:
            return BreakpointType.SCAR_TRIGGERED

        # 2. 检查高优先级执念
        high_intensity_motivations = [
            m for m in self.get_active_motivations() if m.priority >= 8
        ]
        if high_intensity_motivations:
            return BreakpointType.CHARACTER_BREAKOUT

        # 3. 无合理原因的偏离
        return BreakpointType.OOC

    def to_dict(self) -> dict:
        return {
            "character_id": self.character_id,
            "novel_id": self.novel_id,
            "base_traits": self.base_traits,
            "scars": [s.to_dict() for s in self.scars],
            "motivations": [m.to_dict() for m in self.motivations],
            "emotional_arc": [e.to_dict() for e in self.emotional_arc],
            "current_state_summary": self.current_state_summary,
            "last_updated_chapter": self.last_updated_chapter,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CharacterState":
        return cls(
            character_id=data.get("character_id", ""),
            novel_id=data.get("novel_id", ""),
            base_traits=data.get("base_traits", []),
            scars=[Scar.from_dict(s) for s in data.get("scars", [])],
            motivations=[Motivation.from_dict(m) for m in data.get("motivations", [])],
            emotional_arc=[EmotionalArcNode.from_dict(e) for e in data.get("emotional_arc", [])],
            current_state_summary=data.get("current_state_summary", ""),
            last_updated_chapter=data.get("last_updated_chapter", 0),
        )

    def build_context_injection(
        self,
        current_chapter: int = 0,
        display_name: Optional[str] = None,
    ) -> str:
        """构建注入文本（V9: 从 T0 降级到编辑手记，语气从铁律变为参考）

        Args:
            current_chapter: 当前章节（用于伤疤强度衰减）
            display_name: Bible 人物姓名；若提供则注入上下文时用姓名而非 character_id（UUID）
        """
        if not self.scars and not self.motivations:
            return ""

        label = (display_name or "").strip() or self.character_id
        lines = [f"  {label}："]

        # 伤疤（V9: 显示衰减后的有效强度）
        for scar in self.get_active_scars(current_chapter):
            eff = scar.effective_intensity(current_chapter) if current_chapter > 0 else scar.intensity
            lines.append(
                f"    经历过：[第{scar.source_chapter}章] {scar.source_event} "
                f"→ {scar.impact}(强度{eff}/10)"
            )
            if scar.sensitivity_tags:
                tags_str = "/".join(scar.sensitivity_tags[:3])
                lines.append(f"      触发词: {tags_str}")

        # 执念
        for motivation in self.get_top_motivations(3):
            lines.append(
                f"    当前驱动力：{motivation.description}(P{motivation.priority})"
            )

        # 当前状态摘要
        if self.current_state_summary:
            lines.append(f"    状态: {self.current_state_summary}")

        return "\n".join(lines)
