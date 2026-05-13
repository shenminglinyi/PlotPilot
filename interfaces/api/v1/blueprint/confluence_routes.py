"""汇流点 CRUD API"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from infrastructure.persistence.database.sqlite_confluence_point_repository import SqliteConfluencePointRepository
from domain.novel.entities.confluence_point import ConfluencePoint, VALID_MERGE_TYPES
from interfaces.api.dependencies import get_confluence_point_repository

router = APIRouter(prefix="/novels/{novel_id}/confluence-points", tags=["confluence-points"])


class ConfluencePointCreate(BaseModel):
    source_storyline_id: str
    target_storyline_id: str
    target_chapter: int = Field(ge=1)
    merge_type: str = "absorb"
    context_summary: str = ""
    pre_reveal_hint: str = ""
    behavior_guards: List[str] = Field(default_factory=list)


class ConfluencePointUpdate(BaseModel):
    target_chapter: Optional[int] = Field(None, ge=1)
    merge_type: Optional[str] = None
    context_summary: Optional[str] = None
    pre_reveal_hint: Optional[str] = None
    behavior_guards: Optional[List[str]] = None
    resolved: Optional[bool] = None


def _to_dict(cp: ConfluencePoint) -> Dict[str, Any]:
    return {
        "id": cp.id,
        "novel_id": cp.novel_id,
        "source_storyline_id": cp.source_storyline_id,
        "target_storyline_id": cp.target_storyline_id,
        "target_chapter": cp.target_chapter,
        "merge_type": cp.merge_type,
        "context_summary": cp.context_summary,
        "pre_reveal_hint": cp.pre_reveal_hint,
        "behavior_guards": cp.behavior_guards,
        "resolved": cp.resolved,
    }


@router.get("")
async def list_confluence_points(
    novel_id: str,
    repo: SqliteConfluencePointRepository = Depends(get_confluence_point_repository),
) -> List[Dict[str, Any]]:
    return [_to_dict(cp) for cp in repo.get_by_novel_id(novel_id)]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_confluence_point(
    novel_id: str,
    body: ConfluencePointCreate,
    repo: SqliteConfluencePointRepository = Depends(get_confluence_point_repository),
) -> Dict[str, Any]:
    if body.merge_type not in VALID_MERGE_TYPES:
        raise HTTPException(status_code=422, detail=f"merge_type must be one of {list(VALID_MERGE_TYPES)}")
    cp = ConfluencePoint(
        id=str(uuid.uuid4()),
        novel_id=novel_id,
        source_storyline_id=body.source_storyline_id,
        target_storyline_id=body.target_storyline_id,
        target_chapter=body.target_chapter,
        merge_type=body.merge_type,
        context_summary=body.context_summary,
        pre_reveal_hint=body.pre_reveal_hint,
        behavior_guards=body.behavior_guards,
    )
    repo.save(cp)
    return _to_dict(cp)


@router.patch("/{cp_id}")
async def update_confluence_point(
    novel_id: str,
    cp_id: str,
    body: ConfluencePointUpdate,
    repo: SqliteConfluencePointRepository = Depends(get_confluence_point_repository),
) -> Dict[str, Any]:
    cp = repo.get_by_id(cp_id)
    if not cp or cp.novel_id != novel_id:
        raise HTTPException(status_code=404, detail="Confluence point not found")
    if body.target_chapter is not None:
        cp.target_chapter = body.target_chapter
    if body.merge_type is not None:
        if body.merge_type not in VALID_MERGE_TYPES:
            raise HTTPException(status_code=422, detail="invalid merge_type")
        cp.merge_type = body.merge_type
    if body.context_summary is not None:
        cp.context_summary = body.context_summary
    if body.pre_reveal_hint is not None:
        cp.pre_reveal_hint = body.pre_reveal_hint
    if body.behavior_guards is not None:
        cp.behavior_guards = body.behavior_guards
    if body.resolved is not None:
        cp.resolved = body.resolved
    repo.save(cp)
    return _to_dict(cp)


@router.delete("/{cp_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_confluence_point(
    novel_id: str,
    cp_id: str,
    repo: SqliteConfluencePointRepository = Depends(get_confluence_point_repository),
):
    cp = repo.get_by_id(cp_id)
    if not cp or cp.novel_id != novel_id:
        raise HTTPException(status_code=404, detail="Confluence point not found")
    repo.delete(cp_id)
