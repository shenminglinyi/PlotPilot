"""Anti-AI 节点 — Anti-AI 防御体系（6 个节点）

七层纵深防御体系：
- anti_ai_behavior: 行为协议 (L1+L2)
- anti_ai_allowlist: 场景化白名单 (L3)
- anti_ai_char_lock: 角色状态锁 (L4)
- anti_ai_mid_refresh: 生成中刷新 (L5+L6)
- anti_ai_audit: 章后审计 (L7)
- anti_ai_finale: 终章增强

CPMS 联动：核心模式 — prompt_mode=INJECT
  这些节点从广场拉取提示词片段，返回文本给下游生成节点注入到变量槽。
  生成节点（如 exec_writer）通过 meta.cpms_sub_keys 声明需要注入的子提示词。
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


# ─── anti_ai_behavior: 行为协议 (L1+L2) ───


@NodeRegistry.register("anti_ai_behavior")
class BehaviorProtocolNode(BaseNode):
    """Anti-AI 行为协议 — 协议化指令集替代禁令清单"""

    meta = NodeMeta(
        node_type="anti_ai_behavior",
        display_name="📋 行为协议",
        category=NodeCategory.ANTI_AI,
        icon="📋",
        color="#dc2626",
        input_ports=[
            NodePort(name="nervous_habits", data_type=PortDataType.TEXT, required=False),
            NodePort(name="allowlist_block", data_type=PortDataType.TEXT, required=False),
        ],
        output_ports=[
            NodePort(name="behavior_protocol", data_type=PortDataType.TEXT),
        ],
        prompt_template="",
        prompt_variables=["nervous_habits", "allowlist_block"],
        is_configurable=True,
        can_disable=True,
        default_timeout_seconds=10,
        cpms_node_key="anti-ai-behavior-protocol",
        prompt_mode=PromptMode.INJECT,
        description="L1+L2 核心协议：协议化指令(P1-P5)替代禁令清单，替换策略(R1-R8)",
        default_edges=["exec_writer"],
    )

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        import time
        start = time.time()

        try:
            # INJECT 模式：从 CPMS 拉取提示词片段
            resolved = self.get_effective_prompt()
            behavior_protocol = resolved.get("system", "") or resolved.get("user_template", "")

            # 如果有变量，渲染它们
            if behavior_protocol:
                variables = {
                    "nervous_habits": inputs.get("nervous_habits", ""),
                    "allowlist_block": inputs.get("allowlist_block", ""),
                }
                for key, value in variables.items():
                    behavior_protocol = behavior_protocol.replace(f"{{{{{key}}}}}", str(value))

            return NodeResult(
                outputs={"behavior_protocol": behavior_protocol},
                status=NodeStatus.SUCCESS,
                duration_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            return NodeResult(outputs={"behavior_protocol": ""}, status=NodeStatus.ERROR, duration_ms=int((time.time() - start) * 1000), error=str(e))

    def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        return True


# ─── anti_ai_allowlist: 场景化白名单 (L3) ───


@NodeRegistry.register("anti_ai_allowlist")
class AllowlistNode(BaseNode):
    """Anti-AI 场景化白名单 — 特定场景豁免"""

    meta = NodeMeta(
        node_type="anti_ai_allowlist",
        display_name="🧾 白名单解释器",
        category=NodeCategory.ANTI_AI,
        icon="🧾",
        color="#e11d48",
        input_ports=[
            NodePort(name="scene_type", data_type=PortDataType.TEXT, required=True),
            NodePort(name="allowed_patterns", data_type=PortDataType.TEXT, required=False),
            NodePort(name="forbidden_patterns", data_type=PortDataType.TEXT, required=False),
        ],
        output_ports=[
            NodePort(name="allowlist_block", data_type=PortDataType.TEXT),
        ],
        prompt_template="",
        prompt_variables=["scene_type", "allowed_patterns", "forbidden_patterns"],
        is_configurable=True,
        can_disable=True,
        default_timeout_seconds=10,
        cpms_node_key="anti-ai-allowlist-explain",
        prompt_mode=PromptMode.INJECT,
        description="L3 场景化豁免：战斗/悬疑/恐怖/告白场景部分AI味模式允许",
        default_edges=["anti_ai_behavior"],
    )

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        import time
        start = time.time()

        try:
            resolved = self.get_effective_prompt()
            allowlist_block = resolved.get("user_template", "") or resolved.get("system", "")

            if allowlist_block:
                variables = {
                    "scene_type": inputs.get("scene_type", "default"),
                    "allowed_patterns": inputs.get("allowed_patterns", ""),
                    "forbidden_patterns": inputs.get("forbidden_patterns", ""),
                }
                for key, value in variables.items():
                    allowlist_block = allowlist_block.replace(f"{{{{{key}}}}}", str(value))

            return NodeResult(
                outputs={"allowlist_block": allowlist_block},
                status=NodeStatus.SUCCESS,
                duration_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            return NodeResult(outputs={"allowlist_block": ""}, status=NodeStatus.ERROR, duration_ms=int((time.time() - start) * 1000), error=str(e))

    def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        return True


# ─── anti_ai_char_lock: 角色状态锁 (L4) ───


@NodeRegistry.register("anti_ai_char_lock")
class CharacterStateLockNode(BaseNode):
    """Anti-AI 角色状态锁 — 强制注入角色锚点"""

    meta = NodeMeta(
        node_type="anti_ai_char_lock",
        display_name="🔒 角色状态锁",
        category=NodeCategory.ANTI_AI,
        icon="🔒",
        color="#be123c",
        input_ports=[
            NodePort(name="character_name", data_type=PortDataType.TEXT, required=True),
            NodePort(name="physical_state", data_type=PortDataType.TEXT, required=False),
            NodePort(name="emotional_baseline", data_type=PortDataType.TEXT, required=False),
            NodePort(name="nervous_habit", data_type=PortDataType.TEXT, required=False),
            NodePort(name="voice_print", data_type=PortDataType.TEXT, required=False),
        ],
        output_ports=[
            NodePort(name="character_state_lock", data_type=PortDataType.TEXT),
        ],
        prompt_template="",
        prompt_variables=["character_name", "physical_state", "emotional_baseline", "nervous_habit", "voice_print"],
        is_configurable=True,
        can_disable=True,
        default_timeout_seconds=10,
        cpms_node_key="anti-ai-character-state-lock",
        prompt_mode=PromptMode.INJECT,
        description="L4 角色状态向量：声线指纹+紧张习惯+反应模式三维度锁定",
        default_edges=["anti_ai_behavior"],
    )

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        import time
        start = time.time()

        try:
            resolved = self.get_effective_prompt()
            char_lock = resolved.get("user_template", "") or resolved.get("system", "")

            if char_lock:
                for key in ["character_name", "physical_state", "emotional_baseline",
                            "nervous_habit", "voice_print", "reaction_pattern",
                            "known_information", "unknown_information",
                            "voice_rule", "physical_inertia_rule"]:
                    val = inputs.get(key, context.get(key, ""))
                    char_lock = char_lock.replace(f"{{{{{key}}}}}", str(val))

            return NodeResult(
                outputs={"character_state_lock": char_lock},
                status=NodeStatus.SUCCESS,
                duration_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            return NodeResult(outputs={"character_state_lock": ""}, status=NodeStatus.ERROR, duration_ms=int((time.time() - start) * 1000), error=str(e))

    def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        return True


# ─── anti_ai_mid_refresh: 生成中刷新 (L5+L6) ───


@NodeRegistry.register("anti_ai_mid_refresh")
class MidGenerationRefreshNode(BaseNode):
    """Anti-AI 生成中刷新 — L5+L6 Token级拦截"""

    meta = NodeMeta(
        node_type="anti_ai_mid_refresh",
        display_name="🔄 生成中刷新",
        category=NodeCategory.ANTI_AI,
        icon="🔄",
        color="#9f1239",
        input_ports=[
            NodePort(name="content_so_far", data_type=PortDataType.TEXT, required=True),
            NodePort(name="refresh_instructions", data_type=PortDataType.TEXT, required=False),
        ],
        output_ports=[
            NodePort(name="refresh_block", data_type=PortDataType.TEXT),
        ],
        prompt_template="",
        prompt_variables=["content_so_far", "refresh_instructions"],
        is_configurable=True,
        can_disable=True,
        default_timeout_seconds=10,
        cpms_node_key="anti-ai-mid-generation-refresh",
        prompt_mode=PromptMode.INJECT,
        description="L5+L6 上下文配额+Token级拦截刷新指令",
        default_edges=["exec_writer"],
    )

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        import time
        start = time.time()

        try:
            resolved = self.get_effective_prompt()
            refresh_block = resolved.get("system", "") or resolved.get("user_template", "")

            if refresh_block:
                for key, value in inputs.items():
                    refresh_block = refresh_block.replace(f"{{{{{key}}}}}", str(value))

            return NodeResult(
                outputs={"refresh_block": refresh_block},
                status=NodeStatus.SUCCESS,
                duration_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            return NodeResult(outputs={"refresh_block": ""}, status=NodeStatus.ERROR, duration_ms=int((time.time() - start) * 1000), error=str(e))

    def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        return True


# ─── anti_ai_audit: 章后审计 (L7) ───


@NodeRegistry.register("anti_ai_audit")
class ChapterAuditNode(BaseNode):
    """Anti-AI 章后审计 — 35+增强模式扫描"""

    meta = NodeMeta(
        node_type="anti_ai_audit",
        display_name="🔍 章后审计",
        category=NodeCategory.ANTI_AI,
        icon="🔍",
        color="#881337",
        input_ports=[
            NodePort(name="content", data_type=PortDataType.TEXT, required=True),
        ],
        output_ports=[
            NodePort(name="total_hits", data_type=PortDataType.SCORE),
            NodePort(name="severity_score", data_type=PortDataType.SCORE),
            NodePort(name="hits", data_type=PortDataType.LIST),
            NodePort(name="overall_assessment", data_type=PortDataType.TEXT),
        ],
        prompt_template="",
        prompt_variables=["content"],
        is_configurable=True,
        can_disable=True,
        default_timeout_seconds=60,
        cpms_node_key="anti-ai-chapter-audit",
        prompt_mode=PromptMode.CPMS_FIRST,
        description="L7 章后审计：35+增强模式扫描，涵盖8大类AI味检测",
        default_edges=["review_improvement"],
    )

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        import time
        start = time.time()
        content = inputs.get("content", "")

        try:
            total_hits = 0
            severity_score = 0.0
            hits = []
            overall_assessment = "未检测"

            resolved = self.resolve_prompt({"content": content})

            try:
                from domain.ai.services.llm_service import LLMService
                from domain.ai.value_objects.prompt import Prompt
                from domain.ai.services.llm_service import GenerationConfig

                llm = LLMService()
                prompt = Prompt(system=resolved["system"], user=resolved["user"])
                config = GenerationConfig(max_tokens=2000, temperature=0.2)
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
                    total_hits = parsed.get("total_hits", 0)
                    severity_score = float(parsed.get("severity_score", 0))
                    hits = parsed.get("hits", [])
                    overall_assessment = parsed.get("overall_assessment", "未检测")
                except (json.JSONDecodeError, TypeError):
                    overall_assessment = raw_text[:200]

            except Exception as e:
                logger.warning(f"LLM 调用失败: {e}")

            return NodeResult(
                outputs={
                    "total_hits": total_hits,
                    "severity_score": severity_score,
                    "hits": hits,
                    "overall_assessment": overall_assessment,
                },
                status=NodeStatus.WARNING if severity_score > 50 else NodeStatus.SUCCESS,
                metrics={"severity_score": severity_score},
                duration_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            return NodeResult(outputs={"total_hits": 0, "severity_score": 0, "hits": [], "overall_assessment": ""}, status=NodeStatus.ERROR, duration_ms=int((time.time() - start) * 1000), error=str(e))

    def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        return "content" in inputs


# ─── anti_ai_finale: 终章增强 ───


@NodeRegistry.register("anti_ai_finale")
class FinaleEnhancementNode(BaseNode):
    """Anti-AI 终章增强 — 结尾反AI味专项"""

    meta = NodeMeta(
        node_type="anti_ai_finale",
        display_name="🎬 终章增强",
        category=NodeCategory.ANTI_AI,
        icon="🎬",
        color="#4c0519",
        input_ports=[
            NodePort(name="content", data_type=PortDataType.TEXT, required=True),
            NodePort(name="is_final_chapter", data_type=PortDataType.BOOLEAN, required=False, default=False),
        ],
        output_ports=[
            NodePort(name="finale_block", data_type=PortDataType.TEXT),
        ],
        prompt_template="",
        prompt_variables=["content", "is_final_chapter"],
        is_configurable=True,
        can_disable=True,
        default_timeout_seconds=10,
        cpms_node_key="anti-ai-finale-enhancement",
        prompt_mode=PromptMode.INJECT,
        description="终章/尾声段落的 Anti-AI 增强注入",
        default_edges=["exec_writer"],
    )

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        import time
        start = time.time()

        try:
            is_final = inputs.get("is_final_chapter", False)
            if not is_final:
                return NodeResult(
                    outputs={"finale_block": ""},
                    status=NodeStatus.SUCCESS,
                    duration_ms=int((time.time() - start) * 1000),
                )

            resolved = self.get_effective_prompt()
            finale_block = resolved.get("system", "") or resolved.get("user_template", "")

            if finale_block:
                for key, value in inputs.items():
                    finale_block = finale_block.replace(f"{{{{{key}}}}}", str(value))

            return NodeResult(
                outputs={"finale_block": finale_block},
                status=NodeStatus.SUCCESS,
                duration_ms=int((time.time() - start) * 1000),
            )
        except Exception as e:
            return NodeResult(outputs={"finale_block": ""}, status=NodeStatus.ERROR, duration_ms=int((time.time() - start) * 1000), error=str(e))

    def validate_inputs(self, inputs: Dict[str, Any]) -> bool:
        return True
