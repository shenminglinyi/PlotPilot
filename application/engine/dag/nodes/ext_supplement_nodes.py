"""Extraction 补充节点 — 信息提取（4 个补充节点）

- ext_state: 章节状态提取（9维度）
- ext_style: 文风分析（8维度）
- ext_narrative_sync: 章节叙事同步提取
- ext_summary: 摘要生成（多粒度）

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


# ─── ext_state: 章节状态提取 ───


@NodeRegistry.register("ext_state")
class StateExtractionNode(BaseNode):
    """章节状态提取 — 9维度结构化信息提取"""

    meta = NodeMeta(
        node_type="ext_state",
        display_name="🔬 状态提取",
        category=NodeCategory.VALIDATION,
        icon="🔬",
        color="#0891b2",
        input_ports=[
            NodePort(name="content", data_type=PortDataType.TEXT, required=True),
        ],
        output_ports=[
            NodePort(name="state_json", data_type=PortDataType.JSON),
        ],
        prompt_template="",
        prompt_variables=["content"],
        is_configurable=True,
        can_disable=True,
        default_timeout_seconds=60,
        cpms_node_key="chapter-state-extraction",
        prompt_mode=PromptMode.CPMS_FIRST,
        description="9维度结构化状态提取：人物、关系、伏笔、事件、时间线、故事线",
        default_edges=["val_narrative"],
    )

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        import time
        start = time.time()
        content = inputs.get("content", "")

        try:
            state_json = {}

            resolved = self.resolve_prompt({"content": content})

            try:
                from domain.ai.services.llm_service import LLMService
                from domain.ai.value_objects.prompt import Prompt
                from domain.ai.services.llm_service import GenerationConfig

                llm = LLMService()
                prompt = Prompt(system=resolved["system"], user=resolved["user"])
                config = GenerationConfig(max_tokens=3000, temperature=0.2)
                if self._config:
                    if self._config.temperature is not None:
                        config.temperature = self._config.temperature
                    if self._config.max_tokens is not None:
                        config.max_tokens = self._config.max_tokens

                result = await llm.generate(prompt, config)
                raw_text = result.text if hasattr(result, 'text') else str(result)

                import json
                try:
                    state_json = json.loads(raw_text)
                except (json.JSONDecodeError, TypeError):
                    state_json = {"raw_text": raw_text}

            except Exception as e:
                logger.warning(f"LLM 调用失败: {e}")

            return NodeResult(
                outputs={"state_json": state_json},
                status=NodeStatus.SUCCESS,
                duration_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            return NodeResult(outputs={"state_json": {}}, status=NodeStatus.ERROR, duration_ms=int((time.time() - start) * 1000), error=str(e))

    def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        return "content" in inputs


# ─── ext_style: 文风分析 ───


@NodeRegistry.register("ext_style")
class StyleAnalysisNode(BaseNode):
    """文风分析 — 8维度文风指纹提取"""

    meta = NodeMeta(
        node_type="ext_style",
        display_name="🎨 文风指纹",
        category=NodeCategory.VALIDATION,
        icon="🎨",
        color="#0e7490",
        input_ports=[
            NodePort(name="content", data_type=PortDataType.TEXT, required=True),
        ],
        output_ports=[
            NodePort(name="style_fingerprint", data_type=PortDataType.JSON),
        ],
        prompt_template="",
        prompt_variables=["content"],
        is_configurable=True,
        can_disable=True,
        default_timeout_seconds=60,
        cpms_node_key="style-analysis",
        prompt_mode=PromptMode.CPMS_FIRST,
        description="8维度文风指纹提取：叙事视角、台词比、描写深度、情绪浓度、节奏、感官、修辞、句式",
        default_edges=["val_style"],
    )

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        import time
        start = time.time()
        content = inputs.get("content", "")

        try:
            style_fingerprint = {}

            resolved = self.resolve_prompt({"content": content})

            try:
                from domain.ai.services.llm_service import LLMService
                from domain.ai.value_objects.prompt import Prompt
                from domain.ai.services.llm_service import GenerationConfig

                llm = LLMService()
                prompt = Prompt(system=resolved["system"], user=resolved["user"])
                config = GenerationConfig(max_tokens=1500, temperature=0.2)
                if self._config:
                    if self._config.temperature is not None:
                        config.temperature = self._config.temperature
                    if self._config.max_tokens is not None:
                        config.max_tokens = self._config.max_tokens

                result = await llm.generate(prompt, config)
                raw_text = result.text if hasattr(result, 'text') else str(result)

                import json
                try:
                    style_fingerprint = json.loads(raw_text)
                except (json.JSONDecodeError, TypeError):
                    style_fingerprint = {"raw_text": raw_text}

            except Exception as e:
                logger.warning(f"LLM 调用失败: {e}")

            return NodeResult(
                outputs={"style_fingerprint": style_fingerprint},
                status=NodeStatus.SUCCESS,
                duration_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            return NodeResult(outputs={"style_fingerprint": {}}, status=NodeStatus.ERROR, duration_ms=int((time.time() - start) * 1000), error=str(e))

    def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        return "content" in inputs


# ─── ext_narrative_sync: 章节叙事同步提取 ───


@NodeRegistry.register("ext_narrative_sync")
class NarrativeSyncExtractionNode(BaseNode):
    """章节叙事同步提取 — 增强版叙事状态机快照"""

    meta = NodeMeta(
        node_type="ext_narrative_sync",
        display_name="🔄 叙事同步提取",
        category=NodeCategory.VALIDATION,
        icon="🔄",
        color="#155e75",
        input_ports=[
            NodePort(name="content", data_type=PortDataType.TEXT, required=True),
            NodePort(name="foreshadow_context", data_type=PortDataType.TEXT, required=False),
        ],
        output_ports=[
            NodePort(name="sync_json", data_type=PortDataType.JSON),
        ],
        prompt_template="",
        prompt_variables=["content", "foreshadow_context"],
        is_configurable=True,
        can_disable=True,
        default_timeout_seconds=60,
        cpms_node_key="chapter-narrative-sync",
        prompt_mode=PromptMode.CPMS_FIRST,
        description="增强版叙事提取：为后续大纲修正提供精准的'状态机'快照",
        default_edges=["val_foreshadow"],
    )

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        import time
        start = time.time()
        content = inputs.get("content", "")

        try:
            sync_json = {}

            resolved = self.resolve_prompt({
                "content": content,
                "foreshadow_context": inputs.get("foreshadow_context", ""),
            })

            try:
                from domain.ai.services.llm_service import LLMService
                from domain.ai.value_objects.prompt import Prompt
                from domain.ai.services.llm_service import GenerationConfig

                llm = LLMService()
                prompt = Prompt(system=resolved["system"], user=resolved["user"])
                config = GenerationConfig(max_tokens=3000, temperature=0.2)
                if self._config:
                    if self._config.temperature is not None:
                        config.temperature = self._config.temperature
                    if self._config.max_tokens is not None:
                        config.max_tokens = self._config.max_tokens

                result = await llm.generate(prompt, config)
                raw_text = result.text if hasattr(result, 'text') else str(result)

                import json
                try:
                    sync_json = json.loads(raw_text)
                except (json.JSONDecodeError, TypeError):
                    sync_json = {"raw_text": raw_text}

            except Exception as e:
                logger.warning(f"LLM 调用失败: {e}")

            return NodeResult(
                outputs={"sync_json": sync_json},
                status=NodeStatus.SUCCESS,
                duration_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            return NodeResult(outputs={"sync_json": {}}, status=NodeStatus.ERROR, duration_ms=int((time.time() - start) * 1000), error=str(e))

    def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        return "content" in inputs


# ─── ext_summary: 摘要生成（多粒度） ───


@NodeRegistry.register("ext_summary")
class SummaryNode(BaseNode):
    """摘要生成 — 检查点/卷/部/幕多粒度"""

    meta = NodeMeta(
        node_type="ext_summary",
        display_name="📋 摘要生成",
        category=NodeCategory.VALIDATION,
        icon="📋",
        color="#164e63",
        input_ports=[
            NodePort(name="content", data_type=PortDataType.TEXT, required=True),
            NodePort(name="summary_type", data_type=PortDataType.TEXT, required=False, default="checkpoint"),
        ],
        output_ports=[
            NodePort(name="summary_text", data_type=PortDataType.TEXT),
        ],
        prompt_template="",
        prompt_variables=["content", "summary_type"],
        is_configurable=True,
        can_disable=True,
        default_timeout_seconds=60,
        cpms_node_key="summary-checkpoint",
        prompt_mode=PromptMode.CPMS_FIRST,
        description="多粒度摘要生成：checkpoint/act/part/volume",
        default_edges=["ctx_memory"],
    )

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        import time
        start = time.time()
        content = inputs.get("content", "")
        summary_type = inputs.get("summary_type", "checkpoint")

        try:
            summary_text = ""

            # 根据 summary_type 选择 CPMS node_key
            cpms_key_map = {
                "checkpoint": "summary-checkpoint",
                "act": "summary-act",
                "part": "summary-part",
                "volume": "summary-volume",
            }
            original_key = self.meta.cpms_node_key
            # 动态覆盖 cpms_node_key
            target_key = cpms_key_map.get(summary_type, "summary-checkpoint")
            self.meta.cpms_node_key = target_key

            try:
                resolved = self.resolve_prompt({"content": content})

                try:
                    from domain.ai.services.llm_service import LLMService
                    from domain.ai.value_objects.prompt import Prompt
                    from domain.ai.services.llm_service import GenerationConfig

                    llm = LLMService()
                    prompt = Prompt(system=resolved["system"], user=resolved["user"])
                    config = GenerationConfig(max_tokens=1500, temperature=0.4)
                    if self._config:
                        if self._config.temperature is not None:
                            config.temperature = self._config.temperature
                        if self._config.max_tokens is not None:
                            config.max_tokens = self._config.max_tokens

                    result = await llm.generate(prompt, config)
                    summary_text = result.text if hasattr(result, 'text') else str(result)

                except Exception as e:
                    logger.warning(f"LLM 调用失败: {e}")
            finally:
                # 恢复原始 key
                self.meta.cpms_node_key = original_key

            return NodeResult(
                outputs={"summary_text": summary_text},
                status=NodeStatus.SUCCESS,
                duration_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            return NodeResult(outputs={"summary_text": ""}, status=NodeStatus.ERROR, duration_ms=int((time.time() - start) * 1000), error=str(e))

    def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        return "content" in inputs
