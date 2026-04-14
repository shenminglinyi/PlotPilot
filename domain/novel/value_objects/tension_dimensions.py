"""多维张力分析结果值对象。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TensionDimensions:
    """多维张力分析结果（所有分值范围 0-100）。

    Attributes:
        plot_tension: 情节张力 — 冲突烈度、悬念密度、信息不对称
        emotional_tension: 情绪张力 — 角色情绪波动、读者共情深度
        pacing_tension: 节奏张力 — 场景切换频率、叙述节奏、信息密度
        composite_score: 综合张力 — 加权汇总（plot 40%, emotional 30%, pacing 30%）
    """

    plot_tension: float
    emotional_tension: float
    pacing_tension: float
    composite_score: float

    # 权重：情节 > 情绪 = 节奏
    _WEIGHTS = (0.40, 0.30, 0.30)

    def __post_init__(self) -> None:
        for name in (
            "plot_tension",
            "emotional_tension",
            "pacing_tension",
            "composite_score",
        ):
            val = getattr(self, name)
            if not isinstance(val, (int, float)):
                raise TypeError(f"{name} must be numeric, got {type(val).__name__}")
            if not (0.0 <= float(val) <= 100.0):
                raise ValueError(f"{name} must be 0-100, got {val}")

    @classmethod
    def from_raw_scores(
        cls,
        plot: float,
        emotional: float,
        pacing: float,
    ) -> TensionDimensions:
        """从三个维度原始分值构造实例，自动计算加权综合分。"""
        plot = max(0.0, min(100.0, float(plot)))
        emotional = max(0.0, min(100.0, float(emotional)))
        pacing = max(0.0, min(100.0, float(pacing)))
        composite = round(
            plot * cls._WEIGHTS[0]
            + emotional * cls._WEIGHTS[1]
            + pacing * cls._WEIGHTS[2],
            1,
        )
        return cls(
            plot_tension=plot,
            emotional_tension=emotional,
            pacing_tension=pacing,
            composite_score=composite,
        )

    @classmethod
    def neutral(cls) -> TensionDimensions:
        """返回全维度 50.0 的中性结果（用于兜底）。"""
        return cls(50.0, 50.0, 50.0, 50.0)
