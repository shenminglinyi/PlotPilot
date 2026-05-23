"""世界观 SSE 单次流式输出的增量 JSON 解析。

架构：通用 JSON 流提取（infrastructure.json_stream） + schema 归一化（worldbuilding_schema）。
服务端产出规范字段事件，前端只消费 SSE，不再自行解析 JSON。
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from application.world.worldbuilding_merge import WORLD_BUILDING_DIMENSION_KEYS
from application.world.worldbuilding_schema import canonicalize_dimension_fields
from infrastructure.json_stream.incremental_extractor import (
    JsonStreamBuffer,
    extract_complete_string_fields,
    extract_streaming_tail_string_field,
    find_key_object_brace_start,
    scan_balanced_brace_end,
    try_parse_json_object,
)

_DIM_KEYS_ORDER: Tuple[str, ...] = WORLD_BUILDING_DIMENSION_KEYS


def _decode_json_string_fragment(value: str) -> str:
    return value.replace("\\\\", "\\").replace("\\n", "\n").replace("\\t", "\t").replace('\\"', '"')


def _extract_dimension_string(buf: str, dim_key: str) -> Optional[Tuple[str, bool]]:
    """兼容模型违规输出 ``"dimension": "..."`` 的场景。

    正常协议要求维度值是对象；若模型退化为维度级字符串，将其映射到该维度主字段，
    避免前端只能看到 raw JSON。
    """
    complete = re.search(rf'"{re.escape(dim_key)}"\s*:\s*"((?:[^"\\]|\\.)*)"', buf)
    if complete:
        return _decode_json_string_fragment(complete.group(1)), True

    tail = re.search(rf'"{re.escape(dim_key)}"\s*:\s*"((?:[^"\\]|\\.)*)$', buf)
    if tail:
        return _decode_json_string_fragment(tail.group(1)), False

    return None


def _worldbuilding_inner_start(buf: str) -> Optional[int]:
    """定位 worldbuilding 对象内层起始 ``{``。"""
    m = re.search(r'"worldbuilding"\s*:\s*\{', buf)
    if not m:
        return None
    return m.end() - 1


def _dimension_object_body(buf: str, dim_key: str) -> Optional[Tuple[str, bool]]:
    """返回 (维度对象内部片段, 是否已闭合)。未找到维度键则 None。"""
    brace = find_key_object_brace_start(buf, dim_key)
    if brace is None:
        return None
    end = scan_balanced_brace_end(buf, brace)
    if end is not None:
        inner = buf[brace + 1 : end - 1]
        return inner, True
    inner = buf[brace + 1 :]
    return inner, False


def _try_extract_dimension_object(buf: str, dim_key: str) -> Optional[Tuple[Dict[str, str], int, int]]:
    """从 buffer 中提取某个维度的完整 JSON 对象（已 schema 归一化）。"""
    brace = find_key_object_brace_start(buf, dim_key)
    if brace is None:
        return None
    parsed = try_parse_json_object(buf, brace)
    if parsed is None:
        return None
    obj, end = parsed
    normalized = canonicalize_dimension_fields(dim_key, obj)
    if not normalized:
        return None
    return normalized, brace, end


class WorldbuildingStreamIncrementalParser:
    """累积 LLM 流式文本，按规范字段 / 维度产出事件。"""

    def __init__(self) -> None:
        self._buf = JsonStreamBuffer()
        self._emitted_dims: Set[str] = set()
        self._emitted_fields: Dict[str, Set[str]] = {d: set() for d in _DIM_KEYS_ORDER}
        self._last_partial: Dict[str, Dict[str, str]] = {d: {} for d in _DIM_KEYS_ORDER}
        # Cache opening-brace position per dimension to avoid O(n²) re-scanning
        self._dim_brace_start: Dict[str, Optional[int]] = {d: None for d in _DIM_KEYS_ORDER}

    @property
    def buffer(self) -> str:
        return self._buf.text

    def feed(self, chunk: str) -> List[Dict[str, Any]]:
        self._buf.feed(chunk)
        buf = self._buf.text
        events: List[Dict[str, Any]] = []

        for dim_key in _DIM_KEYS_ORDER:
            if dim_key in self._emitted_dims:
                continue

            # Locate opening brace once and cache; avoid repeating the full-buffer regex search
            if self._dim_brace_start[dim_key] is None:
                brace = find_key_object_brace_start(buf, dim_key)
                if brace is None:
                    dim_string = _extract_dimension_string(buf, dim_key)
                    if dim_string:
                        text, closed = dim_string
                        content = canonicalize_dimension_fields(dim_key, {dim_key: text})
                        if not content:
                            continue
                        fk = next(iter(content))
                        fv = content[fk]
                        if closed:
                            if fk not in self._emitted_fields[dim_key]:
                                self._emitted_fields[dim_key].add(fk)
                                events.append({"type": "field", "key": dim_key, "field": fk, "value": fv})
                            self._emitted_dims.add(dim_key)
                            events.append({"type": "dimension", "key": dim_key, "content": content})
                            self._last_partial[dim_key].clear()
                        else:
                            prev = self._last_partial[dim_key].get(fk)
                            if prev != fv:
                                self._last_partial[dim_key][fk] = fv
                                events.append({
                                    "type": "field_partial",
                                    "key": dim_key,
                                    "field": fk,
                                    "value": fv,
                                })
                    continue
                self._dim_brace_start[dim_key] = brace

            brace = self._dim_brace_start[dim_key]
            end = scan_balanced_brace_end(buf, brace)

            if end is not None:
                # Dimension fully closed: parse once with json.loads
                try:
                    obj = json.loads(buf[brace:end])
                except json.JSONDecodeError:
                    continue
                if not isinstance(obj, dict):
                    continue
                content = canonicalize_dimension_fields(dim_key, obj)
                if not content:
                    continue
                self._emitted_dims.add(dim_key)
                for fk, fv in content.items():
                    if fk not in self._emitted_fields[dim_key]:
                        self._emitted_fields[dim_key].add(fk)
                        events.append({"type": "field", "key": dim_key, "field": fk, "value": fv})
                events.append({"type": "dimension", "key": dim_key, "content": content})
                self._last_partial[dim_key].clear()
                continue

            # Dimension still open: incremental string-field extraction on the partial body
            body = buf[brace + 1:]

            raw_complete = extract_complete_string_fields(body)
            if raw_complete:
                canon = canonicalize_dimension_fields(dim_key, raw_complete)
                for fk, fv in canon.items():
                    if fk in self._emitted_fields[dim_key]:
                        continue
                    self._emitted_fields[dim_key].add(fk)
                    events.append({"type": "field", "key": dim_key, "field": fk, "value": fv})

            tail = extract_streaming_tail_string_field(body)
            if tail:
                raw_k, partial_v = tail
                canon_k = canonicalize_dimension_fields(dim_key, {raw_k: partial_v})
                if canon_k:
                    fk = next(iter(canon_k))
                    fv = canon_k[fk]
                    prev = self._last_partial[dim_key].get(fk)
                    if prev != fv:
                        self._last_partial[dim_key][fk] = fv
                        events.append({
                            "type": "field_partial",
                            "key": dim_key,
                            "field": fk,
                            "value": fv,
                        })

        return events

    def emitted_dimensions(self) -> Set[str]:
        return set(self._emitted_dims)

    def parse_full_worldbuilding(
        self,
        *,
        sanitize: Optional[Any] = None,
        repair: Optional[Any] = None,
    ) -> Dict[str, Dict[str, str]]:
        """流结束后解析完整 worldbuilding（降级 / 补漏）。"""
        raw = self._buf.text
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
                    return self._emitted_snapshot_from_buffer()

        if not isinstance(parsed, dict):
            return self._emitted_snapshot_from_buffer()

        wb = parsed.get("worldbuilding")
        if isinstance(wb, dict):
            parsed = wb

        out: Dict[str, Dict[str, str]] = {}
        for dim_key in _DIM_KEYS_ORDER:
            block = parsed.get(dim_key)
            if isinstance(block, dict):
                norm = canonicalize_dimension_fields(dim_key, block)
                if norm:
                    out[dim_key] = norm
        return out

    def _emitted_snapshot_from_buffer(self) -> Dict[str, Dict[str, str]]:
        out: Dict[str, Dict[str, str]] = {}
        for dim_key in _DIM_KEYS_ORDER:
            extracted = _try_extract_dimension_object(self._buf.text, dim_key)
            if extracted:
                out[dim_key], _, _ = extracted
        return out
