"""从 LLM 文本中抽取 JSON 对象（去 fence、截最外层 {{…}}），供各契约模块复用。"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple


def strip_json_fences(raw: str) -> str:
    """去掉 ``` / ```json 代码块包装。"""
    content = raw.strip()
    if "```json" in content:
        content = content.split("```json", 1)[1].split("```", 1)[0]
    elif "```" in content:
        content = content.split("```", 1)[1].split("```", 1)[0]
    return content.strip()


def extract_outer_json_object(text: str) -> str:
    """取第一个 '{' 并尝试修复被截断的 JSON。容忍前后废话。"""
    start = text.find("{")
    if start == -1: return text
    
    # 1. 先尝试正常的截取（容忍前后废话）
    end = text.rfind("}")
    if end != -1 and end > start:
        candidate = text[start:end+1]
        try:
            json.loads(candidate)
            return candidate  # 完美闭合且合法
        except json.JSONDecodeError:
            pass # 可能被截断了，导致最后一个 } 是错误的（例如字符串内部的 }）

    # 2. 如果正常的截取失败，说明要么不是合法 JSON，要么是被截断了
    text = text[start:]
    
    def repair_json(s: str) -> str:
        s = s.strip()
        if not s: return "{}"
        try:
            json.loads(s)
            return s
        except json.JSONDecodeError:
            pass
            
        def _do_repair(partial_s: str) -> str:
            stack = []
            in_string = False
            escape = False
            for c in partial_s:
                if in_string:
                    if escape: escape = False
                    elif c == '\\': escape = True
                    elif c == '"': in_string = False
                else:
                    if c == '"': in_string = True
                    elif c == '{': stack.append('}')
                    elif c == '[': stack.append(']')
                    elif c == '}': 
                        if stack and stack[-1] == '}': stack.pop()
                    elif c == ']':
                        if stack and stack[-1] == ']': stack.pop()
            res = partial_s
            if in_string: res += '"'
            res = res.strip()
            while res.endswith(','): res = res[:-1].strip()
            while stack:
                res = res.strip()
                if res.endswith(','): res = res[:-1].strip()
                res += stack.pop()
            return res

        current_s = s
        max_retries = 15
        while max_retries > 0 and current_s:
            repaired = _do_repair(current_s)
            try:
                json.loads(repaired)
                return repaired
            except json.JSONDecodeError:
                idx = current_s.rfind(',')
                if idx == -1: break
                current_s = current_s[:idx]
            max_retries -= 1
        return _do_repair(s)
        
    return repair_json(text)


def parse_llm_json_to_dict(raw: str) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """解析为 dict。成功 (data, [])；失败 (None, [错误信息…])。"""
    try:
        cleaned = strip_json_fences(raw)
        cleaned = extract_outer_json_object(cleaned)
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        return None, [f"JSON 解析失败: {e}"]
    except Exception as e:  # pragma: no cover
        return None, [f"预处理失败: {e}"]

    if not isinstance(data, dict):
        return None, ["根节点必须是 JSON 对象"]
    return data, []
