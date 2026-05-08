"""章节修复 API 端点"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from application.audit.services.chapter_repair_service import ChapterRepairService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chapter-repair"])


# ── 请求模型 ──


class ExpandChapterRequest(BaseModel):
    target_words: int = Field(default=4000, ge=500, le=20000, description="目标字数")


class BatchExpandRequest(BaseModel):
    chapter_numbers: list[int] = Field(..., min_length=1, description="章节号列表")
    target_words: int = Field(default=4000, ge=500, le=20000, description="目标字数")


# ── 依赖注入 ──


def _get_service() -> ChapterRepairService:
    from interfaces.api.dependencies import get_chapter_repair_service
    return get_chapter_repair_service()


# ── 端点 ──


@router.get("/novels/{novel_id}/chapter-repair/scan")
async def scan_short_chapters(
    novel_id: str,
    threshold: int = Query(default=4000, ge=100, le=20000, description="字数阈值"),
    service: ChapterRepairService = Depends(_get_service),
):
    """扫描字数不足的章节"""
    result = service.scan_short_chapters(novel_id, threshold)
    return {
        "novel_id": result.novel_id,
        "threshold": result.threshold,
        "total_chapters": result.total_chapters,
        "short_chapters": [
            {
                "chapter_number": ch.chapter_number,
                "title": ch.title,
                "word_count": ch.word_count,
                "status": ch.status,
                "content_preview": ch.content_preview,
                "severity": ch.severity,
            }
            for ch in result.short_chapters
        ],
        "summary": result.summary,
    }


@router.post("/novels/{novel_id}/chapter-repair/expand/{chapter_number}")
async def expand_chapter(
    novel_id: str,
    chapter_number: int,
    request: ExpandChapterRequest,
    service: ChapterRepairService = Depends(_get_service),
):
    """SSE 流式扩写单个章节"""

    async def event_gen():
        try:
            async for event in service.expand_chapter(novel_id, chapter_number, request.target_words):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"扩写 SSE 异常: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/novels/{novel_id}/chapter-repair/batch-expand")
async def batch_expand_chapters(
    novel_id: str,
    request: BatchExpandRequest,
    service: ChapterRepairService = Depends(_get_service),
):
    """SSE 流式批量扩写章节"""

    async def event_gen():
        try:
            async for event in service.batch_expand_chapters(
                novel_id, request.chapter_numbers, request.target_words
            ):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"批量扩写 SSE 异常: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
