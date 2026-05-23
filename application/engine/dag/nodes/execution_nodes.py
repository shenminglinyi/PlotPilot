"""Execution 节点 — 执行与生成（4 个节点）

- exec_planning: 规划引擎
- exec_writer: 剧情引擎
- exec_beat: 节拍放大器
- exec_scene: 场景导演
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

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
from infrastructure.ai.prompt_keys import (
    ANTI_AI_ALLOWLIST_EXPLAIN,
    ANTI_AI_BEHAVIOR_PROTOCOL,
    ANTI_AI_CHARACTER_STATE_LOCK,
    AUTOPILOT_STREAM_BEAT as _WORKFLOW_BEAT_NODE_KEY,
    CHAPTER_GENERATION_MAIN as _WORKFLOW_CHAPTER_GEN_NODE_KEY,
    MACRO_PLANNING,
    SCENE_DIRECTOR,
)

from application.workflows.prose_discipline import build_prose_discipline_block

logger = logging.getLogger(__name__)


def _dag_context_builder():
    """尽力获取与 API 相同的 ContextBuilder（节拍放大依赖完整依赖链）。"""
    try:
        from interfaces.api.dependencies import get_context_builder

        return get_context_builder()
    except Exception as e:
        logger.warning("DAG exec_beat: ContextBuilder 不可用: %s", e)
        return None


def _serialize_beats_for_state(beats: List[Any]) -> List[Dict[str, Any]]:
    """Beat 数据类 / dict → 可写入 DAG state / JSON 的 dict 列表。"""
    out: List[Dict[str, Any]] = []
    for b in beats or []:
        if isinstance(b, dict):
            out.append(dict(b))
            continue
        out.append(
            {
                "description": getattr(b, "description", "") or "",
                "target_words": int(getattr(b, "target_words", 0) or 0),
                "focus": getattr(b, "focus", "") or "",
                "expansion_hints": list(getattr(b, "expansion_hints", None) or []),
                "scene_goal": getattr(b, "scene_goal", "") or "",
                "transition_from_prev": getattr(b, "transition_from_prev", "") or "",
                "location_id": getattr(b, "location_id", "") or "",
            }
        )
    return out


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
        prompt_variables=["novel_id", "target_chapters"],
        is_configurable=True,
        can_disable=False,
        default_timeout_seconds=120,
        cpms_node_key=MACRO_PLANNING,
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
        prompt_variables=["context", "outline", "voice_block", "fact_lock", "foreshadowing_block", "behavior_protocol", "character_state_lock", "allowlist_block", "nervous_habits"],
        is_configurable=True,
        can_disable=False,
        default_timeout_seconds=300,
        cpms_node_key=_WORKFLOW_CHAPTER_GEN_NODE_KEY,
        # ★ CPMS 子提示词自动注入（Anti-AI 层）
        cpms_sub_keys=[
            CPMSInjectionPoint(cpms_node_key=ANTI_AI_BEHAVIOR_PROTOCOL, target_variable="behavior_protocol", description="Anti-AI 行为协议 P1-P5+R1-R8"),
            CPMSInjectionPoint(cpms_node_key=ANTI_AI_CHARACTER_STATE_LOCK, target_variable="character_state_lock", description="角色状态锁 L4"),
            CPMSInjectionPoint(cpms_node_key=ANTI_AI_ALLOWLIST_EXPLAIN, target_variable="allowlist_block", description="场景化白名单 L3"),
        ],
        prompt_mode=PromptMode.CPMS_FIRST,
        description="AutoNovelGenerationWorkflow — Anti-AI 协议化章节生成；全托管时由 ChapterConductor（铺陈/收束/着陆）控节拍，超硬上限时按书目偏好 smart_truncate 或字符硬截断",
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
    """节拍放大器 — 优先消费上游 ``plan_outline`` 的 ``chapter_plan_json``，否则现场构建章前执行计划再投影为 beats。"""

    meta = NodeMeta(
        node_type="exec_beat",
        display_name="🥁 节拍放大器",
        category=NodeCategory.EXECUTION,
        icon="🥁",
        color="#14b8a6",
        input_ports=[
            NodePort(name="outline", data_type=PortDataType.TEXT, required=True),
            NodePort(
                name="chapter_plan_json",
                data_type=PortDataType.JSON,
                required=False,
                default=None,
                description="来自 planning_outline_partition（plan_outline）的标准 ChapterExecutionPlan JSON",
            ),
            NodePort(
                name="target_chapter_words",
                data_type=PortDataType.SCORE,
                required=False,
                default=2500,
            ),
            NodePort(
                name="beat_sheet_json",
                data_type=PortDataType.JSON,
                required=False,
                default=None,
                description="可选 BeatSheet JSON；无上游 plan 时传入 build_chapter_execution_plan_async",
            ),
        ],
        output_ports=[
            NodePort(name="beats", data_type=PortDataType.LIST),
        ],
        prompt_variables=["outline"],
        is_configurable=True,
        can_disable=True,
        default_timeout_seconds=60,
        cpms_node_key=_WORKFLOW_BEAT_NODE_KEY,
        description="承接 plan_outline 的 chapter_plan_json → ContextBuilder 投影为 beats；缺失时再调用 build_chapter_execution_plan_async",
        default_edges=["exec_writer"],
    )

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        import time

        start = time.time()

        try:
            beats_out: List[Dict[str, Any]] = []
            outline = str(inputs.get("outline", "") or "")

            chap_raw = context.get("chapter_number") or inputs.get("chapter_number") or 1
            try:
                chap = int(chap_raw)
            except (TypeError, ValueError):
                chap = 1
            tw_raw = inputs.get("target_chapter_words") or context.get("target_chapter_words") or 2500
            try:
                tw = int(tw_raw)
            except (TypeError, ValueError):
                tw = 2500
            nid = context.get("novel_id") if isinstance(context, dict) else None

            sheet = inputs.get("beat_sheet_json")
            beat_sheet_json: Optional[Dict[str, Any]] = None
            if isinstance(sheet, dict):
                beat_sheet_json = sheet if sheet else None
            elif isinstance(sheet, str) and sheet.strip():
                try:
                    import json

                    beat_sheet_json = json.loads(sheet)
                except json.JSONDecodeError:
                    beat_sheet_json = None
                    logger.warning("exec_beat: beat_sheet_json 解析失败，已忽略")

            raw_plan = inputs.get("chapter_plan_json")
            chapter_plan = None
            if isinstance(raw_plan, dict) and raw_plan.get("atoms"):
                try:
                    from application.engine.dag.plan.schema import ChapterExecutionPlan

                    chapter_plan = ChapterExecutionPlan.model_validate(raw_plan)
                except Exception as e:
                    logger.warning("exec_beat: chapter_plan_json 无效，将重新规划: %s", e)

            try:
                from application.engine.dag.plan.outline_beat_planner import (
                    build_chapter_execution_plan_async,
                )

                builder = _dag_context_builder()
                if builder:
                    use_upstream = chapter_plan is not None and bool(chapter_plan.atoms)
                    if not use_upstream:
                        try:
                            chapter_plan = await build_chapter_execution_plan_async(
                                outline,
                                target_chapter_words=tw,
                                novel_id=str(nid) if nid else None,
                                chapter_number=chap,
                                beat_sheet_json=beat_sheet_json,
                                use_llm=True,
                            )
                        except Exception as plan_err:
                            logger.warning("章前执行计划（exec_beat）失败：%s", plan_err)
                            chapter_plan = None

                    use_plan = chapter_plan is not None and bool(chapter_plan.atoms)
                    beats_raw = builder.magnify_outline_to_beats(
                        chap,
                        outline,
                        target_chapter_words=tw,
                        chapter_execution_plan=chapter_plan if use_plan else None,
                        beat_sheet=None,
                    )
                    beats_out = _serialize_beats_for_state(beats_raw)
                elif outline:
                    beats_out = [{"description": outline, "target_words": tw, "focus": "pacing"}]
            except Exception as e:
                logger.warning(f"ContextBuilder.magnify_outline_to_beats 调用失败: {e}")
                if outline:
                    beats_out = [{"description": outline, "target_words": 800, "focus": "pacing"}]

            return NodeResult(
                outputs={"beats": beats_out},
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
        prompt_variables=["outline"],
        is_configurable=True,
        can_disable=True,
        default_timeout_seconds=60,
        cpms_node_key=SCENE_DIRECTOR,
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
