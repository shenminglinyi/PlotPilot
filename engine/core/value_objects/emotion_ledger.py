"""EmotionLedger值对象 — 情绪账本（替代传统摘要）

核心改进：从"流水账摘要"升级为"小说家视角的情绪账本"

传统摘要（流水账）：
- 林羽和赵虎打了一架，林羽赢了。然后去了客栈。

EmotionLedger（小说家视角）：
- 【核心损失】林羽失去信任的导师（心境变化：多疑、谨慎）
- 【势能转化】从"被动挨打" → "暗中筹谋的猎手"
- 【未解悬念】赵虎的眼神暗示：另有幕后黑手

四大维度：
1. EmotionalWound：核心损失（失去导师 → 多疑）
2. EmotionalBoon：核心获得（获得剑谱 → 实力提升）
3. PowerShift：势能转化（被动挨打 → 暗中筹谋）
4. OpenLoop：未解悬念（赵虎眼神另有隐情）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class EmotionalWound:
    """情绪创伤（核心损失）

    不是事件记录，而是事件对角色心态的影响
    示例：失去导师 → 心境变化：多疑、谨慎
    """
    description: str     # 创伤描述："失去信任的导师"
    impact: str          # 对角色心态的影响："多疑、谨慎"
    chapter_number: int = 0

    def to_summary_line(self) -> str:
        return f"【核心损失】{self.description}（心境变化：{self.impact}）"


@dataclass(frozen=True)
class EmotionalBoon:
    """情绪收获（核心获得）

    示例：获得剑谱 → 实力提升，自信增加
    """
    description: str     # 收获描述："获得师父的剑谱"
    value: str           # 带来的价值："实力提升，自信增加"
    chapter_number: int = 0

    def to_summary_line(self) -> str:
        return f"【核心获得】{self.description}（价值：{self.value}）"


@dataclass(frozen=True)
class PowerShift:
    """势能转化

    记录角色/局势的权力关系变化
    示例：从"被动挨打" → "暗中筹谋的猎手"
    """
    from_state: str      # 从"被动挨打"
    to_state: str        # 到"暗中筹谋的猎手"
    trigger: str = ""    # 触发原因

    def to_summary_line(self) -> str:
        return f"【势能转化】从「{self.from_state}」→「{self.to_state}」"


@dataclass(frozen=True)
class OpenLoop:
    """未解悬念

    不是所有伏笔都需要回收，但需要追踪
    示例：赵虎的眼神暗示——另有幕后黑手
    """
    description: str     # 悬念描述："赵虎死前不可置信的眼神"
    hint: str            # 暗示线索："另有幕后黑手"
    planted_chapter: int = 0
    urgency: float = 0.5  # 紧迫度 0-1（接近1需要尽快回收）

    def to_summary_line(self) -> str:
        return f"【未解悬念】{self.description}（暗示：{self.hint}）"


@dataclass(frozen=True)
class EmotionLedger:
    """情绪账本值对象（替代传统摘要）

    小说家视角的章节状态记录：
    - Wounds/Boons: 核心损失与获得
    - PowerShift: 势能转化
    - OpenLoops: 未解悬念

    这不是流水账，而是记录"林羽心里憋着什么火"
    """
    wounds: List[EmotionalWound] = field(default_factory=list)
    boons: List[EmotionalBoon] = field(default_factory=list)
    power_shifts: List[PowerShift] = field(default_factory=list)
    open_loops: List[OpenLoop] = field(default_factory=list)

    @classmethod
    def create_empty(cls) -> EmotionLedger:
        """创建空账本"""
        return cls(wounds=[], boons=[], power_shifts=[], open_loops=[])

    def add_wound(self, wound: EmotionalWound) -> EmotionLedger:
        """追加创伤（返回新账本，不可变）"""
        return EmotionLedger(
            wounds=self.wounds + [wound],
            boons=self.boons,
            power_shifts=self.power_shifts,
            open_loops=self.open_loops,
        )

    def add_boon(self, boon: EmotionalBoon) -> EmotionLedger:
        """追加收获"""
        return EmotionLedger(
            wounds=self.wounds,
            boons=self.boons + [boon],
            power_shifts=self.power_shifts,
            open_loops=self.open_loops,
        )

    def add_power_shift(self, shift: PowerShift) -> EmotionLedger:
        """追加势能转化"""
        return EmotionLedger(
            wounds=self.wounds,
            boons=self.boons,
            power_shifts=self.power_shifts + [shift],
            open_loops=self.open_loops,
        )

    def add_open_loop(self, loop: OpenLoop) -> EmotionLedger:
        """追加未解悬念"""
        return EmotionLedger(
            wounds=self.wounds,
            boons=self.boons,
            power_shifts=self.power_shifts,
            open_loops=self.open_loops + [loop],
        )

    def close_loop(self, loop_description: str) -> EmotionLedger:
        """关闭已回收的悬念"""
        remaining = [l for l in self.open_loops if l.description != loop_description]
        return EmotionLedger(
            wounds=self.wounds,
            boons=self.boons,
            power_shifts=self.power_shifts,
            open_loops=remaining,
        )

    def to_t0_section(self) -> str:
        """生成T0层情绪账本注入内容"""
        lines = ["[情绪账本]"]
        for w in self.wounds[-3:]:  # 最近3个创伤
            lines.append(w.to_summary_line())
        for b in self.boons[-3:]:
            lines.append(b.to_summary_line())
        for ps in self.power_shifts[-2:]:
            lines.append(ps.to_summary_line())
        for ol in self.open_loops:
            lines.append(ol.to_summary_line())
        return "\n".join(lines)

    def to_chapter_summary(self) -> str:
        """生成章节摘要（替代传统流水账）"""
        parts = []
        if self.wounds:
            parts.append("核心损失：" + "；".join(w.to_summary_line() for w in self.wounds))
        if self.boons:
            parts.append("核心获得：" + "；".join(b.to_summary_line() for b in self.boons))
        if self.power_shifts:
            parts.append("势能变化：" + "；".join(ps.to_summary_line() for ps in self.power_shifts))
        if self.open_loops:
            parts.append("未解悬念：" + "；".join(ol.to_summary_line() for ol in self.open_loops))
        return "\n".join(parts)

    def to_dict(self) -> dict:
        """序列化"""
        return {
            "wounds": [{"description": w.description, "impact": w.impact, "chapter": w.chapter_number} for w in self.wounds],
            "boons": [{"description": b.description, "value": b.value, "chapter": b.chapter_number} for b in self.boons],
            "power_shifts": [{"from": ps.from_state, "to": ps.to_state, "trigger": ps.trigger} for ps in self.power_shifts],
            "open_loops": [{"description": ol.description, "hint": ol.hint, "urgency": ol.urgency} for ol in self.open_loops],
        }

    @classmethod
    def from_dict(cls, data: dict) -> EmotionLedger:
        """反序列化"""
        wounds = [EmotionalWound(**w) for w in data.get("wounds", [])]
        boons = [EmotionalBoon(**b) for b in data.get("boons", [])]
        power_shifts = [PowerShift(**ps) for ps in data.get("power_shifts", [])]
        open_loops = [OpenLoop(**ol) for ol in data.get("open_loops", [])]
        return cls(wounds=wounds, boons=boons, power_shifts=power_shifts, open_loops=open_loops)
