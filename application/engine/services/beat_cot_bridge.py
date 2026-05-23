"""节拍间 CoT（思维链）桥接服务

在每个节拍生成完毕后，分析叙事状态并为下一节拍生成精确的桥接指令。
这保证了连续节拍之间的叙事连贯性，避免"拼接感"。

核心设计：
- 使用方案C（叙事状态机）：active_scene + narrative_momentum + transition + risk
- 轻量调用：max_tokens=400，temperature=0.25，延迟 < 5s
- 完全可选：失败时静默降级，不影响主流程
- 结果直接注入下一节拍的 build_beat_prompt 调用
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 节拍尾部截取长度（字符数），用于提供上下文
_TAIL_CHARS = 500


@dataclass
class BeatActiveScene:
    location: str = ""
    characters_present: List[str] = field(default_factory=list)
    atmosphere: str = ""


@dataclass
class BeatTransition:
    type: str = "emotion_continue"  # emotion_continue|action_continue|dialogue_continue|scene_cut|internal_shift
    opening_line: str = ""          # 可直接写入正文的第一句话
    carry_forward: str = ""         # 必须延续的叙事要素


@dataclass
class BeatBridge:
    """节拍桥接分析结果

    由 compute_beat_bridge() 生成，注入到下一节拍的 build_beat_prompt() 中。
    """
    active_scene: BeatActiveScene = field(default_factory=BeatActiveScene)
    narrative_momentum: str = ""    # 读者注意力聚焦点
    transition: BeatTransition = field(default_factory=BeatTransition)
    risk: str = ""                  # 最容易出现的叙事断层

    @property
    def opening_line(self) -> str:
        return self.transition.opening_line

    @property
    def carry_forward(self) -> str:
        return self.transition.carry_forward

    def to_prompt_block(self) -> str:
        """生成注入 beat_prompt 的桥接块文本"""
        lines = ["【叙事衔接指令（承接上一节拍）】"]

        scene = self.active_scene
        if scene.location or scene.atmosphere:
            parts = []
            if scene.location:
                parts.append(f"地点：{scene.location}")
            if scene.atmosphere:
                parts.append(f"氛围：{scene.atmosphere}")
            lines.append("当前场景：" + " | ".join(parts))

        if scene.characters_present:
            lines.append("人物状态：" + "；".join(scene.characters_present))

        if self.narrative_momentum:
            lines.append(f"读者此刻关注：{self.narrative_momentum}")

        if self.transition.carry_forward:
            lines.append(f"必须延续：{self.transition.carry_forward}")

        if self.transition.opening_line:
            lines.append(f"你的第一句话（直接写入正文）：\n「{self.transition.opening_line}」")

        if self.risk:
            lines.append(f"刻意规避：{self.risk}")

        return "\n".join(lines)


def _parse_bridge_response(text: str) -> Optional[BeatBridge]:
    """解析 LLM 返回的 JSON 为 BeatBridge"""
    stripped = text.strip()
    # 去掉 Markdown 代码围栏
    if "```" in stripped:
        for chunk in stripped.split("```"):
            ch = chunk.strip()
            if ch.startswith("json"):
                ch = ch[4:].strip()
            if ch.startswith("{"):
                stripped = ch
                break
    # 提取 JSON
    lo = stripped.find("{")
    hi = stripped.rfind("}")
    if lo < 0 or hi <= lo:
        return None
    try:
        data = json.loads(stripped[lo: hi + 1])
    except json.JSONDecodeError:
        return None

    bridge = BeatBridge()

    # active_scene
    scene_raw = data.get("active_scene") or {}
    if isinstance(scene_raw, dict):
        bridge.active_scene = BeatActiveScene(
            location=str(scene_raw.get("location") or "").strip(),
            characters_present=[str(c) for c in (scene_raw.get("characters_present") or [])],
            atmosphere=str(scene_raw.get("atmosphere") or "").strip(),
        )

    bridge.narrative_momentum = str(data.get("narrative_momentum") or "").strip()

    # transition
    trans_raw = data.get("transition") or {}
    if isinstance(trans_raw, dict):
        bridge.transition = BeatTransition(
            type=str(trans_raw.get("type") or "emotion_continue").strip(),
            opening_line=str(trans_raw.get("opening_line") or "").strip(),
            carry_forward=str(trans_raw.get("carry_forward") or "").strip(),
        )

    bridge.risk = str(data.get("risk") or "").strip()
    return bridge


async def compute_beat_bridge(
    prev_beat_content: str,
    next_beat_intent: str,
    *,
    llm_service: Any = None,
    chapter_outline: str = "",
) -> Optional[BeatBridge]:
    """在节拍 N 生成完毕后，为节拍 N+1 计算 CoT 桥接指令。

    Args:
        prev_beat_content: 上一节拍的完整正文
        next_beat_intent: 下一节拍的叙事意图（来自 outline-beat-partition atoms[i].intent）
        llm_service: 可选，注入 LLM 实现（不传则从依赖注入获取）
        chapter_outline: 本章章纲（可选，帮助保持大局观）

    Returns:
        BeatBridge 对象，失败时返回 None（调用方应静默降级）
    """
    if not prev_beat_content or not next_beat_intent:
        return None

    # 截取尾部以减少 token 消耗
    tail = prev_beat_content.strip()[-_TAIL_CHARS:]

    try:
        from infrastructure.ai.prompt_keys import BEAT_COT_BRIDGE
        from infrastructure.ai.prompt_registry import get_prompt_registry
        from infrastructure.ai.prompt_manager import get_prompt_manager

        # 确保种子已加载
        try:
            get_prompt_manager().ensure_seeded()
        except Exception:
            pass

        reg = get_prompt_registry()
        rendered = reg.render(
            BEAT_COT_BRIDGE,
            {
                "prev_beat_tail": tail,
                "next_beat_intent": next_beat_intent,
                "chapter_outline": chapter_outline or "",
            },
        )

        system_text = (rendered.system or "").strip() if rendered else ""
        user_text = (rendered.user or "").strip() if rendered else ""

        if not user_text:
            logger.debug("[BeatCoTBridge] CPMS 渲染失败，使用内置 fallback 提示词")
            system_text, user_text = _build_fallback_prompts(tail, next_beat_intent)

    except Exception as e:
        logger.debug("[BeatCoTBridge] 加载 CPMS 节点失败（%s），使用内置 fallback", e)
        system_text, user_text = _build_fallback_prompts(tail, next_beat_intent)

    if not user_text:
        return None

    try:
        if llm_service is None:
            from interfaces.api.dependencies import get_llm_service
            llm_service = get_llm_service()

        from domain.ai.services.llm_service import GenerationConfig
        from domain.ai.value_objects.prompt import Prompt

        prompt = Prompt(system=system_text, user=user_text)
        config = GenerationConfig(max_tokens=400, temperature=0.25)

        pieces: List[str] = []
        async for chunk in llm_service.stream_generate(prompt, config):
            if chunk:
                pieces.append(chunk)

        raw_text = "".join(pieces).strip()
        if not raw_text:
            return None

        bridge = _parse_bridge_response(raw_text)
        if bridge:
            logger.debug(
                "[BeatCoTBridge] 桥接成功: momentum=%r opening=%r risk=%r",
                bridge.narrative_momentum[:30] if bridge.narrative_momentum else "",
                bridge.opening_line[:30] if bridge.opening_line else "",
                bridge.risk,
            )
        return bridge

    except Exception as e:
        logger.debug("[BeatCoTBridge] LLM 调用失败（不影响主流程）: %s", e)
        return None


def _build_fallback_prompts(tail: str, next_intent: str) -> tuple[str, str]:
    """CPMS 不可用时的内置 fallback 提示词（与测试中最优的方案C一致）"""
    system = (
        "你是叙事状态机分析器，专门负责中文网络小说的节拍间连贯性分析。"
        "输出严格 JSON，不加任何 Markdown 围栏或前置说明。"
    )
    user = f"""[上一节拍结尾]
{tail}

[下一节拍任务]
{next_intent}

分析叙事状态，给出过渡指令，输出 JSON：
{{
  "active_scene": {{
    "location": "场景地点（10字以内）",
    "characters_present": ["人物1状态", "人物2状态"],
    "atmosphere": "氛围关键词（8字以内）"
  }},
  "narrative_momentum": "读者注意力聚焦于什么（15字以内）",
  "transition": {{
    "type": "emotion_continue|action_continue|dialogue_continue|scene_cut|internal_shift",
    "opening_line": "下一节拍第一句话，可直接写入正文（15-30字）",
    "carry_forward": "必须延续的叙事要素（15字以内）"
  }},
  "risk": "最容易出现的叙事断层（12字以内）"
}}"""
    return system, user
