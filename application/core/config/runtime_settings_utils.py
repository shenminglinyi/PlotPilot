"""Small helpers for reading runtime settings from ConfigAccessor sections."""

from __future__ import annotations

from typing import Any


def section_value(section: Any, key: str, default: Any) -> Any:
    if section is None:
        return default
    try:
        value = section.get(key, default)
    except AttributeError:
        return default
    return default if value is None else value


def positive_float(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def non_negative_float(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


def positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def non_negative_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default
