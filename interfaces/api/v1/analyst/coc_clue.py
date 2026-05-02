"""CoC 线索账本 API。"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field

from application.analyst.services.coc_clue_service import CocClueService
from interfaces.api.dependencies import get_coc_clue_service, get_novel_service


router = APIRouter(tags=["coc-clues"])


class CocClueItem(BaseModel):
    id: str
    novel_id: str
    clue_key: str
    clue_text: str
    visibility: str
    reveal_chapter: Optional[int] = None
    known_by: str
    confidence: float
    lock_level: str
    status: str
    notes: str
    created_at: str
    updated_at: str


class CocClueEvent(BaseModel):
    id: str
    clue_id: str
    novel_id: str
    clue_key: str
    chapter_number: int
    event_type: str
    evidence: str
    notes: str
    created_at: str


class CocClueCognitionLayers(BaseModel):
    author_truth: List[str] = []
    character_known: List[str] = []
    reader_known: List[str] = []


class CocClueOverview(BaseModel):
    novel_id: str
    items: List[CocClueItem]
    recent_events: List[CocClueEvent]
    cognition_layers: CocClueCognitionLayers


class UpsertCocClueItemRequest(BaseModel):
    entry_id: Optional[str] = Field(default=None, min_length=1, max_length=64)
    clue_key: str = Field(..., min_length=1, max_length=120)
    clue_text: str = Field(default="", max_length=10000)
    visibility: str = Field(default="reader_known", max_length=40)
    reveal_chapter: Optional[int] = Field(default=None, ge=1)
    known_by: str = Field(default="", max_length=200)
    confidence: float = Field(default=0.5, ge=0, le=1)
    lock_level: str = Field(default="soft", max_length=20)
    status: str = Field(default="active", max_length=20)
    notes: str = Field(default="", max_length=4000)


class CreateCocClueEventRequest(BaseModel):
    entry_id: Optional[str] = Field(default=None, min_length=1, max_length=64)
    clue_key: Optional[str] = Field(default=None, min_length=1, max_length=120)
    chapter_number: int = Field(..., ge=1)
    event_type: str = Field(default="mention", max_length=40)
    evidence: str = Field(default="", max_length=10000)
    notes: str = Field(default="", max_length=4000)


def _ensure_novel_exists(novel_id: str, novel_service) -> None:
    if novel_service.get_novel(novel_id) is None:
        raise HTTPException(status_code=404, detail="Novel not found")


@router.get(
    "/novels/{novel_id}/coc-clues/overview",
    response_model=CocClueOverview,
)
def get_coc_clue_overview(
    novel_id: str = Path(...),
    novel_service=Depends(get_novel_service),
    service: CocClueService = Depends(get_coc_clue_service),
) -> CocClueOverview:
    _ensure_novel_exists(novel_id, novel_service)
    return CocClueOverview(**service.get_overview(novel_id))


@router.post(
    "/novels/{novel_id}/coc-clues/items",
    response_model=CocClueItem,
    status_code=201,
)
def upsert_coc_clue_item(
    request: UpsertCocClueItemRequest,
    novel_id: str = Path(...),
    novel_service=Depends(get_novel_service),
    service: CocClueService = Depends(get_coc_clue_service),
) -> CocClueItem:
    _ensure_novel_exists(novel_id, novel_service)
    try:
        payload = service.upsert_item(novel_id=novel_id, **request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CocClueItem(**payload)


@router.post(
    "/novels/{novel_id}/coc-clues/events",
    response_model=CocClueEvent,
    status_code=201,
)
def create_coc_clue_event(
    request: CreateCocClueEventRequest,
    novel_id: str = Path(...),
    novel_service=Depends(get_novel_service),
    service: CocClueService = Depends(get_coc_clue_service),
) -> CocClueEvent:
    _ensure_novel_exists(novel_id, novel_service)
    try:
        payload = service.create_event(novel_id=novel_id, **request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CocClueEvent(**payload)
