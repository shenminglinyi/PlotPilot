"""故事线归一化配置读取。

章节叙事同步需要把 LLM 输出的同义故事线标签合并到既有 Storyline。
具体词表属于可演进配置资产，不能散落在同步流程代码里。
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, Tuple

import yaml


_CONFIG_PATH = (
    Path(__file__).resolve().parents[3]
    / "shared"
    / "taxonomy"
    / "storyline_normalization_cn_v1.yaml"
)


@dataclass(frozen=True)
class StorylineNormalizationProfile:
    """故事线归一化配置。"""

    alias_words: Tuple[str, ...]
    distinctive_tokens: frozenset[str]
    replacements: Dict[str, str]


def _as_text_tuple(value: object) -> Tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


@lru_cache(maxsize=1)
def get_storyline_normalization_profile() -> StorylineNormalizationProfile:
    """读取故事线归一化配置。

    配置缺失时返回空配置，避免在叙事同步中继续使用隐藏硬编码词表。
    """
    if not _CONFIG_PATH.is_file():
        return StorylineNormalizationProfile((), frozenset(), {})

    data = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        return StorylineNormalizationProfile((), frozenset(), {})

    alias_words = _as_text_tuple(data.get("alias_words"))
    distinctive_tokens = frozenset(_as_text_tuple(data.get("distinctive_tokens")))
    raw_replacements = data.get("replacements") or {}
    replacements = {
        str(src).strip(): str(dst).strip()
        for src, dst in raw_replacements.items()
        if str(src).strip() and str(dst).strip()
    } if isinstance(raw_replacements, dict) else {}

    return StorylineNormalizationProfile(
        alias_words=alias_words,
        distinctive_tokens=distinctive_tokens,
        replacements=replacements,
    )
