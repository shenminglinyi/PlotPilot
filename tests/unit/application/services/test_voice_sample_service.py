"""Unit tests for VoiceSampleService"""
import json
import pytest
from unittest.mock import Mock, MagicMock
from application.analyst.services.voice_sample_service import VoiceSampleService


class TestVoiceSampleService:
    """VoiceSampleService 单元测试"""

    @pytest.fixture
    def mock_repository(self):
        """Mock VoiceVaultRepository"""
        return Mock()

    @pytest.fixture
    def service(self, mock_repository):
        """创建 VoiceSampleService 实例"""
        return VoiceSampleService(mock_repository)

    def test_append_sample_calculates_diff(self, service, mock_repository):
        """测试 append_sample 计算差异分析"""
        # Arrange
        novel_id = "novel-123"
        chapter_number = 1
        scene_type = "dialogue"
        ai_original = "这是AI生成的原文。"
        author_refined = "这是作者修改后的文本。"
        mock_repository.append_sample.return_value = "sample-456"

        # Act
        sample_id = service.append_sample(
            novel_id=novel_id,
            chapter_number=chapter_number,
            scene_type=scene_type,
            ai_original=ai_original,
            author_refined=author_refined
        )

        # Assert
        assert sample_id == "sample-456"
        mock_repository.append_sample.assert_called_once()

        # 验证调用参数
        call_args = mock_repository.append_sample.call_args
        assert call_args[1]['novel_id'] == novel_id
        assert call_args[1]['chapter_number'] == chapter_number
        assert call_args[1]['scene_type'] == scene_type
        assert call_args[1]['ai_original'] == ai_original
        assert call_args[1]['author_refined'] == author_refined

        # 验证 diff_analysis 是有效的 JSON
        diff_json = call_args[1]['diff_analysis']
        diff_data = json.loads(diff_json)
        assert 'edit_distance' in diff_data
        assert 'similarity_ratio' in diff_data
        assert 'original_length' in diff_data
        assert 'refined_length' in diff_data
        assert diff_data['original_length'] == len(ai_original)
        assert diff_data['refined_length'] == len(author_refined)

    def test_append_sample_calls_repository(self, service, mock_repository):
        """测试 append_sample 调用仓储"""
        # Arrange
        mock_repository.append_sample.return_value = "sample-789"

        # Act
        sample_id = service.append_sample(
            novel_id="novel-001",
            chapter_number=5,
            scene_type=None,
            ai_original="Original text",
            author_refined="Refined text"
        )

        # Assert
        assert sample_id == "sample-789"
        mock_repository.append_sample.assert_called_once()

    def test_append_sample_returns_sample_id(self, service, mock_repository):
        """测试 append_sample 返回样本 ID"""
        # Arrange
        expected_id = "sample-xyz"
        mock_repository.append_sample.return_value = expected_id

        # Act
        result = service.append_sample(
            novel_id="novel-999",
            chapter_number=10,
            scene_type="action",
            ai_original="Test original",
            author_refined="Test refined"
        )

        # Assert
        assert result == expected_id

    def test_calculate_diff_analysis_identical_texts(self, service):
        """测试相同文本的差异分析"""
        # Arrange
        text = "完全相同的文本"

        # Act
        diff = service._calculate_diff_analysis(text, text)

        # Assert
        assert diff['edit_distance'] == 0
        assert diff['similarity_ratio'] == 1.0
        assert diff['original_length'] == len(text)
        assert diff['refined_length'] == len(text)
        assert diff['added_chars'] == 0
        assert diff['removed_chars'] == 0
        assert diff['length_change'] == 0

    def test_calculate_diff_analysis_different_texts(self, service):
        """测试不同文本的差异分析"""
        # Arrange
        original = "短文本"
        refined = "这是一个更长的修改后的文本"

        # Act
        diff = service._calculate_diff_analysis(original, refined)

        # Assert
        assert diff['edit_distance'] > 0
        assert diff['similarity_ratio'] < 1.0
        assert diff['original_length'] == len(original)
        assert diff['refined_length'] == len(refined)
        assert diff['added_chars'] > 0
        assert diff['length_change'] > 0

    def test_levenshtein_distance_empty_strings(self, service):
        """测试空字符串的编辑距离"""
        assert service._levenshtein_distance("", "") == 0
        assert service._levenshtein_distance("abc", "") == 3
        assert service._levenshtein_distance("", "xyz") == 3

    def test_levenshtein_distance_identical(self, service):
        """测试相同字符串的编辑距离"""
        assert service._levenshtein_distance("hello", "hello") == 0

    def test_levenshtein_distance_single_char_diff(self, service):
        """测试单字符差异的编辑距离"""
        assert service._levenshtein_distance("hello", "hallo") == 1
        assert service._levenshtein_distance("hello", "hell") == 1
        assert service._levenshtein_distance("hello", "helloo") == 1
