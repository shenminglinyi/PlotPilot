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
    CPMSInjectionPoint,
    NodeCategory,
    NodeMeta,
    NodePort,
    NodeResult,
    NodeStatus,
    PortDataType,
    PromptMode,
)
from application.engine.dag.registry import BaseNode, NodeRegistry

from application.workflows.prose_discipline import build_prose_discipline_block

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
        cpms_node_key="macro-planning",
        description="PlanningService.generate_macro_plan",
        default_edges=["exec_beat"],
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

# CPMS 提示词节点 key（复用主工作流提示词体系，减少维护成本）
_WORKFLOW_CHAPTER_GEN_NODE_KEY = "chapter-generation-main"
_WORKFLOW_BEAT_NODE_KEY = "autopilot-stream-beat"


@NodeRegistry.register("exec_writer")
class WriterNode(BaseNode):
    """剧情引擎 — AutoNovelGenerationWorkflow.generate_chapter_stream

    优化点：
    1. 复用 CPMS 提示词注册表（chapter-generation-main），与主工作流保持一致
    2. 分节拍生成时使用 autopilot-stream-beat 模板，避免冗余系统指令
    3. 无节拍时使用精简版 system prompt，减少 token 开销
    """

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
            NodePort(name="fact_lock", data_type=PortDataType.TEXT, required=False),
            # ★ Anti-AI 子注入点变量槽
            NodePort(name="behavior_protocol", data_type=PortDataType.TEXT, required=False),
            NodePort(name="character_state_lock", data_type=PortDataType.TEXT, required=False),
            NodePort(name="allowlist_block", data_type=PortDataType.TEXT, required=False),
            NodePort(name="nervous_habits", data_type=PortDataType.TEXT, required=False),
        ],
        output_ports=[
            NodePort(name="content", data_type=PortDataType.TEXT),
            NodePort(name="word_count", data_type=PortDataType.SCORE),
        ],
        prompt_template="写作姿态：回忆并讲述这段事；避免写成交差用的说明文。\n\n{{context}}\n{{outline}}\n{{voice_block}}",
        prompt_variables=["context", "outline", "voice_block", "fact_lock", "foreshadowing_block", "behavior_protocol", "character_state_lock", "allowlist_block", "nervous_habits"],
        is_configurable=True,
        can_disable=False,
        default_timeout_seconds=300,
        cpms_node_key="chapter-generation-main",
        # ★ CPMS 子提示词自动注入（Anti-AI 层）
        cpms_sub_keys=[
            CPMSInjectionPoint(cpms_node_key="anti-ai-behavior-protocol", target_variable="behavior_protocol", description="Anti-AI 行为协议 P1-P5+R1-R8"),
            CPMSInjectionPoint(cpms_node_key="anti-ai-character-state-lock", target_variable="character_state_lock", description="角色状态锁 L4"),
            CPMSInjectionPoint(cpms_node_key="anti-ai-allowlist-explain", target_variable="allowlist_block", description="场景化白名单 L3"),
        ],
        prompt_mode=PromptMode.CPMS_FIRST,
        description="AutoNovelGenerationWorkflow — Anti-AI 协议化章节生成；全托管时由 ChapterConductor（铺陈/收束/着陆）控节拍，超硬上限触发 smart_truncate 句界截断",
        default_edges=["val_style", "val_tension", "val_anti_ai"],
    )

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        import time
        start = time.time()

        try:
            content = ""
            word_count = 0
            novel_id = context.get("novel_id", "")

            # 收集上下文变量
            beats = inputs.get("beats", []) or []
            variables = {
                "context": inputs.get("context", ""),
                "outline": inputs.get("outline", ""),
                "voice_block": inputs.get("voice_block", ""),
                "fact_lock": inputs.get("fact_lock", ""),
                "foreshadowing_block": inputs.get("foreshadowing_block", ""),
                "debt_due_block": inputs.get("debt_due_block", ""),
                "planning_section": "",
                # ★ Anti-AI 子注入变量（优先使用上游传来的，缺失时由 cpms_sub_keys 自动拉取）
                "behavior_protocol": inputs.get("behavior_protocol", ""),
                "character_state_lock": inputs.get("character_state_lock", ""),
                "allowlist_block": inputs.get("allowlist_block", ""),
                "nervous_habits": inputs.get("nervous_habits", ""),
                "beat_extra": "",
                "beat_section": "",
                "prose_discipline": build_prose_discipline_block(
                    beat_mode=bool(beats),
                    beat_target_words=None,
                ),
            }

            # ★ 使用 resolve_prompt 统一获取提示词（自动走 CPMS → Config → Meta + 子注入）
            resolved = self.resolve_prompt(variables)

            # 调用 LLM 生成
            try:
                from domain.ai.services.llm_service import LLMService
                from domain.ai.value_objects.prompt import Prompt
                from domain.ai.services.llm_service import GenerationConfig

                llm = LLMService()
                system_prompt = resolved["system"]
                user_prompt = resolved["user"] or "请开始写作"

                prompt = Prompt(system=system_prompt, user=user_prompt)

                # 根据是否有节拍，调整生成参数
                config = GenerationConfig()
                if beats and len(beats) > 0:
                    config = GenerationConfig(
                        max_tokens=2000,
                        temperature=0.85,
                    )
                else:
                    config = GenerationConfig(
                        max_tokens=4000,
                        temperature=0.80,
                    )

                # 应用用户配置覆盖
                if self._config:
                    if self._config.temperature is not None:
                        config.temperature = self._config.temperature
                    if self._config.max_tokens is not None:
                        config.max_tokens = self._config.max_tokens

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
        cpms_node_key="autopilot-stream-beat",
        description="ContextBuilder.magnify_outline_to_beats；产出 beats 供剧情引擎按节拍写作与指挥遥测",
        default_edges=["exec_writer"],
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
        cpms_node_key="scene-director",
        description="SceneDirectorService 场景分析",
        default_edges=["exec_beat"],
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
