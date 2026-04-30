"""道具账本 API。"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field

from application.analyst.services.prop_ledger_service import PropLedgerService
from interfaces.api.dependencies import get_novel_service, get_prop_ledger_service


router = APIRouter(tags=["prop-ledger"])


class PropLedgerItem(BaseModel):
    id: str
    novel_id: str
    name: str
    category: str
    status: str
    current_holder: str
    current_location: str
    first_seen_chapter: Optional[int] = None
    last_seen_chapter: Optional[int] = None
    importance: str
    description: str
    notes: str
    created_at: str
    updated_at: str


class PropLedgerEvent(BaseModel):
    id: str
    novel_id: str
    prop_id: str
    prop_name: str
    chapter_number: int
    event_type: str
    holder: str
    location: str
    status: str
    evidence: str
    notes: str
    created_at: str


class PropLedgerWarning(BaseModel):
    severity: str
    title: str
    message: str


class PropLedgerOverview(BaseModel):
    novel_id: str
    items: List[PropLedgerItem]
    recent_events: List[PropLedgerEvent]
    warnings: List[PropLedgerWarning]


class UpsertPropItemRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    category: str = Field(default="", max_length=100)
    status: str = Field(default="", max_length=100)
    current_holder: str = Field(default="", max_length=100)
    current_location: str = Field(default="", max_length=200)
    first_seen_chapter: Optional[int] = Field(default=None, ge=1)
    last_seen_chapter: Optional[int] = Field(default=None, ge=1)
    importance: str = Field(default="normal", max_length=20)
    description: str = Field(default="", max_length=4000)
    notes: str = Field(default="", max_length=4000)


class CreatePropEventRequest(BaseModel):
    prop_name: str = Field(..., min_length=1, max_length=100)
    chapter_number: int = Field(..., ge=1)
    event_type: str = Field(default="mention", max_length=50)
    holder: str = Field(default="", max_length=100)
    location: str = Field(default="", max_length=200)
    status: str = Field(default="", max_length=100)
    evidence: str = Field(default="", max_length=4000)
    notes: str = Field(default="", max_length=4000)


def _ensure_novel_exists(novel_id: str, novel_service) -> None:
    if novel_service.get_novel(novel_id) is None:
        raise HTTPException(status_code=404, detail="Novel not found")


@router.get(
    "/novels/{novel_id}/prop-ledger/overview",
    response_model=PropLedgerOverview,
)
def get_prop_ledger_overview(
    novel_id: str = Path(...),
    novel_service=Depends(get_novel_service),
    service: PropLedgerService = Depends(get_prop_ledger_service),
) -> PropLedgerOverview:
    _ensure_novel_exists(novel_id, novel_service)
    return PropLedgerOverview(**service.get_overview(novel_id))


@router.post(
    "/novels/{novel_id}/prop-ledger/items",
    response_model=PropLedgerItem,
    status_code=201,
)
def upsert_prop_item(
    request: UpsertPropItemRequest,
    novel_id: str = Path(...),
    novel_service=Depends(get_novel_service),
    service: PropLedgerService = Depends(get_prop_ledger_service),
) -> PropLedgerItem:
    _ensure_novel_exists(novel_id, novel_service)
    try:
        return PropLedgerItem(**service.upsert_item(novel_id=novel_id, **request.model_dump()))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/novels/{novel_id}/prop-ledger/events",
    response_model=PropLedgerEvent,
    status_code=201,
)
def create_prop_event(
    request: CreatePropEventRequest,
    novel_id: str = Path(...),
    novel_service=Depends(get_novel_service),
    service: PropLedgerService = Depends(get_prop_ledger_service),
) -> PropLedgerEvent:
    _ensure_novel_exists(novel_id, novel_service)
    try:
        return PropLedgerEvent(**service.create_event(novel_id=novel_id, **request.model_dump()))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
