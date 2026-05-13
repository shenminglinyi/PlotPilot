import uuid
from typing import List, Optional
from domain.novel.entities.storyline import Storyline
from domain.novel.value_objects.novel_id import NovelId
from domain.novel.value_objects.storyline_type import StorylineType
from domain.novel.value_objects.storyline_status import StorylineStatus
from domain.novel.value_objects.storyline_milestone import StorylineMilestone
from domain.novel.value_objects.storyline_role import StorylineRole
from domain.novel.repositories.storyline_repository import StorylineRepository


class StorylineManager:
    """故事线管理领域服务"""

    def __init__(self, repository: StorylineRepository):
        self.repository = repository

    def create_storyline(
        self,
        novel_id: NovelId,
        storyline_type: StorylineType,
        estimated_chapter_start: int,
        estimated_chapter_end: int,
        name: str = "",
        description: str = "",
        role: StorylineRole = StorylineRole.MAIN,
        parent_id: Optional[str] = None,
        chapter_weight: float = 1.0,
    ) -> Storyline:
        """创建新的故事线

        Args:
            novel_id: 小说 ID
            storyline_type: 故事线类型
            estimated_chapter_start: 预计开始章节
            estimated_chapter_end: 预计结束章节
            name: 显示名称（可选）
            description: 详细说明（可选）
            role: 故事线结构角色（main/sub/dark）
            parent_id: 父故事线 ID（可选）
            chapter_weight: 章节权重（默认 1.0）

        Returns:
            创建的故事线实体
        """
        storyline_id = str(uuid.uuid4())
        storyline = Storyline(
            id=storyline_id,
            novel_id=novel_id,
            storyline_type=storyline_type,
            status=StorylineStatus.ACTIVE,
            estimated_chapter_start=estimated_chapter_start,
            estimated_chapter_end=estimated_chapter_end,
            name=name or "",
            description=description or "",
            role=role,
            parent_id=parent_id,
            chapter_weight=chapter_weight,
        )

        self.repository.save(storyline)
        return storyline

    def get_pending_milestones(self, storyline_id: str) -> List[StorylineMilestone]:
        """获取故事线的待完成里程碑

        Args:
            storyline_id: 故事线 ID

        Returns:
            待完成的里程碑列表

        Raises:
            ValueError: 如果故事线不存在
        """
        storyline = self.repository.get_by_id(storyline_id)
        if storyline is None:
            raise ValueError(f"Storyline {storyline_id} not found")

        return storyline.get_pending_milestones()

    def complete_milestone(self, storyline_id: str, milestone_order: int) -> None:
        """完成故事线的里程碑

        Args:
            storyline_id: 故事线 ID
            milestone_order: 里程碑顺序号

        Raises:
            ValueError: 如果故事线不存在或里程碑无效
        """
        storyline = self.repository.get_by_id(storyline_id)
        if storyline is None:
            raise ValueError(f"Storyline {storyline_id} not found")

        storyline.complete_milestone(milestone_order)
        self.repository.save(storyline)

    def get_storyline_context(self, storyline_id: str) -> str:
        """获取故事线上下文信息

        Args:
            storyline_id: 故事线 ID

        Returns:
            故事线上下文的文本描述

        Raises:
            ValueError: 如果故事线不存在
        """
        storyline = self.repository.get_by_id(storyline_id)
        if storyline is None:
            raise ValueError(f"Storyline {storyline_id} not found")

        context_parts = [
            f"Storyline Type: {storyline.storyline_type.value}",
            f"Status: {storyline.status.value}",
            f"Estimated Chapters: {storyline.estimated_chapter_start}-{storyline.estimated_chapter_end}"
        ]

        current_milestone = storyline.get_current_milestone()
        if current_milestone:
            context_parts.append(f"\nCurrent Milestone: {current_milestone.title}")
            context_parts.append(f"Description: {current_milestone.description}")
            context_parts.append(f"Target Chapters: {current_milestone.target_chapter_start}-{current_milestone.target_chapter_end}")
            if current_milestone.prerequisites:
                context_parts.append(f"Prerequisites: {', '.join(current_milestone.prerequisites)}")
            if current_milestone.triggers:
                context_parts.append(f"Triggers: {', '.join(current_milestone.triggers)}")
        else:
            context_parts.append("\nNo current milestone")

        return "\n".join(context_parts)
