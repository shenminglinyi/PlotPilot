"""Story聚合根 — 纯粹的业务模型

核心职责：
- 管理角色、剧情弧线、章节
- 维护当前Checkpoint指针（HEAD）
- 跟踪故事生命周期阶段
- 不含任何技术/审计字段
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Any, Optional
import uuid

from engine.domain.entities.character import Character
from engine.domain.value_objects.checkpoint import CheckpointId


class StoryPhase(str, Enum):
    """故事生命周期阶段 — 全局收敛沙漏的核心状态机"""
    OPENING = "opening"         # 开局期(0-25%)：铺陈悬念，埋设伏笔
    DEVELOPMENT = "development"  # 发展期(25-75%)：激化矛盾，引入支线
    CONVERGENCE = "convergence"  # 收敛期(75-90%)：禁止开新坑，强制填坑
    FINALE = "finale"           # 终局期(90-100%)：终极对决，切断日常


@dataclass(frozen=True)
class StoryId:
    """故事ID值对象"""
    value: str

    @classmethod
    def generate(cls) -> StoryId:
        return cls(value=str(uuid.uuid4()))

    def __str__(self) -> str:
        return self.value


@dataclass
class Story:
    """故事聚合根（纯粹的业务模型）

    核心原则：
    - 只有业务字段，无技术/审计污染
    - 自动驾驶状态由 AutopilotState 值对象管理（在应用层）
    - 审计状态由 AuditSnapshot 值对象管理（在应用层）
    - 当前Checkpoint指针 = Git HEAD
    """
    story_id: StoryId
    title: str
    premise: str

    # 组成部分
    characters: List[Character] = field(default_factory=list)
    plot_arcs: List[Any] = field(default_factory=list)
    chapters: List[Any] = field(default_factory=list)

    # 状态指针
    current_checkpoint: Optional[CheckpointId] = None
    story_phase: StoryPhase = StoryPhase.OPENING
    current_chapter: int = 0
    target_chapters: int = 0

    @classmethod
    def create(cls, title: str, premise: str, target_chapters: int = 0) -> Story:
        """工厂方法：创建故事"""
        return cls(
            story_id=StoryId.generate(),
            title=title,
            premise=premise,
            target_chapters=target_chapters,
        )

    def add_character(self, character: Character) -> None:
        """添加角色"""
        self.characters.append(character)

    def remove_character(self, character_id: str) -> None:
        """移除角色"""
        self.characters = [c for c in self.characters
                           if c.character_id.value != character_id]

    def get_character(self, character_id: str) -> Optional[Character]:
        """获取角色"""
        for c in self.characters:
            if c.character_id.value == character_id:
                return c
        return None

    def advance_plot(self, event: Dict[str, Any]) -> None:
        """推进剧情"""
        if event.get('type') == 'chapter_completed':
            self.current_chapter = event['chapter_number']
        elif event.get('type') == 'phase_transition':
            self.story_phase = StoryPhase(event['new_phase'])

    def compute_progress(self) -> float:
        """计算故事进度 (0.0 ~ 1.0)"""
        if self.target_chapters <= 0:
            return 0.0
        return min(1.0, self.current_chapter / self.target_chapters)

    def determine_phase(self) -> StoryPhase:
        """根据进度自动确定故事阶段"""
        progress = self.compute_progress()
        if progress < 0.25:
            return StoryPhase.OPENING
        elif progress < 0.75:
            return StoryPhase.DEVELOPMENT
        elif progress < 0.90:
            return StoryPhase.CONVERGENCE
        else:
            return StoryPhase.FINALE

    def update_phase(self) -> None:
        """自动更新故事阶段"""
        self.story_phase = self.determine_phase()

    def is_new_foreshadow_allowed(self) -> bool:
        """收敛期和终局期是否允许新伏笔"""
        return self.story_phase in (StoryPhase.OPENING, StoryPhase.DEVELOPMENT)

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "story_id": self.story_id.value,
            "title": self.title,
            "premise": self.premise,
            "story_phase": self.story_phase.value,
            "current_chapter": self.current_chapter,
            "target_chapters": self.target_chapters,
            "current_checkpoint": self.current_checkpoint.value if self.current_checkpoint else None,
            "character_count": len(self.characters),
            "chapter_count": len(self.chapters),
        }
