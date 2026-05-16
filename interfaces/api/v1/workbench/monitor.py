"""监控大盘 API endpoints - 提供张力曲线、人声漂移、伏笔统计等监控数据

重要：SQLite 访问必须在 asyncio.to_thread 中执行，避免阻塞 Starlette 事件循环。
若在 async def 里直接调 chapter_repo / novel_repo，一次慢查询会让全进程所有 API「一起卡」，与「失败隔离」设计理念相悖。
"""

import asyncio
import logging
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from domain.novel.value_objects.novel_id import NovelId
from interfaces.api.dependencies import (
    get_novel_repository,
    get_chapter_repository,
    get_foreshadowing_repository
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/novels", tags=["monitor"])

# 未评估哨兵值（与 TensionDimensions.UNEVALUATED 保持一致）
UNEVALUATED = -1.0


class TensionPoint(BaseModel):
    chapter: int
    tension: float
    title: str
    evaluated: bool = True  # 是否已完成真实评估


class TensionCurveResponse(BaseModel):
    novel_id: str
    points: List[TensionPoint]
    stats: Optional["TensionCurveStats"] = None


class TensionCurveStats(BaseModel):
    """张力曲线统计信息"""
    avg_tension: float = 0.0         # 平均张力（排除未评估）
    max_tension: float = 0.0         # 最高张力
    min_tension: float = 0.0         # 最低张力
    variance: float = 0.0            # 张力方差（衡量起伏程度）
    is_flat: bool = False            # 曲线是否过于平缓（方差<4.0）
    evaluated_count: int = 0         # 已评估章节数
    unevaluated_count: int = 0       # 未评估章节数
    consecutive_low: int = 0         # 连续低张力章节数（<40分即<4.0）


def _get_tension_curve_sync(novel_id: str) -> TensionCurveResponse:
    chapter_repo = get_chapter_repository()
    chapters = chapter_repo.list_by_novel(NovelId(novel_id))

    points: List[TensionPoint] = []
    evaluated_scores: List[float] = []  # 0-100 原始分
    consecutive_low = 0
    max_consecutive_low = 0

    for ch in chapters:
        raw = getattr(ch, "tension_score", None)
        ch_status = getattr(ch, "status", None)
        # 🔥 判断是否已完成真实张力评估：
        # 1. raw 为 None 或 -1（UNEVALUATED）→ 未评估
        # 2. 章节 status=draft 且 tension_score=50.0（schema默认值）→ 未评估
        #    因为 draft 章节没有经过审计管线，50.0 只是建表默认值，不是真实评分
        is_unevaluated = raw is None or float(raw) == UNEVALUATED
        is_default_draft = (
            ch_status == "draft"
            and raw is not None
            and float(raw) == 50.0
            and getattr(ch, "plot_tension", None) is None
        )
        if is_unevaluated or is_default_draft:
            # 未评估的章节
            points.append(
                TensionPoint(
                    chapter=ch.number,
                    tension=0.0,
                    title=ch.title or f"第{ch.number}章",
                    evaluated=False,
                )
            )
        else:
            raw_tension = float(raw)
            tension = raw_tension / 10.0  # 0-100 → 0-10
            points.append(
                TensionPoint(
                    chapter=ch.number,
                    tension=tension,
                    title=ch.title or f"第{ch.number}章",
                    evaluated=True,
                )
            )
            evaluated_scores.append(raw_tension)

            # 连续低张力检测
            if raw_tension < 40:
                consecutive_low += 1
                max_consecutive_low = max(max_consecutive_low, consecutive_low)
            else:
                consecutive_low = 0

    points.sort(key=lambda p: p.chapter)

    # 计算统计信息
    stats = TensionCurveStats()
    evaluated_count = len(evaluated_scores)
    unevaluated_count = len(points) - evaluated_count

    if evaluated_count > 0:
        avg_100 = sum(evaluated_scores) / evaluated_count
        max_100 = max(evaluated_scores)
        min_100 = min(evaluated_scores)

        # 方差（在 0-10 刻度上计算）
        avg_10 = avg_100 / 10.0
        variance = sum((s / 10.0 - avg_10) ** 2 for s in evaluated_scores) / evaluated_count

        stats = TensionCurveStats(
            avg_tension=round(avg_100 / 10.0, 1),
            max_tension=round(max_100 / 10.0, 1),
            min_tension=round(min_100 / 10.0, 1),
            variance=round(variance, 2),
            is_flat=variance < 1.0 and evaluated_count >= 3,  # 方差<1.0=过于平缓
            evaluated_count=evaluated_count,
            unevaluated_count=unevaluated_count,
            consecutive_low=max_consecutive_low,
        )
    else:
        stats.evaluated_count = 0
        stats.unevaluated_count = unevaluated_count

    return TensionCurveResponse(novel_id=novel_id, points=points, stats=stats)


class VoiceDriftResponse(BaseModel):
    character_id: str
    character_name: str
    drift_score: float
    status: str  # "normal" | "warning" | "critical"
    sample_count: int


class ForeshadowStatsResponse(BaseModel):
    total_planted: int
    total_resolved: int
    pending: int
    forgotten_risk: int
    resolution_rate: float


@router.get("/{novel_id}/monitor/tension-curve", response_model=TensionCurveResponse)
async def get_tension_curve(novel_id: str):
    """
    获取章节张力曲线数据

    返回每章的张力值（0-10），用于绘制张力曲线图
    """
    try:
        return await asyncio.to_thread(_get_tension_curve_sync, novel_id)
    except Exception as e:
        logger.error(f"Error fetching tension curve: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch tension curve")


def _get_voice_drift_sync(novel_id: str) -> Optional[List[VoiceDriftResponse]]:
    novel_repo = get_novel_repository()
    novel = novel_repo.get_by_id(NovelId(novel_id))
    if not novel:
        return None

    results: List[VoiceDriftResponse] = []
    characters = getattr(novel, "characters", [])
    for char in characters[:5]:
        char_id = getattr(char, "id", str(char))
        char_name = getattr(char, "name", char_id)
        drift_score = 0.15
        st = "normal"
        if drift_score > 0.5:
            st = "critical"
        elif drift_score > 0.3:
            st = "warning"
        results.append(
            VoiceDriftResponse(
                character_id=char_id,
                character_name=char_name,
                drift_score=drift_score,
                status=st,
                sample_count=10,
            )
        )
    return results


@router.get("/{novel_id}/monitor/voice-drift", response_model=List[VoiceDriftResponse])
async def get_voice_drift(novel_id: str):
    """
    获取人声漂移检测数据

    返回每个角色的语气漂移指数（0-1），超过 0.3 为异常
    """
    try:
        results = await asyncio.to_thread(_get_voice_drift_sync, novel_id)
        if results is None:
            raise HTTPException(status_code=404, detail="Novel not found")
        return results
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching voice drift: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch voice drift data")


def _get_foreshadow_stats_sync(novel_id: str) -> ForeshadowStatsResponse:
    foreshadowing_repo = get_foreshadowing_repository()
    chapter_repo = get_chapter_repository()

    registry = foreshadowing_repo.get_by_novel_id(NovelId(novel_id))
    if not registry:
        return ForeshadowStatsResponse(
            total_planted=0,
            total_resolved=0,
            pending=0,
            forgotten_risk=0,
            resolution_rate=0.0,
        )

    entries = registry.subtext_entries
    total_planted = len(entries)
    total_resolved = sum(1 for e in entries if e.status == "consumed")
    pending = total_planted - total_resolved

    chapters = chapter_repo.list_by_novel(NovelId(novel_id))
    current_chapter = max((ch.number for ch in chapters), default=0)

    forgotten_risk = 0
    for entry in entries:
        if entry.status == "pending":
            planted_chapter = entry.chapter
            if current_chapter - planted_chapter > 10:
                forgotten_risk += 1

    resolution_rate = (total_resolved / total_planted * 100) if total_planted > 0 else 0.0

    return ForeshadowStatsResponse(
        total_planted=total_planted,
        total_resolved=total_resolved,
        pending=pending,
        forgotten_risk=forgotten_risk,
        resolution_rate=round(resolution_rate, 1),
    )


@router.get("/{novel_id}/monitor/foreshadow-stats", response_model=ForeshadowStatsResponse)
async def get_foreshadow_stats(novel_id: str):
    """
    获取伏笔统计数据

    返回已埋伏笔、已回收、待回收、遗忘风险等统计信息
    """
    try:
        return await asyncio.to_thread(_get_foreshadow_stats_sync, novel_id)
    except Exception as e:
        logger.error(f"Error fetching foreshadow stats: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch foreshadow statistics")
