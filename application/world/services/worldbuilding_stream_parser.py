"""世界观 SSE 单次流式输出的增量 JSON 解析。

一次 LLM 调用输出完整 ``worldbuilding`` 对象时，在 token 流到达过程中
尽早识别各维度（core_rules / geography / …）的完整 JSON 子对象并上报。
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from application.world.worldbuilding_merge import WORLD_BUILDING_DIMENSION_KEYS

_DIM_KEYS_ORDER: Tuple[str, ...] = WORLD_BUILDING_DIMENSION_KEYS


def _normalize_field_values(dim_data: Dict[str, Any]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for k, v in dim_data.items():
        if isinstance(v, str) and v.strip():
            out[k] = v.strip()
        elif isinstance(v, (list, dict)):
            out[k] = str(v)
    return out


def _try_extract_dimension_object(buf: str, dim_key: str) -> Optional[Tuple[Dict[str, str], int, int]]:
    """从 buffer 中提取某个维度的完整 JSON 对象。

    Returns:
        (normalized_fields, start_index, end_index) 或 None
    """
    pattern = rf'"{re.escape(dim_key)}"\s*:\s*\{{'
    m = re.search(pattern, buf)
    if not m:
        return None

    brace_start = m.end() - 1  # 指向 '{'
    depth = 0
    in_string = False
    escape_next = False

    for i in range(brace_start, len(buf)):
        ch = buf[i]
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"' and not escape_next:
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                obj_str = buf[brace_start : i + 1]
                try:
                    parsed = json.loads(obj_str)
                except json.JSONDecodeError:
                    return None
                if not isinstance(parsed, dict):
                    return None
                normalized = _normalize_field_values(parsed)
                if not normalized:
                    return None
                return normalized, brace_start, i + 1
    return None


class WorldbuildingStreamIncrementalParser:
    """累积 LLM 流式文本，按维度产出已完成块。"""

    def __init__(self) -> None:
        self._buf = ""
        self._emitted: Set[str] = set()

    @property
    def buffer(self) -> str:
        return self._buf

    def feed(self, chunk: str) -> List[Dict[str, Any]]:
        if chunk:
            self._buf += chunk
        events: List[Dict[str, Any]] = []
        for dim_key in _DIM_KEYS_ORDER:
            if dim_key in self._emitted:
                continue
            extracted = _try_extract_dimension_object(self._buf, dim_key)
            if extracted is None:
                continue
            content, _, _ = extracted
            self._emitted.add(dim_key)
            events.append({"type": "dimension", "key": dim_key, "content": content})
        return events

    def emitted_dimensions(self) -> Set[str]:
        return set(self._emitted)

    def parse_full_worldbuilding(
        self,
        *,
        sanitize: Optional[Any] = None,
        repair: Optional[Any] = None,
    ) -> Dict[str, Dict[str, str]]:
        """流结束后解析完整 worldbuilding（降级 / 补漏）。"""
        raw = self._buf
        if sanitize:
            raw = sanitize(raw)
        if not raw.strip():
            return {}

        content = raw.strip()
        parsed: Any = None
        for attempt in range(3):
            try:
                parsed = json.loads(content)
                break
            except (json.JSONDecodeError, ValueError):
                if attempt == 0 and repair:
                    content = repair(content)
                elif attempt == 1:
                    start = content.find("{")
                    end = content.rfind("}")
                    if start != -1 and end > start:
                        content = content[start : end + 1]
                        if repair:
                            content = repair(content)
                else:
                    return self._emitted_snapshot_from_buffer(sanitize, repair)

        if not isinstance(parsed, dict):
            return self._emitted_snapshot_from_buffer(sanitize, repair)

        wb = parsed.get("worldbuilding")
        if isinstance(wb, dict):
            parsed = wb

        out: Dict[str, Dict[str, str]] = {}
        for dim_key in _DIM_KEYS_ORDER:
            block = parsed.get(dim_key)
            if isinstance(block, dict):
                norm = _normalize_field_values(block)
                if norm:
                    out[dim_key] = norm
        return out

    def _emitted_snapshot_from_buffer(
        self,
        sanitize: Optional[Any],
        repair: Optional[Any],
    ) -> Dict[str, Dict[str, str]]:
        out: Dict[str, Dict[str, str]] = {}
        for dim_key in _DIM_KEYS_ORDER:
            extracted = _try_extract_dimension_object(self._buf, dim_key)
            if extracted:
                out[dim_key], _, _ = extracted
        return out
