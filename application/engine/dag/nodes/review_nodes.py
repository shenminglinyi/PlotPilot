"""Review 节点 — 审稿质检（5 个节点）

- review_character: 人物一致性检查（OOC+AI味双检）
- review_timeline: 时间线一致性检查
- review_storyline: 故事线连贯性检查
- review_foreshadowing: 伏笔使用检查
- review_improvement: 改进建议生成

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


# ─── review_character: 人物一致性检查 ───


@NodeRegistry.register("review_character")
class CharacterReviewNode(BaseNode):
    """人物一致性检查 v2 — OOC + AI味双检"""

    meta = NodeMeta(
        node_type="review_character",
        display_name="👤 人物OOC检测",
        category=NodeCategory.REVIEW,
        icon="👤",
        color="#b45309",
        input_ports=[
            NodePort(name="character_name", data_type=PortDataType.TEXT, required=True),
            NodePort(name="character_profile", data_type=PortDataType.JSON, required=True),
            NodePort(name="chapter_content", data_type=PortDataType.TEXT, required=True),
        ],
        output_ports=[
            NodePort(name="inconsistencies", data_type=PortDataType.LIST),
            NodePort(name="ooc_score", data_type=PortDataType.SCORE),
        ],
        prompt_template="你是最苛刻的审稿人...",
        prompt_variables=["character_name", "character_profile", "chapter_content"],
        is_configurable=True,
        can_disable=True,
        default_timeout_seconds=60,
        cpms_node_key="review-character-consistency",
        prompt_mode=PromptMode.CPMS_FIRST,
        description="OOC检测 + AI味检测双刀审稿",
        default_edges=["review_storyline"],
    )

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        import time
        start = time.time()

        try:
            inconsistencies = []
            ooc_score = 100.0

            resolved = self.resolve_prompt({
                "character_name": inputs.get("character_name", ""),
                "character_profile": str(inputs.get("character_profile", "")),
                "chapter_content": inputs.get("chapter_content", ""),
            })

            try:
                from domain.ai.services.llm_service import LLMService
                from domain.ai.value_objects.prompt import Prompt
                from domain.ai.services.llm_service import GenerationConfig

                llm = LLMService()
                prompt = Prompt(system=resolved["system"], user=resolved["user"])
                config = GenerationConfig(max_tokens=2000, temperature=0.3)
                if self._config:
                    if self._config.temperature is not None:
                        config.temperature = self._config.temperature
                    if self._config.max_tokens is not None:
                        config.max_tokens = self._config.max_tokens

                result = await llm.generate(prompt, config)
                raw_text = result.text if hasattr(result, 'text') else str(result)

                import json
                try:
                    parsed = json.loads(raw_text)
                    inconsistencies = parsed.get("inconsistencies", [])
                    # OOC 分数：无问题100，每条 critical -20，warning -10
                    for item in inconsistencies:
                        severity = item.get("severity", "warning")
                        if severity == "critical":
                            ooc_score -= 20
                        elif severity == "warning":
                            ooc_score -= 10
                        else:
                            ooc_score -= 5
                    ooc_score = max(0, ooc_score)
                except (json.JSONDecodeError, TypeError):
                    inconsistencies = [{"raw_text": raw_text}]

            except Exception as e:
                logger.warning(f"LLM 调用失败: {e}")

            return NodeResult(
                outputs={"inconsistencies": inconsistencies, "ooc_score": ooc_score},
                status=NodeStatus.WARNING if ooc_score < 70 else NodeStatus.SUCCESS,
                metrics={"ooc_score": ooc_score},
                duration_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            return NodeResult(outputs={"inconsistencies": [], "ooc_score": 0}, status=NodeStatus.ERROR, duration_ms=int((time.time() - start) * 1000), error=str(e))

    def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        return "chapter_content" in inputs


# ─── review_timeline: 时间线一致性检查 ───


@NodeRegistry.register("review_timeline")
class TimelineReviewNode(BaseNode):
    """时间线一致性检查 — 物理空间与时间的硬伤"""

    meta = NodeMeta(
        node_type="review_timeline",
        display_name="⏰ 时间线检查",
        category=NodeCategory.REVIEW,
        icon="⏰",
        color="#92400e",
        input_ports=[
            NodePort(name="current_events", data_type=PortDataType.TEXT, required=True),
            NodePort(name="previous_events", data_type=PortDataType.TEXT, required=False),
            NodePort(name="chapter_content", data_type=PortDataType.TEXT, required=True),
        ],
        output_ports=[
            NodePort(name="conflicts", data_type=PortDataType.LIST),
            NodePort(name="timeline_score", data_type=PortDataType.SCORE),
        ],
        prompt_template="你是小说的逻辑质检员...",
        prompt_variables=["current_events", "previous_events", "chapter_content"],
        is_configurable=True,
        can_disable=True,
        default_timeout_seconds=60,
        cpms_node_key="review-timeline-consistency",
        prompt_mode=PromptMode.CPMS_FIRST,
        description="时间穿帮纠错，审查物理空间与时间的硬伤",
        default_edges=["review_foreshadowing"],
    )

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        import time
        start = time.time()

        try:
            conflicts = []
            timeline_score = 100.0

            resolved = self.resolve_prompt({
                "current_events": inputs.get("current_events", ""),
                "previous_events": inputs.get("previous_events", ""),
                "chapter_content": inputs.get("chapter_content", ""),
            })

            try:
                from domain.ai.services.llm_service import LLMService
                from domain.ai.value_objects.prompt import Prompt
                from domain.ai.services.llm_service import GenerationConfig

                llm = LLMService()
                prompt = Prompt(system=resolved["system"], user=resolved["user"])
                config = GenerationConfig(max_tokens=1500, temperature=0.3)
                if self._config:
                    if self._config.temperature is not None:
                        config.temperature = self._config.temperature
                    if self._config.max_tokens is not None:
                        config.max_tokens = self._config.max_tokens

                result = await llm.generate(prompt, config)
                raw_text = result.text if hasattr(result, 'text') else str(result)

                import json
                try:
                    parsed = json.loads(raw_text)
                    conflicts = parsed.get("conflicts", [])
                    for c in conflicts:
                        severity = c.get("severity", "warning")
                        timeline_score -= 25 if severity == "critical" else 10
                    timeline_score = max(0, timeline_score)
                except (json.JSONDecodeError, TypeError):
                    conflicts = [{"raw_text": raw_text}]

            except Exception as e:
                logger.warning(f"LLM 调用失败: {e}")

            return NodeResult(
                outputs={"conflicts": conflicts, "timeline_score": timeline_score},
                status=NodeStatus.WARNING if timeline_score < 70 else NodeStatus.SUCCESS,
                metrics={"timeline_score": timeline_score},
                duration_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            return NodeResult(outputs={"conflicts": [], "timeline_score": 0}, status=NodeStatus.ERROR, duration_ms=int((time.time() - start) * 1000), error=str(e))

    def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        return "chapter_content" in inputs


# ─── review_storyline: 故事线连贯性检查 ───


@NodeRegistry.register("review_storyline")
class StorylineReviewNode(BaseNode):
    """故事线连贯性检查 — 维持多线叙事的紧凑感"""

    meta = NodeMeta(
        node_type="review_storyline",
        display_name="📖 故事线检查",
        category=NodeCategory.REVIEW,
        icon="📖",
        color="#78350f",
        input_ports=[
            NodePort(name="active_storylines", data_type=PortDataType.TEXT, required=True),
            NodePort(name="chapter_content", data_type=PortDataType.TEXT, required=True),
        ],
        output_ports=[
            NodePort(name="gaps", data_type=PortDataType.LIST),
            NodePort(name="storyline_progress", data_type=PortDataType.SCORE),
        ],
        prompt_template="你是长篇架构审核员...",
        prompt_variables=["active_storylines", "chapter_content"],
        is_configurable=True,
        can_disable=True,
        default_timeout_seconds=60,
        cpms_node_key="review-storyline-consistency",
        prompt_mode=PromptMode.CPMS_FIRST,
        description="避免挖坑不填和主线偏移，维持多线叙事的紧凑感",
        default_edges=["review_character"],
    )

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        import time
        start = time.time()

        try:
            gaps = []
            storyline_progress = 80.0

            resolved = self.resolve_prompt({
                "active_storylines": inputs.get("active_storylines", ""),
                "chapter_content": inputs.get("chapter_content", ""),
            })

            try:
                from domain.ai.services.llm_service import LLMService
                from domain.ai.value_objects.prompt import Prompt
                from domain.ai.services.llm_service import GenerationConfig

                llm = LLMService()
                prompt = Prompt(system=resolved["system"], user=resolved["user"])
                config = GenerationConfig(max_tokens=1500, temperature=0.3)
                if self._config:
                    if self._config.temperature is not None:
                        config.temperature = self._config.temperature
                    if self._config.max_tokens is not None:
                        config.max_tokens = self._config.max_tokens

                result = await llm.generate(prompt, config)
                raw_text = result.text if hasattr(result, 'text') else str(result)

                import json
                try:
                    parsed = json.loads(raw_text)
                    gaps = parsed.get("gaps", [])
                    for g in gaps:
                        severity = g.get("severity", "warning")
                        storyline_progress -= 15 if severity == "warning" else 10
                    storyline_progress = max(0, storyline_progress)
                except (json.JSONDecodeError, TypeError):
                    gaps = [{"raw_text": raw_text}]

            except Exception as e:
                logger.warning(f"LLM 调用失败: {e}")

            return NodeResult(
                outputs={"gaps": gaps, "storyline_progress": storyline_progress},
                status=NodeStatus.SUCCESS,
                metrics={"storyline_progress": storyline_progress},
                duration_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            return NodeResult(outputs={"gaps": [], "storyline_progress": 0}, status=NodeStatus.ERROR, duration_ms=int((time.time() - start) * 1000), error=str(e))

    def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        return "chapter_content" in inputs


# ─── review_foreshadowing: 伏笔使用检查 ───


@NodeRegistry.register("review_foreshadowing")
class ForeshadowingReviewNode(BaseNode):
    """伏笔使用检查 — 契诃夫的枪"""

    meta = NodeMeta(
        node_type="review_foreshadowing",
        display_name="🎯 伏笔使用检查",
        category=NodeCategory.REVIEW,
        icon="🎯",
        color="#a16207",
        input_ports=[
            NodePort(name="foreshadowings", data_type=PortDataType.TEXT, required=True),
            NodePort(name="chapter_content", data_type=PortDataType.TEXT, required=True),
        ],
        output_ports=[
            NodePort(name="missed_opportunities", data_type=PortDataType.LIST),
        ],
        prompt_template="你是伏笔追踪大师...",
        prompt_variables=["foreshadowings", "chapter_content"],
        is_configurable=True,
        can_disable=True,
        default_timeout_seconds=60,
        cpms_node_key="review-foreshadowing-usage",
        prompt_mode=PromptMode.CPMS_FIRST,
        description="检查并促成'契诃夫的枪'在最佳时机开火",
        default_edges=["review_improvement"],
    )

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        import time
        start = time.time()

        try:
            missed_opportunities = []

            resolved = self.resolve_prompt({
                "foreshadowings": inputs.get("foreshadowings", ""),
                "chapter_content": inputs.get("chapter_content", ""),
            })

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
                raw_text = result.text if hasattr(result, 'text') else str(result)

                import json
                try:
                    parsed = json.loads(raw_text)
                    missed_opportunities = parsed.get("missed_opportunities", [])
                except (json.JSONDecodeError, TypeError):
                    missed_opportunities = [{"raw_text": raw_text}]

            except Exception as e:
                logger.warning(f"LLM 调用失败: {e}")

            return NodeResult(
                outputs={"missed_opportunities": missed_opportunities},
                status=NodeStatus.SUCCESS,
                duration_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            return NodeResult(outputs={"missed_opportunities": []}, status=NodeStatus.ERROR, duration_ms=int((time.time() - start) * 1000), error=str(e))

    def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        return "chapter_content" in inputs


# ─── review_improvement: 改进建议生成 ───


@NodeRegistry.register("review_improvement")
class ImprovementReviewNode(BaseNode):
    """改进建议生成 — 基于审稿报告给出可操作建议"""

    meta = NodeMeta(
        node_type="review_improvement",
        display_name="💡 改进建议",
        category=NodeCategory.REVIEW,
        icon="💡",
        color="#ca8a04",
        input_ports=[
            NodePort(name="chapter_content", data_type=PortDataType.TEXT, required=True),
            NodePort(name="review_reports", data_type=PortDataType.JSON, required=False),
        ],
        output_ports=[
            NodePort(name="suggestions", data_type=PortDataType.LIST),
            NodePort(name="priority", data_type=PortDataType.TEXT),
        ],
        prompt_template="你是经验丰富的写作教练...",
        prompt_variables=["chapter_content", "review_reports"],
        is_configurable=True,
        can_disable=True,
        default_timeout_seconds=60,
        cpms_node_key="review-improvement-suggestions",
        prompt_mode=PromptMode.CPMS_FIRST,
        description="基于审稿报告给出可操作的改进建议",
        default_edges=["gw_review"],
    )

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        import time
        start = time.time()

        try:
            suggestions = []
            priority = "normal"

            resolved = self.resolve_prompt({
                "chapter_content": inputs.get("chapter_content", ""),
                "review_reports": str(inputs.get("review_reports", "")),
            })

            try:
                from domain.ai.services.llm_service import LLMService
                from domain.ai.value_objects.prompt import Prompt
                from domain.ai.services.llm_service import GenerationConfig

                llm = LLMService()
                prompt = Prompt(system=resolved["system"], user=resolved["user"])
                config = GenerationConfig(max_tokens=2000, temperature=0.5)
                if self._config:
                    if self._config.temperature is not None:
                        config.temperature = self._config.temperature
                    if self._config.max_tokens is not None:
                        config.max_tokens = self._config.max_tokens

                result = await llm.generate(prompt, config)
                raw_text = result.text if hasattr(result, 'text') else str(result)

                import json
                try:
                    parsed = json.loads(raw_text)
                    suggestions = parsed.get("suggestions", [])
                    priority = parsed.get("priority", "normal")
                except (json.JSONDecodeError, TypeError):
                    suggestions = [{"raw_text": raw_text}]

            except Exception as e:
                logger.warning(f"LLM 调用失败: {e}")

            return NodeResult(
                outputs={"suggestions": suggestions, "priority": priority},
                status=NodeStatus.SUCCESS,
                duration_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            return NodeResult(outputs={"suggestions": [], "priority": "normal"}, status=NodeStatus.ERROR, duration_ms=int((time.time() - start) * 1000), error=str(e))

    def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        return "chapter_content" in inputs
