"""叙事基础词表读取。

词表属于可演进配置资产，业务服务只按用途读取，不在代码中内嵌题材样例词。
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Tuple

import yaml


_CONFIG_PATH = (
    Path(__file__).resolve().parents[3]
    / "shared"
    / "taxonomy"
    / "narrative_lexicon_cn_v1.yaml"
)


@dataclass(frozen=True)
class NarrativeLexicon:
    """叙事基础词表。"""

    non_character_words: frozenset[str]
    promise_keywords: Tuple[str, ...]


def _as_text_tuple(value: object) -> Tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


@lru_cache(maxsize=1)
def get_narrative_lexicon() -> NarrativeLexicon:
    """读取叙事基础词表。"""
    if not _CONFIG_PATH.is_file():
        return NarrativeLexicon(frozenset(), ())

    data = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        return NarrativeLexicon(frozenset(), ())

    non_character_words = frozenset(_as_text_tuple(data.get("non_character_words")))
    promise_keywords = _as_text_tuple(data.get("promise_keywords"))
    return NarrativeLexicon(
        non_character_words=non_character_words,
        promise_keywords=promise_keywords,
    )
