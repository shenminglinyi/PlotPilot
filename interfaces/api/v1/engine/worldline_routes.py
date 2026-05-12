"""世界线管理 API（故事 Git 模型）"""
import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from application.checkpoint.services.unified_checkpoint_service import UnifiedCheckpointService
from interfaces.api.dependencies import get_novel_service, get_unified_checkpoint_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/novels", tags=["worldline"])


# ─── Pydantic DTOs ────────────────────────────────────────────────

class CheckpointNodeDTO(BaseModel):
    id: str
    name: str
    trigger_type: str
    branch_name: str
    created_at: str
    anchor_chapter: Optional[int] = None


class CheckpointEdgeDTO(BaseModel):
    from_id: str = Field(alias="from")
    to_id: str = Field(alias="to")
    model_config = ConfigDict(populate_by_name=True)


class BranchInfoDTO(BaseModel):
    id: str = ""
    name: str
    head_id: str
    is_default: int = 0
    storyline_id: Optional[str] = None


class WorldlineGraphDTO(BaseModel):
    nodes: List[CheckpointNodeDTO] = Field(default_factory=list)
    edges: List[Dict[str, str]] = Field(default_factory=list)
    branches: List[BranchInfoDTO] = Field(default_factory=list)
    head_id: Optional[str] = None


class CreateCheckpointRequest(BaseModel):
    trigger_type: str = "MANUAL"
    name: str
    description: Optional[str] = None
    branch_name: str = "main"
    story_state: Optional[dict] = None
    character_masks: Optional[dict] = None
    emotion_ledger: Optional[dict] = None
    active_foreshadows: Optional[List[str]] = None
    outline: Optional[str] = None
    recent_summary: Optional[str] = None


class CreateCheckpointResponse(BaseModel):
    checkpoint_id: str
    message: str = "checkpoint 已创建"


class CreateBranchRequest(BaseModel):
    name: str
    from_checkpoint_id: str
    storyline_id: Optional[str] = None


class CreateBranchResponse(BaseModel):
    branch_id: str
    message: str = "分支已创建"


class CheckoutResponse(BaseModel):
    stash_id: str
    restored_chapters: int
    deleted_chapters: int
    message: str = "checkout 完成"


class HardResetResponse(BaseModel):
    stash_id: str
    restored_chapters: int
    deleted_chapters: int
    message: str = "hard_reset 完成"


class UpdateBranchRequest(BaseModel):
    name: Optional[str] = None
    storyline_id: Optional[str] = None


# ─── API Endpoints ────────────────────────────────────────────────

@router.get("/{novel_id}/worldline/graph", response_model=WorldlineGraphDTO)
async def get_worldline_graph(
    novel_id: str,
    novel_service=Depends(get_novel_service),
    svc: UnifiedCheckpointService = Depends(get_unified_checkpoint_service),
):
    """获取世界线图（节点 / 边 / 分支）"""
    if novel_service.get_novel(novel_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Novel not found")
    try:
        data = svc.get_checkpoint_graph(novel_id)
        return WorldlineGraphDTO(**data)
    except Exception as e:
        logger.error("get_worldline_graph 失败 novel=%s: %s", novel_id, e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/{novel_id}/worldline/checkpoints", response_model=List[CheckpointNodeDTO])
async def list_worldline_checkpoints(
    novel_id: str,
    novel_service=Depends(get_novel_service),
    svc: UnifiedCheckpointService = Depends(get_unified_checkpoint_service),
):
    """列出小说所有 checkpoint"""
    if novel_service.get_novel(novel_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Novel not found")
    try:
        items = svc.list_checkpoints(novel_id)
        return [CheckpointNodeDTO(**item) for item in items]
    except Exception as e:
        logger.error("list_worldline_checkpoints 失败 novel=%s: %s", novel_id, e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/{novel_id}/worldline/checkpoints",
    response_model=CreateCheckpointResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_worldline_checkpoint(
    novel_id: str,
    body: CreateCheckpointRequest,
    novel_service=Depends(get_novel_service),
    svc: UnifiedCheckpointService = Depends(get_unified_checkpoint_service),
):
    """手动创建 checkpoint"""
    if novel_service.get_novel(novel_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Novel not found")
    try:
        checkpoint_id = svc.create_checkpoint(
            novel_id=novel_id,
            trigger_type=body.trigger_type,
            name=body.name,
            description=body.description,
            branch_name=body.branch_name,
            story_state=body.story_state,
            character_masks=body.character_masks,
            emotion_ledger=body.emotion_ledger,
            active_foreshadows=body.active_foreshadows,
            outline=body.outline,
            recent_summary=body.recent_summary,
        )
        return CreateCheckpointResponse(checkpoint_id=checkpoint_id)
    except Exception as e:
        logger.error("create_worldline_checkpoint 失败 novel=%s: %s", novel_id, e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/{novel_id}/worldline/checkpoints/{checkpoint_id}",
    response_model=CheckpointNodeDTO,
)
async def get_worldline_checkpoint(
    novel_id: str,
    checkpoint_id: str,
    novel_service=Depends(get_novel_service),
    svc: UnifiedCheckpointService = Depends(get_unified_checkpoint_service),
):
    """获取单个 checkpoint 详情"""
    if novel_service.get_novel(novel_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Novel not found")
    try:
        data = svc.get_checkpoint(checkpoint_id)
        if data is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Checkpoint not found")
        return CheckpointNodeDTO(**data)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_worldline_checkpoint 失败 novel=%s checkpoint=%s: %s", novel_id, checkpoint_id, e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.delete(
    "/{novel_id}/worldline/checkpoints/{checkpoint_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_worldline_checkpoint(
    novel_id: str,
    checkpoint_id: str,
    novel_service=Depends(get_novel_service),
    svc: UnifiedCheckpointService = Depends(get_unified_checkpoint_service),
):
    """软删除 checkpoint"""
    if novel_service.get_novel(novel_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Novel not found")
    try:
        svc.delete_checkpoint(checkpoint_id)
    except Exception as e:
        logger.error("delete_worldline_checkpoint 失败 novel=%s checkpoint=%s: %s", novel_id, checkpoint_id, e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/{novel_id}/worldline/branches", response_model=List[BranchInfoDTO])
async def list_worldline_branches(
    novel_id: str,
    novel_service=Depends(get_novel_service),
    svc: UnifiedCheckpointService = Depends(get_unified_checkpoint_service),
):
    """列出小说所有分支"""
    if novel_service.get_novel(novel_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Novel not found")
    try:
        items = svc.list_branches(novel_id)
        return [BranchInfoDTO(**item) for item in items]
    except Exception as e:
        logger.error("list_worldline_branches 失败 novel=%s: %s", novel_id, e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/{novel_id}/worldline/branches",
    response_model=CreateBranchResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_worldline_branch(
    novel_id: str,
    body: CreateBranchRequest,
    novel_service=Depends(get_novel_service),
    svc: UnifiedCheckpointService = Depends(get_unified_checkpoint_service),
):
    """创建新分支"""
    if novel_service.get_novel(novel_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Novel not found")
    try:
        branch_id = svc.create_branch(
            novel_id=novel_id,
            name=body.name,
            from_checkpoint_id=body.from_checkpoint_id,
            storyline_id=body.storyline_id,
        )
        return CreateBranchResponse(branch_id=branch_id)
    except Exception as e:
        logger.error("create_worldline_branch 失败 novel=%s: %s", novel_id, e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/{novel_id}/worldline/branches/by-storyline/{storyline_id}",
    response_model=Optional[BranchInfoDTO],
)
async def get_branch_by_storyline(
    novel_id: str,
    storyline_id: str,
    novel_service=Depends(get_novel_service),
    svc: UnifiedCheckpointService = Depends(get_unified_checkpoint_service),
):
    """查找与指定故事线绑定的世界线分支"""
    if novel_service.get_novel(novel_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Novel not found")
    try:
        branch = svc.get_branch_by_storyline(novel_id, storyline_id)
        if branch is None:
            return None
        return BranchInfoDTO(**branch)
    except Exception as e:
        logger.error("get_branch_by_storyline 失败 novel=%s storyline=%s: %s", novel_id, storyline_id, e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.put(
    "/{novel_id}/worldline/branches/{branch_id}",
    response_model=BranchInfoDTO,
)
async def update_worldline_branch(
    novel_id: str,
    branch_id: str,
    body: UpdateBranchRequest,
    novel_service=Depends(get_novel_service),
    svc: UnifiedCheckpointService = Depends(get_unified_checkpoint_service),
):
    """更新分支（重命名 / 绑定故事线）"""
    if novel_service.get_novel(novel_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Novel not found")
    try:
        svc.update_branch(branch_id, name=body.name, storyline_id=body.storyline_id)
        items = svc.list_branches(novel_id)
        for item in items:
            if item.get("id") == branch_id:
                return BranchInfoDTO(**item)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branch not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("update_worldline_branch 失败 novel=%s branch=%s: %s", novel_id, branch_id, e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/{novel_id}/worldline/checkpoints/{checkpoint_id}/checkout",
    response_model=CheckoutResponse,
)
async def checkout_worldline(
    novel_id: str,
    checkpoint_id: str,
    novel_service=Depends(get_novel_service),
    svc: UnifiedCheckpointService = Depends(get_unified_checkpoint_service),
):
    """非破坏性 checkout（章节内容可能被替换，旧内容存入 stash）"""
    if novel_service.get_novel(novel_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Novel not found")
    try:
        logger.warning(
            "checkout 操作将替换 novel=%s 的章节内容，旧内容存入 stash，checkpoint=%s",
            novel_id,
            checkpoint_id,
        )
        result = svc.checkout(novel_id, checkpoint_id)
        return CheckoutResponse(
            stash_id=result["stash_id"],
            restored_chapters=result["restored_chapters"],
            deleted_chapters=result["deleted_chapters"],
        )
    except Exception as e:
        logger.error("checkout 失败 novel=%s checkpoint=%s: %s", novel_id, checkpoint_id, e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/{novel_id}/worldline/checkpoints/{checkpoint_id}/hard-reset",
    response_model=HardResetResponse,
)
async def hard_reset_worldline(
    novel_id: str,
    checkpoint_id: str,
    novel_service=Depends(get_novel_service),
    svc: UnifiedCheckpointService = Depends(get_unified_checkpoint_service),
):
    """破坏性 hard reset（不可撤销，直接删除 checkpoint 之后的所有章节）"""
    if novel_service.get_novel(novel_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Novel not found")
    try:
        result = svc.hard_reset(novel_id, checkpoint_id)
        return HardResetResponse(
            stash_id=result["stash_id"],
            restored_chapters=result["restored_chapters"],
            deleted_chapters=result["deleted_chapters"],
        )
    except Exception as e:
        logger.error("hard_reset 失败 novel=%s checkpoint=%s: %s", novel_id, checkpoint_id, e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
