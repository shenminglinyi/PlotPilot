"""连续性总览 API"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Path, Query
from pydantic import BaseModel, Field

from application.analyst.services.continuity_overview_service import ContinuityOverviewService
from interfaces.api.dependencies import get_continuity_overview_service


router = APIRouter(tags=["continuity"])


class CharacterDropoutItem(BaseModel):
    character_id: str
    character_name: str
    last_appearance_chapter: int
    chapters_absent: int
    appearance_count: int
    severity: str


class RelationshipSpotlightItem(BaseModel):
    source_character: str
    target_character: str
    relation: str
    description: str


class RelationshipSignalItem(BaseModel):
    source_character: str
    target_character: str
    relation: str
    description: str = ""
    last_joint_chapter: int
    joint_appearance_count: int
    change_signal: str
    signal_excerpt: str = ""
    severity: str


class StaleRelationshipItem(BaseModel):
    source_character: str
    target_character: str
    relation: str
    description: str = ""
    last_joint_chapter: int
    chapters_since_joint: int
    severity: str


class RelationshipTrackingSummary(BaseModel):
    tracked_pairs: int
    active_signals: List[RelationshipSignalItem]
    stale_pairs: List[StaleRelationshipItem]


class TimelineEventItem(BaseModel):
    id: str
    chapter_number: int
    event: str
    timestamp: str
    timestamp_type: str


class TimelineSummary(BaseModel):
    total_events: int
    current_chapter_has_event: bool
    current_chapter_events: List[TimelineEventItem]
    recent_events: List[TimelineEventItem]


class VoiceDriftSummary(BaseModel):
    drift_alert: bool
    latest_similarity_score: Optional[float]
    scored_chapters: int
    alert_threshold: float
    alert_consecutive: int


class OutlineDeviationSummary(BaseModel):
    status: str
    overlap_score: Optional[float]
    outline_excerpt: str
    summary_excerpt: str
    warning_reasons: List[str] = Field(default_factory=list)


class ContinuityOverviewResponse(BaseModel):
    novel_id: str
    chapter_number: int
    latest_chapter_number: int
    character_dropouts: List[CharacterDropoutItem]
    relationship_spotlights: List[RelationshipSpotlightItem]
    relationship_tracking: RelationshipTrackingSummary
    voice_drift: VoiceDriftSummary
    timeline: TimelineSummary
    outline_deviation: OutlineDeviationSummary


@router.get(
    "/novels/{novel_id}/continuity/overview",
    response_model=ContinuityOverviewResponse,
    summary="获取连续性总览",
    description="聚合角色掉线、时间线覆盖、文风漂移与关系摘要，供作者工作台快速巡检。",
)
def get_continuity_overview(
    novel_id: str = Path(..., description="小说 ID"),
    chapter_number: Optional[int] = Query(None, ge=1, description="当前关注章节；省略时使用最新章节"),
    service: ContinuityOverviewService = Depends(get_continuity_overview_service),
) -> ContinuityOverviewResponse:
    payload = service.get_overview(novel_id, chapter_number)
    return ContinuityOverviewResponse(**payload)
