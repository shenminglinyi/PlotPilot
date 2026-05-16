"""Anti-AI 学习服务 — 从审计数据中自适应学习新模式。

核心功能：
- 从章节审计报告中提取高频 AI 味模式
- 自动学习未在规则库中定义的新模式
- 基于历史数据动态调整模式严重性权重
- 提供学习报告供人工审核
- 人工审核通过的模式可导入到规则库
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


@dataclass
class LearnedPattern:
    """学习到的潜在 AI 味模式。"""
    pattern: str                    # 正则表达式或文本模式
    name: str                       # 模式名称
    hit_count: int = 0              # 命中次数
    chapter_occurrences: List[int] = field(default_factory=list)  # 出现在哪些章节
    avg_surrounding_chars: int = 0  # 上下文平均长度
    co_occurrence_categories: Set[str] = field(default_factory=set)  # 常同时出现的分类
    confidence: float = 0.0         # 置信度 0-1
    status: str = "pending"         # pending/approved/rejected
    suggested_severity: str = "warning"  # 建议严重级别
    suggested_category: str = ""    # 建议分类


@dataclass
class LearningReport:
    """学习报告。"""
    novel_id: str
    total_chapters_analyzed: int = 0
    new_patterns_discovered: int = 0
    patterns_approved: int = 0
    patterns_rejected: int = 0
    severity_adjustments: int = 0
    top_patterns: List[LearnedPattern] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


class AntiAILearningService:
    """Anti-AI 自适应学习服务。

    学习策略：
    1. 频次学习：在多个章节中反复出现的表达，很可能是 AI 味模式
    2. 共现学习：与已知 AI 味模式频繁共现的表达，可能也是 AI 味
    3. 上下文学习：出现在相似上下文中的表达，可能属于同一类 AI 味
    4. 严重性调整：根据实际命中数据调整已知模式的严重性
    """

    # 学习参数
    MIN_OCCURRENCES_FOR_LEARNING = 3  # 至少在3个章节出现才考虑学习
    MIN_CONFIDENCE_FOR_SUGGESTION = 0.5  # 最低置信度阈值
    MAX_PENDING_PATTERNS = 50  # 最多待审核模式数

    # 常见 AI 味句式结构模板（用于结构化学习）
    AI_STRUCTURAL_TEMPLATES = [
        # "X地Y" 结构（副词+动词）
        (r"([\u4e00-\u9fff]{1,2})地([\u4e00-\u9fff]{1,4})", "副词+动词结构"),
        # "不禁X" 结构
        (r"不禁([\u4e00-\u9fff]{1,6})", "不禁系列"),
        # "缓缓X" 结构
        (r"缓缓([\u4e00-\u9fff]{1,4})", "缓缓系列"),
        # "微微X" 结构
        (r"微微([\u4e00-\u9fff]{1,4})", "微微系列"),
        # "暗自X" 结构
        (r"暗自([\u4e00-\u9fff]{1,4})", "暗自系列"),
        # "一X就Y" 结构
        (r"一([\u4e00-\u9fff]{1,2})就([\u4e00-\u9fff]{1,6})", "一X就Y结构"),
    ]

    # 严重性调整规则
    SEVERITY_ADJUSTMENT_RULES = {
        # 如果一个 warning 模式在超过 50% 的章节中出现，提升为 critical
        "warning_to_critical_threshold": 0.5,
        # 如果一个 info 模式在超过 30% 的章节中出现，提升为 warning
        "info_to_warning_threshold": 0.3,
    }

    def __init__(self):
        self._learned_patterns: Dict[str, LearnedPattern] = {}
        self._approved_patterns: List[LearnedPattern] = []
        self._chapter_history: Dict[str, List[int]] = {}  # novel_id -> [chapter_numbers]

    def analyze_chapter_audit(
        self,
        novel_id: str,
        chapter_number: int,
        content: str,
        hits: List[Any],
    ) -> List[LearnedPattern]:
        """分析章节审计结果，提取潜在新模式。

        Args:
            novel_id: 小说 ID
            chapter_number: 章节号
            content: 章节正文
            hits: ClicheHit 列表

        Returns:
            新发现的潜在模式列表
        """
        new_patterns = []

        # 更新章节历史
        if novel_id not in self._chapter_history:
            self._chapter_history[novel_id] = []
        self._chapter_history[novel_id].append(chapter_number)

        # 策略1：结构化模板学习
        for template_regex, template_name in self.AI_STRUCTURAL_TEMPLATES:
            matches = re.findall(template_regex, content)
            if not matches:
                continue

            for match_group in matches:
                if isinstance(match_group, tuple):
                    match_text = "".join(match_group)
                else:
                    match_text = match_group

                # 检查是否已经在已知规则库中
                if self._is_known_pattern(match_text, hits):
                    continue

                pattern_key = f"{template_name}:{match_text}"

                if pattern_key not in self._learned_patterns:
                    self._learned_patterns[pattern_key] = LearnedPattern(
                        pattern=template_regex,
                        name=f"{template_name}({match_text})",
                        hit_count=1,
                        chapter_occurrences=[chapter_number],
                        co_occurrence_categories={
                            getattr(h, 'category', '') for h in hits if getattr(h, 'category', '')
                        },
                        confidence=0.2,
                        suggested_severity="info",
                        suggested_category=template_name.split("系列")[0] if "系列" in template_name else "句式",
                    )
                    new_patterns.append(self._learned_patterns[pattern_key])
                else:
                    lp = self._learned_patterns[pattern_key]
                    lp.hit_count += 1
                    if chapter_number not in lp.chapter_occurrences:
                        lp.chapter_occurrences.append(chapter_number)
                    lp.co_occurrence_categories.update(
                        getattr(h, 'category', '') for h in hits if getattr(h, 'category', '')
                    )
                    # 更新置信度
                    lp.confidence = min(1.0, lp.hit_count * 0.1 + len(lp.chapter_occurrences) * 0.15)

                    # 根据出现频率调整建议严重性
                    if len(lp.chapter_occurrences) >= 5:
                        lp.suggested_severity = "warning"
                    if len(lp.chapter_occurrences) >= 10:
                        lp.suggested_severity = "critical"

        # 策略2：共现学习 — 找到与已知 AI 味高频共现的短语
        if hits:
            surrounding_texts = self._extract_surrounding_texts(content, hits)
            for text in surrounding_texts:
                # 检查是否包含常见的 AI 味结构词
                for trigger_word in ["仿佛", "宛如", "不禁", "缓缓", "微微", "暗自", "分明"]:
                    if trigger_word in text and len(text) > 4:
                        pattern_key = f"cooccur:{trigger_word}:{text[:20]}"

                        if pattern_key not in self._learned_patterns:
                            self._learned_patterns[pattern_key] = LearnedPattern(
                                pattern=re.escape(text[:20]),
                                name=f"共现模式({trigger_word})",
                                hit_count=1,
                                chapter_occurrences=[chapter_number],
                                co_occurrence_categories={
                                    getattr(h, 'category', '') for h in hits if getattr(h, 'category', '')
                                },
                                confidence=0.3,
                                suggested_severity="info",
                                suggested_category="共现",
                            )

        # 清理：移除低置信度的旧模式
        self._cleanup_patterns()

        return new_patterns

    def generate_learning_report(self, novel_id: str) -> LearningReport:
        """生成学习报告。"""
        total_chapters = len(self._chapter_history.get(novel_id, []))

        pending = [p for p in self._learned_patterns.values() if p.status == "pending"]
        approved = [p for p in self._learned_patterns.values() if p.status == "approved"]
        rejected = [p for p in self._learned_patterns.values() if p.status == "rejected"]

        # 按置信度排序
        top_patterns = sorted(pending, key=lambda p: p.confidence, reverse=True)[:10]

        recommendations = []
        for p in top_patterns:
            if p.confidence >= self.MIN_CONFIDENCE_FOR_SUGGESTION:
                recommendations.append(
                    f"建议审核模式 '{p.name}'（置信度 {p.confidence:.0%}，"
                    f"出现 {p.hit_count} 次，跨 {len(p.chapter_occurrences)} 章）"
                )

        return LearningReport(
            novel_id=novel_id,
            total_chapters_analyzed=total_chapters,
            new_patterns_discovered=len(pending),
            patterns_approved=len(approved),
            patterns_rejected=len(rejected),
            severity_adjustments=0,
            top_patterns=top_patterns,
            recommendations=recommendations,
        )

    def approve_pattern(self, pattern_key: str) -> Optional[LearnedPattern]:
        """人工审核通过一个模式。"""
        if pattern_key in self._learned_patterns:
            lp = self._learned_patterns[pattern_key]
            lp.status = "approved"
            self._approved_patterns.append(lp)
            logger.info("AntiAILearning: 模式 '%s' 已审核通过", lp.name)
            return lp
        return None

    def reject_pattern(self, pattern_key: str) -> Optional[LearnedPattern]:
        """人工审核拒绝一个模式。"""
        if pattern_key in self._learned_patterns:
            lp = self._learned_patterns[pattern_key]
            lp.status = "rejected"
            logger.info("AntiAILearning: 模式 '%s' 已拒绝", lp.name)
            return lp
        return None

    def get_approved_patterns(self) -> List[Tuple[str, str, str, str, str]]:
        """获取已审核通过的模式列表（兼容 cliche_scanner 格式）。

        Returns:
            [(regex, name, severity, category, replacement_hint), ...]
        """
        return [
            (p.pattern, p.name, p.suggested_severity, p.suggested_category, "从学习服务导入")
            for p in self._approved_patterns
        ]

    def get_pending_patterns(self) -> List[LearnedPattern]:
        """获取待审核的模式列表。"""
        return [
            p for p in self._learned_patterns.values()
            if p.status == "pending" and p.confidence >= self.MIN_CONFIDENCE_FOR_SUGGESTION
        ]

    def compute_severity_adjustments(
        self,
        novel_id: str,
        known_patterns: List[Tuple[str, str, str, str, str]],
        chapter_hit_counts: Dict[str, int],
        total_chapters: int,
    ) -> Dict[str, str]:
        """根据历史数据计算已知模式的严重性调整建议。

        Args:
            novel_id: 小说 ID
            known_patterns: 已知模式列表 [(regex, name, severity, category, hint), ...]
            chapter_hit_counts: {pattern_name: 出现在多少章节}
            total_chapters: 总章节数

        Returns:
            {pattern_name: suggested_new_severity}
        """
        adjustments = {}
        if total_chapters <= 0:
            return adjustments

        for regex, name, severity, category, hint in known_patterns:
            chapters_hit = chapter_hit_counts.get(name, 0)
            ratio = chapters_hit / total_chapters

            if severity == "warning" and ratio >= self.SEVERITY_ADJUSTMENT_RULES["warning_to_critical_threshold"]:
                adjustments[name] = "critical"
            elif severity == "info" and ratio >= self.SEVERITY_ADJUSTMENT_RULES["info_to_warning_threshold"]:
                adjustments[name] = "warning"

        return adjustments

    def _is_known_pattern(self, text: str, hits: List[Any]) -> bool:
        """检查文本是否已被已知规则命中。"""
        for h in hits:
            hit_text = getattr(h, 'text', '')
            if hit_text and hit_text in text:
                return True
        return False

    def _extract_surrounding_texts(
        self,
        content: str,
        hits: List[Any],
        context_chars: int = 30,
    ) -> List[str]:
        """提取命中点周围的文本。"""
        texts = []
        for h in hits:
            start = getattr(h, 'start', 0)
            end = getattr(h, 'end', 0)
            if start <= 0 or end <= 0:
                continue

            # 取命中点前后各 context_chars 个字符
            ctx_start = max(0, start - context_chars)
            ctx_end = min(len(content), end + context_chars)
            surrounding = content[ctx_start:ctx_end].strip()
            if surrounding:
                texts.append(surrounding)

        return texts

    def _cleanup_patterns(self) -> None:
        """清理低置信度的旧模式，防止积累过多。"""
        if len(self._learned_patterns) <= self.MAX_PENDING_PATTERNS:
            return

        # 移除最低置信度的 pending 模式
        pending = [
            (key, p) for key, p in self._learned_patterns.items()
            if p.status == "pending"
        ]
        pending.sort(key=lambda x: x[1].confidence)

        to_remove = len(self._learned_patterns) - self.MAX_PENDING_PATTERNS
        for i in range(min(to_remove, len(pending))):
            key = pending[i][0]
            del self._learned_patterns[key]

        logger.debug("AntiAILearning: 清理了 %d 个低置信度模式", to_remove)


# 全局单例
_service: Optional[AntiAILearningService] = None


def get_anti_ai_learning_service() -> AntiAILearningService:
    """获取全局 Anti-AI 学习服务。"""
    global _service
    if _service is None:
        _service = AntiAILearningService()
    return _service
