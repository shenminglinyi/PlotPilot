"""NovelPro AI form suggestion API."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel, Field

from application.analyst.services.novelpro_ai_suggestion_service import (
    NovelProAISuggestionService,
)
from interfaces.api.dependencies import get_novelpro_ai_suggestion_service


router = APIRouter(tags=["novelpro-suggestions"])


class NovelProSuggestionRequest(BaseModel):
    suggestion_type: str = Field(..., min_length=1, max_length=80)
    fields: List[str] = Field(..., min_length=1)
    chapter_number: Optional[int] = Field(default=None, ge=1)
    target: Dict[str, Any] = Field(default_factory=dict)
    current_values: Dict[str, Any] = Field(default_factory=dict)
    instruction: str = Field(default="", max_length=2000)


class NovelProSuggestionResponse(BaseModel):
    suggestion_type: str
    fields: Dict[str, Any]
    rationale: str = ""


@router.post(
    "/novels/{novel_id}/novelpro/suggestions",
    response_model=NovelProSuggestionResponse,
    summary="生成 NovelPro 表单建议",
    description="使用 PP 当前激活 AI 配置，为口吻、连续性和战力等手动表单生成可编辑草稿。",
)
async def suggest_novelpro_fields(
    request: NovelProSuggestionRequest,
    novel_id: str = Path(..., description="小说 ID"),
    service: NovelProAISuggestionService = Depends(get_novelpro_ai_suggestion_service),
) -> NovelProSuggestionResponse:
    payload = await service.suggest_fields(
        novel_id=novel_id,
        suggestion_type=request.suggestion_type,
        fields=request.fields,
        chapter_number=request.chapter_number,
        target=request.target,
        current_values=request.current_values,
        instruction=request.instruction,
    )
    return NovelProSuggestionResponse(**payload)
