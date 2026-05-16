"""全托管运行时 → DAG 主节点语义策略（声明式、可替换、无散落 if/else）

解析结果使用 **节点 type**（与 ``NodeRegistry`` / 画布 ``NodeDefinition.type`` 对齐），
再由 ``dag_runtime_projection`` 在**具体 DAG 实例**上解析为 ``node_id``，
避免写死画布 ``node_id``（自定义 DAG 中 id 可与 type 不同）。

扩展方式：
1. 增删 ``*_ROWS`` / ``_AUDIT_PROGRESS_ROWS`` 元组中的行（唯一真源）；
2. 或 ``register_policy_hook`` 注入附加规则（返回非 None 则覆盖默认结果）；
3. 或传入自定义 ``ProjectionSemantics`` 替换语义锚点 type。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from domain.novel.entities.novel import AutopilotStatus, NovelStage

from application.engine.narrative_projection.runtime_snapshot import NarrativeRuntimeSnapshot


# ─── 可注入语义锚点（仅此处出现「默认用哪个 type」）───


@dataclass(frozen=True)
class ProjectionSemantics:
    """熔断/审计兜底等在 DAG 画布上的语义锚点（type 级，非实例 id）。"""

    error_highlight_node_type: str = "gw_circuit"
    auditing_fallback_node_type: str = "val_style"
    fallback_pending_node_type: str = "ctx_blueprint"


DEFAULT_SEMANTICS = ProjectionSemantics()

# 审计进度 token → 高亮节点 type（与 autopilot_daemon 写入字符串对齐）
_AUDIT_PROGRESS_ROWS: Tuple[Tuple[str, str], ...] = (
    ("voice_check", "val_style"),
    ("aftermath_pipeline", "val_narrative"),
    ("tension_scoring", "val_tension"),
    ("tension", "val_tension"),
    ("aftermath", "val_narrative"),
    ("anti_ai", "val_anti_ai"),
)
AUDIT_PROGRESS_TO_NODE_TYPE: Dict[str, str] = dict(_AUDIT_PROGRESS_ROWS)


@dataclass(frozen=True)
class SubstepPrimaryRow:
    """writing_substep 命中任一 token → 主节点 type。"""

    substeps: frozenset[str]
    primary_node_type: str
    status: str = "running"


# 顺序即优先级（先匹配先生效）
SUBSTEP_PRIMARY_ROWS: Tuple[SubstepPrimaryRow, ...] = (
    SubstepPrimaryRow(frozenset({"macro_planning"}), "ctx_blueprint"),
    SubstepPrimaryRow(frozenset({"act_planning"}), "ctx_memory"),
    SubstepPrimaryRow(frozenset({"llm_calling"}), "exec_writer"),
    SubstepPrimaryRow(
        frozenset({"chapter_found", "context_assembly", "beat_magnification"}),
        "exec_beat",
    ),
    SubstepPrimaryRow(
        frozenset({"soft_landing", "persisting", "continuity_check", "chapter_persist"}),
        "exec_writer",
    ),
    SubstepPrimaryRow(frozenset({"audit_voice_check"}), "val_style"),
    SubstepPrimaryRow(frozenset({"audit_tension"}), "val_tension"),
    SubstepPrimaryRow(frozenset({"audit_aftermath"}), "val_narrative"),
    SubstepPrimaryRow(frozenset({"audit_anti_ai"}), "val_anti_ai"),
)


@dataclass(frozen=True)
class StagePrimaryRow:
    """current_stage 命中 → 主节点 type（auditing 单独走审计进度表）。"""

    stages: frozenset[str]
    primary_node_type: str
    status: str = "running"


STAGE_PRIMARY_ROWS: Tuple[StagePrimaryRow, ...] = (
    StagePrimaryRow(frozenset({NovelStage.MACRO_PLANNING.value, NovelStage.PLANNING.value}), "ctx_blueprint"),
    StagePrimaryRow(frozenset({NovelStage.ACT_PLANNING.value}), "ctx_memory"),
    StagePrimaryRow(frozenset({NovelStage.WRITING.value}), "exec_writer"),
    StagePrimaryRow(frozenset({NovelStage.PAUSED_FOR_REVIEW.value}), "gw_review", status="warning"),
    StagePrimaryRow(frozenset({NovelStage.COMPLETED.value}), "gw_review", status="completed"),
)


PolicyHook = Callable[[NarrativeRuntimeSnapshot, ProjectionSemantics], Optional[Tuple[str, str]]]
_policy_hooks: List[PolicyHook] = []


def register_policy_hook(fn: PolicyHook) -> None:
    """注册附加解析钩子（后插；返回非 None 则覆盖默认结果）。"""
    _policy_hooks.append(fn)


def clear_policy_hooks_for_tests() -> None:
    """单测隔离用。"""
    _policy_hooks.clear()


def resolve_primary_node_type(
    snapshot: NarrativeRuntimeSnapshot,
    semantics: ProjectionSemantics = DEFAULT_SEMANTICS,
) -> Optional[Tuple[str, str]]:
    """返回 ``(primary_node_type, status)``；与全托管无关时返回 ``None``。"""
    if snapshot.autopilot_status == AutopilotStatus.ERROR.value:
        return (semantics.error_highlight_node_type, "error")

    if snapshot.autopilot_status != AutopilotStatus.RUNNING.value:
        return None

    ws = snapshot.writing_substep
    if ws:
        for row in SUBSTEP_PRIMARY_ROWS:
            if ws in row.substeps:
                hit: Tuple[str, str] = (row.primary_node_type, row.status)
                return _apply_hooks(snapshot, semantics, hit)

    st = snapshot.current_stage
    if st == NovelStage.AUDITING.value:
        nt = AUDIT_PROGRESS_TO_NODE_TYPE.get(snapshot.audit_progress or "")
        if not nt:
            nt = semantics.auditing_fallback_node_type
        hit = (nt, "running")
        return _apply_hooks(snapshot, semantics, hit)

    for row in STAGE_PRIMARY_ROWS:
        if st in row.stages:
            hit = (row.primary_node_type, row.status)
            return _apply_hooks(snapshot, semantics, hit)

    hit = (semantics.fallback_pending_node_type, "pending")
    return _apply_hooks(snapshot, semantics, hit)


def _apply_hooks(
    snapshot: NarrativeRuntimeSnapshot,
    semantics: ProjectionSemantics,
    default: Tuple[str, str],
) -> Tuple[str, str]:
    for fn in _policy_hooks:
        r = fn(snapshot, semantics)
        if r is not None:
            return r
    return default


def first_node_id_for_type(
    nodes: Sequence[Tuple[str, str, bool]],
    node_type: str,
    *,
    prefer_enabled: bool = True,
) -> Optional[str]:
    """在 DAG 实例上把语义 type 解析为第一个匹配的 ``node_id``。"""
    if prefer_enabled:
        for nid, ntype, enabled in nodes:
            if enabled and ntype == node_type:
                return nid
    for nid, ntype, _ in nodes:
        if ntype == node_type:
            return nid
    return None
