"""GhostAnnotation DTO 单元测试"""
import pytest
from application.audit.dtos.ghost_annotation import GhostAnnotation


class TestGhostAnnotation:
    """测试 GhostAnnotation DTO"""

    def test_create_ghost_annotation_success(self):
        """测试成功创建幽灵批注"""
        annotation = GhostAnnotation(
            type="setting_conflict",
            severity="warning",
            message="设定库中李明为 [水系]，此处使用了 [火系]",
            entity_id="char-001",
            entity_name="李明",
            expected="水系",
            actual="火系"
        )

        assert annotation.type == "setting_conflict"
        assert annotation.severity == "warning"
        assert annotation.message == "设定库中李明为 [水系]，此处使用了 [火系]"
        assert annotation.entity_id == "char-001"
        assert annotation.entity_name == "李明"
        assert annotation.expected == "水系"
        assert annotation.actual == "火系"

    def test_create_ghost_annotation_minimal(self):
        """测试创建最小字段的批注"""
        annotation = GhostAnnotation(
            type="other",
            severity="info",
            message="提示信息"
        )

        assert annotation.type == "other"
        assert annotation.severity == "info"
        assert annotation.message == "提示信息"
        assert annotation.entity_id is None
        assert annotation.entity_name is None
        assert annotation.expected is None
        assert annotation.actual is None

    def test_create_ghost_annotation_empty_type(self):
        """测试空 type 抛出异常"""
        with pytest.raises(ValueError, match="type cannot be empty"):
            GhostAnnotation(
                type="",
                severity="warning",
                message="测试"
            )

    def test_create_ghost_annotation_empty_severity(self):
        """测试空 severity 抛出异常"""
        with pytest.raises(ValueError, match="severity cannot be empty"):
            GhostAnnotation(
                type="setting_conflict",
                severity="",
                message="测试"
            )

    def test_create_ghost_annotation_empty_message(self):
        """测试空 message 抛出异常"""
        with pytest.raises(ValueError, match="message cannot be empty"):
            GhostAnnotation(
                type="setting_conflict",
                severity="warning",
                message=""
            )

    def test_create_ghost_annotation_invalid_type(self):
        """测试无效的 type"""
        with pytest.raises(ValueError, match="type must be one of"):
            GhostAnnotation(
                type="invalid_type",
                severity="warning",
                message="测试"
            )

    def test_create_ghost_annotation_invalid_severity(self):
        """测试无效的 severity"""
        with pytest.raises(ValueError, match="severity must be one of"):
            GhostAnnotation(
                type="setting_conflict",
                severity="critical",
                message="测试"
            )

    def test_to_dict(self):
        """测试转换为字典"""
        annotation = GhostAnnotation(
            type="setting_conflict",
            severity="warning",
            message="测试消息",
            entity_id="char-001",
            entity_name="李明",
            expected="水系",
            actual="火系"
        )

        result = annotation.to_dict()

        assert result == {
            "type": "setting_conflict",
            "severity": "warning",
            "message": "测试消息",
            "entity_id": "char-001",
            "entity_name": "李明",
            "expected": "水系",
            "actual": "火系"
        }

    def test_to_dict_with_none_values(self):
        """测试包含 None 值的字典转换"""
        annotation = GhostAnnotation(
            type="other",
            severity="info",
            message="测试"
        )

        result = annotation.to_dict()

        assert result == {
            "type": "other",
            "severity": "info",
            "message": "测试",
            "entity_id": None,
            "entity_name": None,
            "expected": None,
            "actual": None
        }

    def test_ghost_annotation_is_frozen(self):
        """测试 GhostAnnotation 是不可变的"""
        annotation = GhostAnnotation(
            type="setting_conflict",
            severity="warning",
            message="测试"
        )

        with pytest.raises(Exception):  # dataclass frozen=True 会抛出异常
            annotation.message = "新消息"

    def test_all_valid_types(self):
        """测试所有有效的 type 值"""
        valid_types = ["setting_conflict", "character_inconsistency", "timeline_error", "other"]

        for type_value in valid_types:
            annotation = GhostAnnotation(
                type=type_value,
                severity="warning",
                message="测试"
            )
            assert annotation.type == type_value

    def test_all_valid_severities(self):
        """测试所有有效的 severity 值"""
        valid_severities = ["info", "warning", "error"]

        for severity_value in valid_severities:
            annotation = GhostAnnotation(
                type="other",
                severity=severity_value,
                message="测试"
            )
            assert annotation.severity == severity_value
