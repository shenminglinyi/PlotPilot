"""QualityGuardrail总控 — 六维度质量检查

核心设计：
- enforce模式：Checkpoint保存前拦截，不达标则阻止保存
- advise模式：提供建议但不阻止
- 六维度检查：语言风格/角色一致性/情节密度/命名/视角/节奏
- QualityViolationError：质量违规异常

集成流程：
1. advance_plot() 生成章节内容
2. QualityGuardrail.enforce() 检查
3. 通过 → 创建Checkpoint
4. 不通过 → 抛出QualityViolationError，返回修正建议
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple

from engine.core.value_objects.character_mask import CharacterMask
from engine.application.quality_guardrails.language_style_guardrail import (
    LanguageStyleGuardrail, StyleViolation,
)
from engine.application.quality_guardrails.character_consistency_guardrail import (
    CharacterConsistencyGuardrail, ConsistencyViolation,
)
from engine.application.quality_guardrails.plot_density_guardrail import (
    PlotDensityGuardrail, DensityViolation,
)
from engine.application.quality_guardrails.naming_guardrail import (
    NamingGuardrail, NamingViolation,
)
from engine.application.quality_guardrails.viewpoint_guardrail import (
    ViewpointGuardrail, ViewpointViolation,
)
from engine.application.quality_guardrails.rhythm_guardrail import (
    RhythmGuardrail, RhythmViolation,
)

logger = logging.getLogger(__name__)


class QualityViolationError(Exception):
    """质量违规异常 — Checkpoint保存前拦截"""

    def __init__(self, violations: List[Dict[str, Any]], overall_score: float):
        self.violations = violations
        self.overall_score = overall_score
        message = f"质量检查不通过(评分{overall_score:.2f})，共{len(violations)}项违规"
        super().__init__(message)


@dataclass
class QualityReport:
    """质量检查报告"""
    overall_score: float = 0.0
    language_style_score: float = 0.0
    character_consistency_score: float = 0.0
    plot_density_score: float = 0.0
    naming_score: float = 0.0
    viewpoint_score: float = 0.0
    rhythm_score: float = 0.0
    all_violations: List[Dict[str, Any]] = field(default_factory=list)
    passed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_score": round(self.overall_score, 3),
            "scores": {
                "language_style": round(self.language_style_score, 3),
                "character_consistency": round(self.character_consistency_score, 3),
                "plot_density": round(self.plot_density_score, 3),
                "naming": round(self.naming_score, 3),
                "viewpoint": round(self.viewpoint_score, 3),
                "rhythm": round(self.rhythm_score, 3),
            },
            "violation_count": len(self.all_violations),
            "violations": self.all_violations,
            "passed": self.passed,
        }


class QualityGuardrail:
    """质量守门人总控

    使用方式：
    ```python
    guardrail = QualityGuardrail()

    # enforce模式：Checkpoint保存前拦截
    try:
        report = guardrail.enforce(text, character_masks, ...)
        # 通过 → 创建Checkpoint
    except QualityViolationError as e:
        # 不通过 → 修正后重写

    # advise模式：仅提供建议
    report = guardrail.advise(text, character_masks, ...)
    ```
    """

    # 最低通过分数
    MIN_PASS_SCORE = 0.6

    def __init__(self):
        self._language_style = LanguageStyleGuardrail()
        self._character_consistency = CharacterConsistencyGuardrail()
        self._plot_density = PlotDensityGuardrail()
        self._naming = NamingGuardrail()
        self._viewpoint = ViewpointGuardrail()
        self._rhythm = RhythmGuardrail()

    def check(
        self,
        text: str,
        character_masks: Dict[str, CharacterMask] = None,
        chapter_goal: str = "",
        character_names: List[str] = None,
        scene_info: Dict[str, Any] = None,
        foreshadows: List[Dict[str, Any]] = None,
        era: str = "ancient",
        scene_type: str = "auto",
    ) -> QualityReport:
        """执行六维度质量检查

        Args:
            text: 待检查文本
            character_masks: 角色面具字典
            chapter_goal: 章节目标
            character_names: 角色名列表
            scene_info: 场景信息
            foreshadows: 活跃伏笔列表
            era: 时代背景
            scene_type: 场景类型

        Returns:
            QualityReport
        """
        violations: List[Dict[str, Any]] = []

        # 1. 语言风格
        ls_score, ls_violations = self._language_style.check(text)
        for v in ls_violations:
            violations.append({
                "dimension": "language_style",
                "type": v.type_name,
                "severity": v.severity,
                "original": v.original_text,
                "suggestion": v.suggestion,
            })

        # 2. 角色一致性
        cc_score = 1.0
        if character_masks:
            cc_score, cc_violations = self._character_consistency.check(text, character_masks)
            for v in cc_violations:
                violations.append({
                    "dimension": "character_consistency",
                    "type": v.type_name,
                    "character": v.character_name,
                    "severity": v.severity,
                    "description": v.description,
                    "suggestion": v.suggestion,
                })

        # 3. 情节密度
        pd_score, pd_violations = self._plot_density.check(text, chapter_goal)
        for v in pd_violations:
            violations.append({
                "dimension": "plot_density",
                "type": v.violation_type,
                "severity": v.severity,
                "description": v.description,
                "suggestion": v.suggestion,
            })

        # 4. 命名
        n_score = 1.0
        if character_names:
            n_score, n_violations = self._naming.check(character_names, era)
            for v in n_violations:
                violations.append({
                    "dimension": "naming",
                    "type": v.type_name,
                    "character": v.character_name,
                    "severity": v.severity,
                    "suggestion": v.suggestion,
                })

        # 5. 视角
        vp_score = 1.0
        if scene_info:
            vp_score, vp_violations = self._viewpoint.check(text, scene_info, foreshadows)
            for v in vp_violations:
                violations.append({
                    "dimension": "viewpoint",
                    "type": v.type_name,
                    "severity": v.severity,
                    "description": v.description,
                    "suggestion": v.suggestion,
                })

        # 6. 节奏
        r_score, r_violations = self._rhythm.check(text, scene_type)
        for v in r_violations:
            violations.append({
                "dimension": "rhythm",
                "type": v.type_name,
                "severity": v.severity,
                "description": v.description,
                "suggestion": v.suggestion,
            })

        # 加权计算总分
        overall = (
            ls_score * 0.25 +
            cc_score * 0.25 +
            pd_score * 0.20 +
            n_score * 0.05 +
            vp_score * 0.10 +
            r_score * 0.15
        )

        return QualityReport(
            overall_score=overall,
            language_style_score=ls_score,
            character_consistency_score=cc_score,
            plot_density_score=pd_score,
            naming_score=n_score,
            viewpoint_score=vp_score,
            rhythm_score=r_score,
            all_violations=violations,
            passed=overall >= self.MIN_PASS_SCORE and len(violations) == 0,
        )

    def enforce(
        self,
        text: str,
        character_masks: Dict[str, CharacterMask] = None,
        chapter_goal: str = "",
        character_names: List[str] = None,
        scene_info: Dict[str, Any] = None,
        foreshadows: List[Dict[str, Any]] = None,
        era: str = "ancient",
        scene_type: str = "auto",
        min_score: float = None,
    ) -> QualityReport:
        """强制执行质量检查（Checkpoint保存前拦截）

        不达标则抛出QualityViolationError

        Args:
            同check()

        Returns:
            QualityReport（通过时）

        Raises:
            QualityViolationError: 质量不达标时
        """
        report = self.check(
            text=text,
            character_masks=character_masks,
            chapter_goal=chapter_goal,
            character_names=character_names,
            scene_info=scene_info,
            foreshadows=foreshadows,
            era=era,
            scene_type=scene_type,
        )

        threshold = min_score or self.MIN_PASS_SCORE

        if report.overall_score < threshold:
            raise QualityViolationError(
                violations=report.all_violations,
                overall_score=report.overall_score,
            )

        return report

    def advise(
        self,
        text: str,
        character_masks: Dict[str, CharacterMask] = None,
        chapter_goal: str = "",
        character_names: List[str] = None,
        scene_info: Dict[str, Any] = None,
        foreshadows: List[Dict[str, Any]] = None,
        era: str = "ancient",
        scene_type: str = "auto",
    ) -> QualityReport:
        """建议模式（不拦截，仅提供建议）"""
        return self.check(
            text=text,
            character_masks=character_masks,
            chapter_goal=chapter_goal,
            character_names=character_names,
            scene_info=scene_info,
            foreshadows=foreshadows,
            era=era,
            scene_type=scene_type,
        )
