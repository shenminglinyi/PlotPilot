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

import logging

from application.workflows.beat_context_extractor import (
    BeatTailAnchor,
    extract_beat_tail_anchor,
    extract_core_event,
    extract_paragraph_participants,
)

logger = logging.getLogger(__name__)

# ── 滑动窗口参数 ──
# 单章内累计正文注入上限
_MAX_PRIOR_DRAFT_CHARS = 14_000

# 🔗 V3：近期节拍全文保留阈值（最近 1-2 个节拍，约 2000-3000 字）
_RECENT_BEATS_FULL_CHARS = 3_000

# 🔗 V3：结构化回溯上限（远期节拍压缩后的摘要，约 500 字）
_RECAP_MAX_CHARS = 500

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

        characters = extract_paragraph_participants(para)

        core_event = extract_core_event(para)

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

def build_beat_transition_directive(
    anchor: BeatTailAnchor,
    beat_index: int,
    total_beats: int,
    next_beat_description: str = "",
) -> str:
    """构建节拍间过渡建议（V9: 从铁律降级为建议）

    V9 设计哲学：
      原来的"节拍衔接铁律"过于刚性——不允许"后来"、"之后"等跳跃词，
      强迫每一节拍必须物理接续上一节拍。这扼杀了节拍间的"呼吸感"。

      新设计：给出衔接建议而非铁律，允许 AI 灵活处理节拍间过渡。
    """
    if not anchor.tail_state and not anchor.last_moment:
        # 无锚点信息，用通用过渡
        return (
            f"【节拍过渡（第{beat_index + 1}/{total_beats}节拍）】\n"
            f"- 从上一节拍的结尾自然过渡\n"
            f"- 保持叙事流畅"
        )

    parts = [f"【🔗 节拍过渡参考（第{beat_index + 1}/{total_beats}节拍）】"]

    # 1. 前节拍状态 → 衔接建议（V9: 从"必须"变为"可以"）
    state_directives = {
        "对话中": (
            "上一节拍停在对白中间。你可以：\n"
            "  - 先回应/延续对话（保持弦外之音和情绪张力）\n"
            "  - 或用旁白视角补充角色内心，再回到对话\n"
            "  - 对话自然结束后再推进新情节"
        ),
        "动作中": (
            "上一节拍停在一个动作进行中。你可以：\n"
            "  - 展示该动作的完成或结果\n"
            "  - 或跳过动作结果，从后续反应开始\n"
            "  - 写角色对动作结果的反应（表情/心理/下一步）"
        ),
        "悬念中": (
            "上一节拍留下了悬念。你可以：\n"
            "  - 延续悬念的紧张感（用角色反应加深而非消解）\n"
            "  - 或暂时搁置，从另一条线索开篇\n"
            "  - 如果合适，也可以揭晓悬念"
        ),
        "叙述中": (
            "上一节拍在叙述中结束。你可以：\n"
            "  - 承接叙述的情绪惯性自然过渡\n"
            "  - 或切换到具体场景/对话打破叙述节奏\n"
            "  - 用环境细节或角色动作作为过渡桥梁"
        ),
        "场景转换": (
            "上一节拍有场景/时间转换。你可以：\n"
            "  - 在新场景中用感官细节站稳脚跟\n"
            "  - 或直接进入新场景的对话/动作\n"
            "  - 时间跳跃是合法的文学技法"
        ),
    }

    directive = state_directives.get(anchor.tail_state, "从上一节拍自然过渡。")
    parts.append(directive)

    # 2. 情绪基调 → 情绪参考（V9: 从"不能"变为"建议"）
    mood_directives = {
        '紧张': "情绪参考：上一节拍紧张，紧张感通常会延续一段时间。",
        '愤怒': "情绪参考：上一节拍愤怒，余怒未消是常见的。",
        '悲伤': "情绪参考：上一节拍悲伤，悲伤有惯性。",
        '悬疑': "情绪参考：上一节拍悬疑，不要急于揭晓。",
        '舒缓': "情绪参考：上一节拍舒缓，可以自然过渡。",
        '日常': "情绪参考：日常节奏。",
    }

    mood_hint = mood_directives.get(anchor.mood_tone, "")
    if mood_hint:
        parts.append(mood_hint)

    # 3. 最后画面 → 参考信息（V9: 不再说"必须接续"）
    if anchor.last_moment:
        parts.append(
            f"📍 上一节拍最后画面：……{anchor.last_moment}"
        )

    # 4. 下一节拍描述（如果有）
    if next_beat_description:
        parts.append(f"📋 本节拍方向：{next_beat_description[:80]}")

    # V9: 删除了原来的"节拍衔接铁律"3条禁令
    # 不再禁止跳跃词，不再强制物理接续

    return "\n".join(parts)
