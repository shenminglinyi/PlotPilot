"""战力系统 API。"""
from __future__ import annotations

from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field

from application.analyst.services.power_system_service import PowerSystemService
from interfaces.api.dependencies import get_novel_service, get_power_system_service


router = APIRouter(tags=["power-system"])


class PowerSystemRules(BaseModel):
    id: str
    novel_id: str
    genre_type: str
    tier_schema: str
    core_rules: str
    taboo_rules: str
    escalation_rules: str
    created_at: str = ""
    updated_at: str = ""


class PowerCharacterProfile(BaseModel):
    id: str
    novel_id: str
    character_name: str
    tier: str
    rank_score: int
    abilities: str
    limitations: str
    growth_stage: str
    last_verified_chapter: Optional[int] = None
    notes: str
    created_at: str
    updated_at: str


class PowerProgressionEvent(BaseModel):
    id: str
    novel_id: str
    chapter_number: int
    character_name: str
    event_type: str
    opponent: str
    outcome: str
    power_delta: int
    evidence: str
    created_at: str


class PowerWarning(BaseModel):
    severity: str
    title: str
    message: str


class PowerSystemOverview(BaseModel):
    novel_id: str
    standard: str
    rules: PowerSystemRules
    profiles: List[PowerCharacterProfile]
    recent_events: List[PowerProgressionEvent]
    warnings: List[PowerWarning]


class UpsertPowerRulesRequest(BaseModel):
    genre_type: str = Field(default="system_game", max_length=50)
    tier_schema: str = Field(default="", max_length=4000)
    core_rules: str = Field(default="", max_length=6000)
    taboo_rules: str = Field(default="", max_length=4000)
    escalation_rules: str = Field(default="", max_length=4000)


class UpsertPowerProfileRequest(BaseModel):
    character_name: str = Field(..., min_length=1, max_length=100)
    tier: str = Field(default="", max_length=100)
    rank_score: int = Field(default=0, ge=0, le=100)
    abilities: str = Field(default="", max_length=4000)
    limitations: str = Field(default="", max_length=4000)
    growth_stage: str = Field(default="", max_length=1000)
    last_verified_chapter: Optional[int] = Field(default=None, ge=1)
    notes: str = Field(default="", max_length=4000)


class CreatePowerEventRequest(BaseModel):
    chapter_number: int = Field(..., ge=1)
    character_name: str = Field(..., min_length=1, max_length=100)
    event_type: str = Field(default="battle", max_length=50)
    opponent: str = Field(default="", max_length=100)
    outcome: str = Field(default="", max_length=1000)
    power_delta: int = Field(default=0, ge=-10, le=10)
    evidence: str = Field(default="", max_length=4000)


def _ensure_novel_exists(novel_id: str, novel_service) -> None:
    if novel_service.get_novel(novel_id) is None:
        raise HTTPException(status_code=404, detail="Novel not found")


@router.get(
    "/novels/{novel_id}/power-system/overview",
    response_model=PowerSystemOverview,
)
def get_power_system_overview(
    novel_id: str = Path(...),
    novel_service=Depends(get_novel_service),
    service: PowerSystemService = Depends(get_power_system_service),
) -> PowerSystemOverview:
    _ensure_novel_exists(novel_id, novel_service)
    return PowerSystemOverview(**service.get_overview(novel_id))


@router.put(
    "/novels/{novel_id}/power-system/rules",
    response_model=PowerSystemRules,
)
def upsert_power_rules(
    request: UpsertPowerRulesRequest,
    novel_id: str = Path(...),
    novel_service=Depends(get_novel_service),
    service: PowerSystemService = Depends(get_power_system_service),
) -> PowerSystemRules:
    _ensure_novel_exists(novel_id, novel_service)
    payload = service.upsert_rules(
        novel_id=novel_id,
        genre_type=request.genre_type,
        tier_schema=request.tier_schema,
        core_rules=request.core_rules,
        taboo_rules=request.taboo_rules,
        escalation_rules=request.escalation_rules,
    )
    return PowerSystemRules(**payload)


@router.post(
    "/novels/{novel_id}/power-system/profiles",
    response_model=PowerCharacterProfile,
    status_code=201,
)
def upsert_power_profile(
    request: UpsertPowerProfileRequest,
    novel_id: str = Path(...),
    novel_service=Depends(get_novel_service),
    service: PowerSystemService = Depends(get_power_system_service),
) -> PowerCharacterProfile:
    _ensure_novel_exists(novel_id, novel_service)
    payload = service.upsert_profile(novel_id=novel_id, **request.model_dump())
    return PowerCharacterProfile(**payload)


@router.post(
    "/novels/{novel_id}/power-system/events",
    response_model=PowerProgressionEvent,
    status_code=201,
)
def create_power_event(
    request: CreatePowerEventRequest,
    novel_id: str = Path(...),
    novel_service=Depends(get_novel_service),
    service: PowerSystemService = Depends(get_power_system_service),
) -> PowerProgressionEvent:
    _ensure_novel_exists(novel_id, novel_service)
    payload = service.create_event(novel_id=novel_id, **request.model_dump())
    return PowerProgressionEvent(**payload)
