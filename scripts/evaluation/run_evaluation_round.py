"""多轮API跑文评测 — 自动运行第N轮评测

使用方式:
  python scripts/evaluation/run_evaluation_round.py --round 2 --chapters 5
  python scripts/evaluation/run_evaluation_round.py --round 4 --chapters 20
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

import asyncio
import json
from datetime import datetime

from scripts.evaluation.novel_writing_runner import run_writing_evaluation
from scripts.evaluation.novelist_quality_evaluator import NovelistQualityEvaluator


async def run_round(round_number: int, num_chapters: int):
    print("=" * 70)
    print(f"第{round_number}轮 API跑文评测 — 生成{num_chapters}章")
    print("=" * 70)

    assessment = await run_writing_evaluation(
        num_chapters=num_chapters,
        round_number=round_number,
    )
    if not assessment:
        print("跑文失败，退出")
        return None

    # 小说家评测
    print("\n" + "=" * 70)
    print("小说家角度深度评估")
    print("=" * 70)

    evaluator = NovelistQualityEvaluator()
    output_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "..", "data", "logs", "prompt_v2_tests",
        f"round_{round_number:02d}",
    )
    result_file = os.path.join(output_dir, f"round_{round_number:02d}_results.json")

    if not os.path.exists(result_file):
        print(f"未找到结果文件: {result_file}")
        return assessment

    with open(result_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    chapters = data.get("chapters", [])
    novel_assessment = evaluator.evaluate_novel(chapters)

    print(f"\n评级: {novel_assessment.grade}")
    print(f"总分: {novel_assessment.overall_score:.3f}")
    print(f"\n各维度:")
    for dim in novel_assessment.dimensions:
        print(f"  {dim.name}: {dim.score:.3f} (权重{dim.weight})")

    if novel_assessment.cross_chapter_issues:
        print(f"\n跨章问题:")
        for issue in novel_assessment.cross_chapter_issues:
            print(f"  - {issue}")

    if novel_assessment.improvement_suggestions:
        print(f"\n改进建议:")
        for s in novel_assessment.improvement_suggestions:
            print(f"  - {s}")

    # 保存小说家评测报告
    novel_report = {
        "round": round_number,
        "num_chapters": num_chapters,
        "timestamp": datetime.now().isoformat(),
        "grade": novel_assessment.grade,
        "overall_score": novel_assessment.overall_score,
        "dimensions": [
            {"name": d.name, "score": d.score, "weight": d.weight,
             "weighted_score": d.weighted_score, "details": d.details, "issues": d.issues}
            for d in novel_assessment.dimensions
        ],
        "chapter_scores": novel_assessment.chapter_scores,
        "cross_chapter_issues": novel_assessment.cross_chapter_issues,
        "improvement_suggestions": novel_assessment.improvement_suggestions,
    }

    report_file = os.path.join(output_dir, f"round_{round_number:02d}_novelist_report.json")
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(novel_report, f, ensure_ascii=False, indent=2)
    print(f"\n报告已保存: {report_file}")

    return novel_assessment


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--round", type=int, required=True)
    parser.add_argument("--chapters", type=int, default=5)
    args = parser.parse_args()
    asyncio.run(run_round(args.round, args.chapters))


if __name__ == "__main__":
    main()
