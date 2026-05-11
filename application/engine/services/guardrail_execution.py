"""质量护栏执行（与 HTTP guardrail/check 同源逻辑），供章后管线与路由复用。"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def normalize_violation_severity_for_api(severity: Any) -> str:
    """将引擎侧 0–1 数值严重度或已有字符串转为 API/前端使用的标签。"""
    if isinstance(severity, (int, float)):
        x = float(severity)
        if x >= 0.75:
            return "error"
        if x >= 0.45:
            return "warning"
        return "info"
    if severity is None:
        return "info"
    s = str(severity).strip()
    return s if s else "info"


DIMENSION_META = [
    ("language_style", "语言风格", 0.25),
    ("character_consistency", "角色一致性", 0.25),
    ("plot_density", "情节密度", 0.20),
    ("naming", "命名", 0.05),
    ("viewpoint", "视角", 0.10),
    ("rhythm", "节奏", 0.15),
]


def _character_masks_for_novel(novel_id: str) -> Dict[str, Any]:
    masks: Dict[str, Any] = {}
    try:
        from engine.core.value_objects.character_mask import CharacterMask
        from interfaces.api.dependencies import get_cast_service

        cast_graph = get_cast_service().get_cast_graph(novel_id)
        for ch in cast_graph.characters or []:
            mask = CharacterMask(
                character_id=getattr(ch, "id", "") or "",
                name=ch.name,
                core_belief="",
            )
            masks[ch.name] = mask
    except Exception:
        pass
    return masks


def _violations_from_quality_error(e: Any) -> List[Dict[str, Any]]:
    violations: List[Dict[str, Any]] = []
    for v in getattr(e, "violations", []) or []:
        if isinstance(v, dict):
            violations.append(
                {
                    "dimension": v.get("dimension", ""),
                    "type": v.get("type", ""),
                    "severity": normalize_violation_severity_for_api(v.get("severity", "error")),
                    "description": v.get("description", str(v)),
                    "original": v.get("original", ""),
                    "suggestion": v.get("suggestion", ""),
                    "character": v.get("character", ""),
                }
            )
        else:
            violations.append(
                {
                    "dimension": "",
                    "type": "",
                    "severity": "error",
                    "description": str(v),
                    "original": "",
                    "suggestion": "",
                    "character": "",
                }
            )
    return violations


def quality_report_to_snapshot_dict(report: Any) -> Dict[str, Any]:
    """将 QualityReport 转为与前端 GuardrailCheckResponse 一致的 dict。"""
    dimensions: List[Dict[str, Any]] = []
    for key, name, weight in DIMENSION_META:
        score = float(getattr(report, f"{key}_score", 0.0) or 0.0)
        dimensions.append({"name": name, "key": key, "score": round(score, 3), "weight": weight})

    violations: List[Dict[str, Any]] = []
    for v in report.all_violations:
        violations.append(
            {
                "dimension": v.get("dimension", ""),
                "type": v.get("type", ""),
                "severity": normalize_violation_severity_for_api(v.get("severity", "info")),
                "description": v.get("description", ""),
                "original": v.get("original", ""),
                "suggestion": v.get("suggestion", ""),
                "character": v.get("character", ""),
            }
        )

    return {
        "overall_score": round(float(report.overall_score), 3),
        "passed": bool(report.passed),
        "dimensions": dimensions,
        "violations": violations,
    }


def run_guardrail_sync(
    novel_id: str,
    text: str,
    chapter_goal: str,
    character_names: Optional[List[str]],
    era: str,
    scene_type: str,
    mode: str,
) -> Dict[str, Any]:
    """同步执行护栏（advise | enforce），返回与前端 GuardrailCheckResponse 一致的 dict。"""
    from interfaces.api.dependencies import get_quality_guardrail
    from engine.runtime.quality_guardrails.quality_guardrail import QualityViolationError

    guardrail = get_quality_guardrail()
    character_masks = _character_masks_for_novel(novel_id) or None

    try:
        if mode == "enforce":
            report = guardrail.enforce(
                text=text,
                character_masks=character_masks,
                chapter_goal=chapter_goal,
                character_names=character_names or None,
                era=era,
                scene_type=scene_type,
            )
        else:
            report = guardrail.advise(
                text=text,
                character_masks=character_masks,
                chapter_goal=chapter_goal,
                character_names=character_names or None,
                era=era,
                scene_type=scene_type,
            )
        return quality_report_to_snapshot_dict(report)
    except QualityViolationError as e:
        return {
            "overall_score": round(float(getattr(e, "overall_score", 0.0) or 0.0), 3),
            "passed": False,
            "dimensions": [],
            "violations": _violations_from_quality_error(e),
        }
    except Exception as e:
        logger.warning("护栏执行失败 novel=%s mode=%s: %s", novel_id, mode, e)
        raise


def run_guardrail_advise_sync(
    novel_id: str,
    text: str,
    chapter_goal: str,
    *,
    character_names: Optional[List[str]] = None,
    era: str = "ancient",
    scene_type: str = "auto",
) -> Dict[str, Any]:
    """保存后自动：建议模式。"""
    return run_guardrail_sync(
        novel_id,
        text,
        chapter_goal,
        character_names,
        era,
        scene_type,
        "advise",
    )
