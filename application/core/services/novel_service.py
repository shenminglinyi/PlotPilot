"""Novel 应用服务"""
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from domain.novel.entities.novel import Novel, NovelStage
from domain.novel.entities.chapter import Chapter
from domain.novel.value_objects.novel_id import NovelId
from domain.novel.value_objects.word_count import WordCount
from domain.novel.repositories.novel_repository import NovelRepository
from domain.novel.repositories.chapter_repository import ChapterRepository
from domain.shared.exceptions import EntityNotFoundError
from application.core.dtos.novel_dto import NovelDTO
from domain.structure.story_node import StoryNode, NodeType, PlanningStatus, PlanningSource
from infrastructure.persistence.database.story_node_repository import StoryNodeRepository


class NovelService:
    """Novel 应用服务

    协调领域对象和基础设施，实现应用用例。
    """

    def __init__(
        self,
        novel_repository: NovelRepository,
        chapter_repository: ChapterRepository,
        story_node_repository: Optional[StoryNodeRepository] = None,
    ):
        """初始化服务

        Args:
            novel_repository: Novel 仓储
            chapter_repository: Chapter 仓储（统计以落盘章节为准）
            story_node_repository: StoryNode 仓储（用于同步叙事结构）
        """
        self.novel_repository = novel_repository
        self.chapter_repository = chapter_repository
        self.story_node_repository = story_node_repository

    def _hydrate_chapters(self, novel: Novel) -> Novel:
        """用 Chapter 仓储补齐 DTO 所需章节列表。"""
        if self.chapter_repository is None:
            return novel
        try:
            chapters = self.chapter_repository.list_by_novel(novel.novel_id)
            if isinstance(chapters, list):
                novel.chapters = chapters
        except Exception:
            pass
        return novel

    def ensure_default_act_for_chapters(self, novel_id: str) -> None:
        """若无任何「幕」节点，创建默认第一幕，以便 add_chapter 能挂接章节到叙事结构树。"""
        if not self.story_node_repository:
            return
        tree = self.story_node_repository.get_tree_sync(novel_id)
        acts = [n for n in tree.nodes if n.node_type == NodeType.ACT]
        if acts:
            return
        act_node = StoryNode(
            id=f"act-{novel_id}-1",
            novel_id=novel_id,
            node_type=NodeType.ACT,
            number=1,
            title="第一幕",
            description="初始规划自动创建，可在结构视图中重命名",
            parent_id=None,
            order_index=0,
            planning_status=PlanningStatus.CONFIRMED,
            planning_source=PlanningSource.AI_MACRO,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        self.story_node_repository.save_sync(act_node)

    def create_novel(
        self,
        novel_id: str,
        title: str,
        author: str,
        target_chapters: int,
        premise: str = ""
    ) -> NovelDTO:
        """创建新小说

        Args:
            novel_id: 小说 ID
            title: 标题
            author: 作者
            target_chapters: 目标章节数
            premise: 故事梗概/创意

        Returns:
            NovelDTO
        """
        novel = Novel(
            id=NovelId(novel_id),
            title=title,
            author=author,
            target_chapters=target_chapters,
            premise=premise,
            stage=NovelStage.PLANNING
        )

        self.novel_repository.save(novel)

        return NovelDTO.from_domain(novel)

    def get_novel(self, novel_id: str) -> Optional[NovelDTO]:
        novel = self.novel_repository.get_by_id(NovelId(novel_id))

        if novel is None:
            return None

        dto = NovelDTO.from_domain(self._hydrate_chapters(novel))

        dto.has_bible = self._check_has_bible(novel_id)
        dto.has_outline = self._check_has_outline(novel_id)

        return dto

    def _check_has_bible(self, novel_id: str) -> bool:
        storage = getattr(self.novel_repository, "storage", None)
        if storage is not None and hasattr(storage, "exists"):
            try:
                return bool(storage.exists(f"novels/{novel_id}/bible.json"))
            except Exception:
                pass

        try:
            from infrastructure.persistence.database.sqlite_bible_repository import SqliteBibleRepository
            from infrastructure.persistence.database.connection import get_database
            bible_repo = SqliteBibleRepository(get_database())
            bible = bible_repo.get_by_novel_id(NovelId(novel_id))
            return bible is not None
        except Exception:
            return False

    def _check_has_outline(self, novel_id: str) -> bool:
        if not self.story_node_repository:
            return False
        try:
            tree = self.story_node_repository.get_tree_sync(novel_id)
            act_nodes = [n for n in tree.nodes if n.node_type == NodeType.ACT]
            return len(act_nodes) > 0
        except Exception:
            return False

    def list_novels(self) -> List[NovelDTO]:
        """列出所有小说

        Returns:
            NovelDTO 列表
        """
        novels = self.novel_repository.list_all()
        return [NovelDTO.from_domain(self._hydrate_chapters(novel)) for novel in novels]

    def delete_novel(self, novel_id: str) -> None:
        """删除小说

        Args:
            novel_id: 小说 ID
        """
        self.novel_repository.delete(NovelId(novel_id))

    def add_chapter(
        self,
        novel_id: str,
        chapter_id: str,
        number: int,
        title: str,
        content: str
    ) -> NovelDTO:
        """添加章节

        Args:
            novel_id: 小说 ID
            chapter_id: 章节 ID
            number: 章节编号
            title: 章节标题
            content: 章节内容

        Returns:
            更新后的 NovelDTO

        Raises:
            ValueError: 如果小说不存在或章节号不连续
        """
        novel = self.novel_repository.get_by_id(NovelId(novel_id))

        if novel is None:
            raise ValueError(f"Novel not found: {novel_id}")

        # 查询数据库中实际的章节数
        existing_chapters = self.chapter_repository.list_by_novel(NovelId(novel_id))
        if not isinstance(existing_chapters, list):
            existing_chapters = list(getattr(novel, "chapters", []) or [])
        expected_number = len(existing_chapters) + 1

        # 验证章节号是否连续
        if number != expected_number:
            raise ValueError(f"Chapter number must be {expected_number}, got {number}")

        chapter = Chapter(
            id=chapter_id,
            novel_id=NovelId(novel_id),
            number=number,
            title=title,
            content=content
        )

        # 直接保存章节，不通过Novel实体
        self.chapter_repository.save(chapter)
        if not any(getattr(c, "number", None) == chapter.number for c in novel.chapters):
            novel.chapters.append(chapter)
        self.novel_repository.save(novel)

        # 同步创建 StoryNode 章节节点，并关联到当前活跃的幕
        if self.story_node_repository:
            try:
                # 查找当前活跃的幕（最新的幕）
                tree = self.story_node_repository.get_tree_sync(novel_id)
                acts = [node for node in tree.nodes if node.node_type == NodeType.ACT]

                if acts:
                    # 获取最新的幕
                    current_act = max(acts, key=lambda x: x.number)

                    # 创建章节节点
                    chapter_node = StoryNode(
                        id=f"chapter-{novel_id}-{number}",
                        novel_id=novel_id,
                        node_type=NodeType.CHAPTER,
                        number=number,
                        title=title,
                        description="",
                        parent_id=current_act.id,  # 关联到当前幕
                        order_index=len(tree.nodes),
                        content=content,
                        word_count=len(content),
                        status="draft",
                        created_at=datetime.now(),
                        updated_at=datetime.now()
                    )

                    self.story_node_repository.save_sync(chapter_node)

                    # 更新幕的章节范围
                    children = self.story_node_repository.get_children_sync(current_act.id)
                    chapter_nodes = [node for node in children if node.node_type == NodeType.CHAPTER]
                    if chapter_nodes:
                        chapter_numbers = [node.number for node in chapter_nodes]
                        current_act.chapter_start = min(chapter_numbers)
                        current_act.chapter_end = max(chapter_numbers)
                        current_act.chapter_count = len(chapter_numbers)
                        self.story_node_repository.save_sync(current_act)

            except Exception as e:
                # 如果同步失败，不影响章节创建
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Failed to sync chapter to story structure: {e}")

        # 重新加载Novel以返回最新状态
        novel = self.novel_repository.get_by_id(NovelId(novel_id)) or novel
        return NovelDTO.from_domain(self._hydrate_chapters(novel))

    def update_novel(self, novel_id: str, title: Optional[str] = None, author: Optional[str] = None, 
                     target_chapters: Optional[int] = None, premise: Optional[str] = None) -> NovelDTO:
        """更新小说基本信息

        Args:
            novel_id: 小说 ID
            title: 小说标题（可选）
            author: 作者（可选）
            target_chapters: 目标章节数（可选）
            premise: 故事梗概/创意（可选）

        Returns:
            更新后的 NovelDTO

        Raises:
            EntityNotFoundError: 如果小说不存在
        """
        novel = self.novel_repository.get_by_id(NovelId(novel_id))
        if novel is None:
            raise EntityNotFoundError("Novel", novel_id)

        # 更新提供的字段
        if title is not None:
            novel.title = title
        if author is not None:
            novel.author = author
        if target_chapters is not None:
            novel.target_chapters = target_chapters
        if premise is not None:
            novel.premise = premise

        self.novel_repository.save(novel)
        return NovelDTO.from_domain(self._hydrate_chapters(novel))

    def update_novel_stage(self, novel_id: str, stage: str) -> NovelDTO:
        """更新小说阶段

        Args:
            novel_id: 小说 ID
            stage: 阶段

        Returns:
            更新后的 NovelDTO

        Raises:
            EntityNotFoundError: 如果小说不存在
        """
        novel = self.novel_repository.get_by_id(NovelId(novel_id))
        if novel is None:
            raise EntityNotFoundError("Novel", novel_id)

        novel.stage = NovelStage(stage)
        self.novel_repository.save(novel)

        return NovelDTO.from_domain(self._hydrate_chapters(novel))

    def update_auto_approve_mode(self, novel_id: str, auto_approve_mode: bool) -> NovelDTO:
        """更新全自动模式设置

        Args:
            novel_id: 小说 ID
            auto_approve_mode: 是否开启全自动模式

        Returns:
            更新后的 NovelDTO

        Raises:
            EntityNotFoundError: 如果小说不存在
        """
        novel = self.novel_repository.get_by_id(NovelId(novel_id))
        if novel is None:
            raise EntityNotFoundError("Novel", novel_id)

        novel.auto_approve_mode = auto_approve_mode
        self.novel_repository.save(novel)

        return NovelDTO.from_domain(self._hydrate_chapters(novel))

    def get_novel_statistics(self, novel_id: str) -> Dict[str, Any]:
        """获取小说统计信息（以 Chapter 仓储落盘为准，与列表/读写 API 一致）

        Args:
            novel_id: 小说 ID

        Returns:
            与前端顶栏 BookStats 对齐的字段；数据来源为 ``list_by_novel``，非 novel 聚合 JSON 内嵌章节。

        Raises:
            EntityNotFoundError: 如果小说不存在
        """
        novel = self.novel_repository.get_by_id(NovelId(novel_id))
        if novel is None:
            raise EntityNotFoundError("Novel", novel_id)

        chapters = self.chapter_repository.list_by_novel(NovelId(novel_id))
        total = len(chapters)
        total_words = sum(c.word_count.value for c in chapters)
        completed = sum(1 for c in chapters if c.word_count.value > 0)
        avg = total_words // total if total > 0 else 0
        completion = (completed / total) if total > 0 else 0.0

        return {
            "slug": novel_id,
            "title": novel.title,
            "total_chapters": total,
            "completed_chapters": completed,
            "total_words": total_words,
            "avg_chapter_words": avg,
            "completion_rate": completion,
            "stage": novel.stage.value,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
