import pytest
from unittest.mock import Mock, AsyncMock
from application.analyst.services.state_extractor import StateExtractor
from application.analyst.services.state_updater import StateUpdater
from domain.novel.services.consistency_checker import ConsistencyChecker
from domain.novel.value_objects.consistency_context import ConsistencyContext
from domain.ai.services.llm_service import LLMService, GenerationResult
from domain.ai.value_objects.token_usage import TokenUsage
from domain.bible.entities.bible import Bible
from domain.bible.entities.character import Character
from domain.bible.entities.character_registry import CharacterRegistry
from domain.bible.value_objects.character_id import CharacterId
from domain.novel.entities.foreshadowing_registry import ForeshadowingRegistry
from domain.novel.entities.plot_arc import PlotArc
from domain.novel.value_objects.event_timeline import EventTimeline
from domain.bible.value_objects.relationship_graph import RelationshipGraph
from domain.novel.value_objects.novel_id import NovelId
from domain.bible.repositories.bible_repository import BibleRepository
from domain.novel.repositories.foreshadowing_repository import ForeshadowingRepository


class TestConsistencyCheckingEndToEnd:
    """端到端一致性检查测试"""

    def setup_method(self):
        """设置测试环境"""
        # 创建 mock repositories
        self.bible_repository = Mock(spec=BibleRepository)
        self.foreshadowing_repository = Mock(spec=ForeshadowingRepository)

        # 创建 mock LLM service
        self.llm_service = Mock(spec=LLMService)

        # 创建服务
        self.extractor = StateExtractor(llm_service=self.llm_service)
        self.updater = StateUpdater(
            bible_repository=self.bible_repository,
            foreshadowing_repository=self.foreshadowing_repository
        )
        self.checker = ConsistencyChecker()

        # 创建测试数据
        self.novel_id = NovelId("novel-1")
        self.bible = Bible(id="bible-1", novel_id=self.novel_id)
        self.character_registry = CharacterRegistry(id="registry-1", novel_id="novel-1")
        self.foreshadowing_registry = ForeshadowingRegistry(id="foreshadow-1", novel_id=self.novel_id)
        self.plot_arc = PlotArc(id="arc-1", novel_id=self.novel_id)
        self.event_timeline = EventTimeline()
        self.relationship_graph = RelationshipGraph()

    @pytest.mark.asyncio
    async def test_full_workflow_with_new_character(self):
        """测试完整工作流 - 新角色"""
        # 1. 提取章节状态
        content = "张三是一个勇敢的战士，第一次出现在第5章。"

        self.llm_service.generate = AsyncMock(return_value=GenerationResult(
            content='{"new_characters": [{"name": "张三", "description": "勇敢的战士", "first_appearance": 5}], "character_actions": [], "relationship_changes": [], "foreshadowing_planted": [], "foreshadowing_resolved": [], "events": []}',
            token_usage=TokenUsage(input_tokens=100, output_tokens=50)
        ))

        chapter_state = await self.extractor.extract_chapter_state(content=content)

        # 2. 更新状态
        self.bible_repository.get_by_novel_id.return_value = self.bible
        self.foreshadowing_repository.get_by_novel_id.return_value = self.foreshadowing_registry

        self.updater.update_from_chapter(
            novel_id="novel-1",
            chapter_number=5,
            chapter_state=chapter_state
        )

        # 3. 一致性检查
        context = ConsistencyContext(
            bible=self.bible,
            character_registry=self.character_registry,
            foreshadowing_registry=self.foreshadowing_registry,
            plot_arc=self.plot_arc,
            event_timeline=self.event_timeline,
            relationship_graph=self.relationship_graph
        )

        report = self.checker.check_all(
            chapter_state=chapter_state,
            context=context
        )

        # 验证结果
        assert len(chapter_state.new_characters) == 1
        assert self.bible_repository.save.called
        assert len(report.issues) == 0  # 新角色不应该有问题

    @pytest.mark.asyncio
    async def test_full_workflow_with_character_action_inconsistency(self):
        """测试完整工作流 - 角色行为不一致"""
        # 1. 提取章节状态（包含不存在的角色）
        content = "不存在的角色做了某事。"

        self.llm_service.generate = AsyncMock(return_value=GenerationResult(
            content='{"new_characters": [], "character_actions": [{"character_id": "nonexistent", "action": "做了某事", "chapter": 5}], "relationship_changes": [], "foreshadowing_planted": [], "foreshadowing_resolved": [], "events": []}',
            token_usage=TokenUsage(input_tokens=100, output_tokens=50)
        ))

        chapter_state = await self.extractor.extract_chapter_state(content=content)

        # 2. 一致性检查（不更新状态，因为有问题）
        context = ConsistencyContext(
            bible=self.bible,
            character_registry=self.character_registry,
            foreshadowing_registry=self.foreshadowing_registry,
            plot_arc=self.plot_arc,
            event_timeline=self.event_timeline,
            relationship_graph=self.relationship_graph
        )

        report = self.checker.check_all(
            chapter_state=chapter_state,
            context=context
        )

        # 验证结果
        assert len(report.issues) > 0
        assert report.has_critical_issues()
        assert any("not found" in issue.description.lower() for issue in report.issues)

    @pytest.mark.asyncio
    async def test_full_workflow_with_foreshadowing(self):
        """测试完整工作流 - 伏笔"""
        # 1. 提取章节状态（埋下伏笔）
        content = "一个神秘的预言被提及。"

        self.llm_service.generate = AsyncMock(return_value=GenerationResult(
            content='{"new_characters": [], "character_actions": [], "relationship_changes": [], "foreshadowing_planted": [{"description": "神秘的预言", "chapter": 5}], "foreshadowing_resolved": [], "events": []}',
            token_usage=TokenUsage(input_tokens=100, output_tokens=50)
        ))

        chapter_state = await self.extractor.extract_chapter_state(content=content)

        # 2. 更新状态
        self.bible_repository.get_by_novel_id.return_value = self.bible
        self.foreshadowing_repository.get_by_novel_id.return_value = self.foreshadowing_registry

        self.updater.update_from_chapter(
            novel_id="novel-1",
            chapter_number=5,
            chapter_state=chapter_state
        )

        # 3. 一致性检查
        context = ConsistencyContext(
            bible=self.bible,
            character_registry=self.character_registry,
            foreshadowing_registry=self.foreshadowing_registry,
            plot_arc=self.plot_arc,
            event_timeline=self.event_timeline,
            relationship_graph=self.relationship_graph
        )

        report = self.checker.check_all(
            chapter_state=chapter_state,
            context=context
        )

        # 验证结果
        assert len(chapter_state.foreshadowing_planted) == 1
        assert self.foreshadowing_repository.save.called
        assert len(report.issues) == 0

    @pytest.mark.asyncio
    async def test_full_workflow_with_complex_chapter(self):
        """测试完整工作流 - 复杂章节"""
        # 先添加一个角色到 Bible
        char_id = CharacterId("char-1")
        character = Character(id=char_id, name="张三", description="主角")
        self.bible.add_character(character)

        # 1. 提取章节状态（包含多种元素）
        content = """
        第五章：新的开始

        张三做出了重要决定。
        一个神秘的预言被提及。
        """

        self.llm_service.generate = AsyncMock(return_value=GenerationResult(
            content='{"new_characters": [], "character_actions": [{"character_id": "char-1", "action": "做出了重要决定", "chapter": 5}], "relationship_changes": [], "foreshadowing_planted": [{"description": "神秘的预言", "chapter": 5}], "foreshadowing_resolved": [], "events": []}',
            token_usage=TokenUsage(input_tokens=200, output_tokens=100)
        ))

        chapter_state = await self.extractor.extract_chapter_state(content=content)

        # 2. 更新状态
        self.bible_repository.get_by_novel_id.return_value = self.bible
        self.foreshadowing_repository.get_by_novel_id.return_value = self.foreshadowing_registry

        self.updater.update_from_chapter(
            novel_id="novel-1",
            chapter_number=5,
            chapter_state=chapter_state
        )

        # 3. 一致性检查
        context = ConsistencyContext(
            bible=self.bible,
            character_registry=self.character_registry,
            foreshadowing_registry=self.foreshadowing_registry,
            plot_arc=self.plot_arc,
            event_timeline=self.event_timeline,
            relationship_graph=self.relationship_graph
        )

        report = self.checker.check_all(
            chapter_state=chapter_state,
            context=context
        )

        # 验证结果
        assert len(chapter_state.character_actions) == 1
        assert len(chapter_state.foreshadowing_planted) == 1
        assert self.foreshadowing_repository.save.called
        assert len(report.issues) == 0  # 应该没有问题

    @pytest.mark.asyncio
    async def test_workflow_prevents_update_on_critical_issues(self):
        """测试工作流 - 有严重问题时阻止更新"""
        # 1. 提取章节状态（包含不存在的角色）
        content = "不存在的角色做了某事。"

        self.llm_service.generate = AsyncMock(return_value=GenerationResult(
            content='{"new_characters": [], "character_actions": [{"character_id": "nonexistent", "action": "做了某事", "chapter": 5}], "relationship_changes": [], "foreshadowing_planted": [], "foreshadowing_resolved": [], "events": []}',
            token_usage=TokenUsage(input_tokens=100, output_tokens=50)
        ))

        chapter_state = await self.extractor.extract_chapter_state(content=content)

        # 2. 一致性检查
        context = ConsistencyContext(
            bible=self.bible,
            character_registry=self.character_registry,
            foreshadowing_registry=self.foreshadowing_registry,
            plot_arc=self.plot_arc,
            event_timeline=self.event_timeline,
            relationship_graph=self.relationship_graph
        )

        report = self.checker.check_all(
            chapter_state=chapter_state,
            context=context
        )

        # 3. 如果有严重问题，不应该更新
        if report.has_critical_issues():
            # 不调用 updater
            pass
        else:
            self.updater.update_from_chapter(
                novel_id="novel-1",
                chapter_number=5,
                chapter_state=chapter_state
            )

        # 验证结果
        assert report.has_critical_issues()
        assert not self.bible_repository.save.called
        assert not self.foreshadowing_repository.save.called
