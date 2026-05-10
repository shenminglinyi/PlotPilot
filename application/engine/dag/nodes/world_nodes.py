"""World 节点 — 世界设定（4 个节点）

- world_bible_all: 完整 Bible 生成
- world_worldbuilding: 世界观与文风生成
- world_characters: 人物群像生成
- world_locations: 地点地图生成

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


# ─── world_bible_all: 完整 Bible 生成 ───


@NodeRegistry.register("world_bible_all")
class BibleAllNode(BaseNode):
    """完整 Bible 生成 — 一键构建五维度世界体系与人物群像"""

    meta = NodeMeta(
        node_type="world_bible_all",
        display_name="🏰 完整Bible生成",
        category=NodeCategory.WORLD,
        icon="🏰",
        color="#15803d",
        input_ports=[
            NodePort(name="premise", data_type=PortDataType.TEXT, required=True),
            NodePort(name="genre", data_type=PortDataType.TEXT, required=False),
        ],
        output_ports=[
            NodePort(name="bible_json", data_type=PortDataType.JSON),
        ],
        prompt_template="你是一位拥有造物主思维的网文世界架构师...",
        prompt_variables=["premise", "genre"],
        is_configurable=True,
        can_disable=False,
        default_timeout_seconds=120,
        cpms_node_key="bible-all",
        prompt_mode=PromptMode.CPMS_FIRST,
        description="一键构建具备内生矛盾与自驱力的五维度世界体系与人物群像",
        default_edges=["world_worldbuilding", "world_characters"],
    )

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        import time
        start = time.time()

        try:
            bible_json = {}

            # 使用 resolve_prompt 统一获取提示词
            resolved = self.resolve_prompt({
                "premise": inputs.get("premise", ""),
                "genre": inputs.get("genre", ""),
            })

            try:
                from domain.ai.services.llm_service import LLMService
                from domain.ai.value_objects.prompt import Prompt
                from domain.ai.services.llm_service import GenerationConfig

                llm = LLMService()
                prompt = Prompt(system=resolved["system"], user=resolved["user"])
                config = GenerationConfig(max_tokens=4000, temperature=0.8)

                # 应用用户配置覆盖
                if self._config:
                    if self._config.temperature is not None:
                        config.temperature = self._config.temperature
                    if self._config.max_tokens is not None:
                        config.max_tokens = self._config.max_tokens

                result = await llm.generate(prompt, config)
                raw_text = result.text if hasattr(result, 'text') else str(result)

                # 尝试解析 JSON
                import json
                try:
                    bible_json = json.loads(raw_text)
                except (json.JSONDecodeError, TypeError):
                    bible_json = {"raw_text": raw_text}

            except Exception as e:
                logger.warning(f"LLM 调用失败: {e}")

            return NodeResult(
                outputs={"bible_json": bible_json},
                status=NodeStatus.SUCCESS,
                duration_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            return NodeResult(outputs={"bible_json": {}}, status=NodeStatus.ERROR, duration_ms=int((time.time() - start) * 1000), error=str(e))

    def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        return "premise" in inputs


# ─── world_worldbuilding: 世界观与文风生成 ───


@NodeRegistry.register("world_worldbuilding")
class WorldbuildingNode(BaseNode):
    """世界观与文风生成 — 5维度硬核框架"""

    meta = NodeMeta(
        node_type="world_worldbuilding",
        display_name="🌍 世界观生成",
        category=NodeCategory.WORLD,
        icon="🌍",
        color="#059669",
        input_ports=[
            NodePort(name="premise", data_type=PortDataType.TEXT, required=True),
            NodePort(name="existing_settings", data_type=PortDataType.TEXT, required=False),
        ],
        output_ports=[
            NodePort(name="worldbuilding_json", data_type=PortDataType.JSON),
        ],
        prompt_template="你是好莱坞科幻/奇幻概念设计师...",
        prompt_variables=["premise", "existing_settings"],
        is_configurable=True,
        can_disable=True,
        default_timeout_seconds=120,
        cpms_node_key="bible-worldbuilding",
        prompt_mode=PromptMode.CPMS_FIRST,
        description="生成避免悬浮感、具有厚重社会生态的5维度世界观体系",
        default_edges=["world_characters", "world_locations"],
    )

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        import time
        start = time.time()

        try:
            worldbuilding_json = {}

            resolved = self.resolve_prompt({
                "premise": inputs.get("premise", ""),
                "existing_settings": inputs.get("existing_settings", ""),
            })

            try:
                from domain.ai.services.llm_service import LLMService
                from domain.ai.value_objects.prompt import Prompt
                from domain.ai.services.llm_service import GenerationConfig

                llm = LLMService()
                prompt = Prompt(system=resolved["system"], user=resolved["user"])
                config = GenerationConfig(max_tokens=3000, temperature=0.8)
                if self._config:
                    if self._config.temperature is not None:
                        config.temperature = self._config.temperature
                    if self._config.max_tokens is not None:
                        config.max_tokens = self._config.max_tokens

                result = await llm.generate(prompt, config)
                raw_text = result.text if hasattr(result, 'text') else str(result)

                import json
                try:
                    worldbuilding_json = json.loads(raw_text)
                except (json.JSONDecodeError, TypeError):
                    worldbuilding_json = {"raw_text": raw_text}

            except Exception as e:
                logger.warning(f"LLM 调用失败: {e}")

            return NodeResult(
                outputs={"worldbuilding_json": worldbuilding_json},
                status=NodeStatus.SUCCESS,
                duration_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            return NodeResult(outputs={"worldbuilding_json": {}}, status=NodeStatus.ERROR, duration_ms=int((time.time() - start) * 1000), error=str(e))

    def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        return "premise" in inputs


# ─── world_characters: 人物群像生成 ───


@NodeRegistry.register("world_characters")
class CharactersNode(BaseNode):
    """人物群像生成 — 基于社会生态孵化立体人物"""

    meta = NodeMeta(
        node_type="world_characters",
        display_name="👥 人物群像生成",
        category=NodeCategory.WORLD,
        icon="👥",
        color="#0d9488",
        input_ports=[
            NodePort(name="worldbuilding", data_type=PortDataType.TEXT, required=True),
            NodePort(name="style_guide", data_type=PortDataType.TEXT, required=False),
            NodePort(name="existing_characters", data_type=PortDataType.TEXT, required=False),
        ],
        output_ports=[
            NodePort(name="characters_json", data_type=PortDataType.JSON),
        ],
        prompt_template="你是顶级卡司导演...",
        prompt_variables=["worldbuilding", "style_guide", "existing_characters"],
        is_configurable=True,
        can_disable=True,
        default_timeout_seconds=120,
        cpms_node_key="bible-characters",
        prompt_mode=PromptMode.CPMS_FIRST,
        description="根据社会生态孵化具有内源性冲突和错综羁绊的立体人物",
        default_edges=["world_locations"],
    )

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        import time
        start = time.time()

        try:
            characters_json = {}

            resolved = self.resolve_prompt({
                "worldbuilding": inputs.get("worldbuilding", ""),
                "style_guide": inputs.get("style_guide", ""),
                "existing_characters": inputs.get("existing_characters", ""),
            })

            try:
                from domain.ai.services.llm_service import LLMService
                from domain.ai.value_objects.prompt import Prompt
                from domain.ai.services.llm_service import GenerationConfig

                llm = LLMService()
                prompt = Prompt(system=resolved["system"], user=resolved["user"])
                config = GenerationConfig(max_tokens=3000, temperature=0.8)
                if self._config:
                    if self._config.temperature is not None:
                        config.temperature = self._config.temperature
                    if self._config.max_tokens is not None:
                        config.max_tokens = self._config.max_tokens

                result = await llm.generate(prompt, config)
                raw_text = result.text if hasattr(result, 'text') else str(result)

                import json
                try:
                    characters_json = json.loads(raw_text)
                except (json.JSONDecodeError, TypeError):
                    characters_json = {"raw_text": raw_text}

            except Exception as e:
                logger.warning(f"LLM 调用失败: {e}")

            return NodeResult(
                outputs={"characters_json": characters_json},
                status=NodeStatus.SUCCESS,
                duration_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            return NodeResult(outputs={"characters_json": {}}, status=NodeStatus.ERROR, duration_ms=int((time.time() - start) * 1000), error=str(e))

    def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        return "worldbuilding" in inputs


# ─── world_locations: 地点地图生成 ───


@NodeRegistry.register("world_locations")
class LocationsNode(BaseNode):
    """地点地图生成 — 具有叙事功能的地缘拓扑网络"""

    meta = NodeMeta(
        node_type="world_locations",
        display_name="🗺️ 地点地图生成",
        category=NodeCategory.WORLD,
        icon="🗺️",
        color="#65a30d",
        input_ports=[
            NodePort(name="worldbuilding", data_type=PortDataType.TEXT, required=True),
            NodePort(name="existing_locations", data_type=PortDataType.TEXT, required=False),
            NodePort(name="character_context", data_type=PortDataType.TEXT, required=False),
        ],
        output_ports=[
            NodePort(name="locations_json", data_type=PortDataType.JSON),
        ],
        prompt_template="你是关卡设计师...",
        prompt_variables=["worldbuilding", "existing_locations", "character_context"],
        is_configurable=True,
        can_disable=True,
        default_timeout_seconds=120,
        cpms_node_key="bible-locations",
        prompt_mode=PromptMode.CPMS_FIRST,
        description="构建具有叙事功能的地缘拓扑网络",
        default_edges=["exec_planning"],
    )

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        import time
        start = time.time()

        try:
            locations_json = {}

            resolved = self.resolve_prompt({
                "worldbuilding": inputs.get("worldbuilding", ""),
                "existing_locations": inputs.get("existing_locations", ""),
                "character_context": inputs.get("character_context", ""),
            })

            try:
                from domain.ai.services.llm_service import LLMService
                from domain.ai.value_objects.prompt import Prompt
                from domain.ai.services.llm_service import GenerationConfig

                llm = LLMService()
                prompt = Prompt(system=resolved["system"], user=resolved["user"])
                config = GenerationConfig(max_tokens=3000, temperature=0.8)
                if self._config:
                    if self._config.temperature is not None:
                        config.temperature = self._config.temperature
                    if self._config.max_tokens is not None:
                        config.max_tokens = self._config.max_tokens

                result = await llm.generate(prompt, config)
                raw_text = result.text if hasattr(result, 'text') else str(result)

                import json
                try:
                    locations_json = json.loads(raw_text)
                except (json.JSONDecodeError, TypeError):
                    locations_json = {"raw_text": raw_text}

            except Exception as e:
                logger.warning(f"LLM 调用失败: {e}")

            return NodeResult(
                outputs={"locations_json": locations_json},
                status=NodeStatus.SUCCESS,
                duration_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            return NodeResult(outputs={"locations_json": {}}, status=NodeStatus.ERROR, duration_ms=int((time.time() - start) * 1000), error=str(e))

    def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        return "worldbuilding" in inputs
