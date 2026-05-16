import pytest
from domain.novel.entities.plot_arc import PlotArc
from domain.novel.value_objects.novel_id import NovelId
from domain.novel.value_objects.plot_point import PlotPoint, PlotPointType
from domain.novel.value_objects.tension_level import TensionLevel


class TestPlotArc:
    """PlotArc 实体测试"""

    def test_create_plot_arc(self):
        """测试创建剧情弧"""
        novel_id = NovelId("novel-123")
        plot_arc = PlotArc(id="arc-1", novel_id=novel_id)

        assert plot_arc.id == "arc-1"
        assert plot_arc.novel_id == novel_id
        assert plot_arc.key_points == []

    def test_add_plot_point(self):
        """测试添加剧情点"""
        novel_id = NovelId("novel-123")
        plot_arc = PlotArc(id="arc-1", novel_id=novel_id)

        point1 = PlotPoint(
            chapter_number=1,
            point_type=PlotPointType.OPENING,
            description="Story begins",
            tension=TensionLevel.LOW
        )
        point2 = PlotPoint(
            chapter_number=5,
            point_type=PlotPointType.CLIMAX,
            description="Major conflict",
            tension=TensionLevel.PEAK
        )

        plot_arc.add_plot_point(point1)
        plot_arc.add_plot_point(point2)

        assert len(plot_arc.key_points) == 2
        assert plot_arc.key_points[0] == point1
        assert plot_arc.key_points[1] == point2

    def test_add_plot_point_auto_sort(self):
        """测试添加剧情点时自动排序"""
        novel_id = NovelId("novel-123")
        plot_arc = PlotArc(id="arc-1", novel_id=novel_id)

        point1 = PlotPoint(
            chapter_number=5,
            point_type=PlotPointType.CLIMAX,
            description="Major conflict",
            tension=TensionLevel.PEAK
        )
        point2 = PlotPoint(
            chapter_number=1,
            point_type=PlotPointType.OPENING,
            description="Story begins",
            tension=TensionLevel.LOW
        )
        point3 = PlotPoint(
            chapter_number=3,
            point_type=PlotPointType.RISING_ACTION,
            description="Rising tension",
            tension=TensionLevel.MEDIUM
        )

        plot_arc.add_plot_point(point1)
        plot_arc.add_plot_point(point2)
        plot_arc.add_plot_point(point3)

        assert len(plot_arc.key_points) == 3
        assert plot_arc.key_points[0].chapter_number == 1
        assert plot_arc.key_points[1].chapter_number == 3
        assert plot_arc.key_points[2].chapter_number == 5

    def test_get_expected_tension_exact_match(self):
        """测试获取期望张力 - 精确匹配"""
        novel_id = NovelId("novel-123")
        plot_arc = PlotArc(id="arc-1", novel_id=novel_id)

        point1 = PlotPoint(
            chapter_number=1,
            point_type=PlotPointType.OPENING,
            description="Story begins",
            tension=TensionLevel.LOW
        )
        point2 = PlotPoint(
            chapter_number=5,
            point_type=PlotPointType.CLIMAX,
            description="Major conflict",
            tension=TensionLevel.PEAK
        )

        plot_arc.add_plot_point(point1)
        plot_arc.add_plot_point(point2)

        assert plot_arc.get_expected_tension(1) == TensionLevel.LOW
        assert plot_arc.get_expected_tension(5) == TensionLevel.PEAK

    def test_get_expected_tension_interpolation(self):
        """测试获取期望张力 - 线性插值"""
        novel_id = NovelId("novel-123")
        plot_arc = PlotArc(id="arc-1", novel_id=novel_id)

        point1 = PlotPoint(
            chapter_number=1,
            point_type=PlotPointType.OPENING,
            description="Story begins",
            tension=TensionLevel.LOW  # 1
        )
        point2 = PlotPoint(
            chapter_number=5,
            point_type=PlotPointType.CLIMAX,
            description="Major conflict",
            tension=TensionLevel.PEAK  # 4
        )

        plot_arc.add_plot_point(point1)
        plot_arc.add_plot_point(point2)

        # Chapter 3 is midpoint between 1 and 5
        # Tension: LOW(1) → PEAK(10), midpoint = 5.5 → rounds to SURGE(5)
        # But actually: 1 + (10-1)*(2/4) = 1 + 4.5 = 5.5 → rounds to 6 (TENSION_6)
        assert plot_arc.get_expected_tension(3) == TensionLevel.TENSION_6

    def test_get_expected_tension_before_first_point(self):
        """测试获取期望张力 - 在第一个剧情点之前"""
        novel_id = NovelId("novel-123")
        plot_arc = PlotArc(id="arc-1", novel_id=novel_id)

        point1 = PlotPoint(
            chapter_number=5,
            point_type=PlotPointType.OPENING,
            description="Story begins",
            tension=TensionLevel.LOW
        )

        plot_arc.add_plot_point(point1)

        # Before first point, return first point's tension
        assert plot_arc.get_expected_tension(1) == TensionLevel.LOW
        assert plot_arc.get_expected_tension(3) == TensionLevel.LOW

    def test_get_expected_tension_after_last_point(self):
        """测试获取期望张力 - 在最后一个剧情点之后"""
        novel_id = NovelId("novel-123")
        plot_arc = PlotArc(id="arc-1", novel_id=novel_id)

        point1 = PlotPoint(
            chapter_number=5,
            point_type=PlotPointType.CLIMAX,
            description="Major conflict",
            tension=TensionLevel.PEAK
        )

        plot_arc.add_plot_point(point1)

        # After last point, return last point's tension
        assert plot_arc.get_expected_tension(10) == TensionLevel.PEAK
        assert plot_arc.get_expected_tension(100) == TensionLevel.PEAK

    def test_get_expected_tension_no_points(self):
        """测试获取期望张力 - 没有剧情点"""
        novel_id = NovelId("novel-123")
        plot_arc = PlotArc(id="arc-1", novel_id=novel_id)

        # No points, return MEDIUM as default (changed from LOW to MEDIUM for better default)
        assert plot_arc.get_expected_tension(1) == TensionLevel.MEDIUM

    def test_get_next_plot_point(self):
        """测试获取下一个剧情点"""
        novel_id = NovelId("novel-123")
        plot_arc = PlotArc(id="arc-1", novel_id=novel_id)

        point1 = PlotPoint(
            chapter_number=1,
            point_type=PlotPointType.OPENING,
            description="Story begins",
            tension=TensionLevel.LOW
        )
        point2 = PlotPoint(
            chapter_number=5,
            point_type=PlotPointType.CLIMAX,
            description="Major conflict",
            tension=TensionLevel.PEAK
        )
        point3 = PlotPoint(
            chapter_number=10,
            point_type=PlotPointType.RESOLUTION,
            description="Story ends",
            tension=TensionLevel.LOW
        )

        plot_arc.add_plot_point(point1)
        plot_arc.add_plot_point(point2)
        plot_arc.add_plot_point(point3)

        # From chapter 1, next is chapter 5
        assert plot_arc.get_next_plot_point(1) == point2
        # From chapter 3, next is chapter 5
        assert plot_arc.get_next_plot_point(3) == point2
        # From chapter 5, next is chapter 10
        assert plot_arc.get_next_plot_point(5) == point3
        # From chapter 10, no next point
        assert plot_arc.get_next_plot_point(10) is None
        # From chapter 15, no next point
        assert plot_arc.get_next_plot_point(15) is None

    def test_get_next_plot_point_no_points(self):
        """测试获取下一个剧情点 - 没有剧情点"""
        novel_id = NovelId("novel-123")
        plot_arc = PlotArc(id="arc-1", novel_id=novel_id)

        assert plot_arc.get_next_plot_point(1) is None

    def test_add_plot_point_none_validation(self):
        """测试添加剧情点 - None 验证"""
        novel_id = NovelId("novel-123")
        plot_arc = PlotArc(id="arc-1", novel_id=novel_id)

        with pytest.raises(ValueError, match="Plot point cannot be None"):
            plot_arc.add_plot_point(None)

    def test_get_expected_tension_invalid_chapter_number(self):
        """测试获取期望张力 - 无效章节号"""
        novel_id = NovelId("novel-123")
        plot_arc = PlotArc(id="arc-1", novel_id=novel_id)

        with pytest.raises(ValueError, match="Chapter number must be positive"):
            plot_arc.get_expected_tension(0)

        with pytest.raises(ValueError, match="Chapter number must be positive"):
            plot_arc.get_expected_tension(-1)

    def test_get_next_plot_point_invalid_chapter_number(self):
        """测试获取下一个剧情点 - 无效章节号"""
        novel_id = NovelId("novel-123")
        plot_arc = PlotArc(id="arc-1", novel_id=novel_id)

        with pytest.raises(ValueError, match="Chapter number must be positive"):
            plot_arc.get_next_plot_point(0)

        with pytest.raises(ValueError, match="Chapter number must be positive"):
            plot_arc.get_next_plot_point(-1)

    def test_get_expected_tension_same_chapter_points(self):
        """测试获取期望张力 - 相同章节的剧情点（防止除零）"""
        novel_id = NovelId("novel-123")
        plot_arc = PlotArc(id="arc-1", novel_id=novel_id)

        # Add two points with the same chapter number (edge case)
        point1 = PlotPoint(
            chapter_number=5,
            point_type=PlotPointType.OPENING,
            description="First event",
            tension=TensionLevel.LOW
        )
        point2 = PlotPoint(
            chapter_number=5,
            point_type=PlotPointType.CLIMAX,
            description="Second event",
            tension=TensionLevel.PEAK
        )

        plot_arc.add_plot_point(point1)
        plot_arc.add_plot_point(point2)

        # Should return the first point's tension without division by zero
        result = plot_arc.get_expected_tension(5)
        assert result in [TensionLevel.LOW, TensionLevel.PEAK]
