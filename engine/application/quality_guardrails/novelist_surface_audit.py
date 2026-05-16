"""专业小说家向「表面质检」——在少量规则命中时仍保持分值区分度。

说明：守门人系统是启发式规则，无法替代真人编辑审稿；此处采用更保守的先验，
对网文稿件常见薄弱点（播音腔套话、「的」字链、起手单调等）做小幅度扣分。
"""
from __future__ import annotations

import math
import re
from typing import List, Tuple

# 播音腔 / 评述腔套话（单条视为轻微问题；高频叠加）
AUTHORIAL_PHRASES = [
    "从某种意义上", "从某种程度上", "在某种程度上", "在某种意义上",
    "总体而言", "总的来说", "不得不说", "值得一提的是", "与此同时",
    "不禁让人", "令人不禁", "让人忍不住", "读者可以清楚地看到",
]


def narrator_register_penalty(text: str) -> float:
    """因叙述者评述腔而产生的扣分基数 (0 ~ ~0.12)。"""
    body = text.replace(" ", "").replace("\n", "")
    if len(body) < 220:
        return 0.0

    hits = sum(body.count(p) for p in AUTHORIAL_PHRASES)
    density = hits / max(len(body) / 1000, 1e-6)
    if hits == 0:
        return 0.0
    # hits 越少惩罚越温和；密度上去后加重
    return min(0.12, (hits ** 0.7) * 0.038 + density * 0.012)


def de_particle_pressure_penalty(text: str) -> float:
    """「的」过高的黏连语感税 (0 ~ ~0.10)。

    「的」多未必错，但作为 cheap proxy：统计意义超过阈值时视作表达不够干爽。
    """
    body = text.replace(" ", "").replace("\n", "")
    n = len(body)
    if n < 500:
        return 0.0
    cnt = body.count("的")
    per_100 = cnt / max(n / 100, 1e-6)
    # 长篇小说常见 4～6「的」/百字；明显堆叠再上税
    if per_100 < 8.8:
        return 0.0
    excess = per_100 - 8.8
    return min(0.10, excess * 0.035)


_MONO_SUBJECT = re.compile(r"^(?:他|她|他们|她们)\s*")


def repetitive_subject_penalty(text: str) -> float:
    """连续以「他/她…」开头的句子比例过高。"""
    # 粗略按句号、问号、感叹号、换行切段
    parts = [p.strip() for p in re.split(r"[。\n!?？！]", text) if p.strip()]
    if len(parts) < 10:
        return 0.0

    mono = sum(1 for p in parts if _MONO_SUBJECT.match(p))
    r = mono / len(parts)
    if r < 0.42:
        return 0.0
    excess = r - 0.42
    return min(0.12, excess * 0.35)


_SENT_LEN_SPLIT = re.compile(r"[。！？!?]")


def sentence_length_uniformity_penalty(text: str) -> float:
    """句子长度极端均匀 → 读来像匀速输出；给轻微节奏税。"""
    sents = [s.strip() for s in _SENT_LEN_SPLIT.split(text) if s.strip()]
    if len(sents) < 14:
        return 0.0
    lens = [len(s) for s in sents]
    avg = sum(lens) / len(lens)
    if avg < 14:
        return 0.0
    variance = sum((x - avg) ** 2 for x in lens) / len(lens)
    sd = variance ** 0.5
    # sd 非常小且平均句偏长时才罚
    if sd > max(avg * 0.45, 7.8):
        return 0.0
    severity = math.exp(-sd / max(avg * 0.18, 1.0))
    return min(0.08, severity * 0.06)


def combined_language_surface_penalty(text: str) -> float:
    """合并语言类表面扣分，封顶避免与既有违规爆炸叠加。"""
    p = (
        narrator_register_penalty(text)
        + de_particle_pressure_penalty(text)
        + repetitive_subject_penalty(text)
        + sentence_length_uniformity_penalty(text)
    )
    return min(0.22, p)


def bulky_paragraph_metrics(text: str) -> Tuple[int, int]:
    """返回 (超长段落数量, 总有效段数)。

    「超长」阈值：段落字符数明显高于网文排版舒适区时常暗示信息块未切开。
    """
    paras = [p.strip().replace("\r\n", "\n") for p in text.split("\n\n") if p.strip()]
    if not paras:
        paras = [p.strip() for p in text.splitlines() if p.strip()]
        if not paras:
            return 0, 0
    lengths = []
    for p in paras:
        lc = len(p.replace(" ", "").replace("\n", ""))
        lengths.append(lc)
    total = len(lengths)

    avg = sum(lengths) / max(total, 1)
    # 动态阈值：平均值较大时阈值略放宽
    cut = max(420, min(760, avg * 1.95 + 120))
    long_ct = sum(1 for lc in lengths if lc >= cut)
    return long_ct, total


def default_scene_rhythm_penalty(text: str) -> Tuple[float, str]:
    """无特定场景归类时的通用节奏扣分与说明短语。"""
    body = "".join(text.split())
    if len(body) < 280:
        return 0.0, ""

    long_ct, para_total = bulky_paragraph_metrics(text)
    if para_total <= 2:
        return 0.0, ""

    ratio = long_ct / max(para_total, 1)

    penalty = 0.0
    detail_bits: List[str] = []
    if long_ct >= 2 and ratio >= 0.22:
        p = min(0.38, ratio * 0.55 + (long_ct - 2) * 0.04)
        penalty += p
        detail_bits.append(f"连续大块段落偏多（≥{long_ct}段超长）")

    # 标点节奏：超长段 + 问号/省略号稀薄时略罚
    if len(body) > 650:
        qmarks = body.count("？") + body.count("?")
        ellip = body.count("…") + body.count("......")
        if qmarks + ellip < 2 and long_ct >= 1:
            penalty += 0.05
            detail_bits.append("对话/悬念标点稀少且段落偏臃肿")

    return min(0.38, penalty), "；".join(detail_bits)
