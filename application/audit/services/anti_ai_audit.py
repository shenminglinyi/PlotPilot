"""Anti-AI 指标与审计服务 — Layer 7: 章后审计与指标追踪。

核心功能：
- 对生成的章节进行 35+ 模式 AI 味扫描
- 计算综合 AI 味评分
- 生成结构化审计报告
- 追踪章节间的 AI 味趋势
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from application.audit.services.cliche_scanner import ClicheHit, ClicheScanner

logger = logging.getLogger(__name__)


@dataclass
class AntiAIMetrics:
    """Anti-AI 指标快照。"""
    chapter_id: str = ""
    total_hits: int = 0
    critical_hits: int = 0
    warning_hits: int = 0
    info_hits: int = 0
    severity_score: float = 0.0  # 0-100，越高AI味越重
    category_distribution: Dict[str, int] = field(default_factory=dict)
    top_patterns: List[str] = field(default_factory=list)
    overall_assessment: str = "未检测"  # 纯净/轻微/中等/严重


@dataclass
class AntiAIAuditReport:
    """Anti-AI 审计报告。"""
    chapter_id: str = ""
    metrics: AntiAIMetrics = field(default_factory=AntiAIMetrics)
    hits: List[ClicheHit] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    improvement_suggestions: List[str] = field(default_factory=list)


class AntiAIAuditor:
    """Anti-AI 审计服务。"""

    SEVERITY_WEIGHTS = {"critical": 3.0, "warning": 1.0, "info": 0.3}
    ASSESSMENT_THRESHOLDS = [(5.0, "严重"), (3.0, "中等"), (1.0, "轻微"), (0.0, "纯净")]

    def scan_chapter(self, chapter_id: str, content: str) -> AntiAIAuditReport:
        """对章节进行 Anti-AI 审计。"""
        scanner = ClicheScanner(use_enhanced=True)
        hits = scanner.scan_cliches(content)
        metrics = self._calculate_metrics(chapter_id, hits, content)
        recommendations = self._generate_recommendations(metrics, hits)
        improvement_suggestions = self._generate_improvement_suggestions(hits)
        return AntiAIAuditReport(
            chapter_id=chapter_id,
            metrics=metrics,
            hits=hits,
            recommendations=recommendations,
            improvement_suggestions=improvement_suggestions,
        )

    def _calculate_metrics(self, chapter_id: str, hits: List[ClicheHit], content: str) -> AntiAIMetrics:
        """计算 Anti-AI 指标。"""
        critical_count = sum(1 for h in hits if h.severity == "critical")
        warning_count = sum(1 for h in hits if h.severity == "warning")
        info_count = sum(1 for h in hits if h.severity == "info")

        char_count = max(len(content), 1)
        raw_score = sum(self.SEVERITY_WEIGHTS.get(h.severity, 0.5) for h in hits)
        normalized_score = min(100.0, (raw_score / char_count) * 1000 * 10)

        category_dist: Dict[str, int] = {}
        for h in hits:
            cat = h.category or "其他"
            category_dist[cat] = category_dist.get(cat, 0) + 1

        pattern_counts: Dict[str, int] = {}
        for h in hits:
            pattern_counts[h.pattern] = pattern_counts.get(h.pattern, 0) + 1
        top_patterns = sorted(pattern_counts, key=pattern_counts.get, reverse=True)[:5]

        assessment = "纯净"
        for threshold, label in self.ASSESSMENT_THRESHOLDS:
            if normalized_score >= threshold:
                assessment = label
                break

        return AntiAIMetrics(
            chapter_id=chapter_id, total_hits=len(hits),
            critical_hits=critical_count, warning_hits=warning_count, info_hits=info_count,
            severity_score=round(normalized_score, 1),
            category_distribution=category_dist, top_patterns=top_patterns,
            overall_assessment=assessment,
        )

    def _generate_recommendations(self, metrics: AntiAIMetrics, hits: List[ClicheHit]) -> List[str]:
        """生成修改建议。"""
        recs = []
        if metrics.critical_hits > 0:
            critical_patterns = [h.pattern for h in hits if h.severity == "critical"]
            unique = list(dict.fromkeys(critical_patterns))[:3]
            recs.append(f"紧急：发现 {metrics.critical_hits} 处严重AI味模式（{', '.join(unique)}），必须修改")
        if metrics.category_distribution.get("微表情", 0) > 3:
            recs.append("微表情过多：建议用完整姿态变化或对白本身替代")
        if metrics.category_distribution.get("比喻", 0) > 2:
            recs.append("比喻过多：建议用感官细节替代比喻")
        if metrics.category_distribution.get("声线", 0) > 2:
            recs.append("声线标签过多：建议用对白的标点和断句表现语气")
        if metrics.category_distribution.get("情绪", 0) > 2:
            recs.append("情绪标签过多：建议通过动作和环境暗示传递情绪")
        return recs

    def _generate_improvement_suggestions(self, hits: List[ClicheHit]) -> List[str]:
        """生成具体改进建议。"""
        suggestions = []
        seen_patterns = set()
        for h in hits:
            if h.pattern in seen_patterns:
                continue
            seen_patterns.add(h.pattern)
            if h.replacement_hint:
                suggestions.append(f"[{h.category}] {h.pattern} → {h.replacement_hint}")
            if len(suggestions) >= 5:
                break
        return suggestions


_auditor: Optional[AntiAIAuditor] = None

def get_anti_ai_auditor() -> AntiAIAuditor:
    global _auditor
    if _auditor is None:
        _auditor = AntiAIAuditor()
    return _auditor
