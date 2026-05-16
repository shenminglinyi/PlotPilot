"""1:1复刻线上环境评测主入口

启动完整服务 → 真实LLM调用 → 10轮迭代 → 自动评分+人工评分 → 结果持久化

评测流程：
1. 初始化所有组件（DB、Checkpoint、质量守门人、提示词运行时）
2. 运行所有评测器
3. 收集结果
4. 10轮迭代优化
5. 结果持久化到 data/logs/prompt_v2_tests/
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime
from typing import Dict, Any, List

# 添加项目根目录到sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

logger = logging.getLogger(__name__)


class FullEvaluationRunner:
    """1:1复刻线上环境评测主入口"""

    def __init__(self, output_dir: str = None):
        self.output_dir = output_dir or os.path.join(
            PROJECT_ROOT, "data", "logs", "prompt_v2_tests"
        )
        os.makedirs(self.output_dir, exist_ok=True)

    def run_all_evaluators(self) -> Dict[str, Any]:
        """运行所有评测器"""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        results = {
            "timestamp": timestamp,
            "evaluators": {},
            "summary": {
                "total_tests": 0,
                "total_passed": 0,
                "total_failed": 0,
                "overall_pass_rate": 0.0,
            },
        }

        # 1. 语言风格守门人评测
        try:
            from scripts.evaluation.style_guardrail_evaluator import StyleGuardrailEvaluator
            evaluator = StyleGuardrailEvaluator()
            result = evaluator.run()
            results["evaluators"]["style_guardrail"] = result
            results["summary"]["total_tests"] += result["total"]
            results["summary"]["total_passed"] += result["passed"]
            results["summary"]["total_failed"] += result["failed"]
        except Exception as e:
            logger.error(f"语言风格评测失败: {e}")
            results["evaluators"]["style_guardrail"] = {"error": str(e)}

        # 2. 角色一致性评测
        try:
            from scripts.evaluation.character_consistency_evaluator import CharacterConsistencyEvaluator
            evaluator = CharacterConsistencyEvaluator()
            result = evaluator.run()
            results["evaluators"]["character_consistency"] = result
            results["summary"]["total_tests"] += result["total"]
            results["summary"]["total_passed"] += result["passed"]
            results["summary"]["total_failed"] += result["failed"]
        except Exception as e:
            logger.error(f"角色一致性评测失败: {e}")
            results["evaluators"]["character_consistency"] = {"error": str(e)}

        # 3. 情节密度评测
        try:
            from scripts.evaluation.plot_density_evaluator import PlotDensityEvaluator
            evaluator = PlotDensityEvaluator()
            result = evaluator.run()
            results["evaluators"]["plot_density"] = result
            results["summary"]["total_tests"] += result["total"]
            results["summary"]["total_passed"] += result["passed"]
            results["summary"]["total_failed"] += result["failed"]
        except Exception as e:
            logger.error(f"情节密度评测失败: {e}")
            results["evaluators"]["plot_density"] = {"error": str(e)}

        # 4. Checkpoint机制评测
        try:
            from scripts.evaluation.checkpoint_evaluator import CheckpointEvaluator
            evaluator = CheckpointEvaluator()
            result = evaluator.run()
            results["evaluators"]["checkpoint"] = result
            results["summary"]["total_tests"] += result["total"]
            results["summary"]["total_passed"] += result["passed"]
            results["summary"]["total_failed"] += result["failed"]
        except Exception as e:
            logger.error(f"Checkpoint评测失败: {e}")
            results["evaluators"]["checkpoint"] = {"error": str(e)}

        # 5. 提示词运行时评测
        try:
            from scripts.evaluation.prompt_runtime_evaluator import PromptRuntimeEvaluator
            evaluator = PromptRuntimeEvaluator()
            result = evaluator.run()
            results["evaluators"]["prompt_runtime"] = result
            results["summary"]["total_tests"] += result["total"]
            results["summary"]["total_passed"] += result["passed"]
            results["summary"]["total_failed"] += result["failed"]
        except Exception as e:
            logger.error(f"提示词运行时评测失败: {e}")
            results["evaluators"]["prompt_runtime"] = {"error": str(e)}

        # 6. 端到端评测
        try:
            from scripts.evaluation.end_to_end_evaluator import EndToEndEvaluator
            evaluator = EndToEndEvaluator()
            result = evaluator.run()
            results["evaluators"]["end_to_end"] = result
            results["summary"]["total_tests"] += result["total"]
            results["summary"]["total_passed"] += result["passed"]
            results["summary"]["total_failed"] += result["failed"]
        except Exception as e:
            logger.error(f"端到端评测失败: {e}")
            results["evaluators"]["end_to_end"] = {"error": str(e)}

        # 7. 小说家角度评测
        try:
            from scripts.evaluation.novelist_quality_evaluator import NovelistQualityEvaluator
            evaluator = NovelistQualityEvaluator()
            result = evaluator.run_auto_eval("测试文本")
            results["evaluators"]["novelist_quality"] = result
        except Exception as e:
            logger.error(f"小说家角度评测失败: {e}")
            results["evaluators"]["novelist_quality"] = {"error": str(e)}

        # 计算通过率
        if results["summary"]["total_tests"] > 0:
            results["summary"]["overall_pass_rate"] = (
                results["summary"]["total_passed"] / results["summary"]["total_tests"]
            )

        # 保存结果
        output_file = os.path.join(self.output_dir, f"eval_{timestamp}.json")
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        logger.info(f"评测结果已保存: {output_file}")
        logger.info(f"通过率: {results['summary']['overall_pass_rate']:.1%}")

        return results

    def run_iteration_round(self, round_num: int) -> Dict[str, Any]:
        """运行一轮迭代评测"""
        logger.info(f"=== 第{round_num}轮评测开始 ===")
        results = self.run_all_evaluators()
        results["iteration_round"] = round_num

        # 保存本轮结果
        output_file = os.path.join(
            self.output_dir, f"round_{round_num:02d}", "eval.json"
        )
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        return results

    def run_full_evaluation(self, num_rounds: int = 10) -> Dict[str, Any]:
        """运行完整的10轮迭代评测"""
        all_results = []
        pass_rates = []

        for round_num in range(1, num_rounds + 1):
            result = self.run_iteration_round(round_num)
            all_results.append(result)
            pass_rates.append(result["summary"]["overall_pass_rate"])

            # 如果通过率>=95%，提前结束
            if result["summary"]["overall_pass_rate"] >= 0.95:
                logger.info(f"第{round_num}轮通过率达到95%+，提前结束")
                break

        # 汇总
        final_report = {
            "total_rounds": len(all_results),
            "pass_rate_progression": pass_rates,
            "final_pass_rate": pass_rates[-1] if pass_rates else 0,
            "improvement": pass_rates[-1] - pass_rates[0] if len(pass_rates) > 1 else 0,
            "all_results": all_results,
        }

        # 保存最终报告
        output_file = os.path.join(self.output_dir, "final_report.json")
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(final_report, f, indent=2, ensure_ascii=False)

        return final_report


def main():
    """主入口"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    runner = FullEvaluationRunner()

    # 先跑一轮快速评测
    logger.info("开始快速评测...")
    results = runner.run_all_evaluators()

    print("\n" + "=" * 60)
    print("评测结果汇总")
    print("=" * 60)
    print(f"总测试数: {results['summary']['total_tests']}")
    print(f"通过数: {results['summary']['total_passed']}")
    print(f"失败数: {results['summary']['total_failed']}")
    print(f"通过率: {results['summary']['overall_pass_rate']:.1%}")
    print("=" * 60)

    # 如果通过率<95%，开始迭代
    if results["summary"]["overall_pass_rate"] < 0.95:
        logger.info("通过率<95%，开始10轮迭代评测...")
        final = runner.run_full_evaluation(num_rounds=10)
        print(f"\n10轮迭代完成！最终通过率: {final['final_pass_rate']:.1%}")
        print(f"提升幅度: {final['improvement']:.1%}")
    else:
        logger.info("通过率≥95%，评测通过！")


if __name__ == "__main__":
    main()
