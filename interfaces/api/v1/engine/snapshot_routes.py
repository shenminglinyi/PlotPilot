"""语义快照：回滚等到位后的 HTTP 接口。"""
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from application.snapshot.services.snapshot_service import SnapshotService
from interfaces.api.dependencies import get_novel_service, get_snapshot_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/novels", tags=["snapshots"])


class SnapshotRollbackResponse(BaseModel):
    deleted_chapter_ids: List[str] = Field(default_factory=list)
    deleted_count: int = 0
    has_engine_state: bool = False


@router.post(
    "/{novel_id}/snapshots/{snapshot_id}/rollback",
    response_model=SnapshotRollbackResponse,
)
async def rollback_to_snapshot(
    novel_id: str,
    snapshot_id: str,
    novel_service=Depends(get_novel_service),
    snapshot_service: SnapshotService = Depends(get_snapshot_service),
) -> SnapshotRollbackResponse:
    """将作品章节集合恢复为快照中记录的章节指针（删除快照未包含的章节正文行）。"""
    if novel_service.get_novel(novel_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Novel not found")

    try:
        result = snapshot_service.rollback_to_snapshot(novel_id, snapshot_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    return SnapshotRollbackResponse(
        deleted_chapter_ids=result["deleted_chapter_ids"],
        deleted_count=result["deleted_count"],
        has_engine_state=result.get("has_engine_state", False),
    )
