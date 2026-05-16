"""Generation 补充节点 — 生成与创作（3 个补充节点）

- gen_chapter_basic: 基础章节生成
- gen_dialogue: 对白生成
- gen_scene: 场景正文生成

CPMS 联动：每个节点对应提示词广场的一个提示词节点，
execute() 内调用 self.resolve_prompt() 自动走 CPMS → Config → Meta 三级降级。
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

logger = logging.getLogger(__name__)


# ─── gen_chapter_basic: 基础章节生成 ───


@NodeRegistry.register("gen_chapter_basic")
class ChapterBasicNode(BaseNode):
    """基础章节生成 — 引擎层的轻量章节生成"""

    meta = NodeMeta(
        node_type="gen_chapter_basic",
        display_name="📝 基础章节生成",
        category=NodeCategory.EXECUTION,
        icon="📝",
        color="#4338ca",
        input_ports=[
            NodePort(name="novel_title", data_type=PortDataType.TEXT, required=True),
            NodePort(name="chapter_number", data_type=PortDataType.SCORE, required=False),
            NodePort(name="outline", data_type=PortDataType.TEXT, required=True),
            NodePort(name="characters_section", data_type=PortDataType.TEXT, required=False),
            NodePort(name="world_settings_section", data_type=PortDataType.TEXT, required=False),
        ],
        output_ports=[
            NodePort(name="content", data_type=PortDataType.TEXT),
            NodePort(name="word_count", data_type=PortDataType.SCORE),
        ],
        prompt_template="你是长篇小说的创作者...",
        prompt_variables=["novel_title", "chapter_number", "outline", "characters_section", "world_settings_section"],
        is_configurable=True,
        can_disable=True,
        default_timeout_seconds=300,
        cpms_node_key="chapter-generation-basic",
        prompt_mode=PromptMode.CPMS_FIRST,
        description="引擎层基础章节生成，注入 Bible 人物和世界设定",
        default_edges=["val_style"],
    )

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        import time
        start = time.time()

        try:
            content = ""
            word_count = 0

            resolved = self.resolve_prompt({
                "novel_title": inputs.get("novel_title", ""),
                "chapter_number": str(inputs.get("chapter_number", 0)),
                "outline": inputs.get("outline", ""),
                "characters_section": inputs.get("characters_section", ""),
                "world_settings_section": inputs.get("world_settings_section", ""),
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
            return NodeResult(outputs={"content": "", "word_count": 0}, status=NodeStatus.ERROR, duration_ms=int((time.time() - start) * 1000), error=str(e))

    def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        return "outline" in inputs


# ─── gen_dialogue: 对白生成 ───


@NodeRegistry.register("gen_dialogue")
class DialogueNode(BaseNode):
    """对白生成 — 双人或多角色对白场景"""

    meta = NodeMeta(
        node_type="gen_dialogue",
        display_name="💬 对白生成",
        category=NodeCategory.EXECUTION,
        icon="💬",
        color="#6d28d9",
        input_ports=[
            NodePort(name="context", data_type=PortDataType.TEXT, required=False),
            NodePort(name="scene_description", data_type=PortDataType.TEXT, required=True),
            NodePort(name="characters", data_type=PortDataType.TEXT, required=False),
            NodePort(name="tension_level", data_type=PortDataType.TEXT, required=False),
        ],
        output_ports=[
            NodePort(name="dialogue_text", data_type=PortDataType.TEXT),
            NodePort(name="word_count", data_type=PortDataType.SCORE),
        ],
        prompt_template="",
        prompt_variables=["context", "scene_description", "characters", "tension_level"],
        is_configurable=True,
        can_disable=True,
        default_timeout_seconds=120,
        cpms_node_key="dialogue-generation",
        prompt_mode=PromptMode.CPMS_FIRST,
        description="双人或多角色对白场景生成，追求弦外之音和潜台词",
        default_edges=["val_style"],
    )

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        import time
        start = time.time()

        try:
            dialogue_text = ""
            word_count = 0

            resolved = self.resolve_prompt({
                "context": inputs.get("context", ""),
                "scene_description": inputs.get("scene_description", ""),
                "characters": inputs.get("characters", ""),
                "tension_level": inputs.get("tension_level", "medium"),
            })

            try:
                from domain.ai.services.llm_service import LLMService
                from domain.ai.value_objects.prompt import Prompt
                from domain.ai.services.llm_service import GenerationConfig

                llm = LLMService()
                prompt = Prompt(system=resolved["system"], user=resolved["user"])
                config = GenerationConfig(max_tokens=2000, temperature=0.85)
                if self._config:
                    if self._config.temperature is not None:
                        config.temperature = self._config.temperature
                    if self._config.max_tokens is not None:
                        config.max_tokens = self._config.max_tokens

                result = await llm.generate(prompt, config)
                dialogue_text = result.text if hasattr(result, 'text') else str(result)
                word_count = len(dialogue_text)

            except Exception as e:
                logger.warning(f"LLM 调用失败: {e}")

            return NodeResult(
                outputs={"dialogue_text": dialogue_text, "word_count": word_count},
                status=NodeStatus.SUCCESS,
                metrics={"word_count": float(word_count)},
                duration_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            return NodeResult(outputs={"dialogue_text": "", "word_count": 0}, status=NodeStatus.ERROR, duration_ms=int((time.time() - start) * 1000), error=str(e))

    def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        return "scene_description" in inputs


# ─── gen_scene: 场景正文生成 ───


@NodeRegistry.register("gen_scene")
class SceneGenNode(BaseNode):
    """场景正文生成 — 沉浸式反AI场景写作"""

    meta = NodeMeta(
        node_type="gen_scene",
        display_name="🎬 场景正文生成",
        category=NodeCategory.EXECUTION,
        icon="🎬",
        color="#7c3aed",
        input_ports=[
            NodePort(name="title", data_type=PortDataType.TEXT, required=False),
            NodePort(name="goal", data_type=PortDataType.TEXT, required=False),
            NodePort(name="pov_character", data_type=PortDataType.TEXT, required=False),
            NodePort(name="location", data_type=PortDataType.TEXT, required=False),
            NodePort(name="tone", data_type=PortDataType.TEXT, required=False),
            NodePort(name="estimated_words", data_type=PortDataType.SCORE, required=False, default=800),
            NodePort(name="analysis_block", data_type=PortDataType.TEXT, required=False),
            NodePort(name="previous_scenes_block", data_type=PortDataType.TEXT, required=False),
            NodePort(name="foreshadowing_block", data_type=PortDataType.TEXT, required=False),
        ],
        output_ports=[
            NodePort(name="content", data_type=PortDataType.TEXT),
            NodePort(name="word_count", data_type=PortDataType.SCORE),
        ],
        prompt_template="",
        prompt_variables=["title", "goal", "pov_character", "location", "tone", "estimated_words", "analysis_block", "previous_scenes_block", "foreshadowing_block"],
        is_configurable=True,
        can_disable=True,
        default_timeout_seconds=180,
        cpms_node_key="scene-generation",
        prompt_mode=PromptMode.CPMS_FIRST,
        description="v2沉浸式反AI场景生成：MRU理论+POV限制视角",
        default_edges=["val_style"],
    )

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        import time
        start = time.time()

        try:
            content = ""
            word_count = 0

            resolved = self.resolve_prompt({
                "title": inputs.get("title", ""),
                "goal": inputs.get("goal", ""),
                "pov_character": inputs.get("pov_character", ""),
                "location": inputs.get("location", ""),
                "tone": inputs.get("tone", ""),
                "estimated_words": str(inputs.get("estimated_words", 800)),
                "analysis_block": inputs.get("analysis_block", ""),
                "previous_scenes_block": inputs.get("previous_scenes_block", ""),
                "foreshadowing_block": inputs.get("foreshadowing_block", ""),
            })

            try:
                from domain.ai.services.llm_service import LLMService
                from domain.ai.value_objects.prompt import Prompt
                from domain.ai.services.llm_service import GenerationConfig

                llm = LLMService()
                prompt = Prompt(system=resolved["system"], user=resolved["user"])
                est = int(inputs.get("estimated_words", 800))
                config = GenerationConfig(max_tokens=min(est + 500, 4000), temperature=0.85)
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
            return NodeResult(outputs={"content": "", "word_count": 0}, status=NodeStatus.ERROR, duration_ms=int((time.time() - start) * 1000), error=str(e))

    def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        return True
