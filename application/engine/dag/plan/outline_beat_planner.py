"""章纲 → 节拍规划（叙事单元，非句读切分）。

策略优先级：
1. 上游 beat_sheet_json.scenes（若存在）
2. 用户显式结构（编号列表 / 项目符号 / 空行段），**不对单段散文按句号拆**
3. 可选 LLM 分解为有序 atoms
4. 未拆分整章单 atom：保留章纲原文作为一个规划单元
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence

from pydantic import BaseModel, Field

from application.engine.dag.plan.schema import (
    ChapterExecutionPlan,
    PlanAtomSpec,
    PlanDecompositionMode,
    PlanningEnvelope,
)

logger = logging.getLogger(__name__)

# 与 ContextBuilder.MAX_BEATS 对齐，避免 DAG 规划与 magnify 脱节
_MAX_ATOMS = 12


def _resolve_llm_service(llm_service: Any = None) -> Any:
    """使用注入的 LLM 实现；未传入时走 ``get_llm_service()``（与守护进程 / API 同源）。"""
    if llm_service is not None:
        return llm_service
    from interfaces.api.dependencies import get_llm_service

    return get_llm_service()


def render_cpms_outline_partition_prompts(
    outline: str,
    target_chapter_words: int,
) -> tuple[str, str]:
    """从 CPMS 节点 ``outline-beat-partition`` 渲染 system/user（内置种子或广场覆写）。

    不写死提示词段落；仅在 CPMS 不可用时返回空串，由调用方决定是否跳过 LLM 拆解。
    """
    from infrastructure.ai.prompt_keys import OUTLINE_BEAT_PARTITION
    from infrastructure.ai.prompt_manager import get_prompt_manager
    from infrastructure.ai.prompt_registry import get_prompt_registry

    try:
        get_prompt_manager().ensure_seeded()
    except Exception as e:
        logger.warning("ensure_seeded 失败（章纲节拍划分）: %s", e)

    reg = get_prompt_registry()
    res = reg.render(
        OUTLINE_BEAT_PARTITION,
        {
            "outline": (outline or "").strip(),
            "target_chapter_words": str(int(target_chapter_words)),
        },
    )
    if not res or not (res.user or "").strip():
        logger.warning(
            "CPMS %s 渲染失败或 user 为空；无法 LLM 拆节拍",
            OUTLINE_BEAT_PARTITION,
        )
        return "", ""
    runtime_schema_guard = """

### 运行时导演合同字段（必须输出）
每个 atom 除 id/intent/weight/focus/transition_hint 外，必须补齐：
- function: setup|pressure|payoff|reveal|transition|aftermath|hook
- visible_action: 本拍必须写出的可见动作/对白/选择，禁止空泛
- conflict: 本拍的阻碍、误判、压迫或信息差
- delta: 本拍结束后改变的事实、关系或认知
- handoff_to_next: 交给下一拍的承接点
- pov, cast_refs, location_refs, prop_refs, knowledge_refs, must_include, must_not_include 可为空数组/空串
如果没有稳定实体 id，refs 留空，不要编造 token id。
""".rstrip()
    return (res.system or "").strip(), ((res.user or "").strip() + runtime_schema_guard)


class _LLMDecomposeModel(BaseModel):
    """LLM 输出子集校验（atoms 每项可为 dict 或 str）"""

    atoms: List[Any] = Field(default_factory=list)


def outline_fingerprint(outline: str) -> str:
    raw = (outline or "").strip().encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def segment_structured_outline(outline: str) -> Optional[List[str]]:
    """仅当用户显式给出多段结构时返回多条；否则返回 None（禁止句读硬切）。"""
    text = (outline or "").strip()
    if not text:
        return None
    if re.search(r"(?m)^\s*\d+[\.、．\)]", text):
        parts = re.split(r"\n(?=\s*\d+[\.、．\)]\s)", text)
        segs = [p.strip() for p in parts if p.strip()]
        if len(segs) >= 2:
            return segs
    if re.search(r"(?m)^\s*[-*•]\s+\S", text):
        parts = re.split(r"\n(?=\s*[-*•]\s)", text)
        segs = [p.strip() for p in parts if p.strip()]
        if len(segs) >= 2:
            return segs
    paras = [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]
    if len(paras) >= 2:
        return paras
    return None


def _clamp_atoms(atoms: List[PlanAtomSpec]) -> List[PlanAtomSpec]:
    if len(atoms) <= _MAX_ATOMS:
        return atoms
    head = atoms[: _MAX_ATOMS - 1]
    tail_intent = "\n".join(a.intent for a in atoms[_MAX_ATOMS - 1 :])
    tail = PlanAtomSpec(
        id=atoms[_MAX_ATOMS - 1].id,
        intent=tail_intent,
        weight=sum(a.weight for a in atoms[_MAX_ATOMS - 1 :]),
        source_hint=None,
        extensions={"merged_from_overflow": True},
    )
    return head + [tail]


def atoms_from_segments(segments: Sequence[str]) -> List[PlanAtomSpec]:
    out: List[PlanAtomSpec] = []
    for i, seg in enumerate(segments):
        seg = seg.strip()
        if not seg:
            continue
        out.append(
            PlanAtomSpec(
                id=f"b{i + 1}",
                intent=seg,
                weight=float(max(12, len(seg))),
                source_hint=None,
                extensions={"decomposition_mode": PlanDecompositionMode.STRUCTURED_OUTLINE.value},
            )
        )
    return _clamp_atoms(out)


def _pick_scene_fields(obj: Dict[str, Any]) -> tuple[str, str]:
    title = str(obj.get("title") or obj.get("name") or "").strip()
    goal = str(
        obj.get("goal")
        or obj.get("summary")
        or obj.get("description")
        or obj.get("beat")
        or ""
    ).strip()
    intent = f"{title}：{goal}".strip("：").strip() if title and goal else (title or goal or json.dumps(obj, ensure_ascii=False)[:240])
    return title or f"s{hash(json.dumps(obj, sort_keys=True)) % 10000}", intent


def atoms_from_beat_sheet_dict(data: Dict[str, Any]) -> Optional[List[PlanAtomSpec]]:
    if not isinstance(data, dict):
        return None
    scenes = data.get("scenes")
    if not isinstance(scenes, list) or len(scenes) < 1:
        return None
    out: List[PlanAtomSpec] = []
    for i, raw in enumerate(scenes):
        if isinstance(raw, str):
            s = raw.strip()
            if not s:
                continue
            out.append(
                PlanAtomSpec(
                    id=f"b{i + 1}",
                    intent=s,
                    weight=1.0,
                    extensions={"decomposition_mode": PlanDecompositionMode.BEAT_SHEET.value, "scene_index": i},
                )
            )
            continue
        if not isinstance(raw, dict):
            continue
        _, intent = _pick_scene_fields(raw)
        if len(intent.strip()) < 2:
            continue
        ew = raw.get("estimated_words")
        weight = min(100.0, max(0.01, float(ew))) if isinstance(ew, (int, float)) and ew > 0 else 1.0
        ext = {"decomposition_mode": PlanDecompositionMode.BEAT_SHEET.value, "scene_index": i}
        for k in ("pov_character", "location", "tone", "transition_from_prev"):
            if raw.get(k):
                ext[k] = raw[k]
        out.append(PlanAtomSpec(id=f"b{i + 1}", intent=intent, weight=weight, extensions=ext))
    if not out:
        return None
    return _clamp_atoms(out)


def _normalize_llm_atom_entries(entries: List[Dict[str, Any]]) -> List[PlanAtomSpec]:
    out: List[PlanAtomSpec] = []
    for i, row in enumerate(entries):
        intent = str(row.get("intent") or row.get("summary") or row.get("purpose") or "").strip()
        if len(intent) < 2:
            continue
        atom_id = str(row.get("id") or "").strip() or f"b{i + 1}"
        weight = row.get("weight")
        wf = float(weight) if isinstance(weight, (int, float)) and weight > 0 else 1.0
        hint = row.get("source_hint") or row.get("anchor")
        hint_s = str(hint).strip() if hint else None
        ext = dict(row.get("extensions") or {}) if isinstance(row.get("extensions"), dict) else {}
        ext.setdefault("decomposition_mode", PlanDecompositionMode.LLM_OUTLINE_DECOMPOSE.value)
        # 提取新字段：focus 类型和节拍间过渡提示
        focus = row.get("focus") or row.get("type") or ""
        if focus and isinstance(focus, str):
            ext["focus"] = focus.strip()
        transition_hint = row.get("transition_hint") or row.get("transition_from_prev") or ""
        if transition_hint and isinstance(transition_hint, str):
            ext["transition_from_prev"] = transition_hint.strip()
        for key in (
            "function",
            "pov",
            "cast_refs",
            "location_refs",
            "prop_refs",
            "knowledge_refs",
            "visible_action",
            "conflict",
            "delta",
            "handoff_to_next",
            "must_include",
            "must_not_include",
        ):
            value = row.get(key)
            if value not in (None, "", [], {}):
                ext[key] = value
        out.append(
            PlanAtomSpec(
                id=atom_id[:64],
                intent=intent,
                weight=wf,
                source_hint=hint_s,
                extensions=ext,
            )
        )
    return out


def _extract_json_payload(text: str) -> Dict[str, Any]:
    """Parse LLM outline-partition JSON; fall back to json_repair on malformed output."""
    from application.ai.structured_json_pipeline import parse_and_repair_json

    stripped = (text or "").strip()
    if not stripped:
        raise json.JSONDecodeError("empty payload", stripped, 0)

    try:
        out = json.loads(stripped)
        if isinstance(out, list):
            return {"atoms": out}
        if isinstance(out, dict):
            return out
    except json.JSONDecodeError:
        pass

    data, errors = parse_and_repair_json(stripped)
    if isinstance(data, dict):
        if errors:
            logger.info("outline partition JSON repaired: %s", errors[0] if errors else "ok")
        return data

    lo = stripped.find("{")
    hi = stripped.rfind("}")
    if lo >= 0 and hi > lo:
        fragment = stripped[lo : hi + 1]
        data, errors = parse_and_repair_json(fragment)
        if isinstance(data, dict):
            if errors:
                logger.info("outline partition JSON fragment repaired: %s", errors[0] if errors else "ok")
            return data

    detail = errors[0] if errors else "no json object"
    raise json.JSONDecodeError(detail, stripped, 0)


OutlinePartitionEmitDelta = Optional[Callable[[str], Awaitable[None]]]


async def llm_decompose_outline(
    outline: str,
    target_words: int,
    *,
    system: str = "",
    user: str = "",
    emit_delta: OutlinePartitionEmitDelta = None,
    llm_service: Any = None,
) -> Optional[List[PlanAtomSpec]]:
    """调用 LLM 拆 atoms。未显式传入 ``user`` 时从 CPMS ``outline-beat-partition`` 渲染。

    使用 ``stream_generate`` 聚合全文；若传入 ``emit_delta``，每个增量片段会回调（供 SSE 透出）。
    """
    u_in = (user or "").strip()
    s_in = (system or "").strip()
    if not u_in:
        s_cpms, u_cpms = render_cpms_outline_partition_prompts(outline, target_words)
        system, user = s_cpms, u_cpms
    else:
        system, user = s_in, u_in

    if not (user or "").strip():
        return None

    try:
        from domain.ai.services.llm_service import GenerationConfig
        from domain.ai.value_objects.prompt import Prompt

        llm = _resolve_llm_service(llm_service)
        prompt = Prompt(system=system.strip() if system else "", user=user)
        config = GenerationConfig(max_tokens=2000, temperature=0.45)
        pieces: List[str] = []
        async for piece in llm.stream_generate(prompt, config):
            if piece:
                pieces.append(piece)
                if emit_delta:
                    await emit_delta(piece)
        raw_text = "".join(pieces).strip()
        from application.ai.structured_json_pipeline import sanitize_llm_output

        cleaned = sanitize_llm_output(raw_text)
        parsed = _extract_json_payload(cleaned)
        model = _LLMDecomposeModel.model_validate(parsed)
        atoms_raw = []
        for a in model.atoms:
            if isinstance(a, dict):
                atoms_raw.append(a)
            elif isinstance(a, str):
                atoms_raw.append({"intent": a})
        out = _normalize_llm_atom_entries(atoms_raw)
        out = _clamp_atoms(out)
        return out if out else None
    except Exception as e:
        logger.warning("outline LLM decomposition failed: %s", e)
        return None


async def build_chapter_execution_plan_async(
    outline: str,
    *,
    target_chapter_words: int = 2500,
    novel_id: Optional[str] = None,
    chapter_number: Optional[int] = None,
    beat_sheet_json: Optional[Dict[str, Any]] = None,
    use_llm: bool = True,
    llm_system: str = "",
    llm_user: str = "",
    decomposition_label: str = "planning_outline_partition",
    emit_llm_delta: OutlinePartitionEmitDelta = None,
    llm_service: Any = None,
) -> ChapterExecutionPlan:
    """构建章前执行计划。LLM 默认经 CPMS outline-beat-partition；可传 llm_system / llm_user 覆写。"""
    raw = (outline or "").strip()
    env = PlanningEnvelope(
        novel_id=novel_id,
        chapter_number=chapter_number,
        target_chapter_words=target_chapter_words,
        source_outline_hash=outline_fingerprint(raw) if raw else None,
    )
    prov: Dict[str, Any] = {"node_hint": decomposition_label}

    atoms: Optional[List[PlanAtomSpec]] = None
    mode = PlanDecompositionMode.RAW_OUTLINE_SINGLE.value

    if not raw:
        return ChapterExecutionPlan(envelope=env, atoms=[], provenance={**prov, "mode": PlanDecompositionMode.EMPTY_OUTLINE.value})

    if beat_sheet_json and isinstance(beat_sheet_json, dict):
        atoms = atoms_from_beat_sheet_dict(beat_sheet_json)
        if atoms:
            mode = PlanDecompositionMode.BEAT_SHEET.value

    structured: Optional[List[str]] = None
    if atoms is None:
        structured = segment_structured_outline(raw)
        if structured:
            atoms = atoms_from_segments(structured)
            mode = PlanDecompositionMode.STRUCTURED_OUTLINE.value

    if atoms is None and use_llm:
        llm_atoms = await llm_decompose_outline(
            raw,
            target_chapter_words,
            system=llm_system,
            user=llm_user,
            emit_delta=emit_llm_delta,
            llm_service=llm_service,
        )
        if llm_atoms:
            atoms = llm_atoms
            mode = PlanDecompositionMode.LLM_OUTLINE_DECOMPOSE.value

    if atoms is None:
        atoms = [
            PlanAtomSpec(
                id="b1",
                intent=raw,
                weight=1.0,
                extensions={"decomposition_mode": PlanDecompositionMode.RAW_OUTLINE_SINGLE.value},
            )
        ]
        mode = PlanDecompositionMode.RAW_OUTLINE_SINGLE.value

    provenance = {**prov, "mode": mode, "atom_count": len(atoms)}
    return ChapterExecutionPlan(envelope=env, atoms=atoms, provenance=provenance)


def build_chapter_execution_plan_sync(
    outline: str,
    *,
    target_chapter_words: int = 2500,
    novel_id: Optional[str] = None,
    chapter_number: Optional[int] = None,
    beat_sheet_json: Optional[Dict[str, Any]] = None,
    decomposition_label: str = "context_builder_sync",
) -> ChapterExecutionPlan:
    """Build a deterministic ChapterExecutionPlan without LLM.

    This is the synchronous canonical planner for runtime callers that cannot
    await the CPMS-driven LLM decomposition step. It still keeps the planning
    source as ChapterExecutionPlan.
    """
    raw = (outline or "").strip()
    env = PlanningEnvelope(
        novel_id=novel_id,
        chapter_number=chapter_number,
        target_chapter_words=target_chapter_words,
        source_outline_hash=outline_fingerprint(raw) if raw else None,
    )
    prov: Dict[str, Any] = {"node_hint": decomposition_label}

    atoms: Optional[List[PlanAtomSpec]] = None
    mode = PlanDecompositionMode.RAW_OUTLINE_SINGLE.value

    if beat_sheet_json and isinstance(beat_sheet_json, dict):
        atoms = atoms_from_beat_sheet_dict(beat_sheet_json)
        if atoms:
            mode = PlanDecompositionMode.BEAT_SHEET.value

    if atoms is None and raw:
        structured = segment_structured_outline(raw)
        if structured:
            atoms = atoms_from_segments(structured)
            mode = PlanDecompositionMode.STRUCTURED_OUTLINE.value

    if atoms is None and raw:
        atoms = [
            PlanAtomSpec(
                id="b1",
                intent=raw,
                weight=1.0,
                extensions={"decomposition_mode": PlanDecompositionMode.RAW_OUTLINE_SINGLE.value},
            )
        ]
        mode = PlanDecompositionMode.RAW_OUTLINE_SINGLE.value

    if atoms is None:
        atoms = []
        mode = PlanDecompositionMode.EMPTY_OUTLINE.value

    return ChapterExecutionPlan(
        envelope=env,
        atoms=atoms,
        provenance={**prov, "mode": mode, "atom_count": len(atoms)},
    )
