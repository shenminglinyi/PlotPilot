"""同章多节拍续写：将已生成正文注入后续节拍 prompt，减少重复铺垫与对白。

V2 增强：节拍间衔接锚点提取 + 精确过渡指令。

核心问题：
  原来的"连贯性要求"只有5条泛泛规则，AI 不知道上一节拍
  最后停在"对话中间"还是"动作进行中"还是"情绪高潮"，
  导致节拍间的割裂感——像电视剧每段广告后的"跳跃"。

解决方案：
  从上一节拍末尾 ~300 字提取3维衔接锚点：
  1. 尾部状态（对话中/动作中/叙述中/悬念中）
  2. 情绪基调（紧张/舒缓/愤怒/悲伤/日常）
  3. 最后的画面/动作/台词

  然后生成精确的过渡指令，注入到下一节拍的 prompt 中。
"""

import re
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ── 滑动窗口参数 ──
# 单章内累计正文注入上限
_MAX_PRIOR_DRAFT_CHARS = 14_000

# 🔗 V3：近期节拍全文保留阈值（最近 1-2 个节拍，约 2000-3000 字）
_RECENT_BEATS_FULL_CHARS = 3_000

# 🔗 V3：结构化回溯上限（远期节拍压缩后的摘要，约 500 字）
_RECAP_MAX_CHARS = 500


@dataclass
class BeatTailAnchor:
    """节拍尾部衔接锚点

    不是摘要，是"导演的转场笔记"——
    告诉下一节拍的作者（AI）上一节拍"镜头"停在哪里。
    """
    # 尾部状态：对话中 / 动作中 / 叙述中 / 悬念中 / 场景转换
    tail_state: str = ""

    # 情绪基调：紧张 / 舒缓 / 愤怒 / 悲伤 / 日常 / 悬疑
    mood_tone: str = ""

    # 最后的画面/动作/台词（原文截取，~100字）
    last_moment: str = ""


def format_prior_draft_for_prompt(chapter_draft_so_far: str) -> str:
    """V3 滑动窗口 + 结构化回溯

    核心思想（专业小说家视角）：
      作家从来不是把前文从头到尾再读一遍再继续写。
      他脑子里有两种记忆：
        1. "刚才写到哪了" —— 最近 1-2 段的画面、对白、动作（全文保留）
        2. "前面发生了什么" —— 更早的情节骨架（压缩成结构化摘要）

      把 14000 字的全文丢给 LLM，就像让作家每写一段都要
      从头重新读一遍——他的注意力会被分散，真正重要的"衔接信号"
      反而被淹没了。

    架构设计（AI 架构师视角）：
      ┌─────────────────────────────────────────────────────┐
      │  Prompt 上下文布局                                    │
      │                                                       │
      │  [结构化回溯] ← 远期节拍压缩摘要（~500字）             │
      │   "第1节拍：顾言之在茶馆与赵宇对峙，赵宇提到了……"      │
      │   "第2节拍：两人发生冲突，赵宇摔门而出"                │
      │                                                       │
      │  [近期全文] ← 最近 1-2 个节拍原文（~3000字）           │
      │   （完整的对白、动作、环境描写，让 AI 精确衔接）       │
      │                                                       │
      │  [衔接指令] ← 基于近期全文尾部的精确过渡约束           │
      │   "上一节拍停在对话中间，本节拍必须先回应"             │
      └─────────────────────────────────────────────────────┘

      这样 LLM 的注意力集中在：
      - 近期全文 → 精确衔接（"接住"上一节拍）
      - 结构化回溯 → 避免重复（"知道"前面发生了什么）
      - 衔接指令 → 强约束（"必须"怎么接）

    Args:
        chapter_draft_so_far: 本章从第1节拍到当前的累积正文

    Returns:
        格式化后的上文，包含结构化回溯 + 近期全文
    """
    raw = (chapter_draft_so_far or "").strip()
    if not raw:
        return ""

    # 短内容：全部保留（不需要回溯）
    if len(raw) <= _MAX_PRIOR_DRAFT_CHARS:
        return raw

    # ── 分割：近期全文 + 远期回溯 ──
    recent_full = raw[-_RECENT_BEATS_FULL_CHARS:]
    distant_part = raw[:-_RECENT_BEATS_FULL_CHARS]

    # ── 远期部分：压缩成结构化回溯 ──
    recap = _build_structured_recap(distant_part)

    omitted = len(distant_part) - len(recap)

    return (
        f"【📖 本章前段回溯（结构化摘要，{omitted}字→{len(recap)}字）】\n"
        f"{recap}\n\n"
        f"【📝 本章近期正文（全文保留，从此处精确衔接）】\n"
        f"{recent_full}"
    )


def _build_structured_recap(distant_text: str) -> str:
    """将远期正文压缩为结构化回溯

    策略（不用 LLM，纯启发式）：
      1. 按段落/节拍分割
      2. 每段提取：核心事件 + 涉及角色 + 情绪走向
      3. 压缩成一句话概述

    性能：纯字符串操作，零 LLM 调用，微秒级。
    """
    if not distant_text or not distant_text.strip():
        return ""

    # 按 \n\n 分割成段落
    paragraphs = [p.strip() for p in distant_text.split("\n\n") if p.strip()]

    if not paragraphs:
        return ""

    # 如果段落很少，直接截断尾部保留
    if len(paragraphs) <= 3:
        tail = distant_text[-_RECAP_MAX_CHARS:]
        return f"…{tail}"

    recap_parts = []

    # 对每个段落提取核心信息
    for i, para in enumerate(paragraphs):
        if not para:
            continue

        # 提取角色名（引号前的主语）
        characters = _extract_characters_from_paragraph(para)

        # 提取核心动作/事件（简化版：取第一句和最后一句的关键信息）
        core_event = _extract_core_event(para)

        if core_event:
            prefix = f"[段{i+1}]"
            if characters:
                prefix += f" {characters}："
            else:
                prefix += " "
            recap_parts.append(f"{prefix}{core_event}")

    # 如果回溯太长，只保留关键段落（首段 + 尾段 + 含冲突的段落）
    recap_text = "\n".join(recap_parts)
    if len(recap_text) > _RECAP_MAX_CHARS:
        # 保留首段和尾段，中间的找最关键的
        if len(recap_parts) > 2:
            recap_text = recap_parts[0] + "\n…\n" + recap_parts[-1]
        if len(recap_text) > _RECAP_MAX_CHARS:
            recap_text = recap_text[-_RECAP_MAX_CHARS:]

    return recap_text


def _extract_characters_from_paragraph(para: str) -> str:
    """从段落中提取出现的角色名（启发式）"""
    # 寻找对话引号前的主语
    speakers = re.findall(r'([\u4e00-\u9fff]{2,4})[说道喊叫问回答吼笑叹嘀咕嘟囔]', para)

    # 去重
    seen = set()
    unique = []
    for s in speakers:
        if s not in seen and len(s) >= 2:
            seen.add(s)
            unique.append(s)

    return "、".join(unique[:3]) if unique else ""


def _extract_core_event(para: str) -> str:
    """从段落中提取核心事件（一句话概述）

    策略：取第一个完整句子，压缩到 60 字以内。
    """
    if not para:
        return ""

    # 取第一个完整句子
    sentences = re.split(r'[。！？…]', para)
    first = ""
    for s in sentences:
        if s.strip() and len(s.strip()) >= 4:
            first = s.strip()
            break

    if not first:
        first = para[:50]

    # 压缩到 60 字
    if len(first) > 60:
        first = first[:57] + "…"

    return first


def extract_beat_tail_anchor(prior_draft: str) -> BeatTailAnchor:
    """从上一节拍已生成正文中提取衔接锚点（启发式，零 LLM 调用）

    策略：分析最后 ~300 字，判断尾部状态和情绪基调。
    """
    if not prior_draft or not prior_draft.strip():
        return BeatTailAnchor()

    tail = prior_draft.strip()[-300:]

    anchor = BeatTailAnchor()

    # ── 1. 提取最后的画面/动作/台词 ──
    # 取最后2-3个完整句子
    sentences = re.split(r'[。！？…]', tail)
    last_sentences = [s.strip() for s in sentences if s.strip()][-3:]
    if last_sentences:
        anchor.last_moment = "。".join(last_sentences[-2:])
        if len(anchor.last_moment) > 150:
            anchor.last_moment = anchor.last_moment[-150:]

    # ── 2. 判断尾部状态 ──
    # 对话中：末尾有引号或冒号开头的台词
    if re.search(r'[""「『].*[""」』]$', tail) or re.search(r'[：:][""「『]$', tail):
        anchor.tail_state = "对话中"
    # 悬念中：末尾有省略号或破折号
    elif re.search(r'(……|——|…)$', tail):
        anchor.tail_state = "悬念中"
    # 动作中：末尾有动作动词
    elif re.search(r'(走|跑|冲|抓|推|拉|打|踢|跳|站|坐|起|倒|转|举|放|握|按|敲|踢|摔|跌|躲|闪|挡|拔|刺|劈|砍|射|扔|掷|砸|撞|翻|爬|滚|逃|追|赶|拦|挡)[了着过]??$', tail):
        anchor.tail_state = "动作中"
    # 场景转换：有明确的时间/地点变化词
    elif re.search(r'(后来|随后|不久|片刻|这时|此时|翌日|次日|黄昏|清晨|深夜)', tail[-100:]):
        anchor.tail_state = "场景转换"
    else:
        anchor.tail_state = "叙述中"

    # ── 3. 判断情绪基调 ──
    mood_keywords = {
        '紧张': ['紧张', '屏息', '心跳', '颤抖', '冷汗', '握紧', '僵住', '不敢'],
        '愤怒': ['怒', '愤', '吼', '咆哮', '拍桌', '攥紧', '咬牙'],
        '悲伤': ['哭', '泪', '哽咽', '沉默', '低下头', '黯然', '苦笑'],
        '悬疑': ['奇怪', '不对', '可疑', '蹊跷', '疑问', '谁', '为什么', '难道'],
        '舒缓': ['笑', '轻松', '温暖', '舒适', '安心', '释然', '平静'],
        '日常': ['日常', '吃饭', '喝茶', '散步', '闲聊', '笑着', '点头'],
    }

    tail_lower = tail.lower()
    max_hits = 0
    for mood, keywords in mood_keywords.items():
        hits = sum(1 for kw in keywords if kw in tail_lower)
        if hits > max_hits:
            max_hits = hits
            anchor.mood_tone = mood

    if not anchor.mood_tone:
        anchor.mood_tone = "日常"

    return anchor


def build_beat_transition_directive(
    anchor: BeatTailAnchor,
    beat_index: int,
    total_beats: int,
    next_beat_description: str = "",
) -> str:
    """构建节拍间精确过渡指令

    根据上一节拍的尾部锚点，生成精确的衔接约束——
    不再是泛泛的"保持连贯性"，而是告诉 AI：
    "上一节拍停在对话中间，这一节拍要先接住对话再推进"
    """
    if not anchor.tail_state and not anchor.last_moment:
        # 无锚点信息，用通用过渡
        return (
            f"【节拍过渡（第{beat_index + 1}/{total_beats}节拍）】\n"
            f"- 从上一节拍的结尾自然过渡\n"
            f"- 保持叙事流畅，避免突兀跳跃"
        )

    parts = [f"【🔗 节拍衔接指令（第{beat_index + 1}/{total_beats}节拍）】"]

    # 1. 前节拍状态 → 衔接方式
    state_directives = {
        "对话中": (
            "上一节拍停在对白中间。本节拍开头必须：\n"
            "  - 先给出对话的回应或延续（不能跳过不答）\n"
            "  - 保持对话的弦外之音和情绪张力\n"
            "  - 对话回合自然结束后再推进新情节"
        ),
        "动作中": (
            "上一节拍停在一个动作进行中。本节拍开头必须：\n"
            "  - 先展示该动作的完成或结果\n"
            "  - 动作完成后写角色的反应（表情/心理/下一步）\n"
            "  - 不能假装动作已经结束，必须写出过程"
        ),
        "悬念中": (
            "上一节拍留下了悬念（省略号/破折号结尾）。本节拍开头必须：\n"
            "  - 延续这个悬念的紧张感——用角色的反应来加深而非消解\n"
            "  - 可以继续拉高悬念，但不要立刻揭晓答案\n"
            "  - 前三句必须让读者感觉到'有什么事情要发生了'"
        ),
        "叙述中": (
            "上一节拍在叙述中结束。本节拍必须：\n"
            "  - 承接叙述的情绪惯性，不要突然切换节奏\n"
            "  - 从叙述自然过渡到具体场景或对话\n"
            "  - 用环境细节或角色动作作为过渡桥梁"
        ),
        "场景转换": (
            "上一节拍有场景/时间转换。本节拍必须：\n"
            "  - 先在新场景中站稳脚跟——写环境、写角色位置\n"
            "  - 新场景的第一段必须有感官细节（画面/声音/温度）\n"
            "  - 不能跳过场景建立直接开始对话"
        ),
    }

    directive = state_directives.get(anchor.tail_state, "从上一节拍自然过渡。")
    parts.append(directive)

    # 2. 情绪基调 → 情绪衔接
    mood_directives = {
        '紧张': "⚠ 情绪基调：紧张。不能突然轻松——紧张感至少延续到本节拍第一段结束。",
        '愤怒': "⚠ 情绪基调：愤怒。余怒未消——角色不能立刻冷静，至少开头还带着火气。",
        '悲伤': "⚠ 情绪基调：悲伤。悲伤有惯性——角色的沉默或低落至少持续到第一段结束。",
        '悬疑': "⚠ 情绪基调：悬疑。不要急于揭晓——让角色和读者多困惑一会。",
        '舒缓': "情绪基调：舒缓。可以自然过渡到新话题，但不要突然变紧张。",
        '日常': "情绪基调：日常。保持轻松自然的节奏。",
    }

    mood_hint = mood_directives.get(anchor.mood_tone, "")
    if mood_hint:
        parts.append(mood_hint)

    # 3. 最后画面 → 精确衔接
    if anchor.last_moment:
        parts.append(
            f"📍 上一节拍最后画面：……{anchor.last_moment}\n"
            f"→ 本节拍开头必须从这之后自然接续"
        )

    # 4. 下一节拍描述（如果有）
    if next_beat_description:
        parts.append(f"📋 本节拍方向：{next_beat_description[:80]}")

    # 5. 衔接铁律
    parts.append(
        "━━━ 节拍衔接铁律 ━━━\n"
        "① 本节拍第一句话必须是上一节拍最后一幕的延续\n"
        "② 节拍之间没有空行跳转——读者看到的是连续的文本\n"
        "③ 不许用'后来'、'之后'等跳跃词来省略节拍间的过渡"
    )

    return "\n".join(parts)
