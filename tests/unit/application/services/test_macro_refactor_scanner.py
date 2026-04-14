"""Macro Refactor Scanner 单元测试"""
import pytest
from unittest.mock import Mock
from application.audit.services.macro_refactor_scanner import MacroRefactorScanner
from application.audit.dtos.macro_refactor_dto import LogicBreakpoint


class TestMacroRefactorScanner:
    """MacroRefactorScanner 测试套件"""

    @pytest.fixture
    def mock_event_repo(self):
        """Mock NarrativeEventRepository"""
        return Mock()

    @pytest.fixture
    def scanner(self, mock_event_repo):
        """创建 MacroRefactorScanner 实例"""
        return MacroRefactorScanner(mock_event_repo)

    def test_scan_finds_conflicting_motivation(self, scanner, mock_event_repo):
        """测试：扫描找到冲突的动机标签"""
        # Arrange
        novel_id = "novel-123"
        mock_event_repo.list_up_to_chapter.return_value = [
            {
                "event_id": "event-1",
                "chapter_number": 1,
                "event_summary": "主角冲动行事",
                "tags": ["动机:冲动", "情绪:激动"],
                "mutations": []
            },
            {
                "event_id": "event-2",
                "chapter_number": 2,
                "event_summary": "主角愤怒爆发",
                "tags": ["情绪:愤怒", "行为:鲁莽"],
                "mutations": []
            },
            {
                "event_id": "event-3",
                "chapter_number": 3,
                "event_summary": "主角再次冲动",
                "tags": ["动机:冲动"],
                "mutations": []
            }
        ]

        # Act
        breakpoints = scanner.scan_breakpoints(novel_id, trait="冷酷")

        # Assert
        assert len(breakpoints) == 3
        assert all(isinstance(bp, LogicBreakpoint) for bp in breakpoints)
        assert breakpoints[0].event_id == "event-1"
        assert breakpoints[0].chapter == 1
        assert "冷酷" in breakpoints[0].reason
        assert "动机:冲动" in breakpoints[0].tags or "情绪:激动" in breakpoints[0].tags

        mock_event_repo.list_up_to_chapter.assert_called_once_with(novel_id, 999999)

    def test_scan_no_conflicts(self, scanner, mock_event_repo):
        """测试：无冲突事件时返回空列表"""
        # Arrange
        novel_id = "novel-123"
        mock_event_repo.list_up_to_chapter.return_value = [
            {
                "event_id": "event-1",
                "chapter_number": 1,
                "event_summary": "主角冷静分析",
                "tags": ["动机:理性", "情绪:冷静"],
                "mutations": []
            },
            {
                "event_id": "event-2",
                "chapter_number": 2,
                "event_summary": "主角谨慎行动",
                "tags": ["行为:谨慎"],
                "mutations": []
            }
        ]

        # Act
        breakpoints = scanner.scan_breakpoints(novel_id, trait="冷酷")

        # Assert
        assert len(breakpoints) == 0

    def test_scan_partial_match(self, scanner, mock_event_repo):
        """测试：部分事件冲突时只返回冲突的"""
        # Arrange
        novel_id = "novel-123"
        mock_event_repo.list_up_to_chapter.return_value = [
            {
                "event_id": "event-1",
                "chapter_number": 1,
                "event_summary": "主角冷静分析",
                "tags": ["动机:理性"],
                "mutations": []
            },
            {
                "event_id": "event-2",
                "chapter_number": 2,
                "event_summary": "主角冲动行事",
                "tags": ["动机:冲动"],
                "mutations": []
            },
            {
                "event_id": "event-3",
                "chapter_number": 3,
                "event_summary": "主角继续冷静",
                "tags": ["情绪:冷静"],
                "mutations": []
            }
        ]

        # Act
        breakpoints = scanner.scan_breakpoints(novel_id, trait="冷酷")

        # Assert
        assert len(breakpoints) == 1
        assert breakpoints[0].event_id == "event-2"
        assert breakpoints[0].chapter == 2

    def test_scan_empty_events(self, scanner, mock_event_repo):
        """测试：无事件时返回空列表"""
        # Arrange
        novel_id = "novel-123"
        mock_event_repo.list_up_to_chapter.return_value = []

        # Act
        breakpoints = scanner.scan_breakpoints(novel_id, trait="冷酷")

        # Assert
        assert len(breakpoints) == 0

    def test_scan_with_custom_conflict_tags(self, scanner, mock_event_repo):
        """测试：使用自定义冲突标签"""
        # Arrange
        novel_id = "novel-123"
        mock_event_repo.list_up_to_chapter.return_value = [
            {
                "event_id": "event-1",
                "chapter_number": 1,
                "event_summary": "主角感性决策",
                "tags": ["动机:感性"],
                "mutations": []
            },
            {
                "event_id": "event-2",
                "chapter_number": 2,
                "event_summary": "主角激动表现",
                "tags": ["情绪:激动"],
                "mutations": []
            }
        ]

        # Act
        breakpoints = scanner.scan_breakpoints(
            novel_id,
            trait="理性",
            conflict_tags=["动机:感性", "情绪:激动"]
        )

        # Assert
        assert len(breakpoints) == 2
        assert breakpoints[0].event_id == "event-1"
        assert breakpoints[1].event_id == "event-2"
