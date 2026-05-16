"""情节密度守门人评测器

测试指标：
- 无功能形容词识别率
- 无效段落识别率
- 信息密度评分
- 章节目标推进率
"""
from __future__ import annotations

import json
import logging
from typing import Dict, Any, List

from engine.application.quality_guardrails.plot_density_guardrail import PlotDensityGuardrail

logger = logging.getLogger(__name__)


class PlotDensityEvaluator:
    """情节密度守门人评测器"""

    def __init__(self):
        self.guardrail = PlotDensityGuardrail()

    def get_test_cases(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "形容词堆叠",
                "text": "寒冷的冰冷的刺骨的寒风吹过空旷的原野，带来了一种深沉的凝重的压抑的气氛。他不由得默默地轻轻地缓缓地叹了一口气。",
                "chapter_goal": "推进剧情",
                "expected_violations": ["non_functional_adj"],
            },
            {
                "name": "无效段落_纯风景",
                "text": "远处群山连绵，白云悠悠，一条小溪蜿蜒穿过青翠的草地。阳光洒在每一片叶子上，露珠折射出七彩的光芒。鸟儿在枝头歌唱，蝴蝶在花间起舞。这片宁静祥和的景象让人心旷神怡，流连忘返。此时此刻，世间一切烦恼仿佛都消散在这片仙境之中。",
                "chapter_goal": "推进紧张剧情",
                "expected_violations": ["no_goal_progression"],
            },
            {
                "name": "高密度有效段落",
                "text": "他推开门，发现了那封信。信上的字迹他认得——是师父的。'如果看到这封信，说明我已经不在了。'他握紧了拳头。门后传来脚步声，他猛地转身，剑已出鞘。",
                "chapter_goal": "发现真相",
                "expected_violations": [],
            },
        ]

    def run(self) -> Dict[str, Any]:
        test_cases = self.get_test_cases()
        results = {
            "total": len(test_cases),
            "passed": 0,
            "failed": 0,
            "details": [],
        }

        for case in test_cases:
            score, violations = self.guardrail.check(case["text"], case["chapter_goal"])
            violation_types = [v.violation_type for v in violations]

            detected = True
            for expected in case["expected_violations"]:
                if expected not in violation_types:
                    detected = False

            if not case["expected_violations"] and not violation_types:
                detected = True

            if detected:
                results["passed"] += 1
            else:
                results["failed"] += 1

            results["details"].append({
                "name": case["name"],
                "score": score,
                "density_score": self.guardrail.compute_density_score(case["text"]),
                "detected_types": violation_types,
                "expected_types": case["expected_violations"],
                "passed": detected,
            })

        return results


if __name__ == "__main__":
    evaluator = PlotDensityEvaluator()
    results = evaluator.run()
    print(json.dumps(results, indent=2, ensure_ascii=False))
