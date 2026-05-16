"""解析正文中的 [[kind:id|label]] 标记并聚合为章节实体提及（零 token）。"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Tuple

# [[char:uuid|张三]] [[loc:id|长安]] [[faction:id|大周]] [[prop:id|铜镜]]
_TOKEN_RE = re.compile(
    r"\[\[(?P<kind>char|loc|faction|prop):(?P<eid>[^\]|]+)(?:\|(?P<label>[^\]]+))?\]\]",
    re.UNICODE,
)

_KIND_ALIASES = {"char": "char", "loc": "loc", "faction": "faction", "prop": "prop"}


@dataclass(frozen=True)
class ParsedMention:
    kind: str
    entity_id: str
    label: str


def parse_explicit_tokens(text: str) -> List[ParsedMention]:
    out: List[ParsedMention] = []
    for m in _TOKEN_RE.finditer(text or ""):
        kind = _KIND_ALIASES.get(m.group("kind"), m.group("kind"))
        eid = (m.group("eid") or "").strip()
        label = (m.group("label") or "").strip() or eid
        if eid:
            out.append(ParsedMention(kind=kind, entity_id=eid, label=label))
    return out


def aggregate_mentions(mentions: List[ParsedMention]) -> List[Tuple[str, str, str, int]]:
    """返回 (kind, entity_id, label, count) 列表。"""
    acc: Dict[Tuple[str, str], Tuple[str, int]] = {}
    for pm in mentions:
        key = (pm.kind, pm.entity_id)
        if key not in acc:
            acc[key] = (pm.label, 0)
        label, c = acc[key]
        acc[key] = (label or pm.label, c + 1)
    return [(k[0], k[1], v[0], v[1]) for k, v in acc.items()]


def lexicon_match_plain_names(
    text: str,
    *,
    characters: List[Tuple[str, str, List[str]]],
    locations: List[Tuple[str, str, str, List[str]]],
    props: List[Tuple[str, str, List[str]]],
) -> List[ParsedMention]:
    """按最长匹配将纯文本名替换为隐式提及列表（仅统计用，不改写正文）。

    characters: (id, canonical_name, aliases)
    locations: (id, name, location_type, aliases) — faction 用 location_type == 'faction'
    props: (id, name, aliases)
    """
    t = text or ""
    if not t.strip():
        return []

    spans: List[Tuple[int, int, ParsedMention]] = []

    # 角色
    for cid, cname, aliases in characters:
        for phrase in [cname] + list(aliases or []):
            phrase = (phrase or "").strip()
            if len(phrase) < 2:
                continue
            start = 0
            while True:
                i = t.find(phrase, start)
                if i < 0:
                    break
                end = i + len(phrase)
                spans.append((i, end, ParsedMention(kind="char", entity_id=cid, label=cname)))
                start = i + max(1, len(phrase) // 2)

    for lid, name, ltype, aliases in locations:
        kind = "faction" if (ltype or "").lower() == "faction" else "loc"
        for phrase in [name] + list(aliases or []):
            phrase = (phrase or "").strip()
            if len(phrase) < 2:
                continue
            start = 0
            while True:
                i = t.find(phrase, start)
                if i < 0:
                    break
                end = i + len(phrase)
                spans.append((i, end, ParsedMention(kind=kind, entity_id=lid, label=name)))
                start = i + max(1, len(phrase) // 2)

    for pid, name, aliases in props:
        for phrase in [name] + list(aliases or []):
            phrase = (phrase or "").strip()
            if len(phrase) < 2:
                continue
            start = 0
            while True:
                i = t.find(phrase, start)
                if i < 0:
                    break
                end = i + len(phrase)
                spans.append((i, end, ParsedMention(kind="prop", entity_id=pid, label=name)))
                start = i + max(1, len(phrase) // 2)

    if not spans:
        return []

    spans.sort(key=lambda x: (-(x[1] - x[0]), x[0]))
    taken = [False] * len(t)
    picked: List[ParsedMention] = []
    for s, e, pm in spans:
        if any(taken[s:e]):
            continue
        for j in range(s, e):
            taken[j] = True
        picked.append(pm)
    return picked


def collect_chapter_entity_rows(
    text: str,
    *,
    characters: List[Tuple[str, str, List[str]]],
    locations: List[Tuple[str, str, str, List[str]]],
    props: List[Tuple[str, str, List[str]]],
) -> List[Tuple[str, str, str, int]]:
    """显式 [[...]] 标记 + Bible/道具词表命中 → 聚合为 (kind, id, label, count)。"""
    merged = list(parse_explicit_tokens(text)) + lexicon_match_plain_names(
        text, characters=characters, locations=locations, props=props
    )
    return aggregate_mentions(merged)
