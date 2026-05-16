import math
from typing import List, Optional
from domain.shared.base_entity import BaseEntity
from domain.novel.value_objects.novel_id import NovelId
from domain.novel.value_objects.plot_point import PlotPoint
from domain.novel.value_objects.tension_level import TensionLevel


class PlotArc(BaseEntity):
    """剧情弧实体

    ★ Phase 3: 支持非线性插值（smoothstep/Hermite/STEP）
    核心改进：叙事张力不应该是线性斜坡，而应该像心电图一样有急升急降。

    ★ 爽文引擎: STEP 阶跃函数模式
    爽文叙事的核心节奏：日常→挑衅→爆发→余韵→结算
    不是渐变，而是阶跃——瞬间从10%跳到80%，
    这是爽文的"心电图"：低平→急升→爆表→骤降→缓收
    """

    # ── 插值模式 ──
    INTERPOLATION_LINEAR = "linear"        # 线性插值（旧版兼容）
    INTERPOLATION_SMOOTHSTEP = "smoothstep"  # 平滑阶梯（默认，推荐）
    INTERPOLATION_HERMITE = "hermite"       # Hermite 样条（更锐利的转折）
    INTERPOLATION_STEP = "step"            # ★ 爽文引擎: 阶跃函数（爽文专用）

    # ★ 爽文引擎: STEP 阶跃函数的默认阶段配置
    # 描述爽文一章内的标准张力分布：
    #   日常(daily) → 挑衅(provocation) → 爆发(eruption) → 余韵(aftermath) → 结算(settlement)
    # 每个阶段对应一个张力百分比（映射到 0-100）
    STEP_PHASES_DEFAULT = {
        "daily":       {"tension_pct": 10, "weight": 0.15},  # 日常 10%，占 15% 篇幅
        "provocation":  {"tension_pct": 30, "weight": 0.20},  # 挑衅 30%，占 20% 篇幅
        "eruption":    {"tension_pct": 80, "weight": 0.35},  # 爆发 80%，占 35% 篇幅（核心爽点）
        "aftermath":   {"tension_pct": 40, "weight": 0.15},  # 余韵 40%，占 15% 篇幅
        "settlement":  {"tension_pct": 20, "weight": 0.15},  # 结算 20%，占 15% 篇幅
    }

    def __init__(
        self,
        id: str,
        novel_id: NovelId,
        key_points: Optional[List[PlotPoint]] = None,
        slug: str = "default",
        display_name: str = "",
        interpolation: str = "smoothstep",  # ★ Phase 3: 默认使用平滑阶梯
        step_phases: Optional[dict] = None,  # ★ 爽文引擎: 自定义 STEP 阶跃配置
    ):
        super().__init__(id)
        self.novel_id = novel_id
        self.key_points: List[PlotPoint] = key_points if key_points is not None else []
        self.slug = slug or "default"
        self.display_name = display_name or ""
        self.interpolation = interpolation
        self.step_phases = step_phases or self.STEP_PHASES_DEFAULT  # ★ 爽文引擎

    def add_plot_point(self, point: PlotPoint) -> None:
        """添加剧情点，自动按章节号排序"""
        if point is None:
            raise ValueError("Plot point cannot be None")
        self.key_points.append(point)
        self.key_points.sort(key=lambda p: p.chapter_number)

    def get_expected_tension(self, chapter_number: int) -> TensionLevel:
        """获取指定章节的期望张力

        ★ Phase 3: 使用非线性插值，替代原来的线性插值。
        默认使用 smoothstep 插值，使张力曲线呈现自然的 S 形：
        - 在锚点附近变化缓慢（稳定期）
        - 在中间段变化加速（转折期）
        这比线性插值更符合叙事张力的"蓄力→爆发→余波"节奏。

        Args:
            chapter_number: 章节号

        Returns:
            TensionLevel（1-10 档）
        """
        if chapter_number < 1:
            raise ValueError("Chapter number must be positive (>= 1)")

        if not self.key_points:
            return TensionLevel.MEDIUM  # 无锚点时默认暗流(4)，而非最低(1)

        # If before first point, return first point's tension
        if chapter_number <= self.key_points[0].chapter_number:
            return self.key_points[0].tension

        # If after last point, return last point's tension
        if chapter_number >= self.key_points[-1].chapter_number:
            return self.key_points[-1].tension

        # Find the two points to interpolate between
        for i in range(len(self.key_points) - 1):
            current_point = self.key_points[i]
            next_point = self.key_points[i + 1]

            if current_point.chapter_number <= chapter_number <= next_point.chapter_number:
                chapter_diff = next_point.chapter_number - current_point.chapter_number

                # Guard against division by zero
                if chapter_diff == 0:
                    return current_point.tension

                tension_diff = next_point.tension.value - current_point.tension.value
                t = (chapter_number - current_point.chapter_number) / chapter_diff  # 归一化 0~1

                # ★ Phase 3: 根据插值模式选择算法
                if self.interpolation == self.INTERPOLATION_LINEAR:
                    interpolated_value = current_point.tension.value + tension_diff * t
                elif self.interpolation == self.INTERPOLATION_HERMITE:
                    interpolated_value = current_point.tension.value + tension_diff * self._hermite(t)
                elif self.interpolation == self.INTERPOLATION_STEP:
                    # ★ 爽文引擎: 阶跃函数——直接取下一个锚点的值
                    # 不做渐变，而是瞬间跳变，模拟爽文的"蓄力→爆发"节奏
                    interpolated_value = next_point.tension.value
                else:
                    # 默认 smoothstep
                    interpolated_value = current_point.tension.value + tension_diff * self._smoothstep(t)

                # Round to nearest tension level (1-10)
                rounded_value = round(interpolated_value)

                # Clamp to valid range using TensionLevel enum bounds
                rounded_value = max(TensionLevel.LOW.value, min(TensionLevel.PEAK.value, rounded_value))

                return TensionLevel(rounded_value)

        # Fallback (should not reach here)
        return TensionLevel.MEDIUM

    @staticmethod
    def _smoothstep(t: float) -> float:
        """Smoothstep 插值函数

        产生 S 形曲线：在锚点附近平缓（稳定），中间段陡峭（转折）。
        这比线性插值更符合叙事张力的自然节奏：
        - 蓄力阶段：张力缓慢上升（读者尚未紧张）
        - 转折阶段：张力急剧上升（冲突爆发）
        - 余波阶段：张力缓慢上升至峰值（高潮延续）

        公式: 3t² - 2t³
        """
        t = max(0.0, min(1.0, t))  # Clamp
        return t * t * (3.0 - 2.0 * t)

    def get_step_tension_profile(self, chapter_number: int) -> List[dict]:
        """★ 爽文引擎: 获取 STEP 阶跃函数在章节内的张力分布剖面

        根据配置的 step_phases 生成节拍级别的张力指导。
        每个阶段包含：阶段名、张力百分比、建议篇幅占比。

        用途：
        - 注入节拍 Prompt，指导 LLM 在不同阶段输出不同密度的内容
        - 与 ChapterConductor 的 UNFURL/CONVERGE/LAND 阶段对应

        Args:
            chapter_number: 章节号（用于确定是否使用首章/高潮章等特殊配置）

        Returns:
            [{"phase": str, "tension_pct": int, "weight": float}, ...]
        """
        # 前三章使用加速版本（日常更短，爆发更长）
        if chapter_number <= 3:
            early_step_phases = {
                "daily":       {"tension_pct": 15, "weight": 0.08},  # 日常更短
                "provocation":  {"tension_pct": 40, "weight": 0.17},  # 挑衅更急
                "eruption":    {"tension_pct": 85, "weight": 0.45},  # 爆发占比加大
                "aftermath":   {"tension_pct": 45, "weight": 0.15},
                "settlement":  {"tension_pct": 25, "weight": 0.15},
            }
            phases = early_step_phases
        else:
            phases = self.step_phases

        profile = []
        for phase_name, config in phases.items():
            profile.append({
                "phase": phase_name,
                "tension_pct": config["tension_pct"],
                "weight": config["weight"],
            })
        return profile

    def get_step_tension_for_beat(
        self,
        chapter_number: int,
        beat_index: int,
        total_beats: int,
    ) -> int:
        """★ 爽文引擎: 根据节拍位置返回 STEP 阶跃张力值

        将章节的节拍序列映射到 STEP 阶段，返回对应的张力百分比。

        Args:
            chapter_number: 章节号
            beat_index: 当前节拍索引（0-based）
            total_beats: 总节拍数

        Returns:
            张力百分比（0-100）
        """
        profile = self.get_step_tension_profile(chapter_number)

        if total_beats <= 0:
            return 50  # 兜底

        # 计算当前节拍在章节中的归一化位置
        beat_progress = beat_index / total_beats

        # 根据权重分配，确定当前节拍落在哪个 STEP 阶段
        cumulative_weight = 0.0
        for phase_config in profile:
            cumulative_weight += phase_config["weight"]
            if beat_progress < cumulative_weight:
                return phase_config["tension_pct"]

        # 如果超出（浮点误差），返回最后一个阶段
        return profile[-1]["tension_pct"]

    @staticmethod
    def _hermite(t: float) -> float:
        """Hermite 样条插值函数

        比 smoothstep 更锐利的 S 形曲线：
        - 在锚点附近更平缓（更强的"蓄力"效果）
        - 在中间段更陡峭（更戏剧性的"爆发"效果）

        公式: 6t⁵ - 15t⁴ + 10t³ (Ken Perlin's improved smoothstep)
        """
        t = max(0.0, min(1.0, t))  # Clamp
        return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)

    def get_expected_tension_100(self, chapter_number: int) -> int:
        """★ Phase 3: 获取 0-100 刻度的期望张力

        直接返回 TensionLevel.value * 10，方便外部使用统一刻度。

        Args:
            chapter_number: 章节号

        Returns:
            0-100 的期望张力值
        """
        level = self.get_expected_tension(chapter_number)
        return level.value * 10

    def get_next_plot_point(self, current_chapter: int) -> Optional[PlotPoint]:
        """获取当前章节之后的下一个剧情点"""
        if current_chapter < 1:
            raise ValueError("Chapter number must be positive (>= 1)")
        for point in self.key_points:
            if point.chapter_number > current_chapter:
                return point
        return None
