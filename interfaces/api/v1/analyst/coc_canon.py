"""CoC 正典注册表 API。"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field

from application.analyst.services.coc_canon_service import CocCanonService
from interfaces.api.dependencies import (
    get_coc_canon_service,
    get_coc_preset_service,
    get_novel_service,
)


router = APIRouter(tags=["coc-canon"])


class CocCanonEntry(BaseModel):
    id: str
    novel_id: str
    canon_type: str
    title: str
    public_facts: str
    hidden_truth: str
    lock_level: str
    mutable_notes: str
    status: str
    created_at: str
    updated_at: str


class CocCanonEvent(BaseModel):
    id: str
    entry_id: str
    novel_id: str
    canon_type: str
    title: str
    chapter_number: int
    event_type: str
    evidence: str
    notes: str
    created_at: str


class CocCanonCognitionLayers(BaseModel):
    author_truth: List[str] = []
    reader_known: List[str] = []
    author_truth_snippets: List[str] = []


class CocCanonOverview(BaseModel):
    novel_id: str
    entries: List[CocCanonEntry]
    recent_events: List[CocCanonEvent]
    cognition_layers: CocCanonCognitionLayers


class UpsertCocCanonEntryRequest(BaseModel):
    entry_id: Optional[str] = Field(default=None, min_length=1, max_length=64)
    canon_type: str = Field(..., min_length=1, max_length=60)
    title: str = Field(..., min_length=1, max_length=200)
    public_facts: str = Field(default="", max_length=10000)
    hidden_truth: str = Field(default="", max_length=10000)
    lock_level: str = Field(default="soft", max_length=20)
    mutable_notes: str = Field(default="", max_length=4000)
    status: str = Field(default="active", max_length=20)


class CreateCocCanonEventRequest(BaseModel):
    entry_id: Optional[str] = Field(default=None, min_length=1, max_length=64)
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    chapter_number: int = Field(..., ge=1)
    event_type: str = Field(default="mention", max_length=40)
    evidence: str = Field(default="", max_length=10000)
    notes: str = Field(default="", max_length=4000)


class CocPresetTemplate(BaseModel):
    key: str
    name: str
    description: str
    source_novel_id: str
    canon_count: int
    clue_count: int
    prop_count: int = 0


class ApplyCocPresetRequest(BaseModel):
    preset_key: str = Field(default="analysis-loop-721", min_length=1, max_length=80)
    overwrite_existing: bool = Field(default=False)


class ApplyCocPresetResponse(BaseModel):
    preset_key: str
    novel_id: str
    created_canon: int
    created_clues: int
    created_props: int = 0
    skipped: int
    overwrite_existing: bool


def _ensure_novel_exists(novel_id: str, novel_service) -> None:
    if novel_service.get_novel(novel_id) is None:
        raise HTTPException(status_code=404, detail="Novel not found")


@router.get(
    "/novels/{novel_id}/coc-canon/overview",
    response_model=CocCanonOverview,
)
def get_coc_canon_overview(
    novel_id: str = Path(...),
    novel_service=Depends(get_novel_service),
    service: CocCanonService = Depends(get_coc_canon_service),
) -> CocCanonOverview:
    _ensure_novel_exists(novel_id, novel_service)
    return CocCanonOverview(**service.get_overview(novel_id))


@router.post(
    "/novels/{novel_id}/coc-canon/entries",
    response_model=CocCanonEntry,
    status_code=201,
)
def upsert_coc_canon_entry(
    request: UpsertCocCanonEntryRequest,
    novel_id: str = Path(...),
    novel_service=Depends(get_novel_service),
    service: CocCanonService = Depends(get_coc_canon_service),
) -> CocCanonEntry:
    _ensure_novel_exists(novel_id, novel_service)
    try:
        payload = service.upsert_entry(novel_id=novel_id, **request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CocCanonEntry(**payload)


@router.post(
    "/novels/{novel_id}/coc-canon/events",
    response_model=CocCanonEvent,
    status_code=201,
)
def create_coc_canon_event(
    request: CreateCocCanonEventRequest,
    novel_id: str = Path(...),
    novel_service=Depends(get_novel_service),
    service: CocCanonService = Depends(get_coc_canon_service),
) -> CocCanonEvent:
    _ensure_novel_exists(novel_id, novel_service)
    try:
        payload = service.create_event(novel_id=novel_id, **request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CocCanonEvent(**payload)


@router.get(
    "/novels/{novel_id}/coc-preset/templates",
    response_model=List[CocPresetTemplate],
)
def list_coc_preset_templates(
    novel_id: str = Path(...),
    novel_service=Depends(get_novel_service),
    preset_service=Depends(get_coc_preset_service),
) -> List[CocPresetTemplate]:
    _ensure_novel_exists(novel_id, novel_service)
    return [CocPresetTemplate(**item) for item in preset_service.list_presets()]


@router.post(
    "/novels/{novel_id}/coc-preset/apply",
    response_model=ApplyCocPresetResponse,
    status_code=201,
)
def apply_coc_preset(
    request: ApplyCocPresetRequest,
    novel_id: str = Path(...),
    novel_service=Depends(get_novel_service),
    preset_service=Depends(get_coc_preset_service),
) -> ApplyCocPresetResponse:
    _ensure_novel_exists(novel_id, novel_service)
    try:
        payload = preset_service.apply_preset(
            novel_id=novel_id,
            preset_key=request.preset_key,
            overwrite_existing=request.overwrite_existing,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ApplyCocPresetResponse(**payload)
