"""统一快照 API - 合并 Checkpoint 和 Snapshot"""
import logging
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from application.snapshot.services.snapshot_service import SnapshotService
from interfaces.api.dependencies import get_novel_service, get_snapshot_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/novels", tags=["snapshots"])


# ─── Pydantic DTOs ────────────────────────────────────────────────

class UnifiedSnapshotDTO(BaseModel):
    id: str
    novel_id: str
    parent_snapshot_id: Optional[str] = None
    branch_name: str = "main"

    # 触发信息
    trigger_type: str  # CHAPTER / ACT / MILESTONE / MANUAL / AUTO
    name: str
    description: Optional[str] = None

    # 章节指针
    chapter_pointers: List[str] = Field(default_factory=list)

    # 引擎状态
    story_state: dict = Field(default_factory=dict)
    character_masks: dict = Field(default_factory=dict)
    emotion_ledger: dict = Field(default_factory=dict)
    active_foreshadows: List[str] = Field(default_factory=list)
    outline: str = ""
    recent_chapters_summary: str = ""

    # 元数据
    created_at: str = ""
    bible_state: dict = Field(default_factory=dict)
    foreshadow_state: dict = Field(default_factory=dict)


class UnifiedSnapshotListResponse(BaseModel):
    snapshots: List[UnifiedSnapshotDTO] = Field(default_factory=list)


class CreateSnapshotRequest(BaseModel):
    trigger_type: str
    name: str
    description: Optional[str] = None
    chapter_number: Optional[int] = None

    # 引擎状态（可选）
    story_state: Optional[dict] = None
    character_masks: Optional[dict] = None
    emotion_ledger: Optional[dict] = None
    active_foreshadows: Optional[List[str]] = None
    outline: Optional[str] = None
    recent_summary: Optional[str] = None


class CreateSnapshotResponse(BaseModel):
    snapshot_id: str
    message: str = "快照已创建"


class SnapshotRollbackResponse(BaseModel):
    deleted_chapter_ids: List[str] = Field(default_factory=list)
    deleted_count: int = 0
    has_engine_state: bool = False


# ─── API Endpoints ────────────────────────────────────────────────

@router.get("/{novel_id}/snapshots", response_model=UnifiedSnapshotListResponse)
async def list_snapshots(
    novel_id: str,
    novel_service=Depends(get_novel_service),
    snapshot_service: SnapshotService = Depends(get_snapshot_service),
):
    """列出小说的所有快照"""
    if novel_service.get_novel(novel_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Novel not found")

    try:
        snapshots_raw = snapshot_service.list_snapshots(novel_id)
        snapshots = []
        for snap in snapshots_raw:
            snapshots.append(UnifiedSnapshotDTO(
                id=snap.get("id", ""),
                novel_id=novel_id,
                parent_snapshot_id=snap.get("parent_snapshot_id"),
                branch_name=snap.get("branch_name", "main"),
                trigger_type=snap.get("trigger_type", "AUTO"),
                name=snap.get("name", ""),
                description=snap.get("description"),
                chapter_pointers=snap.get("chapter_pointers", []),
                story_state=snap.get("story_state", {}),
                character_masks=snap.get("character_masks", {}),
                emotion_ledger=snap.get("emotion_ledger", {}),
                active_foreshadows=snap.get("active_foreshadows", []),
                outline=snap.get("outline", ""),
                recent_chapters_summary=snap.get("recent_chapters_summary", ""),
                created_at=snap.get("created_at", ""),
                bible_state=snap.get("bible_state", {}),
                foreshadow_state=snap.get("foreshadow_state", {}),
            ))
        return UnifiedSnapshotListResponse(snapshots=snapshots)
    except Exception as e:
        logger.error(f"列出快照失败: {e}")
        return UnifiedSnapshotListResponse()


@router.get("/{novel_id}/snapshots/{snapshot_id}", response_model=UnifiedSnapshotDTO)
async def get_snapshot(
    novel_id: str,
    snapshot_id: str,
    novel_service=Depends(get_novel_service),
    snapshot_service: SnapshotService = Depends(get_snapshot_service),
):
    """获取单个快照详情"""
    if novel_service.get_novel(novel_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Novel not found")

    snapshot = snapshot_service.get_snapshot(snapshot_id)
    if not snapshot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Snapshot not found")

    if snapshot.get("novel_id") != novel_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Snapshot does not belong to this novel")

    return UnifiedSnapshotDTO(
        id=snapshot.get("id", ""),
        novel_id=novel_id,
        parent_snapshot_id=snapshot.get("parent_snapshot_id"),
        branch_name=snapshot.get("branch_name", "main"),
        trigger_type=snapshot.get("trigger_type", "AUTO"),
        name=snapshot.get("name", ""),
        description=snapshot.get("description"),
        chapter_pointers=snapshot.get("chapter_pointers", []),
        story_state=snapshot.get("story_state", {}),
        character_masks=snapshot.get("character_masks", {}),
        emotion_ledger=snapshot.get("emotion_ledger", {}),
        active_foreshadows=snapshot.get("active_foreshadows", []),
        outline=snapshot.get("outline", ""),
        recent_chapters_summary=snapshot.get("recent_chapters_summary", ""),
        created_at=snapshot.get("created_at", ""),
        bible_state=snapshot.get("bible_state", {}),
        foreshadow_state=snapshot.get("foreshadow_state", {}),
    )


@router.post("/{novel_id}/snapshots", response_model=CreateSnapshotResponse, status_code=status.HTTP_201_CREATED)
async def create_snapshot(
    novel_id: str,
    body: CreateSnapshotRequest,
    novel_service=Depends(get_novel_service),
    snapshot_service: SnapshotService = Depends(get_snapshot_service),
):
    """创建新快照"""
    if novel_service.get_novel(novel_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Novel not found")

    try:
        snapshot_id = snapshot_service.create_snapshot(
            novel_id=novel_id,
            trigger_type=body.trigger_type,
            name=body.name,
            description=body.description,
            story_state=body.story_state,
            character_masks=body.character_masks,
            emotion_ledger=body.emotion_ledger,
            active_foreshadows=body.active_foreshadows,
            outline=body.outline or "",
            recent_summary=body.recent_summary or "",
        )
        return CreateSnapshotResponse(snapshot_id=snapshot_id)
    except Exception as e:
        logger.error(f"创建快照失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/{novel_id}/snapshots/{snapshot_id}/rollback",
    response_model=SnapshotRollbackResponse,
)
async def rollback_to_snapshot(
    novel_id: str,
    snapshot_id: str,
    novel_service=Depends(get_novel_service),
    snapshot_service: SnapshotService = Depends(get_snapshot_service),
):
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


@router.delete("/{novel_id}/snapshots/{snapshot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_snapshot(
    novel_id: str,
    snapshot_id: str,
    novel_service=Depends(get_novel_service),
    snapshot_service: SnapshotService = Depends(get_snapshot_service),
):
    """删除快照"""
    if novel_service.get_novel(novel_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Novel not found")

    snapshot = snapshot_service.get_snapshot(snapshot_id)
    if not snapshot:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Snapshot not found")

    if snapshot.get("novel_id") != novel_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Snapshot does not belong to this novel")

    try:
        # TODO: 实现 SnapshotService.delete_snapshot 方法
        logger.warning("delete_snapshot 功能尚未实现")
        # snapshot_service.delete_snapshot(snapshot_id)
    except Exception as e:
        logger.error(f"删除快照失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
