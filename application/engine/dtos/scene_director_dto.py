from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, field_validator


def validate_outline_not_empty(v: str) -> str:
    """Validate that outline is not empty or whitespace-only.

    Args:
        v: The outline string to validate

    Returns:
        The validated outline string

    Raises:
        ValueError: If outline is empty or contains only whitespace
    """
    if isinstance(v, str) and not v.strip():
        raise ValueError("outline cannot be empty or whitespace only")
    return v


class SceneDirectorAnalyzeRequest(BaseModel):
    """Request model for scene director analysis.

    Attributes:
        chapter_number: Chapter number (must be >= 1)
        outline: Scene outline text (must not be empty or whitespace-only)
    """
    chapter_number: int = Field(ge=1)
    outline: str = Field(min_length=1)

    @field_validator("outline", mode="before")
    @classmethod
    def outline_not_empty(cls, v):
        return validate_outline_not_empty(v)


class SceneDirectorAnalysis(BaseModel):
    """Analysis result model with default values for optional fields.

    This model is used internally for analysis operations where fields may not
    be populated. All fields have sensible defaults to support partial analysis.

    Attributes:
        characters: List of character names (defaults to empty list)
        locations: List of location names (defaults to empty list)
        action_types: List of action types (defaults to empty list)
        trigger_keywords: List of trigger keywords (defaults to empty list)
        emotional_state: Emotional state description (defaults to empty string)
        pov: Point of view character (defaults to None)
        performance_notes: Optional list of action-level performance directions
            (e.g., "eyes flicker", "clenches fist"). Should describe observable
            actions and emotions without revealing hidden character settings.
            Defaults to None for backward compatibility.
    """
    characters: List[str] = Field(default_factory=list)
    locations: List[str] = Field(default_factory=list)
    action_types: List[str] = Field(default_factory=list)
    trigger_keywords: List[str] = Field(default_factory=list)
    emotional_state: str = ""
    pov: Optional[str] = None
    performance_notes: Optional[List[str]] = None


class SceneDirectorAnalyzeResponse(SceneDirectorAnalysis):
    """Response model for scene director analysis.

    Inherits from SceneDirectorAnalysis to maintain consistency while allowing
    for future response-specific fields or validation logic. Currently identical
    to parent but provides semantic clarity that this is a response object.
    """
    pass


SceneDirectorInput = Optional[Union[SceneDirectorAnalysis, Dict[str, Any]]]


def coerce_scene_director(raw: SceneDirectorInput) -> Optional[Dict[str, Any]]:
    """将 HTTP / 工作流传入的场记统一为 dict，供引擎层（ allocator、DAG 等）使用。

    API 层可能传入 ``SceneDirectorAnalysis``、普通 ``dict``，或任意带 ``model_dump``
    的 Pydantic v2 模型；在此处收口，避免引擎层混用 ``.get`` 与属性访问。
    """
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, SceneDirectorAnalysis):
        return raw.model_dump()
    dump = getattr(raw, "model_dump", None)
    if callable(dump):
        return dump()
    raise TypeError(
        "scene_director must be None, dict, SceneDirectorAnalysis, or a model with model_dump(); "
        f"got {type(raw).__name__}"
    )


class ContextRetrieveRequest(BaseModel):
    """Request model for context retrieval.

    Attributes:
        chapter_number: Chapter number (must be >= 1)
        outline: Scene outline text (must not be empty or whitespace-only)
        scene_director_result: Optional scene director analysis result for filtering
        max_tokens: Maximum tokens for context (default 35000, range 4096-120000)
    """
    chapter_number: int = Field(ge=1)
    outline: str = Field(min_length=1)
    scene_director_result: Optional[Dict[str, Any]] = None
    max_tokens: int = Field(default=35000, ge=4096, le=120000)

    @field_validator("outline", mode="before")
    @classmethod
    def outline_not_empty(cls, v):
        return validate_outline_not_empty(v)


class ContextRetrieveResponse(BaseModel):
    """Response model for context retrieval.

    Returns layered context with token usage information.

    Attributes:
        layer1: Layer 1 core context with content field
        layer2: Layer 2 smart retrieval with content field
        layer3: Layer 3 recent context with content field
        token_usage: Token usage breakdown by layer and total
    """
    layer1: Dict[str, Any]
    layer2: Dict[str, Any]
    layer3: Dict[str, Any]
    token_usage: Dict[str, int]
