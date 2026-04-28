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
    tracked_relationship_count: int = 0
    stale_relationship_count: int = 0
    stale_relationship_targets: List[str] = Field(default_factory=list)
    dropout_scope: str = "solo"


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
    source: str = "heuristic"


class StaleRelationshipItem(BaseModel):
    source_character: str
    target_character: str
    relation: str
    description: str = ""
    last_joint_chapter: int
    chapters_since_joint: int
    severity: str


class RelationshipTrackingSummary(BaseModel):
    source: str = "heuristic"
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


class OutlineNodeStatusItem(BaseModel):
    node_key: str
    outline_text: str
    status: str
    note: str = ""
    evidence: str = ""


class OutlineDeviationSummary(BaseModel):
    source: str = "heuristic"
    status: str
    overlap_score: Optional[float]
    outline_excerpt: str
    summary_excerpt: str
    warning_reasons: List[str] = Field(default_factory=list)
    outline_nodes: List[OutlineNodeStatusItem] = Field(default_factory=list)


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


class RelationshipEventRequest(BaseModel):
    chapter_number: int = Field(..., ge=1)
    source_character: str = Field(..., min_length=1)
    target_character: str = ""
    relation: str = "关系"
    event_type: str = "update"
    description: str = ""
    evidence: str = ""
    severity: str = "info"


class RelationshipEventResponse(RelationshipEventRequest):
    id: str
    novel_id: str


class OutlineNodeStatusRequest(BaseModel):
    chapter_number: int = Field(..., ge=1)
    node_key: str = Field(..., min_length=1)
    outline_text: str = Field(..., min_length=1)
    status: str = "pending"
    note: str = ""
    evidence: str = ""


class OutlineNodeStatusResponse(OutlineNodeStatusRequest):
    id: str
    novel_id: str


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


@router.post(
    "/novels/{novel_id}/continuity/relationship-events",
    response_model=RelationshipEventResponse,
    summary="记录关系变化事件",
    description="为连续性面板补充结构化关系推进/破裂/修复记录，优先用于后续巡检。",
)
def record_relationship_event(
    request: RelationshipEventRequest,
    novel_id: str = Path(..., description="小说 ID"),
    service: ContinuityOverviewService = Depends(get_continuity_overview_service),
) -> RelationshipEventResponse:
    payload = service.record_relationship_event(novel_id, request.model_dump())
    return RelationshipEventResponse(**payload)


@router.put(
    "/novels/{novel_id}/continuity/outline-nodes",
    response_model=OutlineNodeStatusResponse,
    summary="更新章节大纲节点状态",
    description="记录章节大纲节点是否已完成、变更、缺失或阻塞，用于降低脱纲巡检误判。",
)
def upsert_outline_node_status(
    request: OutlineNodeStatusRequest,
    novel_id: str = Path(..., description="小说 ID"),
    service: ContinuityOverviewService = Depends(get_continuity_overview_service),
) -> OutlineNodeStatusResponse:
    payload = service.upsert_outline_node_status(novel_id, request.model_dump())
    return OutlineNodeStatusResponse(**payload)
