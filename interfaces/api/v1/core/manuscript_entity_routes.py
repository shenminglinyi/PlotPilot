"""手稿实体 API：词表、章节提及、道具（与正文 [[kind:id|label]] 及知识库联动）。"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, Field
from starlette.responses import Response

from application.manuscript.reindex_job import reindex_chapter_entity_mentions
from domain.novel.value_objects.novel_id import NovelId
from infrastructure.persistence.database.connection import get_database
from infrastructure.persistence.database.manuscript_entity_repository import ManuscriptEntityRepository
from infrastructure.persistence.database.sqlite_bible_repository import SqliteBibleRepository

from application.core.services.chapter_service import ChapterService
from interfaces.api.dependencies import get_chapter_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["manuscript"])


class PropCreateBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    aliases: List[str] = Field(default_factory=list)
    holder_character_id: Optional[str] = None
    first_chapter: Optional[int] = Field(default=None, ge=1)


class PropPatchBody(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = None
    aliases: Optional[List[str]] = None
    holder_character_id: Optional[str] = None
    first_chapter: Optional[int] = Field(default=None, ge=1)


@router.get("/{novel_id}/manuscript/entity-lexicon")
def get_entity_lexicon(novel_id: str) -> Dict[str, Any]:
    db = get_database()
    bible = SqliteBibleRepository(db).get_by_novel_id(NovelId(novel_id))
    mrepo = ManuscriptEntityRepository(db)
    props = mrepo.list_props(novel_id)
    if not bible:
        return {"characters": [], "locations": [], "props": props}
    chars = [
        {"id": c.character_id.value, "name": c.name, "aliases": []}
        for c in bible.characters
    ]
    locs = [
        {
            "id": loc.id,
            "name": loc.name,
            "location_type": getattr(loc, "location_type", None) or "other",
            "aliases": [],
        }
        for loc in bible.locations
    ]
    return {"characters": chars, "locations": locs, "props": props}


@router.get("/{novel_id}/chapters/{chapter_number}/entity-mentions")
def list_entity_mentions(
    novel_id: str,
    chapter_number: int = Path(..., gt=0),
):
    mrepo = ManuscriptEntityRepository(get_database())
    return {"mentions": mrepo.list_chapter_mentions(novel_id, chapter_number)}


@router.post("/{novel_id}/chapters/{chapter_number}/entity-mentions/reindex")
def reindex_entity_mentions(
    novel_id: str,
    chapter_number: int = Path(..., gt=0),
    content: Optional[str] = Query(None, description="不传则从章节库读取当前正文"),
    chapter_service: ChapterService = Depends(get_chapter_service),
):
    text = content
    if text is None:
        ch = chapter_service.get_chapter_by_novel_and_number(novel_id, chapter_number)
        if ch is None:
            raise HTTPException(status_code=404, detail="章节不存在")
        text = ch.content or ""
    reindex_chapter_entity_mentions(novel_id, chapter_number, text)
    mrepo = ManuscriptEntityRepository(get_database())
    return {"ok": True, "mentions": mrepo.list_chapter_mentions(novel_id, chapter_number)}


@router.get("/{novel_id}/manuscript/props")
def list_props(novel_id: str):
    return {"props": ManuscriptEntityRepository(get_database()).list_props(novel_id)}


def _validate_holder(novel_id: str, holder_character_id: Optional[str]) -> None:
    """校验 holder_character_id 确实存在于 bible_characters 表。"""
    if not holder_character_id:
        return
    db = get_database()
    row = db.fetch_one(
        "SELECT id FROM bible_characters WHERE id = ? AND novel_id = ?",
        (holder_character_id, novel_id),
    )
    if not row:
        raise HTTPException(
            status_code=422,
            detail=f"持有者角色 ID '{holder_character_id}' 不存在于本作 Bible，请先在世界观中创建该角色",
        )


@router.post("/{novel_id}/manuscript/props")
def create_prop(novel_id: str, body: PropCreateBody):
    _validate_holder(novel_id, body.holder_character_id)
    repo = ManuscriptEntityRepository(get_database())
    row = repo.create_prop(
        novel_id,
        name=body.name,
        description=body.description,
        aliases=body.aliases,
        holder_character_id=body.holder_character_id,
        first_chapter=body.first_chapter,
    )
    return row


@router.patch("/{novel_id}/manuscript/props/{prop_id}")
def patch_prop(novel_id: str, prop_id: str, body: PropPatchBody):
    if body.holder_character_id is not None:
        _validate_holder(novel_id, body.holder_character_id)
    repo = ManuscriptEntityRepository(get_database())
    if not repo.get_prop(novel_id, prop_id):
        raise HTTPException(status_code=404, detail="道具不存在")
    repo.update_prop(
        novel_id,
        prop_id,
        name=body.name,
        description=body.description,
        aliases=body.aliases,
        holder_character_id=body.holder_character_id,
        first_chapter=body.first_chapter,
    )
    return repo.get_prop(novel_id, prop_id)


@router.delete("/{novel_id}/manuscript/props/{prop_id}", status_code=204)
def delete_prop(novel_id: str, prop_id: str):
    repo = ManuscriptEntityRepository(get_database())
    if not repo.get_prop(novel_id, prop_id):
        raise HTTPException(status_code=404, detail="道具不存在")
    repo.delete_prop(novel_id, prop_id)
    return Response(status_code=204)
