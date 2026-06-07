"""规划节点 — 章纲划分节拍（叙事 atoms → chapter_plan_json）"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict

from application.engine.dag.models import (
    DefaultDagSlot,
    NodeCategory,
    NodeMeta,
    NodePort,
    NodeStatus,
    PortDataType,
    PromptMode,
)
from application.engine.dag.plan.outline_beat_planner import build_chapter_execution_plan_async
from application.engine.dag.plan.planning_node_base import AbstractPlanningNode
from application.engine.dag.registry import NodeRegistry
from infrastructure.ai.prompt_keys import OUTLINE_BEAT_PARTITION

logger = logging.getLogger(__name__)


@NodeRegistry.register("planning_outline_partition")
class PlanningOutlinePartitionNode(AbstractPlanningNode):
    """章前规划：产出标准 `chapter_execution_plan`。

    分解优先级：BeatSheet(JSON) → 显式条文结构 →（可选）LLM（**CPMS：`outline-beat-partition`**）→ 整章单 atom。
    节点内不写死长篇提示词；编辑请走提示词广场对应节点。
    """

    meta = NodeMeta(
        node_type="planning_outline_partition",
        display_name="章纲节拍划分",
        category=NodeCategory.PLANNING,
        icon="",
        color="#059669",
        input_ports=[
            NodePort(name="outline", data_type=PortDataType.TEXT, required=True),
            NodePort(
                name="target_chapter_words",
                data_type=PortDataType.SCORE,
                required=False,
                default=2500,
                description="整章目标字数（CPMS 模板变量 target_chapter_words）",
            ),
            NodePort(name="beat_sheet_json", data_type=PortDataType.JSON, required=False, default=None),
            NodePort(
                name="use_llm",
                data_type=PortDataType.BOOLEAN,
                required=False,
                default=True,
                description="无章纲结构与 BeatSheet 时是否调用 LLM 分解（经 CPMS 渲染提示词）",
            ),
        ],
        output_ports=[
            NodePort(
                name=AbstractPlanningNode.PLAN_OUTPUT_PORT,
                data_type=PortDataType.JSON,
                description="ChapterExecutionPlan 序列化",
            ),
        ],
        prompt_variables=["outline", "target_chapter_words"],
        is_configurable=True,
        can_disable=True,
        default_timeout_seconds=90,
        cpms_node_key=OUTLINE_BEAT_PARTITION,
        prompt_mode=PromptMode.CPMS_FIRST,
        description="抽象规划节点 · 章纲 → atoms；LLM 提示词取自 CPMS",
        default_edges=["exec_writer"],
        default_dag_slot=DefaultDagSlot(
            instance_id="plan_outline",
            position={"x": 320.0, "y": 120.0},
            incoming_from=["ctx_blueprint", "ctx_memory"],
            outgoing_to=["exec_beat"],
        ),
    )

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        started = time.perf_counter()
        outline_raw = inputs.get("outline") or ""

        tv = inputs.get("target_chapter_words")
        if tv is None:
            tv = 2500
        try:
            target_chapter_words = int(tv)
        except (TypeError, ValueError):
            target_chapter_words = 2500

        sheet = inputs.get("beat_sheet_json")
        beat_sheet_json: Dict[str, Any] | None
        if sheet is None:
            beat_sheet_json = None
        elif isinstance(sheet, dict):
            beat_sheet_json = sheet if sheet else None
        elif isinstance(sheet, str):
            try:
                import json

                beat_sheet_json = json.loads(sheet) if sheet.strip() else None
            except json.JSONDecodeError:
                beat_sheet_json = None
                logger.warning("beat_sheet_json 解析失败，已忽略")
        else:
            beat_sheet_json = None

        use_llm = inputs.get("use_llm")
        use_llm_bool = True if use_llm is None else bool(use_llm)

        novel_id = context.get("novel_id") if isinstance(context, dict) else None
        chapter_number = context.get("chapter_number") if isinstance(context, dict) else None

        outline = str(outline_raw)

        try:
            plan = await build_chapter_execution_plan_async(
                outline,
                target_chapter_words=target_chapter_words,
                novel_id=str(novel_id) if novel_id else None,
                chapter_number=int(chapter_number) if chapter_number is not None else None,
                beat_sheet_json=beat_sheet_json,
                use_llm=use_llm_bool,
                decomposition_label="planning_outline_partition",
            )

            duration_ms = int((time.perf_counter() - started) * 1000)
            return self.pack_plan_result(
                plan,
                duration_ms=duration_ms,
                metrics={
                    "atom_count": float(len(plan.atoms)),
                    "target_words": float(target_chapter_words),
                },
            )

        except Exception as e:
            logger.exception("planning_outline_partition 失败: %s", e)
            duration_ms = int((time.perf_counter() - started) * 1000)
            from application.engine.dag.plan.schema import (
                ChapterExecutionPlan,
                PlanAtomSpec,
                PlanDecompositionMode,
                PlanningEnvelope,
            )

            env = PlanningEnvelope(
                novel_id=str(novel_id) if novel_id else None,
                chapter_number=int(chapter_number) if chapter_number is not None else None,
                target_chapter_words=target_chapter_words,
            )
            recovery_atoms: list[PlanAtomSpec] = []
            if outline.strip():
                recovery_atoms = [
                    PlanAtomSpec(
                        id="b1",
                        intent=outline.strip(),
                        weight=1.0,
                        extensions={"decomposition_mode": PlanDecompositionMode.ERROR_SINGLE_OUTLINE.value},
                    )
                ]
            fb = ChapterExecutionPlan(
                envelope=env,
                atoms=recovery_atoms,
                provenance={"mode": PlanDecompositionMode.ERROR_SINGLE_OUTLINE.value, "error": str(e)},
            )

            return self.pack_plan_result(
                fb,
                status=NodeStatus.WARNING,
                duration_ms=duration_ms,
                error=str(e),
                metrics={
                    "atom_count": float(len(fb.atoms)),
                    "target_words": float(target_chapter_words),
                },
            )

    def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        return "outline" in inputs
