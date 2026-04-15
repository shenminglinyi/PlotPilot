"""SceneDirectorService - 场景导演服务，基于 LLM 的大纲分析"""
from __future__ import annotations

import logging
import os
from typing import Optional

from application.ai.llm_json_extract import parse_llm_json_to_dict
from application.engine.dtos.scene_director_dto import SceneDirectorAnalysis
from domain.ai.services.llm_service import GenerationConfig, LLMService
from domain.ai.value_objects.prompt import Prompt

logger = logging.getLogger(__name__)

SCENE_DIRECTOR_SYSTEM = """你是小说场记。根据给定章节大纲，只输出一个 JSON 对象，键为：
characters, locations, action_types, trigger_keywords, emotional_state, pov, performance_notes。
characters/locations/action_types/trigger_keywords/performance_notes 均为字符串数组；emotional_state 为简短英文或中文单词；pov 为视点人物名字符串或 null。
performance_notes 是可选的表演指令列表，描述动作级别的导演指示（如"眼神闪烁"、"握紧拳头"）。
注意：不要在表演指令中透露角色的隐藏身份或设定，只描述可观察的动作和情绪。
不要 markdown，不要解释。"""


class SceneDirectorService:
    """场景导演服务 - 使用 LLM 分析章节大纲"""

    # LLM generation configuration constants
    _DEFAULT_MAX_TOKENS = 1024
    _DEFAULT_TEMPERATURE = 0.2

    def __init__(self, llm_service: LLMService, *, model: str = ""):
        self._llm = llm_service
        self._model = model or os.getenv("SYSTEM_MODEL", "")

    async def analyze(self, chapter_number: int, outline: str) -> SceneDirectorAnalysis:
        """分析章节大纲，提取场景信息

        Args:
            chapter_number: 章节号
            outline: 章节大纲文本

        Returns:
            SceneDirectorAnalysis: 分析结果
        """
        user = f"章节号: {chapter_number}\n大纲:\n{outline.strip()}"
        prompt = Prompt(system=SCENE_DIRECTOR_SYSTEM, user=user)
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

        return SceneDirectorAnalysis(
            characters=as_str_list("characters"),
            locations=as_str_list("locations"),
            action_types=as_str_list("action_types"),
            trigger_keywords=as_str_list("trigger_keywords"),
            emotional_state=emotional_state,
            pov=pov,
            performance_notes=as_optional_str_list("performance_notes"),
        )
