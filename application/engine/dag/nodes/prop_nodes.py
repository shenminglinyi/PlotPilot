"""道具上下文 DAG 节点 — ctx_prop_state

负责在章节生成前将道具状态注入 context，输出：
- prop_fact_lock: T0 道具状态锁文本
- prop_suggestions: 建议引入道具文本
- prop_warnings: 一致性警告文本
"""
from __future__ import annotations
import logging
import time
from typing import Any, Dict

from application.engine.dag.models import (
    NodeCategory,
    NodeMeta,
    NodePort,
    NodeResult,
    NodeStatus,
    PortDataType,
)
from application.engine.dag.registry import BaseNode, NodeRegistry

logger = logging.getLogger(__name__)


@NodeRegistry.register("ctx_prop_state")
class PropStateNode(BaseNode):
    """道具状态注入节点 — 输出 T0 道具锁、建议和警告。"""

    meta = NodeMeta(
        node_type="ctx_prop_state",
        display_name="🎒 道具状态",
        category=NodeCategory.PROP,
        icon="🎒",
        color="#f59e0b",
        input_ports=[
            NodePort(name="novel_id", data_type=PortDataType.TEXT, required=True),
            NodePort(name="chapter_number", data_type=PortDataType.TEXT, required=True),
            NodePort(name="character_ids", data_type=PortDataType.LIST, required=False),
        ],
        output_ports=[
            NodePort(name="prop_fact_lock", data_type=PortDataType.TEXT),
            NodePort(name="prop_suggestions", data_type=PortDataType.TEXT),
            NodePort(name="prop_warnings", data_type=PortDataType.TEXT),
        ],
        is_configurable=True,
        can_disable=True,
        default_timeout_seconds=5,
        description="在章节生成前注入道具当前状态（T0 锁 + 建议 + 一致性警告）",
        default_edges=["ctx_voice", "exec_beat"],
    )

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        start = time.time()
        novel_id = inputs.get("novel_id") or context.get("novel_id", "")
        chapter_number = int(inputs.get("chapter_number") or context.get("chapter_number", 1))
        character_ids = inputs.get("character_ids") or []

        try:
            from interfaces.api.dependencies import get_unified_prop_context_builder
            builder = get_unified_prop_context_builder()
            blocks = builder.build_for_chapter(novel_id, chapter_number, character_ids or None)
        except Exception as e:
            logger.warning("[PropStateNode] 构建失败（非致命）: %s", e)
            blocks = {"prop_fact_lock": "", "prop_suggestions": "", "prop_warnings": ""}

        elapsed = (time.time() - start) * 1000
        return NodeResult(
            node_type="ctx_prop_state",
            status=NodeStatus.SUCCESS,
            outputs=blocks,
            metadata={"elapsed_ms": int(elapsed), "novel_id": novel_id, "chapter": chapter_number},
        )

    def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        return bool(inputs.get("novel_id"))
