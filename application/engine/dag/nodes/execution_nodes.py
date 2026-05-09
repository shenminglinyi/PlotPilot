"""Execution 节点 — 执行与生成（4 个节点）

- exec_planning: 规划引擎
- exec_writer: 剧情引擎
- exec_beat: 节拍放大器
- exec_scene: 场景导演
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


# ─── exec_planning: 规划引擎 ───


@NodeRegistry.register("exec_planning")
class PlanningNode(BaseNode):
    """规划引擎 — PlanningService.generate_macro_plan"""

    meta = NodeMeta(
        node_type="exec_planning",
        display_name="📐 规划引擎",
        category=NodeCategory.EXECUTION,
        icon="📐",
        color="#3b82f6",
        input_ports=[
            NodePort(name="novel_id", data_type=PortDataType.TEXT, required=True),
            NodePort(name="target_chapters", data_type=PortDataType.SCORE, required=False),
        ],
        output_ports=[
            NodePort(name="macro_plan", data_type=PortDataType.TEXT),
            NodePort(name="act_plan", data_type=PortDataType.TEXT),
        ],
        prompt_template="为以下小说生成宏观规划...",
        prompt_variables=["novel_id", "target_chapters"],
        is_configurable=True,
        can_disable=False,
        default_timeout_seconds=120,
    )

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        import time
        start = time.time()
        novel_id = inputs.get("novel_id") or context.get("novel_id", "")

        try:
            macro_plan = ""
            act_plan = ""

            try:
                from application.blueprint.services.continuous_planning_service import ContinuousPlanningService
                from infrastructure.persistence.database.connection import get_database
                db = get_database()
                svc = ContinuousPlanningService(db)
                result = await svc.generate_macro_plan(novel_id)
                if result:
                    macro_plan = getattr(result, "plan_text", "") or str(result)
            except Exception as e:
                logger.warning(f"PlanningService 调用失败: {e}")

            return NodeResult(
                outputs={"macro_plan": macro_plan, "act_plan": act_plan},
                status=NodeStatus.SUCCESS,
                duration_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            return NodeResult(outputs={}, status=NodeStatus.ERROR, duration_ms=int((time.time() - start) * 1000), error=str(e))

    def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        return True


# ─── exec_writer: 剧情引擎 ───


@NodeRegistry.register("exec_writer")
class WriterNode(BaseNode):
    """剧情引擎 — AutoNovelGenerationWorkflow.generate_chapter_stream"""

    meta = NodeMeta(
        node_type="exec_writer",
        display_name="✍️ 剧情引擎",
        category=NodeCategory.EXECUTION,
        icon="✍️",
        color="#ef4444",
        input_ports=[
            NodePort(name="context", data_type=PortDataType.TEXT, required=False),
            NodePort(name="outline", data_type=PortDataType.TEXT, required=False),
            NodePort(name="voice_block", data_type=PortDataType.TEXT, required=False),
            NodePort(name="beats", data_type=PortDataType.LIST, required=False),
            NodePort(name="foreshadowing_block", data_type=PortDataType.TEXT, required=False),
            NodePort(name="debt_due_block", data_type=PortDataType.TEXT, required=False),
        ],
        output_ports=[
            NodePort(name="content", data_type=PortDataType.TEXT),
            NodePort(name="word_count", data_type=PortDataType.SCORE),
        ],
        prompt_template="你现在不是在'写文章'，你是在'回忆并讲述一段真实发生过的事'。...\n\n{{context}}\n{{outline}}\n{{voice_block}}",
        prompt_variables=["context", "outline", "voice_block"],
        is_configurable=True,
        can_disable=False,
        default_timeout_seconds=300,
    )

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        import time
        start = time.time()

        try:
            content = ""
            word_count = 0

            # 收集所有上下文输入
            context_parts = []
            for key in ["context", "outline", "voice_block", "foreshadowing_block", "debt_due_block"]:
                val = inputs.get(key, "")
                if val:
                    context_parts.append(val)

            # 如果有 LLM 服务，调用生成
            try:
                from domain.ai.services.llm_service import LLMService
                from domain.ai.value_objects.prompt import Prompt
                from domain.ai.services.llm_service import GenerationConfig

                llm = LLMService()
                template = self.get_prompt_template()
                if template:
                    variables = {}
                    for key in self.meta.prompt_variables:
                        variables[key] = inputs.get(key, "")
                    rendered = self.build_prompt(variables)

                    prompt = Prompt(system=rendered, user="请开始写作")
                    config = GenerationConfig()
                    result = await llm.generate(prompt, config)
                    content = result.text if hasattr(result, 'text') else str(result)
                    word_count = len(content)
            except Exception as e:
                logger.warning(f"LLM 调用失败: {e}")

            return NodeResult(
                outputs={"content": content, "word_count": word_count},
                status=NodeStatus.SUCCESS,
                metrics={"word_count": float(word_count)},
                duration_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            return NodeResult(outputs={}, status=NodeStatus.ERROR, duration_ms=int((time.time() - start) * 1000), error=str(e))

    def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        return True


# ─── exec_beat: 节拍放大器 ───


@NodeRegistry.register("exec_beat")
class BeatNode(BaseNode):
    """节拍放大器 — ContextBuilder.magnify_outline_to_beats"""

    meta = NodeMeta(
        node_type="exec_beat",
        display_name="🥁 节拍放大器",
        category=NodeCategory.EXECUTION,
        icon="🥁",
        color="#14b8a6",
        input_ports=[
            NodePort(name="outline", data_type=PortDataType.TEXT, required=True),
        ],
        output_ports=[
            NodePort(name="beats", data_type=PortDataType.LIST),
        ],
        prompt_template="将以下大纲拆分为详细节拍...",
        prompt_variables=["outline"],
        is_configurable=True,
        can_disable=True,
        default_timeout_seconds=60,
    )

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        import time
        start = time.time()

        try:
            beats = []
            outline = inputs.get("outline", "")

            try:
                from application.engine.services.context_builder import ContextBuilder
                builder = ContextBuilder()
                beats = builder.magnify_outline_to_beats(outline)
            except Exception as e:
                logger.warning(f"ContextBuilder.magnify_outline_to_beats 调用失败: {e}")
                # 降级：简单拆分
                if outline:
                    beats = [{"desc": outline, "target": 800}]

            return NodeResult(
                outputs={"beats": beats},
                status=NodeStatus.SUCCESS,
                duration_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            return NodeResult(outputs={"beats": []}, status=NodeStatus.ERROR, duration_ms=int((time.time() - start) * 1000), error=str(e))

    def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        return True


# ─── exec_scene: 场景导演 ───


@NodeRegistry.register("exec_scene")
class SceneNode(BaseNode):
    """场景导演 — SceneDirectorService"""

    meta = NodeMeta(
        node_type="exec_scene",
        display_name="🎬 场景导演",
        category=NodeCategory.EXECUTION,
        icon="🎬",
        color="#a855f7",
        input_ports=[
            NodePort(name="content", data_type=PortDataType.TEXT, required=False),
            NodePort(name="outline", data_type=PortDataType.TEXT, required=True),
        ],
        output_ports=[
            NodePort(name="scene_analysis", data_type=PortDataType.JSON),
        ],
        prompt_template="分析以下章节大纲的场景信息...",
        prompt_variables=["outline"],
        is_configurable=True,
        can_disable=True,
        default_timeout_seconds=60,
    )

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        import time
        start = time.time()

        try:
            scene_analysis = {}

            try:
                from application.core.services.scene_generation_service import SceneGenerationService
                novel_id = context.get("novel_id", "")
                outline = inputs.get("outline", "")
                svc = SceneGenerationService()
                scene_analysis = svc.analyze(novel_id, outline)
            except Exception as e:
                logger.warning(f"SceneDirectorService 调用失败: {e}")

            return NodeResult(
                outputs={"scene_analysis": scene_analysis},
                status=NodeStatus.SUCCESS,
                duration_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            return NodeResult(outputs={"scene_analysis": {}}, status=NodeStatus.ERROR, duration_ms=int((time.time() - start) * 1000), error=str(e))

    def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        return True
