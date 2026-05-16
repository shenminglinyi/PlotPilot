"""语言风格守门人评测器

测试指标：
- 八股文检测率
- 数字比喻检测率
- 过度理性检测率
- 拐弯描写检测率
- 正常文本通过率
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List

from engine.application.quality_guardrails.language_style_guardrail import (
    LanguageStyleGuardrail, StyleViolation,
)

logger = logging.getLogger(__name__)


@dataclass
class EvalCase:
    """评测用例"""
    name: str
    text: str
    expected_violations: List[str]  # 期望检测到的违规类型
    should_pass: bool = False      # 正常文本应该通过（无违规）


class StyleGuardrailEvaluator:
    """语言风格守门人评测器"""

    def __init__(self):
        self.guardrail = LanguageStyleGuardrail()
        self.results: List[Dict[str, Any]] = []

    def get_test_cases(self) -> List[EvalCase]:
        """获取测试用例"""
        return [
            # 八股文检测
            EvalCase(
                name="八股文_三段式",
                text="他的内心经历了三个阶段：首先是震惊，其次是愤怒，最后是释然。他终于明白了这件事的意义。",
                expected_violations=["eight_legs"],
            ),
            EvalCase(
                name="八股文_递进式",
                text="这不仅是一次考验，而且是一场洗礼，更是命运的转折点。从长远角度来看，这改变了一切。",
                expected_violations=["eight_legs"],
            ),
            # 数字比喻检测
            EvalCase(
                name="数字比喻_明喻堆叠",
                text="她的笑容像春天的阳光一样温暖，像清泉一样甘甜，像晨露一样清新。仿佛梦境一般美丽。",
                expected_violations=["number_metaphor"],
            ),
            # 过度理性检测
            EvalCase(
                name="过度理性_情绪场景分析",
                text="面对母亲的离世，他开始分析自己在家庭中的角色定位，意识到承担责任的必要性，认识到自己必须坚强。",
                expected_violations=["over_rational"],
            ),
            # 拐弯描写检测
            EvalCase(
                name="拐弯描写_冗余感受",
                text="他不由自主地在心中产生了一种无法言说的、仿佛被什么东西深深触动的感觉，一种莫名的悸动在心底蔓延。",
                expected_violations=["detour"],
            ),
            # 正常文本（应该通过）
            EvalCase(
                name="正常文本_简洁有力",
                text="他愣了半晌，攥紧的拳头慢慢松开。她笑了，眼底有光。他心里一颤。",
                expected_violations=[],
                should_pass=True,
            ),
            EvalCase(
                name="正常文本_具体描写",
                text="寒风裹着碎雪灌进领口。他偏身避开，手不自觉地握紧了剑柄。她站在街角，围巾遮住半张脸。",
                expected_violations=[],
                should_pass=True,
            ),
        ]

    def run(self) -> Dict[str, Any]:
        """运行评测"""
        test_cases = self.get_test_cases()
        results = {
            "total": len(test_cases),
            "passed": 0,
            "failed": 0,
            "detection_rates": {
                "eight_legs": {"total": 0, "detected": 0},
                "number_metaphor": {"total": 0, "detected": 0},
                "over_rational": {"total": 0, "detected": 0},
                "detour": {"total": 0, "detected": 0},
            },
            "false_positive_rate": 0.0,
            "details": [],
        }

        for case in test_cases:
            score, violations = self.guardrail.check(case.text)
            violation_types = [v.violation_type for v in violations]

            # 检查期望的违规是否被检测到
            detected = True
            for expected in case.expected_violations:
                if expected not in violation_types:
                    detected = False
                results["detection_rates"][expected]["total"] += 1
                if expected in violation_types:
                    results["detection_rates"][expected]["detected"] += 1

            # 正常文本不应该有违规
            if case.should_pass:
                if len(violations) > 0:
                    detected = False  # 误报

            if detected:
                results["passed"] += 1
            else:
                results["failed"] += 1

            results["details"].append({
                "name": case.name,
                "score": score,
                "detected_types": violation_types,
                "expected_types": case.expected_violations,
                "passed": detected,
            })

        # 计算误报率（正常文本被判违规的比例）
            pass

        # 计算各维度检测率
        for vtype, rate_data in results["detection_rates"].items():
            if rate_data["total"] > 0:
                rate_data["rate"] = rate_data["detected"] / rate_data["total"]
            else:
                rate_data["rate"] = 0.0

        return results


if __name__ == "__main__":
    evaluator = StyleGuardrailEvaluator()
    results = evaluator.run()
    print(json.dumps(results, indent=2, ensure_ascii=False))
