"""从 LLM 文本中抽取 JSON 对象（统一管线），供各契约模块复用。

🔥 核心设计原则：
- 清洗 → 修复 → 解析，三步管线
- 修复环节委托 json_repair 库（mangiucugna/json_repair），它覆盖了：
  · 中文/全角引号自动替换
  · 未闭合的括号/引号补全
  · 尾随逗号删除
  · 注释删除（// 和 /* */）
  · 单引号 → 双引号
  · 省略值补 null
  · 等等 40+ 种常见 LLM 输出格式错误
- 之前自造的 repair_json 只覆盖 3-4 种情况，DeepSeek 等模型的中文引号、
  混合思考链、截断输出等场景处理不了

为什么 Claude 可以但 DeepSeek 不行：
- Claude 严格遵循 JSON 格式，几乎不出错
- DeepSeek/V3/R1 常见问题：
  1. <think>...</think> 思考链混在 JSON 前面
  2. 中文引号（""''）替代标准双引号
  3. 流式截断导致 JSON 不完整（缺少闭合括号）
  4. 在 JSON 值中混入注释（// TODO）
  5. 尾随逗号
  6. 用 undefined/null 混用
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from json_repair import repair_json as _json_repair_lib

from application.ai.llm_output_sanitize import strip_reasoning_artifacts


# ---------------------------------------------------------------------------
# 第一步：清洗（去围栏、去思考链、去零宽字符）
# ---------------------------------------------------------------------------


def strip_json_fences(raw: str) -> str:
    """去掉 ``` / ```json 代码块包装，同时剔除 ANSI 转义、think 标签、零宽字符。

    🔥 修复了之前版本的几个关键问题：
    1. 旧正则 `think>.*? ` 会误匹配任意包含 "think>" 的文本
    2. 旧代码没有处理 DeepSeek R1 的 <think>...</think> 标签（带尖括号）
    3. 旧代码没有处理零宽字符
    """
    content = raw.strip()

    # 1. 去 BOM
    if content and content[0] == "\ufeff":
        content = content[1:]

    # 2. 剔除 ANSI 转义序列
    content = re.sub(r'\x1b\[[0-9;]*m', '', content)

    # 3. 🔥 剔除思维链标签（DeepSeek-R1 / QwQ / Gemini thinking 等）
    #    之前只用 `think>.*? ` 正则，严重错误——会匹配任何包含 "think>" 的文本
    content = strip_reasoning_artifacts(content)

    # 4. 去 markdown 围栏
    #    处理 ```json ... ``` 或 ``` ... ```
    fence_pattern = re.compile(
        r"```(?:json|JSON)?\s*\n?(.*?)\n?\s*```", re.DOTALL
    )
    fence_match = fence_pattern.search(content)
    if fence_match:
        content = fence_match.group(1)

    # 5. 去零宽字符
    content = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", content)

    # 6. strip
    content = content.strip()

    return content


def extract_outer_json_object(text: str) -> str:
    """取第一个 '{' 与最后一个 '}' 之间的片段，容忍前后废话。"""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return text
    return text[start : end + 1]


# ---------------------------------------------------------------------------
# 第二步：修复（委托 json_repair 库）
# ---------------------------------------------------------------------------


def repair_json(text: str) -> str:
    """JSON 修复：委托 json_repair 库，覆盖 40+ 种常见 LLM 输出格式错误。

    之前自造的 repair_json 只覆盖了 3-4 种简单情况（补括号、删尾逗号、截断），
    无法处理中文引号、注释、单引号等 DeepSeek 常见问题。

    json_repair 库（mangiucugna/json_repair）能力：
    - 中文/全角引号 → ASCII 双引号
    - 单引号 → 双引号
    - 未闭合括号/引号补全
    - 尾随逗号删除
    - JS 风格注释删除（// 和 /* */）
    - undefined → null
    - 省略值补 null
    - Unicode 转义修复
    - 科学计数法修复
    - 混合类型数组修复
    等等
    """
    text = text.strip()
    if not text:
        return text

    # 最快路径：直接能解析
    try:
        json.loads(text)
        return text
    except (json.JSONDecodeError, ValueError):
        pass

    # 委托 json_repair 库
    try:
        repaired = _json_repair_lib(text)
        # json_repair 返回的是修复后的 JSON 字符串
        if isinstance(repaired, str):
            # 验证修复结果
            json.loads(repaired)
            return repaired
        # 某些版本可能直接返回对象
        return json.dumps(repaired, ensure_ascii=False)
    except Exception:
        pass

    # 降级：提取最外层 { } 后再修复
    fragment = extract_outer_json_object(text)
    if fragment != text:
        try:
            repaired = _json_repair_lib(fragment)
            if isinstance(repaired, str):
                json.loads(repaired)
                return repaired
            return json.dumps(repaired, ensure_ascii=False)
        except Exception:
            pass

    # 最终降级：返回原文
    return text


# ---------------------------------------------------------------------------
# 第三步：解析入口
# ---------------------------------------------------------------------------


def parse_llm_json_to_dict(raw: str) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """从 LLM 原始输出中解析 JSON 对象。

    完整管线：清洗 → 修复 → 解析

    成功 (data, [])；失败 (None, [错误信息…])。

    🔥 统一入口：所有需要从 LLM 输出解析 JSON 的地方都应使用此函数，
    不要各自造 parse_json_from_response（auto_bible_generator、knowledge_llm_contract
    中的自造版本已废弃）。
    """
    errors: List[str] = []

    try:
        # 第一步：清洗
        cleaned = strip_json_fences(raw)

        # 第二步：提取最外层 JSON 对象
        cleaned = extract_outer_json_object(cleaned)

        # 第三步：修复（委托 json_repair）
        cleaned = repair_json(cleaned)

        # 第四步：解析
        data = json.loads(cleaned)

        if isinstance(data, dict):
            return data, []

        # 如果返回的是列表，取第一个元素
        if isinstance(data, list) and data and isinstance(data[0], dict):
            return data[0], []

        errors.append(f"根节点必须是 JSON 对象，实际是 {type(data).__name__}")

    except json.JSONDecodeError as e:
        errors.append(f"JSON 解析失败: {e}")
    except Exception as e:
        errors.append(f"预处理失败: {e}")

    return None, errors
