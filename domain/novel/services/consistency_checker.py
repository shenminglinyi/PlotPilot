from typing import List, Dict, Any
from domain.novel.value_objects.consistency_context import ConsistencyContext
from domain.novel.value_objects.consistency_report import (
    ConsistencyReport,
    Issue,
    IssueType,
    Severity
)
from domain.novel.value_objects.chapter_state import ChapterState
from domain.bible.value_objects.character_id import CharacterId


class ConsistencyChecker:
    """一致性检查领域服务

    提供多维度的一致性验证功能
    """

    def check_character_consistency(
        self,
        character_id: str,
        action: str,
        context: ConsistencyContext
    ) -> List[Issue]:
        """检查角色行为一致性

        Args:
            character_id: 角色ID
            action: 角色行为描述
            context: 一致性检查上下文

        Returns:
            问题列表
        """
        issues = []

        # 检查角色是否存在
        char_id = CharacterId(character_id)
        character = context.bible.get_character(char_id)

        if character is None:
            issues.append(Issue(
                type=IssueType.CHARACTER_INCONSISTENCY,
                severity=Severity.CRITICAL,
                description=f"Character '{character_id}' not found in Bible",
                location=1  # 默认位置，实际使用时应传入章节号
            ))

        return issues

    def check_relationship_consistency(
        self,
        char1: str,
        char2: str,
        new_relation: str,
        context: ConsistencyContext
    ) -> List[Issue]:
        """检查关系变化一致性

        Args:
            char1: 角色1 ID
            char2: 角色2 ID
            new_relation: 新关系类型
            context: 一致性检查上下文

        Returns:
            问题列表
        """
        issues = []

        # 检查两个角色是否都存在
        char1_id = CharacterId(char1)
        char2_id = CharacterId(char2)

        character1 = context.bible.get_character(char1_id)
        character2 = context.bible.get_character(char2_id)

        if character1 is None:
            issues.append(Issue(
                type=IssueType.RELATIONSHIP_INCONSISTENCY,
                severity=Severity.CRITICAL,
                description=f"Character '{char1}' not found in Bible",
                location=1
            ))

        if character2 is None:
            issues.append(Issue(
                type=IssueType.RELATIONSHIP_INCONSISTENCY,
                severity=Severity.CRITICAL,
                description=f"Character '{char2}' not found in Bible",
                location=1
            ))

        return issues

    def check_event_logic(
        self,
        event: Dict[str, Any],
        context: ConsistencyContext
    ) -> List[Issue]:
        """检查事件逻辑一致性

        Args:
            event: 事件字典
            context: 一致性检查上下文

        Returns:
            问题列表
        """
        issues = []

        # 检查涉及的角色是否都存在
        involved_characters = event.get("involved_characters", [])
        for char_id_str in involved_characters:
            char_id = CharacterId(char_id_str)
            character = context.bible.get_character(char_id)

            if character is None:
                issues.append(Issue(
                    type=IssueType.EVENT_LOGIC_ERROR,
                    severity=Severity.IMPORTANT,
                    description=f"Event involves unknown character '{char_id_str}'",
                    location=event.get("chapter", 1)
                ))

        return issues

    def check_foreshadowing(
        self,
        foreshadowing_id: str,
        context: ConsistencyContext
    ) -> List[Issue]:
        """检查伏笔一致性

        Args:
            foreshadowing_id: 伏笔ID
            context: 一致性检查上下文

        Returns:
            问题列表
        """
        issues = []

        # 检查伏笔是否存在
        foreshadowing = context.foreshadowing_registry.get_by_id(foreshadowing_id)

        if foreshadowing is None:
            issues.append(Issue(
                type=IssueType.FORESHADOWING_ERROR,
                severity=Severity.CRITICAL,
                description=f"Foreshadowing '{foreshadowing_id}' not found in registry",
                location=1
            ))

        return issues

    def resolve_foreshadowing_reference(
        self,
        resolved_data: Dict[str, Any],
        context: ConsistencyContext,
    ) -> str:
        """兼容 LLM 只返回伏笔描述而非持久化 ID 的情况。"""
        fid = str(resolved_data.get("foreshadowing_id", "")).strip()
        if fid and context.foreshadowing_registry.get_by_id(fid):
            return fid

        description = str(
            resolved_data.get("description")
            or resolved_data.get("foreshadowing_description")
            or resolved_data.get("resolved_foreshadowing")
            or fid
            or ""
        ).strip().lower()
        if not description:
            return fid

        exact_match = None
        fuzzy_match = None
        for foreshadowing in context.foreshadowing_registry.foreshadowings:
            candidate = (foreshadowing.description or "").strip().lower()
            if not candidate:
                continue
            if candidate == description:
                exact_match = foreshadowing.id
                break
            if description in candidate or candidate in description:
                fuzzy_match = fuzzy_match or foreshadowing.id

        return exact_match or fuzzy_match or fid

    def check_all(
        self,
        chapter_state: ChapterState,
        context: ConsistencyContext
    ) -> ConsistencyReport:
        """执行完整的一致性检查

        Args:
            chapter_state: 章节状态
            context: 一致性检查上下文

        Returns:
            一致性检查报告
        """
        all_issues = []
        all_warnings = []
        suggestions = []

        # 检查角色行为
        for action in chapter_state.character_actions:
            issues = self.check_character_consistency(
                character_id=action["character_id"],
                action=action["action"],
                context=context
            )
            all_issues.extend(issues)

        # 检查关系变化
        for rel_change in chapter_state.relationship_changes:
            issues = self.check_relationship_consistency(
                char1=rel_change["char1"],
                char2=rel_change["char2"],
                new_relation=rel_change["new_type"],
                context=context
            )
            all_issues.extend(issues)

        # 检查事件
        for event in chapter_state.events:
            issues = self.check_event_logic(
                event=event,
                context=context
            )
            all_issues.extend(issues)

        # 检查伏笔解决
        for resolved in chapter_state.foreshadowing_resolved:
            issues = self.check_foreshadowing(
                foreshadowing_id=self.resolve_foreshadowing_reference(resolved, context),
                context=context
            )
            all_issues.extend(issues)

        return ConsistencyReport(
            issues=all_issues,
            warnings=all_warnings,
            suggestions=suggestions
        )
