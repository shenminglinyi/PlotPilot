"""角色一致性守门人评测器

测试指标：
- OOC检测准确率
- 语言指纹一致性
- 创伤反应验证
- 四维模型覆盖度
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Dict, Any, List

from engine.application.quality_guardrails.character_consistency_guardrail import (
    CharacterConsistencyGuardrail, ConsistencyViolation,
)
from engine.core.value_objects.character_mask import CharacterMask

logger = logging.getLogger(__name__)


class CharacterConsistencyEvaluator:
    """角色一致性守门人评测器"""

    def __init__(self):
        self.guardrail = CharacterConsistencyGuardrail()

    def get_test_masks(self) -> Dict[str, CharacterMask]:
        """获取测试角色面具"""
        return {
            "lin_yu": CharacterMask(
                character_id="lin_yu",
                name="林羽",
                core_belief="信任是致命的软肋，轻信必死",
                moral_taboos=["绝不杀手无寸铁之人"],
                voice_style="惜字如金",
                sentence_pattern="陈述",
                active_wounds=[
                    {"description": "左肩被恩师刺伤", "trigger": "有人靠近左后方", "effect": "肌肉下意识紧绷"},
                ],
                chapter_number=50,
            ),
            "su_yan": CharacterMask(
                character_id="su_yan",
                name="苏言",
                core_belief="真相终将大白",
                voice_style="话多",
                sentence_pattern="反问",
                active_wounds=[],
                chapter_number=30,
            ),
        }

    def get_test_cases(self) -> List[Dict[str, Any]]:
        """获取测试用例"""
        return [
            {
                "name": "OOC_轻易信任",
                "text": "林羽毫不犹豫地相信了陌生人的话，放心地跟着他走了。",
                "masks": ["lin_yu"],
                "expected_violations": ["ooc"],
            },
            {
                "name": "语言指纹_惜字如金说长句",
                "text": "林羽看着远方，长叹一声说道：\u201c这件事的来龙去脉我已经完全想明白了，我们必须立刻采取行动，不能再犹豫了。\u201d",
                "masks": ["lin_yu"],
                "expected_violations": ["voice_mismatch"],
            },
            {
                "name": "创伤反应_触发条件缺失",
                "text": "一个人悄悄站在林羽左后方。林羽继续喝茶，毫无反应，表情毫无变化。",
                "masks": ["lin_yu"],
                "expected_violations": ["wound_trigger_miss"],
            },
            {
                "name": "正常_符合面具",
                "text": "林羽扫了一眼来人，手不自觉地握紧了剑柄。'说。'他只吐出一个字。",
                "masks": ["lin_yu"],
                "expected_violations": [],
            },
        ]

    def run(self) -> Dict[str, Any]:
        """运行评测"""
        all_masks = self.get_test_masks()
        test_cases = self.get_test_cases()

        results = {
            "total": len(test_cases),
            "passed": 0,
            "failed": 0,
            "detection_rates": {
                "ooc": {"total": 0, "detected": 0},
                "voice_mismatch": {"total": 0, "detected": 0},
                "wound_trigger_miss": {"total": 0, "detected": 0},
            },
            "details": [],
        }

        for case in test_cases:
            masks = {k: all_masks[k] for k in case["masks"] if k in all_masks}
            score, violations = self.guardrail.check(case["text"], masks)
            violation_types = [v.violation_type for v in violations]

            detected = True
            for expected in case["expected_violations"]:
                if expected not in violation_types:
                    detected = False
                if expected in results["detection_rates"]:
                    results["detection_rates"][expected]["total"] += 1
                    if expected in violation_types:
                        results["detection_rates"][expected]["detected"] += 1

            if not case["expected_violations"] and not violation_types:
                detected = True

            if detected:
                results["passed"] += 1
            else:
                results["failed"] += 1

            results["details"].append({
                "name": case["name"],
                "score": score,
                "detected_types": violation_types,
                "expected_types": case["expected_violations"],
                "passed": detected,
            })

        for vtype, rate_data in results["detection_rates"].items():
            if rate_data["total"] > 0:
                rate_data["rate"] = rate_data["detected"] / rate_data["total"]

        return results


if __name__ == "__main__":
    evaluator = CharacterConsistencyEvaluator()
    results = evaluator.run()
    print(json.dumps(results, indent=2, ensure_ascii=False))
