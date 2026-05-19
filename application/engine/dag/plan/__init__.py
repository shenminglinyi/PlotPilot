"""章级执行规划抽象 — DAG 共享 Schema 与规划节点基类。

下游执行节点可通过 `chapter_plan_json`（ChapterExecutionPlan 序列化）消费，
扩展新规划能力时请增加 atoms / extensions，避免改 core 字段语义。
"""

from application.engine.dag.plan.outline_beat_planner import render_cpms_outline_partition_prompts
from application.engine.dag.plan.schema import (
    ChapterExecutionPlan,
    PlanningEnvelope,
    PlanAtomSpec,
)
from application.engine.dag.plan.planning_node_base import AbstractPlanningNode

__all__ = [
    "AbstractPlanningNode",
    "ChapterExecutionPlan",
    "PlanningEnvelope",
    "PlanAtomSpec",
    "render_cpms_outline_partition_prompts",
]
