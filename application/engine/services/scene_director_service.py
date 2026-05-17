"""SceneDirectorService - 场景导演服务，基于 LLM 的大纲分析"""
from __future__ import annotations

import logging
import os
from typing import Optional

from application.ai.llm_json_extract import parse_llm_json_to_dict
from application.engine.dtos.scene_director_dto import ActionTransitionGraphPayload, SceneDirectorAnalysis
from domain.ai.services.llm_service import GenerationConfig, LLMService
from domain.ai.value_objects.prompt import Prompt

logger = logging.getLogger(__name__)

# CPMS: 提示词节点 key（统一从 prompt_keys 导入）
from infrastructure.ai.prompt_keys import SCENE_DIRECTOR as _SCENE_DIRECTOR_NODE_KEY

# 硬编码回退（仅在 PromptRegistry 不可用时使用）
_FALLBACK_SCENE_DIRECTOR_SYSTEM = """[Task]
你是小说场记规则引擎。根据章节大纲只输出一个 JSON 对象（不要 markdown，不要解释）。

[Root keys]
characters, locations, action_types, trigger_keywords, emotional_state, pov, performance_notes, atg

[Flat fields]
- characters/locations/action_types/trigger_keywords/performance_notes: 字符串数组
- emotional_state: 简短词
- pov: 视点人物字符串或 null
- performance_notes: 可选，仅可观察的动作/情绪指令列表

[atg — Action Transition Graph]
"atg": {
  "nodes": [{"location_id":"精确微观坐标_禁止仅用室内或室外","initial_props":[],"is_entry_point":false}],
  "transitions": [{"source_location":"","target_location":"","required_action":"","trigger_characters":[]}],
  "visit_sequence": ["按叙事顺序列出 location_id"]
}

[ATG Rules]
1. location_id 必须具体（如 金蔷薇府邸_地下室外走廊），禁止仅用「室内」「室外」作为唯一坐标。
2. 角色从地点 A 至 B 必须在 transitions 中给出 required_action（可观察的动作短语），并填写 trigger_characters。
3. visit_sequence 顺序必须与大纲叙事游走一致；nodes 须覆盖 visit_sequence 中全部坐标。
4. performance_notes 不得泄露隐藏设定。"""


class SceneDirectorService:
    """场景导演服务 - 使用 LLM 分析章节大纲"""

    # LLM generation configuration constants（含 ATG 时需更长 JSON）
    _DEFAULT_MAX_TOKENS = 4096
    _DEFAULT_TEMPERATURE = 0.2

    def __init__(self, llm_service: LLMService, *, model: str = ""):
        self._llm = llm_service
        self._model = model or os.getenv("SYSTEM_MODEL", "")

    def _get_system_prompt(self) -> str:
        """获取场景导演的 system prompt。

        CPMS: 优先从 PromptRegistry 获取（广场可编辑），
        如果 Registry 不可用则回退到硬编码默认值。
        """
        try:
            from infrastructure.ai.prompt_registry import get_prompt_registry
            registry = get_prompt_registry()
            system = registry.get_system(_SCENE_DIRECTOR_NODE_KEY)
            if system:
                return system
        except Exception as exc:
            logger.debug("PromptRegistry 不可用，使用回退提示词: %s", exc)

        return _FALLBACK_SCENE_DIRECTOR_SYSTEM

    async def analyze(self, chapter_number: int, outline: str) -> SceneDirectorAnalysis:
        """分析章节大纲，提取场景信息

        Args:
            chapter_number: 章节号
            outline: 章节大纲文本

        Returns:
            SceneDirectorAnalysis: 分析结果
        """
        user = f"章节号: {chapter_number}\n大纲:\n{outline.strip()}"
        prompt = Prompt(system=self._get_system_prompt(), user=user)
        config = GenerationConfig(
            model=self._model,
            max_tokens=self._DEFAULT_MAX_TOKENS,
            temperature=self._DEFAULT_TEMPERATURE,
        )
        raw = await self._llm.generate(prompt, config)
        data, errs = parse_llm_json_to_dict(raw.content)
        if not data:
            logger.warning("scene director JSON parse failed: %s", errs)
            return SceneDirectorAnalysis()
        return self._coerce(data)

    def _coerce(self, data: dict) -> SceneDirectorAnalysis:
        """将 LLM 返回的字典强制转换为 SceneDirectorAnalysis

        Coerces LLM-returned data into a valid SceneDirectorAnalysis object.
        Handles missing fields, non-list values, and null values gracefully.

        Design Note on Error Propagation:
        When JSON parsing fails in analyze(), we return an empty SceneDirectorAnalysis
        rather than raising an exception. This design choice allows callers to:
        - Treat "no entities extracted" and "parsing failed" uniformly
        - Continue processing without exception handling
        - Log warnings for debugging without disrupting the workflow
        The tradeoff is that callers cannot distinguish between these two cases,
        but this is acceptable for this use case where partial analysis is valid.

        Args:
            data: LLM-returned dictionary. Must be a dict type.

        Returns:
            SceneDirectorAnalysis: Coerced analysis result with all fields populated.

        Raises:
            TypeError: If data is not a dict.
        """
        if not isinstance(data, dict):
            raise TypeError(f"Expected dict, got {type(data).__name__}")

        def as_str_list(key: str) -> list:
            """Convert field to list of strings, handling None and non-list values."""
            v = data.get(key)
            if v is None:
                return []
            if isinstance(v, list):
                return [str(x) for x in v if x is not None]
            return [str(v)]

        def as_optional_str_list(key: str) -> Optional[list]:
            """Convert field to optional list of strings, preserving None for missing fields."""
            v = data.get(key)
            if v is None:
                return None
            if isinstance(v, list):
                return [str(x) for x in v if x is not None]
            return [str(v)]

        pov = data.get("pov")
        if pov is not None:
            pov = str(pov).strip() or None

        emotional_state = data.get("emotional_state")
        if emotional_state is None:
            emotional_state = ""
        else:
            emotional_state = str(emotional_state).strip()

        atg_payload: Optional[ActionTransitionGraphPayload] = None
        raw_atg = data.get("atg")
        if not isinstance(raw_atg, dict):
            raw_atg = data.get("action_transition_graph")
        if isinstance(raw_atg, dict):
            try:
                atg_payload = ActionTransitionGraphPayload.model_validate(raw_atg)
            except Exception as exc:
                logger.warning("scene director ATG validation failed: %s", exc)

        return SceneDirectorAnalysis(
            characters=as_str_list("characters"),
            locations=as_str_list("locations"),
            action_types=as_str_list("action_types"),
            trigger_keywords=as_str_list("trigger_keywords"),
            emotional_state=emotional_state,
            pov=pov,
            performance_notes=as_optional_str_list("performance_notes"),
            action_transition_graph=atg_payload,
        )
