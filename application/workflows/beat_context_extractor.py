"""节拍上下文确定性抽取器。

这里不调用 LLM，也不写剧情方向；只从已生成正文里抽取“承接下一节拍”
需要的结构信号，供 prompt 组装层使用。
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class BeatTailAnchor:
    """节拍尾部衔接锚点。"""

    tail_state: str = ""
    mood_tone: str = ""
    last_moment: str = ""


def extract_paragraph_participants(paragraph: str) -> str:
    """从段落中提取疑似参与角色名。

    规则只依赖中文叙事/对白语法信号，不依赖具体题材或固定角色名。
    """
    text = paragraph or ""
    candidates: list[str] = []
    patterns = [
        r"([\u4e00-\u9fff]{2,6}?)(?:回答|嘀咕|嘟囔|低声|沉声|说|道|喊|叫|问|吼|笑|叹)",
        r"([\u4e00-\u9fff]{2,6}?)[：:][“\"「『]",
        r"[“\"「『][^”\"」』]{1,80}[”\"」』]\s*([\u4e00-\u9fff]{2,6}?)(?:回答|说|道|问|答|喊|吼)",
    ]
    for pattern in patterns:
        candidates.extend(re.findall(pattern, text))

    seen: set[str] = set()
    unique: list[str] = []
    for name in candidates:
        name = _normalize_participant_name(name)
        if len(name) < 2 or name in seen:
            continue
        seen.add(name)
        unique.append(name)

    return "、".join(unique[:3])


def _normalize_participant_name(value: str) -> str:
    name = (value or "").strip()
    name = re.sub(r"(低声|沉声|轻声|冷声|厉声|小声|忽然|突然)?(说|道|问|答|喊|叫|回答|嘀咕|嘟囔)$", "", name)
    name = re.sub(r"(低声|沉声|轻声|冷声|厉声|小声)$", "", name)
    return name.strip()


def extract_core_event(paragraph: str) -> str:
    """抽取段落核心事件。

    评分维度是通用叙事信号：动作、冲突、对白、状态变化和段落位置。
    不内置题材示例，不把任意第一句当成事件。
    """
    sentences = _split_sentences(paragraph)
    if not sentences:
        return ""

    scored: list[tuple[int, int, str]] = []
    last_index = len(sentences) - 1
    for index, sentence in enumerate(sentences):
        score = _score_event_sentence(sentence)
        if index == 0:
            score += 1
        if index == last_index:
            score += 2
        scored.append((score, index, sentence))

    scored.sort(key=lambda item: (-item[0], item[1]))
    selected = scored[0][2]

    if len(sentences) > 1 and scored[0][1] != last_index:
        tail = sentences[-1]
        if _score_event_sentence(tail) >= 2 and tail != selected:
            selected = f"{selected}；{tail}"

    return _compress_sentence(selected, limit=72)


def extract_beat_tail_anchor(prior_draft: str) -> BeatTailAnchor:
    """从上一节拍正文中抽取衔接锚点。"""
    if not prior_draft or not prior_draft.strip():
        return BeatTailAnchor()

    tail = prior_draft.strip()[-300:]
    anchor = BeatTailAnchor()

    sentences = _split_sentences(tail)
    if sentences:
        anchor.last_moment = "。".join(sentences[-2:])
        anchor.last_moment = _compress_sentence(anchor.last_moment, limit=150, keep_tail=True)

    anchor.tail_state = _detect_tail_state(tail)
    anchor.mood_tone = _detect_mood(tail)
    return anchor


def _split_sentences(text: str) -> list[str]:
    raw = (text or "").strip()
    if not raw:
        return []
    parts = re.findall(r"[^。！？!?…]+[。！？!?…]*", raw)
    return [part.strip(" \n\r\t。！？!?") for part in parts if part.strip(" \n\r\t。！？!?")]


def _score_event_sentence(sentence: str) -> int:
    text = sentence or ""
    score = 0
    if re.search(r"[“\"「『].{1,80}[”\"」』]", text):
        score += 2
    if re.search(r"(冲突|争执|质问|拒绝|暴露|揭开|发现|确认|决定|选择|交易|追问|警告|威胁|承认)", text):
        score += 4
    if re.search(r"(走|跑|冲|抓|推|拉|打|踢|跳|站|坐|起身|倒下|转身|举起|放下|握住|按住|敲|摔|跌|躲|闪|挡|拔出|刺|劈|砍|射|扔|砸|撞|翻|爬|滚|逃|追|拦)", text):
        score += 3
    if re.search(r"(意识到|明白|想起|看见|听见|察觉|感觉|变得|开始|终于|突然)", text):
        score += 2
    if len(text) < 6:
        score -= 2
    if len(text) > 90:
        score -= 1
    return score


def _detect_tail_state(tail: str) -> str:
    stripped = (tail or "").strip()
    if re.search(r"[“\"「『][^”\"」』]{1,120}[”\"」』]\s*$", stripped) or re.search(r"[：:]\s*[“\"「『]?$", stripped):
        return "对话中"
    if re.search(r"(……|——|…)\s*$", stripped):
        return "悬念中"
    if re.search(r"(走|跑|冲|抓|推|拉|打|踢|跳|站|坐|起|倒|转|举|放|握|按|敲|摔|跌|躲|闪|挡|拔|刺|劈|砍|射|扔|掷|砸|撞|翻|爬|滚|逃|追|赶|拦)[了着过]?\s*$", stripped):
        return "动作中"
    if re.search(r"(后来|随后|不久|片刻|这时|此时|翌日|次日|黄昏|清晨|深夜)", stripped[-100:]):
        return "场景转换"
    return "叙述中"


def _detect_mood(tail: str) -> str:
    mood_keywords = {
        "紧张": ["紧张", "屏息", "心跳", "颤抖", "冷汗", "握紧", "僵住", "不敢"],
        "愤怒": ["怒", "愤", "吼", "咆哮", "拍桌", "攥紧", "咬牙"],
        "悲伤": ["哭", "泪", "哽咽", "沉默", "低下头", "黯然", "苦笑"],
        "悬疑": ["奇怪", "不对", "可疑", "蹊跷", "疑问", "谁", "为什么", "难道"],
        "舒缓": ["笑", "轻松", "温暖", "舒适", "安心", "释然", "平静"],
        "日常": ["日常", "吃饭", "喝茶", "散步", "闲聊", "笑着", "点头"],
    }
    text = tail or ""
    best_mood = "日常"
    best_hits = 0
    for mood, keywords in mood_keywords.items():
        hits = sum(1 for keyword in keywords if keyword in text)
        if hits > best_hits:
            best_hits = hits
            best_mood = mood
    return best_mood


def _compress_sentence(sentence: str, *, limit: int, keep_tail: bool = False) -> str:
    text = re.sub(r"\s+", " ", (sentence or "").strip())
    if len(text) <= limit:
        return text
    if keep_tail:
        return text[-limit:]
    return text[: max(0, limit - 1)] + "…"
