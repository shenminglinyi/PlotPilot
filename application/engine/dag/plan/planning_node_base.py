"""规划类 DAG 节点基类 — 统一输出 `chapter_plan_json`"""

from __future__ import annotations

from typing import Any, Dict

from application.engine.dag.models import NodeResult, NodeStatus
from application.engine.dag.plan.schema import ChapterExecutionPlan
from application.engine.dag.registry import BaseNode


class AbstractPlanningNode(BaseNode):
    """公约：规划节点产物为标准 `chapter_plan_json`（ChapterExecutionPlan dict）。

    子类在 execute() 内组装 ChapterExecutionPlan 后调用 pack_plan_result。
    """

    PLAN_OUTPUT_PORT = "chapter_plan_json"

    def pack_plan_result(
        self,
        plan: ChapterExecutionPlan,
        *,
        status: NodeStatus = NodeStatus.SUCCESS,
        duration_ms: int = 0,
        error: str | None = None,
        metrics: Dict[str, float] | None = None,
    ) -> NodeResult:
        return NodeResult(
            outputs={self.PLAN_OUTPUT_PORT: plan.model_dump(mode="json")},
            status=status,
            duration_ms=duration_ms,
            error=error,
            metrics=metrics or {},
        )
