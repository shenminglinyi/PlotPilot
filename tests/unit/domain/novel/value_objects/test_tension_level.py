import pytest
from domain.novel.value_objects.tension_level import TensionLevel


def test_tension_level_enum_values():
    """测试 TensionLevel 枚举值（10 档）"""
    assert TensionLevel.LOW == 1
    assert TensionLevel.RIPPLE == 2
    assert TensionLevel.STIR == 3
    assert TensionLevel.MEDIUM == 4
    assert TensionLevel.SURGE == 5
    assert TensionLevel.TENSION_6 == 6
    assert TensionLevel.HIGH == 7
    assert TensionLevel.TENSION_8 == 8
    assert TensionLevel.TENSION_9 == 9
    assert TensionLevel.PEAK == 10


def test_tension_level_comparison():
    """测试 TensionLevel 比较操作"""
    assert TensionLevel.LOW < TensionLevel.MEDIUM
    assert TensionLevel.MEDIUM < TensionLevel.HIGH
    assert TensionLevel.HIGH < TensionLevel.PEAK
    assert TensionLevel.PEAK > TensionLevel.LOW


def test_tension_level_equality():
    """测试 TensionLevel 相等性"""
    assert TensionLevel.LOW == TensionLevel.LOW
    assert TensionLevel.MEDIUM != TensionLevel.HIGH


def test_tension_level_from_value():
    """测试从值创建 TensionLevel"""
    assert TensionLevel(1) == TensionLevel.LOW
    assert TensionLevel(5) == TensionLevel.SURGE
    assert TensionLevel(10) == TensionLevel.PEAK


def test_tension_level_from_score():
    """测试 from_score 方法将 0-100 分映射到 1-10 档"""
    # 极低分
    assert TensionLevel.from_score(0) == TensionLevel.LOW
    assert TensionLevel.from_score(10) == TensionLevel.LOW
    assert TensionLevel.from_score(5) == TensionLevel.LOW

    # 低分段
    assert TensionLevel.from_score(15) == TensionLevel.RIPPLE
    assert TensionLevel.from_score(20) == TensionLevel.RIPPLE

    # 中低段
    assert TensionLevel.from_score(25) == TensionLevel.STIR
    assert TensionLevel.from_score(35) == TensionLevel.STIR

    # 中段
    assert TensionLevel.from_score(40) == TensionLevel.MEDIUM
    assert TensionLevel.from_score(45) == TensionLevel.MEDIUM

    # 中高段
    assert TensionLevel.from_score(50) == TensionLevel.SURGE
    assert TensionLevel.from_score(55) == TensionLevel.SURGE

    # 高段
    assert TensionLevel.from_score(60) == TensionLevel.TENSION_6
    assert TensionLevel.from_score(65) == TensionLevel.TENSION_6

    # 更高段
    assert TensionLevel.from_score(70) == TensionLevel.HIGH
    assert TensionLevel.from_score(75) == TensionLevel.HIGH

    # 极高段
    assert TensionLevel.from_score(80) == TensionLevel.TENSION_8
    assert TensionLevel.from_score(85) == TensionLevel.TENSION_8

    # 巅峰段
    assert TensionLevel.from_score(90) == TensionLevel.TENSION_9
    assert TensionLevel.from_score(94) == TensionLevel.TENSION_9

    # 极限
    assert TensionLevel.from_score(95) == TensionLevel.PEAK
    assert TensionLevel.from_score(100) == TensionLevel.PEAK


def test_tension_level_display_name():
    """测试 display_name 属性"""
    assert TensionLevel.LOW.display_name == "死水"
    assert TensionLevel.SURGE.display_name == "涌潮"
    assert TensionLevel.HIGH.display_name == "风暴"
    assert TensionLevel.PEAK.display_name == "极限"


def test_tension_level_backward_compatible():
    """测试向后兼容性：旧的 LOW/MEDIUM/HIGH/PEAK 仍可用"""
    # LOW=1, MEDIUM=4, HIGH=7, PEAK=10 都还在
    assert TensionLevel.LOW.value == 1
    assert TensionLevel.MEDIUM.value == 4
    assert TensionLevel.HIGH.value == 7
    assert TensionLevel.PEAK.value == 10
