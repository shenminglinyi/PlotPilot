from __future__ import annotations

import re
from hashlib import sha1
from typing import Iterable


_NOISE_RE = re.compile(r"[\s·•\-_:：,，.。!！?？【】\[\]()（）]+")
_STORYLINE_WORDS = (
    "故事线",
    "支线",
    "主线",
    "剧情线",
    "线索",
    "事件",
    "篇章",
)


def normalize_storyline_key(text: str) -> str:
    value = (text or "").strip().lower()
    for token in _STORYLINE_WORDS:
        value = value.replace(token, "")
    value = _NOISE_RE.sub("", value)
    return value[:80] or "untitled"


def canonical_id_for(novel_id: str, title: str, aliases: Iterable[str] = ()) -> str:
    parts = [novel_id, normalize_storyline_key(title)]
    parts.extend(normalize_storyline_key(alias) for alias in aliases)
    digest = sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"csl_{digest}"


def merge_aliases(*groups: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for group in groups:
        for item in group or []:
            value = str(item or "").strip()
            if not value:
                continue
            key = normalize_storyline_key(value)
            if key in seen:
                continue
            seen.add(key)
            out.append(value[:120])
    return out
