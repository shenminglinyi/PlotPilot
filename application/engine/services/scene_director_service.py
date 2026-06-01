"""SceneDirectorService - CPMS-backed scene director analysis."""
from __future__ import annotations

import logging
import os
from typing import Optional

from application.ai.llm_json_extract import parse_llm_json_to_dict
from application.engine.dtos.scene_director_dto import ActionTransitionGraphPayload, SceneDirectorAnalysis
from domain.ai.services.llm_service import GenerationConfig, LLMService
from infrastructure.ai.prompt_keys import SCENE_DIRECTOR as _SCENE_DIRECTOR_NODE_KEY
from infrastructure.ai.prompt_utils import render_required_prompt

logger = logging.getLogger(__name__)


class SceneDirectorService:
    """Scene director service backed by CPMS prompt templates."""

    _DEFAULT_MAX_TOKENS = 4096
    _DEFAULT_TEMPERATURE = 0.2

    def __init__(self, llm_service: LLMService, *, model: str = ""):
        self._llm = llm_service
        self._model = model or os.getenv("SYSTEM_MODEL", "")

    async def analyze(self, chapter_number: int, outline: str) -> SceneDirectorAnalysis:
        """Analyze a chapter outline and extract scene-director metadata."""
        prompt = render_required_prompt(
            _SCENE_DIRECTOR_NODE_KEY,
            {"outline": f"Chapter {chapter_number}\n{outline.strip()}"},
        )
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
