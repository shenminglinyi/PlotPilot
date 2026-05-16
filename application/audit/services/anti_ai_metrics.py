"""Anti-AI 指标服务 — 独立于审计的指标计算与趋势追踪。

核心功能：
- 计算章节的 AI 味密度（hits / 千字）
- 追踪多章节间的 AI 味趋势变化
- 提供指标快照用于仪表板展示
- 支持按分类、严重性的细化统计
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ChapterMetricsSnapshot:
    """单章节指标快照。"""
    chapter_id: str
    chapter_number: int = 0
    total_chars: int = 0
    total_hits: int = 0
    critical_hits: int = 0
    warning_hits: int = 0
    info_hits: int = 0

    # 核心指标
    hit_density: float = 0.0        # 每千字命中数
    critical_density: float = 0.0   # 每千字严重命中数
    severity_score: float = 0.0     # 加权严重性分数 0-100

    # 分类分布
    category_distribution: Dict[str, int] = field(default_factory=dict)
    top_patterns: List[str] = field(default_factory=list)

    # 总体评估
    assessment: str = "未检测"  # 纯净/轻微/中等/严重/未检测

    @property
    def is_clean(self) -> bool:
        return self.assessment == "纯净"

    @property
    def is_severe(self) -> bool:
        return self.assessment in ("中等", "严重")


@dataclass
class TrendPoint:
    """趋势数据点。"""
    chapter_number: int
    severity_score: float
    hit_density: float
    assessment: str


@dataclass
class MetricsTrend:
    """多章节 AI 味趋势。"""
    novel_id: str
    points: List[TrendPoint] = field(default_factory=list)

    @property
    def is_improving(self) -> bool:
        """趋势是否在改善（AI 味在降低）。"""
        if len(self.points) < 2:
            return True
        recent = self.points[-3:] if len(self.points) >= 3 else self.points
        scores = [p.severity_score for p in recent]
        return scores[-1] <= scores[0]

    @property
    def average_score(self) -> float:
        if not self.points:
            return 0.0
        return sum(p.severity_score for p in self.points) / len(self.points)

    @property
    def worst_chapter(self) -> Optional[TrendPoint]:
        if not self.points:
            return None
        return max(self.points, key=lambda p: p.severity_score)

    @property
    def best_chapter(self) -> Optional[TrendPoint]:
        if not self.points:
            return None
        return min(self.points, key=lambda p: p.severity_score)


class AntiAIMetricsService:
    """Anti-AI 指标服务。"""

    # 严重性权重
    SEVERITY_WEIGHTS = {"critical": 3.0, "warning": 1.0, "info": 0.3}

    # 评估阈值
    ASSESSMENT_THRESHOLDS: List[Tuple[float, str]] = [
        (5.0, "严重"),
        (3.0, "中等"),
        (1.0, "轻微"),
        (0.0, "纯净"),
    ]

    def compute_snapshot(
        self,
        chapter_id: str,
        chapter_number: int,
        content: str,
        hits: List[Any],
    ) -> ChapterMetricsSnapshot:
        """计算单章节的指标快照。

        Args:
            chapter_id: 章节 ID
            chapter_number: 章节号
            content: 章节正文
            hits: ClicheHit 列表

        Returns:
            ChapterMetricsSnapshot
        """
        total_chars = max(len(content), 1)
        critical_count = sum(1 for h in hits if getattr(h, 'severity', '') == "critical")
        warning_count = sum(1 for h in hits if getattr(h, 'severity', '') == "warning")
        info_count = sum(1 for h in hits if getattr(h, 'severity', '') == "info")

        # 计算密度（每千字）
        chars_per_k = max(total_chars / 1000.0, 0.001)
        hit_density = len(hits) / chars_per_k
        critical_density = critical_count / chars_per_k

        # 加权严重性分数
        raw_score = sum(
            self.SEVERITY_WEIGHTS.get(getattr(h, 'severity', ''), 0.5)
            for h in hits
        )
        severity_score = min(100.0, (raw_score / chars_per_k) * 10)

        # 分类分布
        category_dist: Dict[str, int] = {}
        for h in hits:
            cat = getattr(h, 'category', '其他') or '其他'
            category_dist[cat] = category_dist.get(cat, 0) + 1

        # 高频模式
        pattern_counts: Dict[str, int] = {}
        for h in hits:
            p = getattr(h, 'pattern', '')
            if p:
                pattern_counts[p] = pattern_counts.get(p, 0) + 1
        top_patterns = sorted(pattern_counts, key=pattern_counts.get, reverse=True)[:5]

        # 评估
        assessment = "纯净"
        for threshold, label in self.ASSESSMENT_THRESHOLDS:
            if severity_score >= threshold:
                assessment = label
                break

        return ChapterMetricsSnapshot(
            chapter_id=chapter_id,
            chapter_number=chapter_number,
            total_chars=total_chars,
            total_hits=len(hits),
            critical_hits=critical_count,
            warning_hits=warning_count,
            info_hits=info_count,
            hit_density=round(hit_density, 2),
            critical_density=round(critical_density, 2),
            severity_score=round(severity_score, 1),
            category_distribution=category_dist,
            top_patterns=top_patterns,
            assessment=assessment,
        )

    def compute_trend(
        self,
        novel_id: str,
        snapshots: List[ChapterMetricsSnapshot],
    ) -> MetricsTrend:
        """计算多章节 AI 味趋势。

        Args:
            novel_id: 小说 ID
            snapshots: 按章节顺序排列的快照列表

        Returns:
            MetricsTrend
        """
        points = [
            TrendPoint(
                chapter_number=s.chapter_number,
                severity_score=s.severity_score,
                hit_density=s.hit_density,
                assessment=s.assessment,
            )
            for s in sorted(snapshots, key=lambda s: s.chapter_number)
        ]

        return MetricsTrend(novel_id=novel_id, points=points)

    def get_improvement_report(
        self,
        snapshots: List[ChapterMetricsSnapshot],
    ) -> Dict[str, Any]:
        """生成改善报告。

        Args:
            snapshots: 快照列表

        Returns:
            改善报告字典
        """
        if not snapshots:
            return {"status": "no_data", "message": "暂无数据"}

        trend = self.compute_trend("report", snapshots)

        # 按分类汇总
        all_categories: Dict[str, int] = {}
        for s in snapshots:
            for cat, count in s.category_distribution.items():
                all_categories[cat] = all_categories.get(cat, 0) + count

        # 最常见的问题分类
        worst_categories = sorted(
            all_categories, key=all_categories.get, reverse=True
        )[:3]

        # 最近5章的趋势
        recent = snapshots[-5:] if len(snapshots) >= 5 else snapshots
        recent_avg = sum(s.severity_score for s in recent) / len(recent)

        return {
            "status": "ok",
            "total_chapters_scanned": len(snapshots),
            "trend_direction": "improving" if trend.is_improving else "worsening",
            "average_score": round(trend.average_score, 1),
            "recent_average_score": round(recent_avg, 1),
            "worst_chapter": (
                trend.worst_chapter.chapter_number if trend.worst_chapter else None
            ),
            "best_chapter": (
                trend.best_chapter.chapter_number if trend.best_chapter else None
            ),
            "most_common_issues": worst_categories,
            "clean_chapters": sum(1 for s in snapshots if s.is_clean),
            "severe_chapters": sum(1 for s in snapshots if s.is_severe),
            "recommendations": self._generate_trend_recommendations(snapshots, trend),
        }

    def _generate_trend_recommendations(
        self,
        snapshots: List[ChapterMetricsSnapshot],
        trend: MetricsTrend,
    ) -> List[str]:
        """基于趋势生成建议。"""
        recs = []

        if not trend.is_improving:
            recs.append(
                "⚠️ AI 味趋势在恶化——建议检查最近的提示词是否被意外修改"
            )

        severe_count = sum(1 for s in snapshots if s.is_severe)
        if severe_count > len(snapshots) * 0.3:
            recs.append(
                f"超过 30% 的章节（{severe_count}/{len(snapshots)}）被评为'中等'或'严重'，"
                "建议加强行为协议的注入强度"
            )

        # 检查特定分类
        all_cats: Dict[str, int] = {}
        for s in snapshots:
            for cat, count in s.category_distribution.items():
                all_cats[cat] = all_cats.get(cat, 0) + count

        if all_cats.get("微表情", 0) > len(snapshots) * 2:
            recs.append("微表情问题频发——建议在行为协议中强调'写完整姿态变化'")
        if all_cats.get("声线", 0) > len(snapshots) * 2:
            recs.append("声线标签问题频发——建议在行为协议中强调'让对白自身说话'")
        if all_cats.get("比喻", 0) > len(snapshots) * 1.5:
            recs.append("比喻问题频发——建议在行为协议中强调'用感官细节替代比喻'")

        return recs


# 全局单例
_service: Optional[AntiAIMetricsService] = None


def get_anti_ai_metrics_service() -> AntiAIMetricsService:
    """获取全局 Anti-AI 指标服务。"""
    global _service
    if _service is None:
        _service = AntiAIMetricsService()
    return _service
