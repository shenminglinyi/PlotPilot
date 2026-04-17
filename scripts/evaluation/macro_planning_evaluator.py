"""宏观规划评测器 - 使用项目现有服务

评测宏观规划生成能力。
"""

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from .base_evaluator import (
    BaseEvaluator,
    EvaluationResult,
    create_metric,
)


class MacroPlanningEvaluator(BaseEvaluator):
    """宏观规划评测器"""

    @property
    def name(self) -> str:
        return "macro_planning"

    def get_test_cases(self) -> List[Dict[str, Any]]:
        """获取测试用例"""
        return [
            {
                "name": "玄幻长篇规划",
                "target_chapters": 300,
                "worldview": "修仙世界，分为凡人界和灵界。主角是从地球穿越而来的程序员，带着一个可以分析万物属性的金手指。",
                "characters": ["林尘", "苏婉儿", "陈傲天"],
                "expected_structure": {"min_parts": 3, "max_parts": 6},
            },
            {
                "name": "都市短篇规划",
                "target_chapters": 50,
                "worldview": "现代都市，互联网行业背景。主角是被裁员的程序员，意外获得预测未来的系统。",
                "characters": ["张明", "李薇"],
                "expected_structure": {"min_parts": 1, "max_parts": 2},
            },
        ]

    async def run_single_test(self, test_case: Dict[str, Any]) -> EvaluationResult:
        """运行单个测试"""
        import time
        start_time = time.time()

        try:
            # 直接使用LLM
            llm = self._get_service("llm")
            from domain.ai.value_objects.prompt import Prompt
            from domain.ai.services.llm_service import GenerationConfig

            system_prompt = """你是一位狂热且极具市场敏锐度的顶级网文主编，精通各种爆款商业节奏。

# 叙事结构理论指导
你设计的结构应符合以下经典叙事原理：
1. 三幕剧结构：Setup（设定）→ Confrontation（对抗）→ Resolution（解决）
2. 英雄之旅：平凡世界→冒险召唤→试炼→深渊→蜕变→归来
3. 情绪曲线：开篇抓人→中段起伏→终局爆发

# 输出格式
请直接输出JSON，包含以下字段：
- "parts": 部列表，每部含 "title", "volumes"
- "volumes": 卷列表，每卷含 "title", "acts"
- "acts": 幕列表，每幕必须含：
  - "title": 幕标题
  - "core_conflict": "谁 vs 谁，赌注是什么"
  - "emotional_turn": "情绪反转"
  - "description": "情节摘要"

不要添加任何解释性文字。"""

            user_prompt = f"""目标章节数：{test_case.get('target_chapters', 100)}

【世界观】
{test_case.get('worldview', '')}

【主要角色】
{', '.join(test_case.get('characters', []))}

请生成完整的叙事结构规划。"""

            prompt = Prompt(system=system_prompt, user=user_prompt)
            config = GenerationConfig(max_tokens=4096, temperature=0.8)

            result = await llm.generate(prompt, config)
            content = result.content
            duration = time.time() - start_time

            # 解析JSON
            structure = self._parse_json(content)

            # 评测
            metrics = self._evaluate_structure(structure, test_case)
            success = all(m.passed for m in metrics)

            return EvaluationResult(
                test_name=test_case["name"],
                success=success,
                metrics=metrics,
                input_data={
                    "target_chapters": test_case.get("target_chapters"),
                },
                output_data=structure if structure else content[:300],
                duration_seconds=duration,
                token_usage={
                    "input": result.token_usage.input_tokens,
                    "output": result.token_usage.output_tokens,
                },
            )

        except Exception as e:
            duration = time.time() - start_time
            return EvaluationResult(
                test_name=test_case["name"],
                success=False,
                error=str(e),
                duration_seconds=duration,
            )

    def _parse_json(self, content: str) -> Dict:
        """解析JSON"""
        try:
            return json.loads(content)
        except:
            pass

        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', content)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except:
                pass

        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except:
                pass

        return {}

    def _evaluate_structure(self, structure: Dict, test_case: Dict) -> List:
        """评测规划结构"""
        metrics = []

        parts = structure.get("parts", [])

        # 1. 结构合理性
        structure_score, structure_details = self._evaluate_structure_quality(parts, test_case)
        metrics.append(create_metric(
            name="结构合理性",
            score=structure_score,
            weight=1.5,
            details=structure_details,
        ))

        # 2. 冲突设计
        conflict_score, conflict_details = self._evaluate_conflicts(parts)
        metrics.append(create_metric(
            name="冲突设计",
            score=conflict_score,
            weight=1.4,
            details=conflict_details,
        ))

        # 3. 情绪曲线
        emotion_score, emotion_details = self._evaluate_emotional_arc(parts)
        metrics.append(create_metric(
            name="情绪曲线",
            score=emotion_score,
            weight=1.2,
            details=emotion_details,
        ))

        # 4. 标题质量
        title_score, title_details = self._evaluate_titles(parts)
        metrics.append(create_metric(
            name="标题吸引力",
            score=title_score,
            weight=0.8,
            details=title_details,
        ))

        return metrics

    def _evaluate_structure_quality(self, parts: List, test_case: Dict) -> tuple:
        """评测结构质量"""
        if not parts:
            return 2.0, "缺少部结构"

        expected = test_case.get("expected_structure", {})
        min_parts = expected.get("min_parts", 1)
        max_parts = expected.get("max_parts", 10)

        score = 5.0
        details = []

        num_parts = len(parts)
        if min_parts <= num_parts <= max_parts:
            score += 2.0
            details.append(f"部数量合理({num_parts}部)")
        else:
            details.append(f"部数量异常({num_parts}部)")

        total_volumes = 0
        total_acts = 0

        for part in parts:
            volumes = part.get("volumes", [])
            total_volumes += len(volumes)
            for vol in volumes:
                acts = vol.get("acts", [])
                total_acts += len(acts)

        if total_volumes >= num_parts:
            score += 1.5
            details.append(f"卷结构完整({total_volumes}卷)")

        if total_acts >= total_volumes * 2:
            score += 1.5
            details.append(f"幕结构丰富({total_acts}幕)")

        return min(score, 10.0), "; ".join(details)

    def _evaluate_conflicts(self, parts: List) -> tuple:
        """评测冲突设计"""
        if not parts:
            return 2.0, "无法评测"

        acts_with_conflict = 0
        total_acts = 0

        for part in parts:
            for vol in part.get("volumes", []):
                for act in vol.get("acts", []):
                    total_acts += 1
                    conflict = act.get("core_conflict", "")
                    if conflict and len(conflict) > 5:
                        acts_with_conflict += 1

        if total_acts == 0:
            return 3.0, "没有幕结构"

        conflict_ratio = acts_with_conflict / total_acts
        score = 3.0 + conflict_ratio * 5.0
        details = f"冲突覆盖率: {conflict_ratio:.0%} ({acts_with_conflict}/{total_acts}幕)"

        return min(score, 10.0), details

    def _evaluate_emotional_arc(self, parts: List) -> tuple:
        """评测情绪曲线"""
        emotions = []

        for part in parts:
            for vol in part.get("volumes", []):
                for act in vol.get("acts", []):
                    emotion = act.get("emotional_turn", "")
                    if emotion:
                        emotions.append(emotion)

        if not emotions:
            return 5.0, "无明确情绪设计"

        score = 5.0
        details = [f"设计了{len(emotions)}处情绪转折"]

        positive_words = ["希望", "喜悦", "胜利", "成功"]
        negative_words = ["绝望", "悲伤", "失败", "牺牲"]

        has_positive = any(any(pw in e for pw in positive_words) for e in emotions)
        has_negative = any(any(nw in e for nw in negative_words) for e in emotions)

        if has_positive and has_negative:
            score += 3.0
            details.append("情绪有正负变化")
        elif has_positive or has_negative:
            score += 1.5
            details.append("情绪有基本设计")

        return min(score, 10.0), "; ".join(details)

    def _evaluate_titles(self, parts: List) -> tuple:
        """评测标题质量"""
        titles = []

        for part in parts:
            if part.get("title"):
                titles.append(part["title"])
            for vol in part.get("volumes", []):
                if vol.get("title"):
                    titles.append(vol["title"])
                for act in vol.get("acts", []):
                    if act.get("title"):
                        titles.append(act["title"])

        if not titles:
            return 3.0, "缺少标题"

        score = 5.0
        details = []

        unique_titles = set(titles)
        if len(unique_titles) == len(titles):
            score += 2.0
            details.append("标题无重复")

        attractive_words = ["血", "战", "杀", "逆", "破", "狂", "霸", "神", "魔", "帝"]
        attractive_count = sum(1 for t in titles for aw in attractive_words if aw in t)
        if attractive_count >= len(titles) * 0.3:
            score += 3.0
            details.append(f"标题有吸引力")

        return min(score, 10.0), "; ".join(details) if details else "标题质量一般"


async def main():
    """运行宏观规划评测"""
    evaluator = MacroPlanningEvaluator()
    report = await evaluator.run_all_tests()

    output_dir = Path(__file__).parent / "results"
    output_path = evaluator.save_results(output_dir)

    print(f"\n评测报告已保存: {output_path}")
    print(f"平均分: {report.average_score:.2f}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
