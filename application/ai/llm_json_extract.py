"""从 LLM 文本中抽取 JSON 对象（去 fence、截最外层 {{…}}），供各契约模块复用。

包含 JSON 智能自愈引擎 (Auto-Repair)，当模型产生残缺 JSON 时能自动补全闭合符号
或自动切断并丢弃最后一个报错的残缺节点，确保生成流程不再卡死。
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple


def strip_json_fences(raw: str) -> str:
    """去掉 ``` / ```json 代码块包装，同时剔除 ANSI 转义与 think 标签。"""
    content = raw.strip()
    # 剔除 ANSI 转义序列
    content = re.sub(r'\x1b\[[0-9;]*m', '', content)
    # 剔除  think ...  思考过程标签（DeepSeek-R1 等模型）
    content = re.sub(r'think>.*? ', '', content, flags=re.DOTALL | re.IGNORECASE)
    if "```json" in content:
        content = content.split("```json", 1)[1].split("```", 1)[0]
    elif "```" in content:
        content = content.split("```", 1)[1].split("```", 1)[0]
    return content.strip()


def extract_outer_json_object(text: str) -> str:
    """取第一个 '{' 与最后一个 '}' 之间的片段，容忍前后废话。"""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return text
    return text[start : end + 1]


def repair_json(text: str) -> str:
    """JSON 智能自愈引擎：尝试修复残缺的 JSON 字符串。

    策略：
    1. 先尝试直接解析
    2. 若失败，尝试补全未闭合的括号/引号
    3. 若仍失败，迭代截断最后一个逗号分隔的节点后重试
    """
    text = text.strip()
    if not text:
        return text

    try:
        json.loads(text)
        return text
    except (json.JSONDecodeError, ValueError):
        pass

    def _do_repair(s: str) -> str:
        s = s.strip()
        if not s:
            return '{}'

        in_string = False
        escape = False
        stack = []
        res = []

        for ch in s:
            if escape:
                res.append(ch)
                escape = False
                continue
            if ch == '\\' and in_string:
                res.append(ch)
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                res.append('"')
                continue
            if in_string:
                res.append(ch)
                continue
            if ch in '{[':
                stack.append('}' if ch == '{' else ']')
                res.append(ch)
            elif ch in ']}' + "'":
                if stack and stack[-1] == ch:
                    stack.pop()
                res.append(ch)
            else:
                res.append(ch)

        if in_string:
            res += '"'
        res = res.strip()
        while res.endswith(','):
            res = res[:-1].strip()
        while stack:
            res = res.strip()
            if res.endswith(','):
                res = res[:-1].strip()
            res += stack.pop()
        return res

    current_s = text
    max_retries = 15
    while max_retries > 0 and current_s:
        repaired = _do_repair(current_s)
        try:
            json.loads(repaired)
            return repaired
        except json.JSONDecodeError:
            idx = current_s.rfind(',')
            if idx == -1:
                break
            current_s = current_s[:idx]
        max_retries -= 1
    return _do_repair(text)


def parse_llm_json_to_dict(raw: str) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """解析为 dict。成功 (data, [])；失败 (None, [错误信息…])。"""
    try:
        cleaned = strip_json_fences(raw)
        cleaned = extract_outer_json_object(cleaned)
        cleaned = repair_json(cleaned)
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        return None, [f"JSON 解析失败: {e}"]
    except Exception as e:  # pragma: no cover
        return None, [f"预处理失败: {e}"]

    if not isinstance(data, dict):
        return None, ["根节点必须是 JSON 对象"]
    return data, []
