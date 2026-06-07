"""生成画像配置读取工具。"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import yaml  # type: ignore

from domain.ai.services.llm_service import GenerationConfig

_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "generation_profiles.yaml"


@lru_cache(maxsize=1)
def load_generation_profiles() -> dict[str, dict[str, Any]]:
    """读取并展开 generation_profiles.yaml。"""
    if not _CONFIG_PATH.is_file():
        return {}
    raw = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        return {}

    resolved: dict[str, dict[str, Any]] = {}

    def resolve(name: str, stack: tuple[str, ...] = ()) -> dict[str, Any]:
        if name in resolved:
            return dict(resolved[name])
        if name in stack:
            raise ValueError(f"GenerationProfile 继承循环: {' -> '.join(stack + (name,))}")
        item = raw.get(name) or {}
        if not isinstance(item, dict):
            item = {}
        parent_name = item.get("extends")
        merged: dict[str, Any] = {}
        if parent_name:
            merged.update(resolve(str(parent_name), stack + (name,)))
        merged.update({k: v for k, v in item.items() if k != "extends"})
        resolved[name] = merged
        return dict(merged)

    for key in raw:
        resolve(str(key))
    return resolved


def get_generation_profile(name: str) -> dict[str, Any]:
    """获取展开后的生成画像。"""
    return dict(load_generation_profiles().get(name, {}))


def generation_config_from_profile(
    name: str,
    *,
    model: str = "",
    response_format: Mapping[str, Any] | None = None,
    **overrides: Any,
) -> GenerationConfig:
    """从画像构造 GenerationConfig，可用 overrides 覆盖。"""
    profile = get_generation_profile(name)
    profile.update({k: v for k, v in overrides.items() if v is not None})
    return GenerationConfig(
        model=model or str(profile.get("model", "")),
        max_tokens=int(profile.get("max_tokens", 4096)),
        temperature=float(profile.get("temperature", 1.0)),
        response_format=dict(response_format) if response_format is not None else profile.get("response_format"),
    )
