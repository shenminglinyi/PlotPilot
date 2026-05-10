"""StoryPhase值对象 — 全局收敛沙漏

核心设计：
- 开局期(0-25%)：铺陈悬念，埋设伏笔 — 允许一切
- 发展期(25-75%)：激化矛盾，引入支线 — 允许新伏笔
- 收敛期(75-90%)：禁止开新坑，强制填坑 — 限制新伏笔
- 终局期(90-100%)：终极对决，切断日常 — 禁止新伏笔

架构定位：
- 独立值对象，可被 Novel 聚合根和 engine/core 共同使用
- 不依赖任何外部模块
"""
from enum import Enum


class StoryPhase(str, Enum):
    """故事生命周期阶段 — 全局收敛沙漏的核心状态机"""
    OPENING = "opening"         # 开局期(0-25%)：铺陈悬念，埋设伏笔
    DEVELOPMENT = "development"  # 发展期(25-75%)：激化矛盾，引入支线
    CONVERGENCE = "convergence"  # 收敛期(75-90%)：禁止开新坑，强制填坑
    FINALE = "finale"           # 终局期(90-100%)：终极对决，切断日常

    @classmethod
    def from_progress(cls, progress: float) -> "StoryPhase":
        """根据进度(0.0~1.0)确定阶段"""
        if progress < 0.25:
            return cls.OPENING
        elif progress < 0.75:
            return cls.DEVELOPMENT
        elif progress < 0.90:
            return cls.CONVERGENCE
        else:
            return cls.FINALE

    @property
    def allow_new_foreshadow(self) -> bool:
        """当前阶段是否允许新伏笔"""
        return self in (StoryPhase.OPENING, StoryPhase.DEVELOPMENT)

    @property
    def allow_new_plot_arc(self) -> bool:
        """当前阶段是否允许新剧情弧线"""
        return self in (StoryPhase.OPENING, StoryPhase.DEVELOPMENT)

    @property
    def display_name(self) -> str:
        """中文显示名"""
        names = {
            StoryPhase.OPENING: "开局期",
            StoryPhase.DEVELOPMENT: "发展期",
            StoryPhase.CONVERGENCE: "收敛期",
            StoryPhase.FINALE: "终局期",
        }
        return names.get(self, self.value)

    @property
    def description(self) -> str:
        """阶段描述"""
        descs = {
            StoryPhase.OPENING: "铺陈悬念，埋设伏笔，建立世界观",
            StoryPhase.DEVELOPMENT: "激化矛盾，引入支线，角色成长",
            StoryPhase.CONVERGENCE: "禁止开新坑，强制填坑，收敛线索",
            StoryPhase.FINALE: "终极对决，切断日常，揭晓谜底",
        }
        return descs.get(self, "")
