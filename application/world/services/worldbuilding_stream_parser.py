"""世界观 SSE 单次流式输出的增量 JSON 解析。

架构：通用 JSON 流提取（infrastructure.json_stream） + schema 归一化（worldbuilding_schema）。
服务端产出规范字段事件，前端只消费 SSE，不再自行解析 JSON。
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from application.world.worldbuilding_merge import WORLD_BUILDING_DIMENSION_KEYS
from application.world.worldbuilding_schema import (
    schema_field_keys,
    validate_complete_dimension_fields,
)
from infrastructure.json_stream.incremental_extractor import (
    JsonStreamBuffer,
    find_key_object_brace_start,
    scan_balanced_brace_end,
    try_parse_json_object,
)

_DIM_KEYS_ORDER: Tuple[str, ...] = WORLD_BUILDING_DIMENSION_KEYS
def _decode_json_string_fragment(value: str) -> str:
    return value.replace("\\\\", "\\").replace("\\n", "\n").replace("\\t", "\t").replace('\\"', '"')


def _extract_dimension_string(buf: str, dim_key: str) -> Optional[Tuple[str, bool]]:
    """Detect model-invalid ``"dimension": "..."`` output.

    Strict schema parsing will ignore it; this helper exists so the parser can
    wait until the invalid string is closed instead of treating the following
    bytes as an object.
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


def _try_extract_dimension_object(buf: str, dim_key: str) -> Optional[Tuple[Dict[str, str], int, int]]:
    """从 buffer 中提取某个维度的完整 JSON 对象（已 schema 归一化）。"""
    brace = find_key_object_brace_start(buf, dim_key)
    if brace is None:
        return None
    parsed = try_parse_json_object(buf, brace)
    if parsed is None:
        return None
    obj, end = parsed
    normalized = validate_complete_dimension_fields(dim_key, obj)
    if not normalized:
        return None
    return normalized, brace, end


def _is_complete_dimension(dim_key: str, content: Dict[str, str]) -> bool:
    """A dimension is ready only after every contract field is publishable."""
    required = schema_field_keys(dim_key)
    return bool(required) and required.issubset(content.keys())


def _dimension_key_start(buf: str, dim_key: str) -> Optional[int]:
    m = re.search(rf'"{re.escape(dim_key)}"\s*:\s*\{{', buf)
    if not m:
        return None
    return m.start()


class WorldbuildingStreamIncrementalParser:
    """累积 LLM 流式文本，按规范字段 / 维度产出事件。"""

    def __init__(self) -> None:
        self._buf = JsonStreamBuffer()
        self._emitted_dims: Set[str] = set()
        self._started_dims: Set[str] = set()
        self._emitted_fields: Dict[str, Dict[str, str]] = {d: {} for d in _DIM_KEYS_ORDER}
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
                        if not closed:
                            continue
                        content = validate_complete_dimension_fields(dim_key, {dim_key: text})
                        if not content:
                            continue
                        fk = next(iter(content))
                        fv = content[fk]
                        if self._emitted_fields[dim_key].get(fk) != fv:
                            self._emitted_fields[dim_key][fk] = fv
                            events.append({"type": "field", "key": dim_key, "field": fk, "value": fv})
                        self._emitted_dims.add(dim_key)
                        events.append({"type": "dimension", "key": dim_key, "content": content})
                    continue
                key_start = _dimension_key_start(buf, dim_key)
                if key_start is not None:
                    self._flush_started_dimensions_before(events, buf, key_start)
                self._dim_brace_start[dim_key] = brace
                if dim_key not in self._started_dims:
                    self._started_dims.add(dim_key)
                    events.append({"type": "dimension_start", "key": dim_key})

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
                content = validate_complete_dimension_fields(dim_key, obj)
                if not content:
                    continue
                if not _is_complete_dimension(dim_key, content):
                    continue
                for fk, fv in content.items():
                    if self._emitted_fields[dim_key].get(fk) != fv:
                        self._emitted_fields[dim_key][fk] = fv
                        events.append({"type": "field", "key": dim_key, "field": fk, "value": fv})
                self._emitted_dims.add(dim_key)
                events.append({"type": "dimension", "key": dim_key, "content": content})
                continue

            # The object is still open. Do not publish field values here:
            # syntactically closed strings can still be model-truncated
            # content. We only commit at a valid, schema-complete dimension
            # boundary so JSON structure, not prose heuristics, decides what
            # reaches the UI.

        return events

    def _flush_started_dimensions_before(
        self,
        events: List[Dict[str, Any]],
        buf: str,
        before_index: int,
    ) -> None:
        """Reserved for boundary hooks.

        We intentionally avoid regex-based recovery here. If a previous
        dimension did not close as valid JSON before the next dimension starts,
        the final parser/repair pass or the patch generation step will handle
        it instead of publishing speculative content to the UI.
        """
        return None

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
                norm = validate_complete_dimension_fields(dim_key, block)
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
