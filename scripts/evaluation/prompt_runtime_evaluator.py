"""提示词运行时评测器

测试指标：
- DB优先读取
- JSON回退
- rule组合渲染
- 变量注入
- 上下文块去重
"""
from __future__ import annotations

import json
import logging
from typing import Dict, Any, List

from infrastructure.ai.prompt_runtime import PromptRuntimeService

logger = logging.getLogger(__name__)


class PromptRuntimeEvaluator:
    """提示词运行时评测器"""

    def run(self) -> Dict[str, Any]:
        results = {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "details": [],
        }

        # 创建带JSON回退的服务
        import tempfile
        import os

        # 创建临时JSON文件
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = os.path.join(tmpdir, "prompts_test.json")
            test_prompts = [
                {
                    "name": "rule.test_pacing",
                    "content": "节奏控制：每{word_count}字必须有信息揭示。{genre}类型小说节奏要求更高。",
                    "metadata": {"node_type": "rule", "subcategory": "pacing"},
                },
                {
                    "name": "rule.test_style",
                    "content": "风格控制：避免八股文，减少数字比喻。当前角色：{character_name}。",
                    "metadata": {"node_type": "rule", "subcategory": "style"},
                },
                {
                    "name": "rule.test_duplicate",
                    "content": "节奏控制：每{word_count}字必须有信息揭示。{genre}类型小说节奏要求更高。",
                    "metadata": {"node_type": "rule", "subcategory": "pacing"},
                },
            ]

            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(test_prompts, f, ensure_ascii=False)

            service = PromptRuntimeService(prompts_dir=tmpdir)

            # 测试1: JSON回退
            results["total"] += 1
            try:
                import asyncio
                prompt = asyncio.get_event_loop().run_until_complete(
                    service.get_prompt("rule.test_pacing")
                )
                if prompt and "节奏控制" in prompt.get("content", ""):
                    results["passed"] += 1
                    results["details"].append({"name": "JSON回退", "passed": True})
                else:
                    results["failed"] += 1
                    results["details"].append({"name": "JSON回退", "passed": False})
            except Exception as e:
                results["failed"] += 1
                results["details"].append({"name": "JSON回退", "passed": False, "error": str(e)})

            # 测试2: 变量注入
            results["total"] += 1
            try:
                rendered = asyncio.get_event_loop().run_until_complete(
                    service.render(
                        rule_keys=["rule.test_pacing"],
                        variables={"word_count": "2000", "genre": "武侠"},
                    )
                )
                if "2000" in rendered and "武侠" in rendered:
                    results["passed"] += 1
                    results["details"].append({"name": "变量注入", "passed": True})
                else:
                    results["failed"] += 1
                    results["details"].append({"name": "变量注入", "passed": False, "rendered": rendered})
            except Exception as e:
                results["failed"] += 1
                results["details"].append({"name": "变量注入", "passed": False, "error": str(e)})

            # 测试3: rule组合渲染
            results["total"] += 1
            try:
                rendered = asyncio.get_event_loop().run_until_complete(
                    service.render(
                        rule_keys=["rule.test_pacing", "rule.test_style"],
                        variables={"word_count": "2000", "genre": "武侠", "character_name": "林羽"},
                    )
                )
                if "节奏控制" in rendered and "风格控制" in rendered:
                    results["passed"] += 1
                    results["details"].append({"name": "rule组合渲染", "passed": True})
                else:
                    results["failed"] += 1
                    results["details"].append({"name": "rule组合渲染", "passed": False})
            except Exception as e:
                results["failed"] += 1
                results["details"].append({"name": "rule组合渲染", "passed": False, "error": str(e)})

            # 测试4: 上下文块去重
            results["total"] += 1
            try:
                rendered = asyncio.get_event_loop().run_until_complete(
                    service.render(
                        rule_keys=["rule.test_pacing", "rule.test_duplicate"],
                        variables={"word_count": "2000", "genre": "武侠"},
                        deduplicate=True,
                    )
                )
                # 重复内容应该被去重
                count = rendered.count("节奏控制")
                if count == 1:
                    results["passed"] += 1
                    results["details"].append({"name": "上下文块去重", "passed": True})
                else:
                    results["failed"] += 1
                    results["details"].append({"name": "上下文块去重", "passed": False, "count": count})
            except Exception as e:
                results["failed"] += 1
                results["details"].append({"name": "上下文块去重", "passed": False, "error": str(e)})

            # 测试5: 变量扫描
            results["total"] += 1
            try:
                variables = service.scan_variables("你好{名字}，欢迎来到{地方}，{名字}你好")
                if "名字" in variables and "地方" in variables:
                    results["passed"] += 1
                    results["details"].append({"name": "变量扫描", "passed": True})
                else:
                    results["failed"] += 1
                    results["details"].append({"name": "变量扫描", "passed": False, "found": variables})
            except Exception as e:
                results["failed"] += 1
                results["details"].append({"name": "变量扫描", "passed": False, "error": str(e)})

        return results


if __name__ == "__main__":
    evaluator = PromptRuntimeEvaluator()
    results = evaluator.run()
    print(json.dumps(results, indent=2, ensure_ascii=False))
