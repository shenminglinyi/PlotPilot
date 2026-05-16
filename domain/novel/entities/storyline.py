from typing import List, Optional
from domain.shared.base_entity import BaseEntity
from domain.novel.value_objects.novel_id import NovelId
from domain.novel.value_objects.storyline_role import StorylineRole
from domain.novel.value_objects.storyline_type import StorylineType
from domain.novel.value_objects.storyline_status import StorylineStatus
from domain.novel.value_objects.storyline_milestone import StorylineMilestone


class Storyline(BaseEntity):
    """故事线实体"""

    def __init__(
        self,
        id: str,
        novel_id: NovelId,
        storyline_type: StorylineType,
        status: StorylineStatus,
        estimated_chapter_start: int,
        estimated_chapter_end: int,
        milestones: Optional[List[StorylineMilestone]] = None,
        current_milestone_index: int = 0,
        name: str = "",
        description: str = "",
        last_active_chapter: int = 0,
        progress_summary: str = "",
        # ── 新增字段（所有均有默认值，向后兼容）──
        role: StorylineRole = StorylineRole.MAIN,
        parent_id: Optional[str] = None,
        chapter_weight: float = 1.0,
    ):
        super().__init__(id)
        self.novel_id = novel_id
        self.storyline_type = storyline_type
        self.status = status
        self.estimated_chapter_start = estimated_chapter_start
        self.estimated_chapter_end = estimated_chapter_end
        self.milestones: List[StorylineMilestone] = milestones if milestones is not None else []
        self.current_milestone_index = current_milestone_index
        self.name = name
        self.description = description
        self.last_active_chapter = last_active_chapter
        self.progress_summary = progress_summary
        self.role = role
        self.parent_id = parent_id
        self.chapter_weight = chapter_weight

    def update_progress(self, chapter_number: int, summary: str) -> None:
        """更新故事线进度

        Args:
            chapter_number: 章节号
            summary: 进度摘要
        """
        self.last_active_chapter = chapter_number
        self.progress_summary = summary

    def add_milestone(self, milestone: StorylineMilestone) -> None:
        """添加里程碑"""
        if milestone is None:
            raise ValueError("Milestone cannot be None")
        self.milestones.append(milestone)

    def get_pending_milestones(self) -> List[StorylineMilestone]:
        """获取待完成的里程碑"""
        return self.milestones[self.current_milestone_index:]

    def complete_milestone(self, order: int) -> None:
        """完成指定顺序的里程碑

        Args:
            order: 里程碑顺序号

        Raises:
            ValueError: 如果里程碑不存在或不能按顺序完成
        """
        # Find milestone with the given order
        milestone_index = None
        for i, milestone in enumerate(self.milestones):
            if milestone.order == order:
                milestone_index = i
                break

        if milestone_index is None:
            raise ValueError(f"Milestone with order {order} not found")

        # Check if we're completing milestones in order
        if milestone_index != self.current_milestone_index:
            raise ValueError(
                f"Cannot complete milestone {order} before completing milestone {self.milestones[self.current_milestone_index].order}"
            )

        # Move to next milestone
        self.current_milestone_index += 1

    def get_current_milestone(self) -> Optional[StorylineMilestone]:
        """获取当前里程碑

        Returns:
            当前里程碑，如果所有里程碑都已完成则返回 None
        """
        if self.current_milestone_index < len(self.milestones):
            return self.milestones[self.current_milestone_index]
        return None
