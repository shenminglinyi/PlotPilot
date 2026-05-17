"""空间拓扑连贯 — ATG 节拍绑定、拓扑校验、递增重试与流式泄露阻截。

与 SceneDirector 产出的 ActionTransitionGraphPayload 及 MicroSceneContext 协同；
避免引入二次 LLM 校验：角色提及采用 roster 词表交集检测。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional, Sequence, Set

from domain.novel.value_objects.action_transition_graph import ActionTransitionGraph, TransitionEdge
from domain.novel.value_objects.micro_scene_context import MicroSceneContext

if TYPE_CHECKING:
    from application.engine.services.context_builder import Beat

logger = logging.getLogger(__name__)


def assign_visit_locations_to_beats(beats: Sequence["Beat"], visit_sequence: Sequence[str]) -> None:
    """按 visit_sequence 将微观坐标绑定到各节拍（均匀采样）。"""
    if not beats or not visit_sequence:
        return
    seq = [str(x).strip() for x in visit_sequence if str(x).strip()]
    if not seq:
        return
    if len(seq) == 1:
        for b in beats:
            b.location_id = seq[0]
        return
    n = len(beats)
    m = len(seq)
    for i, b in enumerate(beats):
        idx = min(round(i * (m - 1) / max(n - 1, 1)), m - 1)
        b.location_id = seq[idx]


def transition_anchor_satisfied(text: str, edge: Optional[TransitionEdge]) -> bool:
    """检测过场锚点是否出现在正文（前缀匹配，适配中文动词短语）。"""
    if edge is None:
        return True
    ra = (edge.required_action or "").strip()
    if not ra:
        return True
    if ra in text:
        return True
    prefix = ra[: min(len(ra), 12)]
    return bool(prefix) and prefix in text


def find_illegal_character_mentions(text: str, roster: Set[str], allowed: Set[str]) -> List[str]:
    """ roster 内角色：出现在正文但未获准入场的名单。"""
    illegal: List[str] = []
    for name in roster:
        name = name.strip()
        if not name or name in allowed:
            continue
        if name in text:
            illegal.append(name)
    return illegal


def initialize_micro_scene_context(
    *,
    graph: Optional[ActionTransitionGraph],
    first_location_id: str,
    roster: Sequence[str],
    pov: Optional[str],
) -> MicroSceneContext:
    """章节首节拍开始前的运行时快照。"""
    ctx = MicroSceneContext(location_id=first_location_id or "")
    seed: Set[str] = set()
    if pov and pov.strip():
        seed.add(pov.strip())
    elif roster:
        seed.add(str(roster[0]).strip())
    ctx.active_characters = {x for x in seed if x}
    if graph and first_location_id:
        node = graph.node(first_location_id)
        if node:
            ctx.active_props = set(node.initial_props)
    return ctx


def refresh_micro_scene_context_after_beat(
    ctx: MicroSceneContext,
    *,
    beat_location_id: str,
    beat_text: str,
    graph: Optional[ActionTransitionGraph],
    roster: Sequence[str],
    character_extractor,
) -> None:
    """节拍完成后刷新在场集合（轻量：复用 BeatCoherenceEnhancer 的角色抽取）。"""
    ctx.location_id = beat_location_id or ctx.location_id
    roster_set = {str(x).strip() for x in roster if str(x).strip()}
    extracted = set(character_extractor(beat_text))
    ctx.active_characters |= extracted & roster_set
    if graph and beat_location_id:
        node = graph.node(beat_location_id)
        if node:
            ctx.active_props |= set(node.initial_props)


@dataclass
class TopologyCommitResult:
    ok: bool
    failure_kind: str = ""
    detail: str = ""
    illegal_characters: tuple[str, ...] = ()


class DraftTopologyCommitGate:
    """Pre-commit 风格拓扑闸门：草稿通过后才可与快照一并提交。"""

    def evaluate(
        self,
        text: str,
        *,
        transitioning: bool,
        edge: Optional[TransitionEdge],
        roster: Set[str],
        active_characters: Set[str],
    ) -> TopologyCommitResult:
        if transitioning:
            if edge is not None and not transition_anchor_satisfied(text, edge):
                return TopologyCommitResult(
                    ok=False,
                    failure_kind="missing_transition",
                    detail="required_action anchor not found in beat draft",
                )
            return TopologyCommitResult(ok=True)
        illegal = tuple(find_illegal_character_mentions(text, roster, active_characters))
        if illegal:
            return TopologyCommitResult(
                ok=False,
                failure_kind="illegal_characters",
                detail="character appears without being active in micro-context",
                illegal_characters=illegal,
            )
        return TopologyCommitResult(ok=True)


class EscalatingBeatRetryDirector:
    """Reject & Retry 时的递增约束生成器（避免盲重试死循环）。"""

    def build_patch(
        self,
        retry_index: int,
        *,
        failure_kind: str,
        edge: Optional[TransitionEdge],
        prev_loc: str,
        curr_loc: str,
        illegal_characters: Sequence[str] = (),
    ) -> str:
        """retry_index 从 1 开始：第一次重试、第二次重试……"""
        if failure_kind == "missing_transition" and edge:
            if retry_index <= 1:
                return (
                    "\n\n【状态流转失败】上一版遗漏必须的物理动作。"
                    f"请重写本段：必须描写从「{prev_loc}」进入「{curr_loc}」的可观察过渡；"
                    f"动作锚点：{edge.required_action}\n"
                )
            anchor = (edge.required_action or "").strip()
            if anchor and not anchor.endswith(("。", "！", "？", "……")):
                anchor += "。"
            return (
                "\n\n【强制锚定】本段正文必须以如下句子开头（一字不改）："
                f"「{anchor}」随后再展开后续情节与对白。\n"
            )
        if failure_kind == "illegal_characters" and illegal_characters:
            joined = "、".join(illegal_characters)
            return (
                "\n\n【实体约束失败】下列角色不应在本段无铺垫直接出场："
                f"{joined}。请重写：删除或改为合理的入场动作描写。\n"
            )
        return "\n\n【拓扑重写】修正空间与实体约束后重新输出本节拍。\n"


class StreamingSceneLeakGuard:
    """同场景节拍下的流式泄露阻截（基于 roster 词表）。"""

    def __init__(
        self,
        *,
        roster: Set[str],
        allowed_characters: Set[str],
        transitioning: bool,
    ) -> None:
        self._roster = roster
        self._allowed = allowed_characters
        self._transitioning = transitioning

    def check(self, cumulative_text: str) -> Optional[str]:
        if self._transitioning:
            return None
        illegal = find_illegal_character_mentions(cumulative_text, self._roster, self._allowed)
        if illegal:
            return f"illegal_character:{illegal[0]}"
        return None
