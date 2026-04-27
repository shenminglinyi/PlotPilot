"""Chapter candidate draft API routes."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Path
from pydantic import BaseModel, Field

from application.core.dtos.chapter_candidate_draft_dto import ChapterCandidateDraftDTO
from application.engine.services.chapter_aftermath_pipeline import ChapterAftermathPipeline
from domain.shared.exceptions import EntityNotFoundError
from interfaces.api.dependencies import (
    get_chapter_aftermath_pipeline,
    get_chapter_candidate_draft_service,
    get_novel_service,
    get_snapshot_service,
)


async def _run_candidate_draft_aftermath(
    novel_id: str,
    chapter_number: int,
    content: str,
    pipeline: ChapterAftermathPipeline,
) -> None:
    await pipeline.run_after_chapter_saved(novel_id, chapter_number, content)


router = APIRouter(prefix="/novels", tags=["chapter-candidate-drafts"])


class CreateChapterCandidateDraftRequest(BaseModel):
    source: str = Field(..., min_length=1, max_length=50)
    title: str = Field(default="", max_length=200)
    content: str = Field(..., min_length=1)
    rationale: str = Field(default="", max_length=2000)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    branch_name: str = Field(default="main", max_length=100)


class ChapterCandidateDraftResponse(BaseModel):
    id: str
    novel_id: str
    chapter_number: int
    branch_name: str
    source: str
    status: str
    title: str
    content: str
    rationale: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str

    @classmethod
    def from_dto(cls, dto: ChapterCandidateDraftDTO) -> "ChapterCandidateDraftResponse":
        return cls(
            id=dto.id,
            novel_id=dto.novel_id,
            chapter_number=dto.chapter_number,
            branch_name=dto.branch_name,
            source=dto.source,
            status=dto.status,
            title=dto.title,
            content=dto.content,
            rationale=dto.rationale,
            metadata=dto.metadata,
            created_at=dto.created_at,
            updated_at=dto.updated_at,
        )


class AcceptChapterCandidateDraftResponse(BaseModel):
    draft: ChapterCandidateDraftResponse
    chapter: Dict[str, Any]
    snapshot_id: str


@router.post(
    "/{novel_id}/chapters/{chapter_number}/candidate-drafts",
    response_model=ChapterCandidateDraftResponse,
    status_code=201,
)
async def create_candidate_draft(
    novel_id: str,
    request: CreateChapterCandidateDraftRequest,
    chapter_number: int = Path(..., ge=1),
    novel_service=Depends(get_novel_service),
    service=Depends(get_chapter_candidate_draft_service),
):
    if novel_service.get_novel(novel_id) is None:
        raise HTTPException(status_code=404, detail="Novel not found")

    draft = service.create_draft(
        novel_id=novel_id,
        chapter_number=chapter_number,
        source=request.source,
        title=request.title,
        content=request.content,
        rationale=request.rationale,
        metadata=request.metadata,
        branch_name=request.branch_name,
    )
    return ChapterCandidateDraftResponse.from_dto(draft)


@router.get(
    "/{novel_id}/chapters/{chapter_number}/candidate-drafts",
    response_model=List[ChapterCandidateDraftResponse],
)
async def list_candidate_drafts(
    novel_id: str,
    chapter_number: int = Path(..., ge=1),
    branch_name: Optional[str] = None,
    novel_service=Depends(get_novel_service),
    service=Depends(get_chapter_candidate_draft_service),
):
    if novel_service.get_novel(novel_id) is None:
        raise HTTPException(status_code=404, detail="Novel not found")

    drafts = service.list_drafts(
        novel_id,
        chapter_number,
        branch_name=branch_name,
    )
    return [ChapterCandidateDraftResponse.from_dto(item) for item in drafts]


@router.post(
    "/{novel_id}/chapters/{chapter_number}/candidate-drafts/{draft_id}/accept",
    response_model=AcceptChapterCandidateDraftResponse,
)
async def accept_candidate_draft(
    novel_id: str,
    draft_id: str,
    background_tasks: BackgroundTasks,
    chapter_number: int = Path(..., ge=1),
    novel_service=Depends(get_novel_service),
    service=Depends(get_chapter_candidate_draft_service),
    pipeline: ChapterAftermathPipeline = Depends(get_chapter_aftermath_pipeline),
    snapshot_service=Depends(get_snapshot_service),
):
    if novel_service.get_novel(novel_id) is None:
        raise HTTPException(status_code=404, detail="Novel not found")

    try:
        accepted = service.accept_draft_as_primary(draft_id)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    draft = accepted["draft"]
    chapter = accepted["chapter"]

    if draft.novel_id != novel_id or draft.chapter_number != chapter_number:
        raise HTTPException(status_code=400, detail="Draft chapter mismatch")

    snapshot_id = snapshot_service.create_snapshot(
        novel_id=novel_id,
        trigger_type="MANUAL",
        name=f"[候选稿采纳] 第{chapter_number}章 · {draft.source}",
        description=draft.rationale or "accept candidate draft as primary chapter",
        branch_name=draft.branch_name or "main",
    )
    background_tasks.add_task(
        _run_candidate_draft_aftermath,
        novel_id,
        chapter_number,
        chapter.content,
        pipeline,
    )
    return AcceptChapterCandidateDraftResponse(
        draft=ChapterCandidateDraftResponse.from_dto(draft),
        chapter={
            "id": chapter.id,
            "novel_id": chapter.novel_id,
            "number": chapter.number,
            "title": chapter.title,
            "content": chapter.content,
            "word_count": chapter.word_count,
            "status": chapter.status,
        },
        snapshot_id=snapshot_id,
    )


@router.post(
    "/{novel_id}/chapters/{chapter_number}/candidate-drafts/{draft_id}/reject",
    response_model=ChapterCandidateDraftResponse,
)
async def reject_candidate_draft(
    novel_id: str,
    draft_id: str,
    chapter_number: int = Path(..., ge=1),
    novel_service=Depends(get_novel_service),
    service=Depends(get_chapter_candidate_draft_service),
):
    if novel_service.get_novel(novel_id) is None:
        raise HTTPException(status_code=404, detail="Novel not found")
    try:
        draft = service.reject_draft(draft_id)
    except EntityNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    if draft.novel_id != novel_id or draft.chapter_number != chapter_number:
        raise HTTPException(status_code=400, detail="Draft chapter mismatch")
    return ChapterCandidateDraftResponse.from_dto(draft)
