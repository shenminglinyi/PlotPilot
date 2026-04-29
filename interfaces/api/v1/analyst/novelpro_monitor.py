"""NovelPro 自动监控中心 API。"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Path, Query
from pydantic import BaseModel

from application.analyst.services.novelpro_monitor_service import NovelProMonitorService
from interfaces.api.dependencies import get_novelpro_monitor_service


router = APIRouter(tags=["novelpro-monitor"])


class MonitorHealth(BaseModel):
    status: str
    score: int
    error_count: int
    warning_count: int
    alert_count: int


class ObsidianMemorySummary(BaseModel):
    primary_memory: bool
    premise_locked: bool
    fact_count: int
    chapter_count: int
    relationship_graph_path: str = ""
    vault_path: str = ""
    vault_configured: bool = False
    obsidian_app_installed: bool = False


class KnowledgeGraphSummary(BaseModel):
    fact_count: int
    relationship_count: int
    entity_count: int


class ContinuityMonitorSummary(BaseModel):
    dropout_count: int
    stale_relationship_count: int
    active_relationship_signal_count: int
    voice_drift_alert: bool
    timeline_conflict_count: int
    current_chapter_has_timeline_event: bool
    outline_status: str


class PowerMonitorSummary(BaseModel):
    profile_count: int
    warning_count: int


class NovelProMonitorAlert(BaseModel):
    severity: str
    source: str
    title: str
    message: str
    action: str


class NovelProMonitorOverview(BaseModel):
    novel_id: str
    chapter_number: int
    health: MonitorHealth
    obsidian: ObsidianMemorySummary
    knowledge_graph: KnowledgeGraphSummary
    continuity: ContinuityMonitorSummary
    power: PowerMonitorSummary
    alerts: List[NovelProMonitorAlert]


class ObsidianSyncResponse(BaseModel):
    synced: bool
    reason: str = ""
    vault_path: str = ""
    chapter_note: str = ""
    fact_count: int = 0


@router.get(
    "/novels/{novel_id}/novelpro/monitor",
    response_model=NovelProMonitorOverview,
    summary="获取 NovelPro 自动监控中心",
    description="聚合 Obsidian 主记忆、关系图、连续性巡检和战力系统提醒。",
)
def get_novelpro_monitor(
    novel_id: str = Path(..., description="小说 ID"),
    chapter_number: Optional[int] = Query(None, ge=1, description="当前关注章节；省略时使用最新章节"),
    service: NovelProMonitorService = Depends(get_novelpro_monitor_service),
) -> NovelProMonitorOverview:
    return NovelProMonitorOverview(**service.get_overview(novel_id, chapter_number))


@router.post(
    "/novels/{novel_id}/novelpro/obsidian/sync",
    response_model=ObsidianSyncResponse,
    summary="手动同步当前章节到 Obsidian 长期记忆",
)
def sync_obsidian_memory(
    novel_id: str = Path(..., description="小说 ID"),
    chapter_number: int = Query(..., ge=1, description="要同步的章节号"),
    service: NovelProMonitorService = Depends(get_novelpro_monitor_service),
) -> ObsidianSyncResponse:
    return ObsidianSyncResponse(**service.sync_obsidian_chapter(novel_id, chapter_number))
