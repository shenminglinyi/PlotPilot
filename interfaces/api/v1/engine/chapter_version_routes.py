import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from application.snapshot.services.chapter_version_service import ChapterVersionService
from interfaces.api.dependencies import get_chapter_version_service, get_novel_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/novels", tags=["chapter-versions"])


class VersionItem(BaseModel):
    version_id: str
    chapter_id: str
    novel_id: str
    chapter_number: int
    summary: str = ""
    created_at: str


class VersionListResponse(BaseModel):
    versions: List[VersionItem]


class DiffResponse(BaseModel):
    v1_id: str
    v2_id: str
    additions: List[str]
    deletions: List[str]


class RollbackRequest(BaseModel):
    version_id: str = Field(..., description="要回滚到的版本ID")


class RollbackResponse(BaseModel):
    snapshot_version_id: str
    restored_version_id: str


@router.get(
    "/{novel_id}/chapters/{chapter_number}/versions",
    response_model=VersionListResponse,
)
async def list_chapter_versions(
    novel_id: str,
    chapter_number: int,
    novel_service=Depends(get_novel_service),
    version_service: ChapterVersionService = Depends(get_chapter_version_service),
) -> VersionListResponse:
    if novel_service.get_novel(novel_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Novel not found")

    rows = version_service.list_versions(novel_id, chapter_number)
    versions = [
        VersionItem(
            version_id=r["id"],
            chapter_id=r.get("chapter_id", ""),
            novel_id=r["novel_id"],
            chapter_number=r["chapter_number"],
            summary=r.get("summary", ""),
            created_at=r.get("created_at", ""),
        )
        for r in rows
    ]
    return VersionListResponse(versions=versions)


@router.get(
    "/{novel_id}/chapters/{chapter_number}/diff",
    response_model=DiffResponse,
)
async def diff_chapter_versions(
    novel_id: str,
    chapter_number: int,
    v1: str = Query(..., description="旧版本ID"),
    v2: str = Query(..., description="新版本ID"),
    novel_service=Depends(get_novel_service),
    version_service: ChapterVersionService = Depends(get_chapter_version_service),
) -> DiffResponse:
    if novel_service.get_novel(novel_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Novel not found")

    try:
        result = version_service.diff_versions(novel_id, chapter_number, v1, v2)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    return DiffResponse(
        v1_id=result["v1_id"],
        v2_id=result["v2_id"],
        additions=result["additions"],
        deletions=result["deletions"],
    )


@router.post(
    "/{novel_id}/chapters/{chapter_number}/rollback",
    response_model=RollbackResponse,
)
async def rollback_chapter_version(
    novel_id: str,
    chapter_number: int,
    request: RollbackRequest,
    novel_service=Depends(get_novel_service),
    version_service: ChapterVersionService = Depends(get_chapter_version_service),
) -> RollbackResponse:
    if novel_service.get_novel(novel_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Novel not found")

    try:
        result = version_service.rollback_to_version(
            novel_id, chapter_number, request.version_id
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    return RollbackResponse(
        snapshot_version_id=result["snapshot_version_id"],
        restored_version_id=result["restored_version_id"],
    )
