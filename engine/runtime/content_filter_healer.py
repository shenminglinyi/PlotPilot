"""内容风控自动诊断与修复。

部分厂商(MiniMax 等)对输入做强制内容风控,章节正文中个别措辞会触发
1026/1027(input/output new_sensitive)类 5xx,且重试永远无效——此前表现
为审计阶段连续失败数百次、全书挂起。本模块在生命周期错误路径上自动:

1. 识别风控类错误(``is_content_filter_error``);
2. 对章节正文做二分探测,定位最小触发片段(``localize_flagged_fragments``);
3. 让 LLM 在保留情节/文风的前提下最小改写该片段,整章复检通过后回写章节
   (``heal_latest_chapter``),下一轮守护进程轮询即恢复正常流程。

所有探测/改写经由 host.llm_service(不经过熔断计数);设置环境变量
``PLOTPILOT_DISABLE_CONTENT_HEAL=1`` 可整体停用。
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Awaitable, Callable

from domain.ai.services.llm_service import GenerationConfig
from domain.ai.value_objects.prompt import Prompt

logger = logging.getLogger(__name__)

# 风控错误特征(不区分大小写匹配异常文本)
CONTENT_FILTER_MARKERS = ("new_sensitive", "(1026)", "(1027)")

# 单轮定位的探测次数上限,控制诊断成本
MAX_PROBES = 16
# 整章复检仍触发时的改写轮数上限
MAX_HEAL_ROUNDS = 3
# 二分下限(字符),避免碎片小到无法改写
MIN_FRAGMENT_LEN = 8

Probe = Callable[[str], Awaitable[None]]


def is_content_filter_error(exc: BaseException) -> bool:
    """判断异常是否为厂商内容风控拒绝(1026/1027/new_sensitive)。"""
    text = f"{type(exc).__name__}: {exc}".lower()
    return any(marker in text for marker in CONTENT_FILTER_MARKERS)


def content_heal_disabled() -> bool:
    return os.environ.get("PLOTPILOT_DISABLE_CONTENT_HEAL", "").strip() in ("1", "true", "yes")


@dataclass
class HealOutcome:
    ok: bool
    content: str = ""
    note: str = ""


class _ProbeUnexpectedError(RuntimeError):
    """探测请求本身失败(网络/鉴权等),无法判断片段是否触发风控。"""


async def _trips(probe: Probe, text: str) -> bool:
    """探测一段文本:风控拒绝 → True;正常响应 → False;其他异常 → 上抛。"""
    try:
        await probe(text)
        return False
    except Exception as exc:
        if is_content_filter_error(exc):
            return True
        raise _ProbeUnexpectedError(f"探测请求失败: {type(exc).__name__}: {exc}") from exc


async def localize_flagged_fragments(
    probe: Probe,
    content: str,
    *,
    max_probes: int = MAX_PROBES,
    min_fragment_len: int = MIN_FRAGMENT_LEN,
) -> list[str] | None:
    """按句子边界二分定位触发风控的最小片段集合。

    返回片段列表(可能为空列表=复检已通过);组合语境触发无法定位时返回 None。
    按句子边界而非中点切分,避免把触发词切成两半导致两侧都探测通过。
    """
    if not await _trips(probe, content):
        return []

    fragments: list[str] = []
    stack: list[str] = [content]
    probes_used = 1

    while stack:
        seg = stack.pop()
        split = _bisect_split(seg) if len(seg) >= min_fragment_len else None
        if split is None or probes_used >= max_probes:
            fragments.append(seg)
            continue
        left, right = split
        left_trips = await _trips(probe, left) if left.strip() else False
        right_trips = await _trips(probe, right) if right.strip() else False
        probes_used += (1 if left.strip() else 0) + (1 if right.strip() else 0)
        if left_trips:
            stack.append(left)
        if right_trips:
            stack.append(right)
        if not left_trips and not right_trips:
            # 两半单独都不触发 → 组合语境触发,无法安全定位
            return None

    return fragments or None


def _bisect_split(seg: str) -> tuple[str, str] | None:
    """在尽量靠近中点的句子边界处把片段切成两半;单句片段不可切。"""
    import re

    sentences = [p for p in re.split(r"(?<=[。!?！？\n])", seg) if p.strip()]
    if len(sentences) < 2:
        return None
    total = len(seg)
    best_index, best_diff = 1, None
    for i in range(1, len(sentences)):
        left_len = sum(len(s) for s in sentences[:i])
        diff = abs(left_len - (total - left_len))
        if best_diff is None or diff < best_diff:
            best_index, best_diff = i, diff
    return "".join(sentences[:best_index]), "".join(sentences[best_index:])


async def _rewrite_fragment(
    generate: Callable[[Prompt, GenerationConfig], Awaitable[object]],
    fragment: str,
    context_before: str,
    context_after: str,
) -> str:
    """让 LLM 对触发片段做最小改写(保留情节/人物/文风)。"""
    system = (
        "你是小说文字编辑。用户提供的一个小说片段被平台内容风控误判拦截。"
        "请在完全保留情节、人物、信息量与文风的前提下对片段做最小改写——"
        "只调整可能触发审查的措辞,禁止增删情节或改变叙述内容。只输出改写后的片段本身,不要任何解释或引号。"
    )
    context_parts = []
    if context_before.strip():
        context_parts.append(f"【前文(仅供参考,不要输出)】…{context_before[-120:]}")
    context_parts.append(f"【待改写片段】\n{fragment}")
    if context_after.strip():
        context_parts.append(f"【后文(仅供参考,不要输出)】…{context_after[:120]}")
    user = "\n\n".join(context_parts)

    result = await generate(
        Prompt(system=system, user=user),
        GenerationConfig(temperature=0.3),
    )
    rewritten = str(result.content).strip().strip("“”\"'").strip()
    return rewritten


async def heal_latest_chapter(
    host: Any,
    novel: Any,
    probe: Probe,
) -> HealOutcome:
    """诊断并修复触发风控的最近完成章节正文。

    流程:定位片段 → LLM 最小改写 → 整章复检 → 通过则回写章节。
    最多 MAX_HEAL_ROUNDS 轮;任何一步无法完成都返回 ok=False 并带原因。
    """
    from domain.novel.entities.novel import NovelId

    chapter_num = host._latest_completed_chapter_number(NovelId(novel.novel_id.value))
    if chapter_num is None:
        return HealOutcome(ok=False, note="找不到已完成章节,无法定位风控内容")

    chapter = host.chapter_repository.get_by_novel_and_number(
        NovelId(novel.novel_id.value), chapter_num
    )
    if not chapter or not (chapter.content or "").strip():
        return HealOutcome(ok=False, note=f"第 {chapter_num} 章内容为空,无法诊断")

    content = chapter.content
    generate = host.llm_service.generate

    for round_no in range(1, MAX_HEAL_ROUNDS + 1):
        fragments = await localize_flagged_fragments(probe, content)
        if fragments is None:
            return HealOutcome(ok=False, note="触发点由多段内容组合语境产生,无法自动定位")
        if not fragments:
            # 复检已通过(例如上一轮改写已生效),直接回写
            _persist(host, chapter, content)
            return HealOutcome(ok=True, content=content, note="复检通过")

        for frag in fragments:
            idx = content.find(frag)
            rewritten = await _rewrite_fragment(
                generate, frag, content[:idx], content[idx + len(frag):]
            )
            if not rewritten or rewritten == frag:
                return HealOutcome(ok=False, note="LLM 改写无有效输出")
            logger.info(
                "[%s] 内容风控自修复: 第%s章片段改写 %r -> %r",
                novel.novel_id.value, chapter_num, frag[:60], rewritten[:60],
            )
            content = content.replace(frag, rewritten, 1)

        if not await _trips(probe, content):
            _persist(host, chapter, content)
            logger.info(
                "[%s] 内容风控自修复成功: 第%s章已改写并复检通过(第 %s 轮)",
                novel.novel_id.value, chapter_num, round_no,
            )
            return HealOutcome(ok=True, content=content, note=f"第 {round_no} 轮改写后复检通过")

    return HealOutcome(ok=False, note=f"{MAX_HEAL_ROUNDS} 轮改写后整章复检仍触发风控")


def _persist(host: Any, chapter: Any, new_content: str) -> None:
    chapter.content = new_content
    host.chapter_repository.save(chapter)


def make_llm_probe(host: Any) -> Probe:
    """构造探测函数:最小请求,仅判断是否触发风控(不经过熔断计数)。"""

    async def probe(text: str) -> None:
        result = await host.llm_service.generate(
            Prompt(system="你是助手", user=text[:60000]),
            GenerationConfig(temperature=0.1),
        )
        _ = result.content  # 正常返回即可

    return probe
