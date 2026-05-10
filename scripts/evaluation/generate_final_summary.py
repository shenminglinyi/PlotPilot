#!/usr/bin/env python3
"""
Generate final summary report for all 5 rounds of evaluation
"""

import os
import json
import datetime
from pathlib import Path

def load_evaluation_results():
    """Load all evaluation results"""
    results = {}
    base_dir = Path("data/logs/prompt_v2_tests")
    
    for round_num in range(6):  # 0-5
        round_dir = base_dir / f"round_{round_num:02d}"
        if round_dir.exists():
            results_file = round_dir / f"round_{round_num:02d}_results.json"
            if results_file.exists():
                with open(results_file, 'r', encoding='utf-8') as f:
                    results[f"round_{round_num:02d}"] = json.load(f)
                    
            novelist_file = round_dir / f"round_{round_num:02d}_novelist_report.json"
            if novelist_file.exists():
                with open(novelist_file, 'r', encoding='utf-8') as f:
                    results[f"round_{round_num:02d}_novelist"] = json.load(f)
    
    return results

def generate_comparison_table(results):
    """Generate comparison table for all rounds"""
    table = []
    headers = ["轮次", "章节数", "总分", "等级", "字数", "语言风格", "角色一致", "情节密度", "伏笔管理", "文笔质量"]
    
    for round_num in range(6):
        round_key = f"round_{round_num:02d}"
        if round_key in results:
            r = results[round_key]
            novelist_key = f"{round_key}_novelist"
            novelist = results.get(novelist_key, {})
            
            row = [
                f"R{round_num}",
                r.get("num_chapters", "-"),
                f"{r.get('assessment', {}).get('overall_score', 0):.3f}",
                r.get("assessment", {}).get("grade", "-"),
                r.get("assessment", {}).get("total_words", "-"),
                f"{r.get('assessment', {}).get('scores', {}).get('language_style', 0):.3f}",
                f"{r.get('assessment', {}).get('scores', {}).get('character_consistency', 0):.3f}",
                f"{r.get('assessment', {}).get('scores', {}).get('plot_density', 0):.3f}",
                f"{novelist.get('overall_score', 0) if novelist else 0:.3f}" if novelist else "-",
                f"{r.get('assessment', {}).get('scores', {}).get('rhythm', 0):.3f}"
            ]
            table.append(row)
    
    return headers, table

def analyze_trends(results):
    """Analyze trends across rounds"""
    trends = {
        "overall_score_trend": [],
        "character_consistency_trend": [],
        "plot_density_trend": [],
        "foreshadow_trend": [],
        "total_violations_trend": []
    }
    
    for round_num in range(6):
        round_key = f"round_{round_num:02d}"
        if round_key in results:
            r = results[round_key]
            novelist_key = f"{round_key}_novelist"
            novelist = results.get(novelist_key, {})
            
            trends["overall_score_trend"].append(r.get("assessment", {}).get("overall_score", 0))
            trends["character_consistency_trend"].append(r.get("assessment", {}).get("scores", {}).get("character_consistency", 0))
            trends["plot_density_trend"].append(r.get("assessment", {}).get("scores", {}).get("plot_density", 0))
            trends["foreshadow_trend"].append(novelist.get("foreshadow_management", {}).get("score", 0) if novelist else 0)
            trends["total_violations_trend"].append(r.get("assessment", {}).get("total_violations", 0))
    
    return trends

def generate_final_report():
    """Generate the final comprehensive report"""
    results = load_evaluation_results()
    
    if not results:
        print("No evaluation results found!")
        return
        
    headers, table = generate_comparison_table(results)
    trends = analyze_trends(results)
    
    report = {
        "生成时间": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "评估轮次": f"R0-R{len([k for k in results.keys() if k.startswith('round_') and not k.endswith('_novelist')])-1}",
        "总结": {
            "总分趋势": "stable" if max(trends["overall_score_trend"]) - min(trends["overall_score_trend"]) < 0.1 else "variable",
            "最佳轮次": max(range(len(trends["overall_score_trend"])), key=lambda i: trends["overall_score_trend"][i]),
            "最差轮次": min(range(len(trends["overall_score_trend"])), key=lambda i: trends["overall_score_trend"][i]),
            "平均总分": sum(trends["overall_score_trend"]) / len(trends["overall_score_trend"]),
            "总违规次数": sum(trends["total_violations_trend"])
        },
        "各维度分析": {
            "角色一致性改进": "需重点关注" if max(trends["character_consistency_trend"]) < 0.8 else "有进步",
            "情节密度优化": "良好" if max(trends["plot_density_trend"]) > 0.7 else "需优化",
            "伏笔管理": "需改善" if max(trends["foreshadow_trend"]) < 0.5 else "有提升",
            "违规控制": "显著改善" if max(trends["total_violations_trend"]) - min(trends["total_violations_trend"]) > 20 else "稳定"
        },
        "详细数据表": {
            "headers": headers,
            "rows": table
        },
        "趋势数据": trends,
        "专业建议": [
            "角色声线特征需要更加突出以解决一致性得分低的问题",
            "跨章节衔接需要加强，确保角色名的自然呼应",
            "伏笔系统需要更均衡的埋设和回收节奏",
            "情节推进需要更稳定的信息密度控制",
            "建议继续优化提示词系统，增强角色辨识度"
        ]
    }
    
    # Save report
    output_dir = Path("data/logs/prompt_v2_tests")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    with open(output_dir / "evaluation_summary.json", 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    print(f"评估报告已生成: {output_dir / 'evaluation_summary.json'}")
    
    # Print summary
    print("\n=== 评测总结 ===")
    print(f"总分趋势: {report['总结']['总分趋势']}")
    print(f"最佳轮次: R{report['总结']['最佳轮次']}")
    print(f"最差轮次: R{report['总结']['最差轮次']}")
    print(f"平均总分: {report['总结']['平均总分']:.3f}")
    print(f"总违规次数: {report['总结']['总违规次数']}")
    
    print("\n=== 关键分析 ===")
    for dim, analysis in report["各维度分析"].items():
        print(f"{dim}: {analysis}")
    
    return report

if __name__ == "__main__":
    generate_final_report()