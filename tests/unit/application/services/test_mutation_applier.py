"""Mutation Applier 单元测试"""
import pytest
from unittest.mock import Mock, MagicMock
from application.audit.services.mutation_applier import MutationApplier
from domain.novel.repositories.narrative_event_repository import NarrativeEventRepository


@pytest.fixture
def mock_event_repository():
    """Mock 事件仓储"""
    return Mock(spec=NarrativeEventRepository)


@pytest.fixture
def mutation_applier(mock_event_repository):
    """创建 MutationApplier 实例"""
    return MutationApplier(mock_event_repository)


@pytest.fixture
def sample_event():
    """示例事件"""
    return {
        "event_id": "event_001",
        "novel_id": "novel_001",
        "chapter": 1,
        "event_summary": "原始摘要",
        "tags": ["情感:同情"],
        "entities": []
    }


def test_apply_add_tag(mutation_applier, mock_event_repository, sample_event):
    """测试添加标签"""
    # Arrange
    mock_event_repository.get_event.return_value = sample_event
    mock_event_repository.update_event.return_value = None

    mutations = [{"type": "add_tag", "tag": "性格:冷酷"}]

    # Act
    result = mutation_applier.apply_mutations("novel_001", "event_001", mutations)

    # Assert
    assert result["success"] is True
    assert "情感:同情" in result["updated_event"]["tags"]
    assert "性格:冷酷" in result["updated_event"]["tags"]
    assert len(result["updated_event"]["tags"]) == 2


def test_apply_remove_tag(mutation_applier, mock_event_repository, sample_event):
    """测试移除标签"""
    # Arrange
    sample_event["tags"] = ["情感:同情", "性格:冷酷"]
    mock_event_repository.get_event.return_value = sample_event
    mock_event_repository.update_event.return_value = None

    mutations = [{"type": "remove_tag", "tag": "情感:同情"}]

    # Act
    result = mutation_applier.apply_mutations("novel_001", "event_001", mutations)

    # Assert
    assert result["success"] is True
    assert "情感:同情" not in result["updated_event"]["tags"]
    assert "性格:冷酷" in result["updated_event"]["tags"]
    assert len(result["updated_event"]["tags"]) == 1


def test_apply_replace_summary(mutation_applier, mock_event_repository, sample_event):
    """测试替换摘要"""
    # Arrange
    mock_event_repository.get_event.return_value = sample_event
    mock_event_repository.update_event.return_value = None

    mutations = [{"type": "replace_summary", "new_summary": "新摘要"}]

    # Act
    result = mutation_applier.apply_mutations("novel_001", "event_001", mutations)

    # Assert
    assert result["success"] is True
    assert result["updated_event"]["event_summary"] == "新摘要"


def test_apply_multiple_mutations(mutation_applier, mock_event_repository, sample_event):
    """测试应用多个 mutations"""
    # Arrange
    mock_event_repository.get_event.return_value = sample_event
    mock_event_repository.update_event.return_value = None

    mutations = [
        {"type": "add_tag", "tag": "性格:冷酷"},
        {"type": "replace_summary", "new_summary": "新摘要"},
        {"type": "add_tag", "tag": "动机:复仇"}
    ]

    # Act
    result = mutation_applier.apply_mutations("novel_001", "event_001", mutations)

    # Assert
    assert result["success"] is True
    assert result["updated_event"]["event_summary"] == "新摘要"
    assert "情感:同情" in result["updated_event"]["tags"]
    assert "性格:冷酷" in result["updated_event"]["tags"]
    assert "动机:复仇" in result["updated_event"]["tags"]
    assert len(result["applied_mutations"]) == 3


def test_apply_invalid_mutation_type(mutation_applier, mock_event_repository, sample_event):
    """测试无效的 mutation type"""
    # Arrange
    mock_event_repository.get_event.return_value = sample_event
    mock_event_repository.update_event.return_value = None

    mutations = [
        {"type": "add_tag", "tag": "性格:冷酷"},
        {"type": "invalid_type", "data": "some_data"},  # 无效类型
        {"type": "replace_summary", "new_summary": "新摘要"}
    ]

    # Act
    result = mutation_applier.apply_mutations("novel_001", "event_001", mutations)

    # Assert
    assert result["success"] is True
    assert "性格:冷酷" in result["updated_event"]["tags"]
    assert result["updated_event"]["event_summary"] == "新摘要"
    # 无效的 mutation 应该被跳过，只应用了 2 个有效的
    assert len(result["applied_mutations"]) == 2


def test_add_tag_deduplication(mutation_applier, mock_event_repository, sample_event):
    """测试添加标签时自动去重"""
    # Arrange
    sample_event["tags"] = ["情感:同情"]
    mock_event_repository.get_event.return_value = sample_event
    mock_event_repository.update_event.return_value = None

    mutations = [
        {"type": "add_tag", "tag": "情感:同情"},  # 重复标签
        {"type": "add_tag", "tag": "性格:冷酷"}
    ]

    # Act
    result = mutation_applier.apply_mutations("novel_001", "event_001", mutations)

    # Assert
    assert result["success"] is True
    assert result["updated_event"]["tags"].count("情感:同情") == 1  # 不重复
    assert "性格:冷酷" in result["updated_event"]["tags"]


def test_remove_nonexistent_tag(mutation_applier, mock_event_repository, sample_event):
    """测试移除不存在的标签（幂等性）"""
    # Arrange
    mock_event_repository.get_event.return_value = sample_event
    mock_event_repository.update_event.return_value = None

    mutations = [{"type": "remove_tag", "tag": "不存在的标签"}]

    # Act
    result = mutation_applier.apply_mutations("novel_001", "event_001", mutations)

    # Assert
    assert result["success"] is True
    assert result["updated_event"]["tags"] == ["情感:同情"]  # 保持不变


def test_apply_mutations_with_reason(mutation_applier, mock_event_repository, sample_event):
    """测试带原因的 mutation 应用"""
    # Arrange
    mock_event_repository.get_event.return_value = sample_event
    mock_event_repository.update_event.return_value = None

    mutations = [{"type": "add_tag", "tag": "性格:冷酷"}]
    reason = "修正人设冲突"

    # Act
    result = mutation_applier.apply_mutations("novel_001", "event_001", mutations, reason)

    # Assert
    assert result["success"] is True
    # reason 应该被记录（未来可扩展到 audit_log）
