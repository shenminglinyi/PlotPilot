"""PlotStateMachine — 故事阶段生命周期管理

核心设计：全局收敛沙漏
- OPENING(0-25%) → DEVELOPMENT(25-75%) → CONVERGENCE(75-90%) → FINALE(90-100%)

收敛期核心规则：
- 禁止开新坑（新伏笔）
- 强制填坑（未回收伏笔需安排回收计划）
- 剧情密度提升
- 日常场景减少

这确保了小说不会"烂尾"——
到75%的时候，所有重要线索开始收束，就像沙漏的下半部分
"""
from __future__ import annotations

import logging
from typing import Dict, Any, List, Optional

from engine.domain.entities.story import StoryPhase
from engine.domain.entities.foreshadow import ForeshadowStatus

logger = logging.getLogger(__name__)


class PlotStateMachine:
    """故事阶段生命周期管理

    核心职责：
    - 管理StoryPhase转换
    - 收敛期规则执行
    - 伏笔回收计划生成
    - 章节预算分配
    """

    # 阶段转换规则
    PHASE_TRANSITIONS = {
        StoryPhase.OPENING: [StoryPhase.DEVELOPMENT],
        StoryPhase.DEVELOPMENT: [StoryPhase.CONVERGENCE],
        StoryPhase.CONVERGENCE: [StoryPhase.FINALE],
        StoryPhase.FINALE: [],  # 终局不可转换
    }

    # 各阶段章节预算分配
    PHASE_BUDGET = {
        StoryPhase.OPENING: {"tension_base": 40, "tension_peak": 60, "daily_ratio": 0.3},
        StoryPhase.DEVELOPMENT: {"tension_base": 60, "tension_peak": 85, "daily_ratio": 0.2},
        StoryPhase.CONVERGENCE: {"tension_base": 75, "tension_peak": 95, "daily_ratio": 0.1},
        StoryPhase.FINALE: {"tension_base": 90, "tension_peak": 100, "daily_ratio": 0.0},
    }

    def __init__(self):
        self._current_phase: StoryPhase = StoryPhase.OPENING
        self._phase_history: List[Dict[str, Any]] = []

    @property
    def current_phase(self) -> StoryPhase:
        return self._current_phase

    def can_transition(self, target: StoryPhase) -> bool:
        """是否允许阶段转换"""
        return target in self.PHASE_TRANSITIONS.get(self._current_phase, [])

    def transition(self, target: StoryPhase, reason: str = "") -> bool:
        """执行阶段转换

        Args:
            target: 目标阶段
            reason: 转换原因

        Returns:
            是否成功
        """
        if not self.can_transition(target):
            logger.warning(f"不允许的阶段转换: {self._current_phase.value} → {target.value}")
            return False

        old_phase = self._current_phase
        self._current_phase = target
        self._phase_history.append({
            "from": old_phase.value,
            "to": target.value,
            "reason": reason,
        })

        logger.info(f"🔄 故事阶段转换: {old_phase.value} → {target.value} ({reason})")
        return True

    def is_new_foreshadow_allowed(self) -> bool:
        """收敛期和终局期是否允许新伏笔"""
        return self._current_phase in (StoryPhase.OPENING, StoryPhase.DEVELOPMENT)

    def get_foreshadow_action(self, foreshadow_status: ForeshadowStatus) -> Optional[str]:
        """获取伏笔应该执行的操作

        Returns:
            'plant' / 'reference' / 'awaken' / 'resolve' / 'abandon' / None
        """
        if self._current_phase == StoryPhase.CONVERGENCE:
            if foreshadow_status == ForeshadowStatus.PLANTED:
                return "awaken"  # 收敛期：唤醒已埋伏笔
            elif foreshadow_status == ForeshadowStatus.REFERENCED:
                return "awaken"
            elif foreshadow_status == ForeshadowStatus.AWAKENING:
                return "resolve"  # 收敛期：回收已唤醒伏笔

        elif self._current_phase == StoryPhase.FINALE:
            if foreshadow_status in (ForeshadowStatus.PLANTED, ForeshadowStatus.REFERENCED, ForeshadowStatus.AWAKENING):
                return "resolve"  # 终局期：强制回收所有伏笔

        return None

    def get_chapter_budget(self) -> Dict[str, Any]:
        """获取当前阶段的章节预算"""
        return self.PHASE_BUDGET.get(self._current_phase, self.PHASE_BUDGET[StoryPhase.OPENING])

    def generate_convergence_plan(self, active_foreshadows: List[Dict[str, Any]]) -> Dict[str, Any]:
        """生成收敛期伏笔回收计划

        Args:
            active_foreshadows: 活跃伏笔列表

        Returns:
            收敛计划（伏笔回收时间表）
        """
        if self._current_phase not in (StoryPhase.CONVERGENCE, StoryPhase.FINALE):
            return {"status": "not_in_convergence", "message": "当前阶段不需要收敛计划"}

        # 按重要度排序
        sorted_foreshadows = sorted(
            active_foreshadows,
            key=lambda f: f.get("emotional_weight", 0.5),
            reverse=True
        )

        plan = []
        for i, f in enumerate(sorted_foreshadows):
            plan.append({
                "foreshadow_id": f.get("id", ""),
                "description": f.get("description", ""),
                "action": self.get_foreshadow_action(ForeshadowStatus(f.get("status", "planted"))),
                "priority": i + 1,
                "emotional_weight": f.get("emotional_weight", 0.5),
            })

        return {
            "status": "convergence_plan",
            "total_foreshadows": len(plan),
            "must_resolve": [p for p in plan if p["emotional_weight"] > 0.8],
            "can_abandon": [p for p in plan if p["emotional_weight"] < 0.3],
            "plan": plan,
        }

    def get_phase_instruction(self) -> str:
        """获取当前阶段的T0层注入指令"""
        instructions = {
            StoryPhase.OPENING: (
                "【开局期写作指令】\n"
                "- 铺陈悬念，建立世界观\n"
                "- 引入核心角色，建立读者认同\n"
                "- 埋设核心伏笔（emotional_weight > 0.8）\n"
                "- 张力控制在40-60，适度起伏\n"
                "- 日常场景占比约30%"
            ),
            StoryPhase.DEVELOPMENT: (
                "【发展期写作指令】\n"
                "- 激化矛盾，推进角色成长弧线\n"
                "- 引入支线角色和势力\n"
                "- 持续埋设伏笔，已有伏笔适时提及\n"
                "- 张力控制在60-85，高潮起伏\n"
                "- 日常场景占比约20%（用于情感缓冲）"
            ),
            StoryPhase.CONVERGENCE: (
                "【收敛期写作指令 — 禁止开新坑】\n"
                "- 不再埋设新伏笔，所有伏笔进入唤醒/回收流程\n"
                "- 剧情密度大幅提升\n"
                "- 日常场景降至10%以下\n"
                "- 张力控制在75-95，持续高压\n"
                "- 核心伏笔必须安排回收计划"
            ),
            StoryPhase.FINALE: (
                "【终局期写作指令 — 强制填坑】\n"
                "- 所有未回收伏笔必须在3章内解决\n"
                "- 终极对决，切断日常\n"
                "- 张力90-100，全程高压\n"
                "- 不允许日常场景\n"
                "- 核心角色弧线必须完成"
            ),
        }
        return instructions.get(self._current_phase, "")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "current_phase": self._current_phase.value,
            "is_new_foreshadow_allowed": self.is_new_foreshadow_allowed(),
            "chapter_budget": self.get_chapter_budget(),
            "phase_history": self._phase_history,
        }
