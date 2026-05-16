"""将 JSON / 包中的「扩展字段」并入 variables，供 PromptRegistry.get_field / get_directives_dict 使用。"""
from __future__ import annotations

import copy
from typing import Any, Dict, List


def normalize_prompt_record(raw: Dict[str, Any]) -> Dict[str, Any]:
    """返回新 dict：把顶层以下划线开头的键（如 _directives）写入 variables 伪条目。

    若 variables 中已有同名 name，不覆盖。
    """
    p = copy.deepcopy(raw)
    variables: List[Dict[str, Any]] = list(p.get("variables") or [])
    existing = {v.get("name") for v in variables if isinstance(v, dict)}

    for key, val in list(p.items()):
        if not key.startswith("_") or key == "_meta":
            continue
        if key in existing:
            continue
        variables.append({"name": key, "value": val})
        existing.add(key)

    p["variables"] = variables
    return p
