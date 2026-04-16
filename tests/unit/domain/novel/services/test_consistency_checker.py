import pytest
from domain.novel.services.consistency_checker import ConsistencyChecker
from domain.novel.value_objects.consistency_context import ConsistencyContext
from domain.novel.value_objects.consistency_report import IssueType, Severity
from domain.novel.value_objects.chapter_state import ChapterState
from domain.bible.entities.bible import Bible
from domain.bible.entities.character import Character
from domain.bible.entities.character_registry import CharacterRegistry
from domain.bible.value_objects.character_id import CharacterId
from domain.novel.entities.foreshadowing_registry import ForeshadowingRegistry
from domain.novel.entities.plot_arc import PlotArc
from domain.novel.value_objects.event_timeline import EventTimeline
from domain.bible.value_objects.relationship_graph import RelationshipGraph
from domain.bible.value_objects.relationship import Relationship, RelationType
from domain.novel.value_objects.novel_id import NovelId
from domain.novel.value_objects.foreshadowing import (
    Foreshadowing,
    ForeshadowingStatus,
    ImportanceLevel
)


class TestConsistencyChecker:
    """测试 ConsistencyChecker 领域服务"""

    def setup_method(self):
        """设置测试环境"""
        self.novel_id = NovelId("novel-1")
        self.bible = Bible(id="bible-1", novel_id=self.novel_id)
        self.character_registry = CharacterRegistry(id="registry-1", novel_id="novel-1")
        self.foreshadowing_registry = ForeshadowingRegistry(id="foreshadow-1", novel_id=self.novel_id)
        self.plot_arc = PlotArc(id="arc-1", novel_id=self.novel_id)
        self.event_timeline = EventTimeline()
        self.relationship_graph = RelationshipGraph()

        self.context = ConsistencyContext(
            bible=self.bible,
            character_registry=self.character_registry,
            foreshadowing_registry=self.foreshadowing_registry,
            plot_arc=self.plot_arc,
            event_timeline=self.event_timeline,
            relationship_graph=self.relationship_graph
        )

        self.checker = ConsistencyChecker()

    def test_check_character_consistency_no_issues(self):
        """测试角色一致性检查 - 无问题"""
        char_id = CharacterId("char-1")
        character = Character(
            id=char_id,
            name="张三",
            description="勇敢的战士"
        )
        self.bible.add_character(character)

        issues = self.checker.check_character_consistency(
            character_id="char-1",
            action="勇敢地冲向敌人",
            context=self.context
        )

        assert len(issues) == 0

    def test_check_character_consistency_character_not_found(self):
        """测试角色一致性检查 - 角色不存在"""
        issues = self.checker.check_character_consistency(
            character_id="nonexistent",
            action="做了某事",
            context=self.context
        )

        assert len(issues) == 1
        assert issues[0].type == IssueType.CHARACTER_INCONSISTENCY
        assert issues[0].severity == Severity.CRITICAL
        assert "not found" in issues[0].description.lower()

    def test_check_relationship_consistency_no_issues(self):
        """测试关系一致性检查 - 无问题"""
        char1_id = CharacterId("char-1")
        char2_id = CharacterId("char-2")

        char1 = Character(id=char1_id, name="张三", description="主角")
        char2 = Character(id=char2_id, name="李四", description="朋友")

        self.bible.add_character(char1)
        self.bible.add_character(char2)

        # 添加现有关系
        relation = Relationship(
            relation_type=RelationType.FRIEND,
            established_in_chapter=1,
            description="好朋友"
        )
        self.relationship_graph.add_relationship(char1_id, char2_id, relation)

        issues = self.checker.check_relationship_consistency(
            char1="char-1",
            char2="char-2",
            new_relation="friend",
            context=self.context
        )

        assert len(issues) == 0

    def test_check_relationship_consistency_character_not_found(self):
        """测试关系一致性检查 - 角色不存在"""
        issues = self.checker.check_relationship_consistency(
            char1="nonexistent",
            char2="char-2",
            new_relation="friend",
            context=self.context
        )

        assert len(issues) >= 1
        assert any(issue.type == IssueType.RELATIONSHIP_INCONSISTENCY for issue in issues)
        assert any(issue.severity == Severity.CRITICAL for issue in issues)

    def test_check_event_logic_no_issues(self):
        """测试事件逻辑检查 - 无问题"""
        char_id = CharacterId("char-1")
        character = Character(id=char_id, name="张三", description="主角")
        self.bible.add_character(character)

        event = {
            "type": "conflict",
            "description": "主角与敌人战斗",
            "involved_characters": ["char-1"],
            "chapter": 5
        }

        issues = self.checker.check_event_logic(
            event=event,
            context=self.context
        )

        assert len(issues) == 0

    def test_check_event_logic_character_not_found(self):
        """测试事件逻辑检查 - 涉及的角色不存在"""
        event = {
            "type": "conflict",
            "description": "战斗",
            "involved_characters": ["nonexistent"],
            "chapter": 5
        }

        issues = self.checker.check_event_logic(
            event=event,
            context=self.context
        )

        assert len(issues) >= 1
        assert any(issue.type == IssueType.EVENT_LOGIC_ERROR for issue in issues)

    def test_check_foreshadowing_no_issues(self):
        """测试伏笔检查 - 无问题"""
        foreshadowing = Foreshadowing(
            id="f-1",
            planted_in_chapter=1,
            description="神秘预言",
            importance=ImportanceLevel.HIGH,
            status=ForeshadowingStatus.PLANTED
        )
        self.foreshadowing_registry.register(foreshadowing)

        issues = self.checker.check_foreshadowing(
            foreshadowing_id="f-1",
            context=self.context
        )

        assert len(issues) == 0

    def test_check_foreshadowing_not_found(self):
        """测试伏笔检查 - 伏笔不存在"""
        issues = self.checker.check_foreshadowing(
            foreshadowing_id="nonexistent",
            context=self.context
        )

        assert len(issues) == 1
        assert issues[0].type == IssueType.FORESHADOWING_ERROR
        assert issues[0].severity == Severity.CRITICAL

    def test_check_all_empty_state(self):
        """测试完整检查 - 空状态"""
        chapter_state = ChapterState(
            new_characters=[],
            character_actions=[],
            relationship_changes=[],
            foreshadowing_planted=[],
            foreshadowing_resolved=[],
            events=[]
        )

        report = self.checker.check_all(
            chapter_state=chapter_state,
            context=self.context
        )

        assert len(report.issues) == 0
        assert len(report.warnings) == 0

    def test_check_all_with_character_actions(self):
        """测试完整检查 - 包含角色行为"""
        char_id = CharacterId("char-1")
        character = Character(id=char_id, name="张三", description="主角")
        self.bible.add_character(character)

        chapter_state = ChapterState(
            new_characters=[],
            character_actions=[
                {
                    "character_id": "char-1",
                    "action": "做出决定",
                    "chapter": 5
                }
            ],
            relationship_changes=[],
            foreshadowing_planted=[],
            foreshadowing_resolved=[],
            events=[]
        )

        report = self.checker.check_all(
            chapter_state=chapter_state,
            context=self.context
        )

        assert len(report.issues) == 0

    def test_check_all_with_issues(self):
        """测试完整检查 - 包含问题"""
        chapter_state = ChapterState(
            new_characters=[],
            character_actions=[
                {
                    "character_id": "nonexistent",
                    "action": "做出决定",
                    "chapter": 5
                }
            ],
            relationship_changes=[],
            foreshadowing_planted=[],
            foreshadowing_resolved=[],
            events=[]
        )

        report = self.checker.check_all(
            chapter_state=chapter_state,
            context=self.context
        )

        assert len(report.issues) > 0
        assert report.has_critical_issues()

    def test_check_all_resolved_foreshadowing_by_description(self):
        """测试完整检查可通过描述匹配已存在伏笔。"""
        self.foreshadowing_registry.register(
            Foreshadowing(
                id="f-1",
                planted_in_chapter=3,
                description="衣物被更换",
                importance=ImportanceLevel.MEDIUM,
                status=ForeshadowingStatus.PLANTED,
            )
        )

        chapter_state = ChapterState(
            new_characters=[],
            character_actions=[],
            relationship_changes=[],
            foreshadowing_planted=[],
            foreshadowing_resolved=[{"foreshadowing_id": "衣物被更换", "chapter": 5}],
            events=[],
        )

        report = self.checker.check_all(
            chapter_state=chapter_state,
            context=self.context
        )

        assert len(report.issues) == 0

    def test_check_all_ambiguous_foreshadowing_description_reports_issue(self):
        """歧义描述不应自动命中第一条伏笔。"""
        self.foreshadowing_registry.register(
            Foreshadowing(
                id="f-1",
                planted_in_chapter=3,
                description="衣物被更换",
                importance=ImportanceLevel.MEDIUM,
                status=ForeshadowingStatus.PLANTED,
            )
        )
        self.foreshadowing_registry.register(
            Foreshadowing(
                id="f-2",
                planted_in_chapter=4,
                description="衣物被更换后袖口有血",
                importance=ImportanceLevel.HIGH,
                status=ForeshadowingStatus.PLANTED,
            )
        )

        chapter_state = ChapterState(
            new_characters=[],
            character_actions=[],
            relationship_changes=[],
            foreshadowing_planted=[],
            foreshadowing_resolved=[{"foreshadowing_id": "衣物被更换后", "chapter": 5}],
            events=[],
        )

        report = self.checker.check_all(
            chapter_state=chapter_state,
            context=self.context
        )

        assert len(report.issues) == 1
        assert report.issues[0].type == IssueType.FORESHADOWING_ERROR
