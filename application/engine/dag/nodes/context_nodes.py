"""Context 节点 — 上下文注入（5 个节点）

- ctx_blueprint: 剧本基建（世界规则、禁忌、氛围）
- ctx_foreshadow: 伏笔注入器
- ctx_voice: 角色声线注入
- ctx_memory: 记忆引擎
- ctx_debt: 叙事债务注入
"""
from __future__ import annotations

import logging
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


# ─── ctx_blueprint: 剧本基建 ───


@NodeRegistry.register("ctx_blueprint")
class BlueprintNode(BaseNode):
    """剧本基建 — 从 BibleService 提取世界规则、禁忌、氛围"""

    meta = NodeMeta(
        node_type="ctx_blueprint",
        display_name="📋 剧本基建",
        category=NodeCategory.CONTEXT,
        icon="📋",
        color="#6366f1",
        input_ports=[
            NodePort(name="novel_id", data_type=PortDataType.TEXT, required=True),
        ],
        output_ports=[
            NodePort(name="world_rules", data_type=PortDataType.TEXT),
            NodePort(name="taboos", data_type=PortDataType.TEXT),
            NodePort(name="atmosphere", data_type=PortDataType.TEXT),
        ],
        prompt_template="提取以下小说的世界观规则和禁忌...",
        prompt_variables=["novel_id"],
        is_configurable=True,
        can_disable=False,
        default_timeout_seconds=30,
        cpms_node_key="context-blueprint",
        description="从 BibleService 提取世界规则、禁忌、氛围",
        default_edges=["ctx_memory", "exec_beat"],
    )

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        import time
        start = time.time()
        novel_id = inputs.get("novel_id") or context.get("novel_id", "")

        try:
            # 尝试调用 BibleService
            world_rules = ""
            taboos = ""
            atmosphere = ""

            try:
                from application.world.services.bible_service import BibleService
                from infrastructure.persistence.database.connection import get_database
                db = get_database()
                bible_svc = BibleService(db)
                bible = bible_svc.get_bible(novel_id)
                if bible:
                    world_rules = getattr(bible, "world_rules", "") or ""
                    taboos = getattr(bible, "taboos", "") or ""
                    atmosphere = getattr(bible, "atmosphere", "") or ""
            except Exception as e:
                logger.warning(f"BibleService 调用失败，使用空值: {e}")

            return NodeResult(
                outputs={"world_rules": world_rules, "taboos": taboos, "atmosphere": atmosphere},
                status=NodeStatus.SUCCESS,
                duration_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            return NodeResult(
                outputs={},
                status=NodeStatus.ERROR,
                duration_ms=int((time.time() - start) * 1000),
                error=str(e),
            )

    def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        return "novel_id" in inputs or True  # novel_id 可从 context 获取


# ─── ctx_foreshadow: 伏笔注入器 ───


@NodeRegistry.register("ctx_foreshadow")
class ForeshadowNode(BaseNode):
    """伏笔注入器 — 从 ContextBudgetAllocator T0 槽提取伏笔信息"""

    meta = NodeMeta(
        node_type="ctx_foreshadow",
        display_name="🪝 伏笔注入器",
        category=NodeCategory.CONTEXT,
        icon="🪝",
        color="#f59e0b",
        input_ports=[
            NodePort(name="novel_id", data_type=PortDataType.TEXT, required=True),
            NodePort(name="chapter_number", data_type=PortDataType.SCORE, required=False),
        ],
        output_ports=[
            NodePort(name="foreshadowing_block", data_type=PortDataType.TEXT),
        ],
        prompt_template="整理以下小说中待回收的伏笔...",
        prompt_variables=["novel_id", "chapter_number"],
        is_configurable=True,
        can_disable=True,
        default_timeout_seconds=30,
        cpms_node_key="context-foreshadow",
        description="从 ContextBudgetAllocator T0 槽提取伏笔信息",
        default_edges=["exec_writer"],
    )

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        import time
        start = time.time()
        novel_id = inputs.get("novel_id") or context.get("novel_id", "")

        try:
            foreshadowing_block = ""

            try:
                from domain.novel.repositories.foreshadowing_repository import ForeshadowingRepository
                from infrastructure.persistence.database.connection import get_database
                db = get_database()
                repo = ForeshadowingRepository(db)
                pending = repo.find_pending_by_novel(novel_id)
                if pending:
                    lines = []
                    for f in pending:
                        lines.append(f"【待回收】{f.description}（第{f.planted_chapter}章埋）")
                    foreshadowing_block = "\n".join(lines)
            except Exception as e:
                logger.warning(f"伏笔数据加载失败: {e}")

            return NodeResult(
                outputs={"foreshadowing_block": foreshadowing_block},
                status=NodeStatus.SUCCESS,
                duration_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            return NodeResult(
                outputs={"foreshadowing_block": ""},
                status=NodeStatus.ERROR,
                duration_ms=int((time.time() - start) * 1000),
                error=str(e),
            )

    def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        return True


# ─── ctx_voice: 角色声线注入 ───


@NodeRegistry.register("ctx_voice")
class VoiceNode(BaseNode):
    """角色声线注入 — style_constraint_builder + character_state_vector"""

    meta = NodeMeta(
        node_type="ctx_voice",
        display_name="🎭 角色声线注入",
        category=NodeCategory.CONTEXT,
        icon="🎭",
        color="#ec4899",
        input_ports=[
            NodePort(name="novel_id", data_type=PortDataType.TEXT, required=True),
            NodePort(name="chapter_number", data_type=PortDataType.SCORE, required=False),
        ],
        output_ports=[
            NodePort(name="voice_block", data_type=PortDataType.TEXT),
            NodePort(name="nervous_habits", data_type=PortDataType.TEXT),
        ],
        prompt_template="提取以下章节涉及角色的声线特征...",
        prompt_variables=["novel_id", "chapter_number"],
        is_configurable=True,
        can_disable=True,
        default_timeout_seconds=30,
        cpms_node_key="context-voice-style",
        description="style_constraint_builder + character_state_vector",
        default_edges=["exec_writer"],
    )

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        import time
        start = time.time()
        novel_id = inputs.get("novel_id") or context.get("novel_id", "")

        try:
            voice_block = ""
            nervous_habits = ""

            try:
                from application.engine.services.style_constraint_builder import build_style_summary
                voice_block = build_style_summary(novel_id)
            except Exception as e:
                logger.warning(f"style_constraint_builder 调用失败: {e}")

            return NodeResult(
                outputs={"voice_block": voice_block, "nervous_habits": nervous_habits},
                status=NodeStatus.SUCCESS,
                duration_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            return NodeResult(
                outputs={"voice_block": "", "nervous_habits": ""},
                status=NodeStatus.ERROR,
                duration_ms=int((time.time() - start) * 1000),
                error=str(e),
            )

    def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        return True


# ─── ctx_memory: 记忆引擎 ───


@NodeRegistry.register("ctx_memory")
class MemoryNode(BaseNode):
    """记忆引擎 — ContextAssembler (feed-forward)"""

    meta = NodeMeta(
        node_type="ctx_memory",
        display_name="🧠 记忆引擎",
        category=NodeCategory.CONTEXT,
        icon="🧠",
        color="#8b5cf6",
        input_ports=[
            NodePort(name="novel_id", data_type=PortDataType.TEXT, required=True),
            NodePort(name="chapter_number", data_type=PortDataType.SCORE, required=False),
        ],
        output_ports=[
            NodePort(name="fact_lock", data_type=PortDataType.TEXT),
            NodePort(name="entity_memory", data_type=PortDataType.TEXT),
        ],
        prompt_template="整理以下小说已确立的事实锁...",
        prompt_variables=["novel_id", "chapter_number"],
        is_configurable=True,
        can_disable=True,
        default_timeout_seconds=30,
        cpms_node_key="context-memory",
        description="ContextAssembler (feed-forward) 记忆注入",
        default_edges=["exec_beat"],
    )

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        import time
        start = time.time()
        novel_id = inputs.get("novel_id") or context.get("novel_id", "")

        try:
            fact_lock = ""
            entity_memory = ""

            try:
                from application.engine.services.context_assembler import ContextAssembler
                assembler = ContextAssembler()
                fact_lock = getattr(assembler, "build_fact_lock", lambda x: "")(novel_id)
            except Exception as e:
                logger.warning(f"ContextAssembler 调用失败: {e}")

            return NodeResult(
                outputs={"fact_lock": fact_lock, "entity_memory": entity_memory},
                status=NodeStatus.SUCCESS,
                duration_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            return NodeResult(
                outputs={"fact_lock": "", "entity_memory": ""},
                status=NodeStatus.ERROR,
                duration_ms=int((time.time() - start) * 1000),
                error=str(e),
            )

    def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        return True


# ─── ctx_debt: 叙事债务注入 ───


@NodeRegistry.register("ctx_debt")
class DebtNode(BaseNode):
    """叙事债务注入 — ContextAssembler DEBT_DUE 槽"""

    meta = NodeMeta(
        node_type="ctx_debt",
        display_name="💰 叙事债务",
        category=NodeCategory.CONTEXT,
        icon="💰",
        color="#f97316",
        input_ports=[
            NodePort(name="novel_id", data_type=PortDataType.TEXT, required=True),
        ],
        output_ports=[
            NodePort(name="debt_due_block", data_type=PortDataType.TEXT),
        ],
        prompt_template="整理以下小说中到期应还的叙事债务...",
        prompt_variables=["novel_id"],
        is_configurable=True,
        can_disable=True,
        default_timeout_seconds=20,
        cpms_node_key="context-debt",
        description="ContextAssembler DEBT_DUE 槽注入",
        default_edges=["exec_writer"],
    )

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        import time
        start = time.time()
        novel_id = inputs.get("novel_id") or context.get("novel_id", "")

        try:
            debt_due_block = ""

            try:
                from domain.novel.repositories.narrative_debt_repository import NarrativeDebtRepository
                from infrastructure.persistence.database.connection import get_database
                db = get_database()
                repo = NarrativeDebtRepository(db)
                debts = repo.find_due_by_novel(novel_id)
                if debts:
                    lines = [f"【到期】{d.description}" for d in debts]
                    debt_due_block = "\n".join(lines)
            except Exception as e:
                logger.warning(f"叙事债务加载失败: {e}")

            return NodeResult(
                outputs={"debt_due_block": debt_due_block},
                status=NodeStatus.SUCCESS,
                duration_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            return NodeResult(
                outputs={"debt_due_block": ""},
                status=NodeStatus.ERROR,
                duration_ms=int((time.time() - start) * 1000),
                error=str(e),
            )

    def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        return True
