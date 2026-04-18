"""伏笔手账本 API：主角/读者当下的疑问，本阶段兑现即可（不必写长文）。"""
from fastapi import APIRouter, Depends, HTTPException, Path
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime
from dataclasses import replace

from domain.novel.repositories.foreshadowing_repository import ForeshadowingRepository
from domain.novel.entities.subtext_ledger_entry import SubtextLedgerEntry
from domain.novel.value_objects.novel_id import NovelId
from domain.shared.exceptions import InvalidOperationError
from interfaces.api.dependencies import get_foreshadowing_repository


router = APIRouter(tags=["foreshadow-ledger"])


class CreateSubtextEntryRequest(BaseModel):
    entry_id: str = Field(..., description="条目 ID")
    chapter: int = Field(..., ge=1, description="埋入章节")
    character_id: str = Field(..., description="关联角色")
    question: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="当下的疑问（主角或读者视角），宜短句",
    )


class UpdateSubtextEntryRequest(BaseModel):
    chapter: Optional[int] = Field(None, ge=1)
    character_id: Optional[str] = None
    question: Optional[str] = Field(None, min_length=1, max_length=4000)
    status: Optional[str] = Field(None, description="pending | consumed")
    consumed_at_chapter: Optional[int] = Field(None, ge=1)


class SubtextEntryResponse(BaseModel):
    id: str
    chapter: int
    character_id: str
    question: str
    status: str
    consumed_at_chapter: Optional[int]
    suggested_resolve_chapter: Optional[int] = None
    resolve_chapter_window: Optional[int] = None
    importance: str = "medium"
    created_at: str


def _entry_to_response(entry: SubtextLedgerEntry) -> SubtextEntryResponse:
    return SubtextEntryResponse(
        id=entry.id,
        chapter=entry.chapter,
        character_id=entry.character_id,
        question=entry.question,
        status=entry.status,
        consumed_at_chapter=entry.consumed_at_chapter,
        suggested_resolve_chapter=getattr(entry, "suggested_resolve_chapter", None),
        resolve_chapter_window=getattr(entry, "resolve_chapter_window", None),
        importance=getattr(entry, "importance", "medium"),
        created_at=entry.created_at.isoformat(),
    )


@router.post("/novels/{novel_id}/foreshadow-ledger", response_model=SubtextEntryResponse, status_code=201)
def create_subtext_entry(
    novel_id: str = Path(..., description="小说 ID"),
    request: CreateSubtextEntryRequest = ...,
    repo: ForeshadowingRepository = Depends(get_foreshadowing_repository),
):
    try:
        registry = repo.get_by_novel_id(NovelId(novel_id))
        if not registry:
            raise HTTPException(status_code=404, detail=f"Novel {novel_id} not found")

        entry = SubtextLedgerEntry(
            id=request.entry_id,
            chapter=request.chapter,
            character_id=request.character_id.strip(),
            question=request.question.strip(),
            status="pending",
        )
        registry.add_subtext_entry(entry)
        repo.save(registry)
        return _entry_to_response(entry)
    except InvalidOperationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/novels/{novel_id}/foreshadow-ledger", response_model=List[SubtextEntryResponse])
def list_subtext_entries(
    novel_id: str = Path(..., description="小说 ID"),
    status: Optional[str] = None,
    repo: ForeshadowingRepository = Depends(get_foreshadowing_repository),
):
    try:
        registry = repo.get_by_novel_id(NovelId(novel_id))
        if not registry:
            raise HTTPException(status_code=404, detail=f"Novel {novel_id} not found")

        results: List[SubtextEntryResponse] = []

        from domain.novel.value_objects.foreshadowing import ForeshadowingStatus

        for f in registry.foreshadowings:
            entry_status = "pending" if f.status == ForeshadowingStatus.PLANTED else "consumed"
            if status and entry_status != status:
                continue
            results.append(
                SubtextEntryResponse(
                    id=f.id,
                    chapter=f.planted_in_chapter,
                    character_id="",
                    question=f.description,
                    status=entry_status,
                    consumed_at_chapter=f.resolved_in_chapter,
                    created_at=datetime.utcnow().isoformat(),
                )
            )

        for e in registry.subtext_entries:
            if status and e.status != status:
                continue
            results.append(_entry_to_response(e))

        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/novels/{novel_id}/foreshadow-ledger/{entry_id}", response_model=SubtextEntryResponse)
def get_subtext_entry(
    novel_id: str = Path(..., description="小说 ID"),
    entry_id: str = Path(..., description="条目 ID"),
    repo: ForeshadowingRepository = Depends(get_foreshadowing_repository),
):
    registry = repo.get_by_novel_id(NovelId(novel_id))
    if not registry:
        raise HTTPException(status_code=404, detail=f"Novel {novel_id} not found")

    entry = registry.get_subtext_entry_by_id(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Entry {entry_id} not found")

    return _entry_to_response(entry)


@router.put("/novels/{novel_id}/foreshadow-ledger/{entry_id}", response_model=SubtextEntryResponse)
def update_subtext_entry(
    novel_id: str = Path(..., description="小说 ID"),
    entry_id: str = Path(..., description="条目 ID"),
    request: UpdateSubtextEntryRequest = ...,
    repo: ForeshadowingRepository = Depends(get_foreshadowing_repository),
):
    try:
        registry = repo.get_by_novel_id(NovelId(novel_id))
        if not registry:
            raise HTTPException(status_code=404, detail=f"Novel {novel_id} not found")

        entry = registry.get_subtext_entry_by_id(entry_id)
        if not entry:
            raise HTTPException(status_code=404, detail=f"Entry {entry_id} not found")

        new_q = request.question.strip() if request.question is not None else entry.question
        new_char = request.character_id.strip() if request.character_id is not None else entry.character_id

        updated_entry = replace(
            entry,
            chapter=request.chapter if request.chapter is not None else entry.chapter,
            character_id=new_char,
            question=new_q,
            status=request.status if request.status is not None else entry.status,
            consumed_at_chapter=(
                request.consumed_at_chapter
                if request.consumed_at_chapter is not None
                else entry.consumed_at_chapter
            ),
        )

        registry.update_subtext_entry(entry_id, updated_entry)
        repo.save(registry)
        return _entry_to_response(updated_entry)
    except InvalidOperationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete("/novels/{novel_id}/foreshadow-ledger/{entry_id}", status_code=204)
def delete_subtext_entry(
    novel_id: str = Path(..., description="小说 ID"),
    entry_id: str = Path(..., description="条目 ID"),
    repo: ForeshadowingRepository = Depends(get_foreshadowing_repository),
):
    try:
        registry = repo.get_by_novel_id(NovelId(novel_id))
        if not registry:
            raise HTTPException(status_code=404, detail=f"Novel {novel_id} not found")

        registry.remove_subtext_entry(entry_id)
        repo.save(registry)
    except InvalidOperationError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
