"""Planning 节点 — 规划设计（3 个补充节点）

- planning_beat_sheet: 节拍表拆解
- planning_quick_macro: 极速宏观规划
- planning_act: 幕级章节规划

CPMS 联动：每个节点对应提示词广场的一个提示词节点，
execute() 内调用 self.resolve_prompt() 自动走 CPMS → Config → Meta 三级降级。
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
    PromptMode,
)
from application.engine.dag.registry import BaseNode, NodeRegistry

logger = logging.getLogger(__name__)


# ─── planning_beat_sheet: 节拍表拆解 ───


@NodeRegistry.register("planning_beat_sheet")
class BeatSheetNode(BaseNode):
    """节拍表拆解 — 将章纲拆解为场景/续场结构"""

    meta = NodeMeta(
        node_type="planning_beat_sheet",
        display_name="🎵 节拍表拆解",
        category=NodeCategory.PLANNING,
        icon="🎵",
        color="#6d28d9",
        input_ports=[
            NodePort(name="outline", data_type=PortDataType.TEXT, required=True),
            NodePort(name="characters_block", data_type=PortDataType.TEXT, required=False),
            NodePort(name="storylines_block", data_type=PortDataType.TEXT, required=False),
            NodePort(name="previous_chapter_block", data_type=PortDataType.TEXT, required=False),
            NodePort(name="foreshadowings_block", data_type=PortDataType.TEXT, required=False),
            NodePort(name="locations_block", data_type=PortDataType.TEXT, required=False),
            NodePort(name="timeline_block", data_type=PortDataType.TEXT, required=False),
        ],
        output_ports=[
            NodePort(name="beat_sheet_json", data_type=PortDataType.JSON),
        ],
        prompt_template="你是深谙'场景与续场'节奏的剧本拆解师...",
        prompt_variables=["outline", "characters_block", "storylines_block", "previous_chapter_block", "foreshadowings_block", "locations_block", "timeline_block"],
        is_configurable=True,
        can_disable=True,
        default_timeout_seconds=60,
        cpms_node_key="beat-sheet-decomposition",
        prompt_mode=PromptMode.CPMS_FIRST,
        description="将章纲拆解为实战可写的场景/续场(Scene & Sequel)结构",
        default_edges=["exec_beat"],
    )

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        import time
        start = time.time()

        try:
            beat_sheet_json = {}

            resolved = self.resolve_prompt({
                "outline": inputs.get("outline", ""),
                "characters_block": inputs.get("characters_block", ""),
                "storylines_block": inputs.get("storylines_block", ""),
                "previous_chapter_block": inputs.get("previous_chapter_block", ""),
                "foreshadowings_block": inputs.get("foreshadowings_block", ""),
                "locations_block": inputs.get("locations_block", ""),
                "timeline_block": inputs.get("timeline_block", ""),
            })

            try:
                from domain.ai.services.llm_service import LLMService
                from domain.ai.value_objects.prompt import Prompt
                from domain.ai.services.llm_service import GenerationConfig

                llm = LLMService()
                prompt = Prompt(system=resolved["system"], user=resolved["user"])
                config = GenerationConfig(max_tokens=3000, temperature=0.6)
                if self._config:
                    if self._config.temperature is not None:
                        config.temperature = self._config.temperature
                    if self._config.max_tokens is not None:
                        config.max_tokens = self._config.max_tokens

                result = await llm.generate(prompt, config)
                raw_text = result.text if hasattr(result, 'text') else str(result)

                import json
                try:
                    beat_sheet_json = json.loads(raw_text)
                except (json.JSONDecodeError, TypeError):
                    beat_sheet_json = {"raw_text": raw_text}

            except Exception as e:
                logger.warning(f"LLM 调用失败: {e}")

            return NodeResult(
                outputs={"beat_sheet_json": beat_sheet_json},
                status=NodeStatus.SUCCESS,
                duration_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            return NodeResult(outputs={"beat_sheet_json": {}}, status=NodeStatus.ERROR, duration_ms=int((time.time() - start) * 1000), error=str(e))

    def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        return "outline" in inputs


# ─── planning_quick_macro: 极速宏观规划 ───


@NodeRegistry.register("planning_quick_macro")
class QuickMacroNode(BaseNode):
    """极速宏观规划·破城槌 — 狂热主编风格"""

    meta = NodeMeta(
        node_type="planning_quick_macro",
        display_name="⚡ 极速宏观规划",
        category=NodeCategory.PLANNING,
        icon="⚡",
        color="#7c3aed",
        input_ports=[
            NodePort(name="premise", data_type=PortDataType.TEXT, required=True),
            NodePort(name="target_chapters", data_type=PortDataType.SCORE, required=False, default=100),
            NodePort(name="worldview", data_type=PortDataType.TEXT, required=False),
            NodePort(name="characters", data_type=PortDataType.TEXT, required=False),
        ],
        output_ports=[
            NodePort(name="macro_plan_json", data_type=PortDataType.JSON),
        ],
        prompt_template="你是一位手握无数畅销书的狂热白金级主编...",
        prompt_variables=["premise", "target_chapters", "worldview", "characters"],
        is_configurable=True,
        can_disable=True,
        default_timeout_seconds=120,
        cpms_node_key="planning-quick-macro",
        prompt_mode=PromptMode.CPMS_FIRST,
        description="极速模式：基于英雄之旅与救猫咪理论强推商业网文骨架",
        default_edges=["planning_act"],
    )

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        import time
        start = time.time()

        try:
            macro_plan_json = {}

            resolved = self.resolve_prompt({
                "premise": inputs.get("premise", ""),
                "target_chapters": str(inputs.get("target_chapters", 100)),
                "worldview": inputs.get("worldview", ""),
                "characters": inputs.get("characters", ""),
            })

            try:
                from domain.ai.services.llm_service import LLMService
                from domain.ai.value_objects.prompt import Prompt
                from domain.ai.services.llm_service import GenerationConfig

                llm = LLMService()
                prompt = Prompt(system=resolved["system"], user=resolved["user"])
                config = GenerationConfig(max_tokens=4000, temperature=0.8)
                if self._config:
                    if self._config.temperature is not None:
                        config.temperature = self._config.temperature
                    if self._config.max_tokens is not None:
                        config.max_tokens = self._config.max_tokens

                result = await llm.generate(prompt, config)
                raw_text = result.text if hasattr(result, 'text') else str(result)

                import json
                try:
                    macro_plan_json = json.loads(raw_text)
                except (json.JSONDecodeError, TypeError):
                    macro_plan_json = {"raw_text": raw_text}

            except Exception as e:
                logger.warning(f"LLM 调用失败: {e}")

            return NodeResult(
                outputs={"macro_plan_json": macro_plan_json},
                status=NodeStatus.SUCCESS,
                duration_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            return NodeResult(outputs={"macro_plan_json": {}}, status=NodeStatus.ERROR, duration_ms=int((time.time() - start) * 1000), error=str(e))

    def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        return "premise" in inputs


# ─── planning_act: 幕级章节规划 ───


@NodeRegistry.register("planning_act")
class ActPlanningNode(BaseNode):
    """幕级章节规划 — 将抽象幕大纲落地为章纲序列"""

    meta = NodeMeta(
        node_type="planning_act",
        display_name="🎭 幕级规划",
        category=NodeCategory.PLANNING,
        icon="🎭",
        color="#8b5cf6",
        input_ports=[
            NodePort(name="context", data_type=PortDataType.TEXT, required=True),
            NodePort(name="chapter_count", data_type=PortDataType.SCORE, required=True, default=5),
        ],
        output_ports=[
            NodePort(name="act_chapters_json", data_type=PortDataType.JSON),
        ],
        prompt_template="你是精密的故事工程师...",
        prompt_variables=["context", "chapter_count"],
        is_configurable=True,
        can_disable=True,
        default_timeout_seconds=120,
        cpms_node_key="planning-act",
        prompt_mode=PromptMode.CPMS_FIRST,
        description="将抽象的幕大纲落地为充满递进张力的章纲序列",
        default_edges=["exec_beat"],
    )

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        import time
        start = time.time()

        try:
            act_chapters_json = {}

            resolved = self.resolve_prompt({
                "context": inputs.get("context", ""),
                "chapter_count": str(inputs.get("chapter_count", 5)),
            })

            try:
                from domain.ai.services.llm_service import LLMService
                from domain.ai.value_objects.prompt import Prompt
                from domain.ai.services.llm_service import GenerationConfig

                llm = LLMService()
                prompt = Prompt(system=resolved["system"], user=resolved["user"])
                config = GenerationConfig(max_tokens=3000, temperature=0.7)
                if self._config:
                    if self._config.temperature is not None:
                        config.temperature = self._config.temperature
                    if self._config.max_tokens is not None:
                        config.max_tokens = self._config.max_tokens

                result = await llm.generate(prompt, config)
                raw_text = result.text if hasattr(result, 'text') else str(result)

                import json
                try:
                    act_chapters_json = json.loads(raw_text)
                except (json.JSONDecodeError, TypeError):
                    act_chapters_json = {"raw_text": raw_text}

            except Exception as e:
                logger.warning(f"LLM 调用失败: {e}")

            return NodeResult(
                outputs={"act_chapters_json": act_chapters_json},
                status=NodeStatus.SUCCESS,
                duration_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            return NodeResult(outputs={"act_chapters_json": {}}, status=NodeStatus.ERROR, duration_ms=int((time.time() - start) * 1000), error=str(e))

    def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        return "context" in inputs
