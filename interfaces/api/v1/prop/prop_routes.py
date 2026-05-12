"""道具全套 API

GET    /novels/{novel_id}/props                    → 列出所有道具
POST   /novels/{novel_id}/props                    → 创建道具
GET    /novels/{novel_id}/props/{prop_id}          → 单个道具详情
PATCH  /novels/{novel_id}/props/{prop_id}          → 更新道具
DELETE /novels/{novel_id}/props/{prop_id}          → 删除道具
GET    /novels/{novel_id}/props/{prop_id}/events   → 事件时间线
POST   /novels/{novel_id}/props/{prop_id}/events   → 手动记录事件
"""
from __future__ import annotations
import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from domain.shared.time_utils import utcnow_iso
from interfaces.api.dependencies import (
    get_unified_prop_repository,
    get_prop_event_repository,
    get_novel_service,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/novels", tags=["props"])


# ─── DTOs ──────────────────────────────────────────────────────────────────

class PropDTO(BaseModel):
    id: str
    novel_id: str
    name: str
    description: str = ""
    aliases: List[str] = Field(default_factory=list)
    prop_category: str = "OTHER"
    lifecycle_state: str = "DORMANT"
    introduced_chapter: Optional[int] = None
    resolved_chapter: Optional[int] = None
    holder_character_id: Optional[str] = None
    attributes: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""


class CreatePropBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    aliases: List[str] = Field(default_factory=list)
    prop_category: str = "OTHER"
    holder_character_id: Optional[str] = None
    introduced_chapter: Optional[int] = None
    attributes: Dict[str, Any] = Field(default_factory=dict)


class PatchPropBody(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    aliases: Optional[List[str]] = None
    prop_category: Optional[str] = None
    lifecycle_state: Optional[str] = None
    holder_character_id: Optional[str] = None
    introduced_chapter: Optional[int] = None
    attributes: Optional[Dict[str, Any]] = None


class PropEventDTO(BaseModel):
    id: str
    prop_id: str
    chapter_number: int
    event_type: str
    source: str
    description: str = ""
    actor_character_id: Optional[str] = None
    from_holder_id: Optional[str] = None
    to_holder_id: Optional[str] = None
    created_at: str = ""


class CreateEventBody(BaseModel):
    chapter_number: int = Field(..., ge=1)
    event_type: str
    description: str = ""
    actor_character_id: Optional[str] = None
    from_holder_id: Optional[str] = None
    to_holder_id: Optional[str] = None


# ─── Helpers ───────────────────────────────────────────────────────────────

def _check_novel(novel_id: str, novel_service) -> None:
    if novel_service.get_novel(novel_id) is None:
        raise HTTPException(status_code=404, detail="Novel not found")


def _prop_to_dto(prop) -> PropDTO:
    return PropDTO(
        id=prop.id.value,
        novel_id=prop.novel_id,
        name=prop.name,
        description=prop.description,
        aliases=prop.aliases,
        prop_category=prop.category.value,
        lifecycle_state=prop.lifecycle_state.value,
        introduced_chapter=prop.introduced_chapter,
        resolved_chapter=prop.resolved_chapter,
        holder_character_id=prop.holder_character_id,
        attributes=prop.attributes,
        created_at=prop.created_at,
        updated_at=prop.updated_at,
    )


# ─── Endpoints ─────────────────────────────────────────────────────────────

@router.get("/{novel_id}/props", response_model=List[PropDTO])
async def list_props(
    novel_id: str,
    novel_service=Depends(get_novel_service),
    repo=Depends(get_unified_prop_repository),
):
    _check_novel(novel_id, novel_service)
    return [_prop_to_dto(p) for p in repo.list_by_novel(novel_id)]


@router.post("/{novel_id}/props", response_model=PropDTO, status_code=201)
async def create_prop(
    novel_id: str,
    body: CreatePropBody,
    novel_service=Depends(get_novel_service),
    repo=Depends(get_unified_prop_repository),
):
    _check_novel(novel_id, novel_service)
    from domain.prop.entities.prop import Prop
    from domain.prop.value_objects.prop_id import PropId
    from domain.prop.value_objects.prop_category import PropCategory
    now = utcnow_iso()
    try:
        prop = Prop(
            id=PropId.generate(),
            novel_id=novel_id,
            name=body.name,
            description=body.description,
            aliases=body.aliases,
            category=PropCategory(body.prop_category),
            holder_character_id=body.holder_character_id,
            introduced_chapter=body.introduced_chapter,
            attributes=body.attributes,
            created_at=now,
            updated_at=now,
        )
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=422, detail=str(e))
    repo.save(prop)
    return _prop_to_dto(prop)


@router.get("/{novel_id}/props/{prop_id}", response_model=PropDTO)
async def get_prop(
    novel_id: str,
    prop_id: str,
    novel_service=Depends(get_novel_service),
    repo=Depends(get_unified_prop_repository),
):
    _check_novel(novel_id, novel_service)
    from domain.prop.value_objects.prop_id import PropId
    prop = repo.get(PropId(prop_id))
    if not prop or prop.novel_id != novel_id:
        raise HTTPException(status_code=404, detail="Prop not found")
    return _prop_to_dto(prop)


@router.patch("/{novel_id}/props/{prop_id}", response_model=PropDTO)
async def patch_prop(
    novel_id: str,
    prop_id: str,
    body: PatchPropBody,
    novel_service=Depends(get_novel_service),
    repo=Depends(get_unified_prop_repository),
):
    _check_novel(novel_id, novel_service)
    from domain.prop.value_objects.prop_id import PropId
    from domain.prop.value_objects.prop_category import PropCategory
    from domain.prop.value_objects.lifecycle_state import LifecycleState
    prop = repo.get(PropId(prop_id))
    if not prop or prop.novel_id != novel_id:
        raise HTTPException(status_code=404, detail="Prop not found")
    try:
        if body.name is not None:
            prop.name = body.name
        if body.description is not None:
            prop.description = body.description
        if body.aliases is not None:
            prop.aliases = body.aliases
        if body.prop_category is not None:
            prop.category = PropCategory(body.prop_category)
        if body.lifecycle_state is not None:
            prop.lifecycle_state = LifecycleState(body.lifecycle_state)
        if body.holder_character_id is not None:
            prop.holder_character_id = body.holder_character_id
        if body.introduced_chapter is not None:
            prop.introduced_chapter = body.introduced_chapter
        if body.attributes is not None:
            prop.attributes = body.attributes
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=422, detail=str(e))
    repo.save(prop)
    return _prop_to_dto(prop)


@router.delete("/{novel_id}/props/{prop_id}", status_code=204)
async def delete_prop(
    novel_id: str,
    prop_id: str,
    novel_service=Depends(get_novel_service),
    repo=Depends(get_unified_prop_repository),
):
    _check_novel(novel_id, novel_service)
    from domain.prop.value_objects.prop_id import PropId
    prop = repo.get(PropId(prop_id))
    if not prop or prop.novel_id != novel_id:
        raise HTTPException(status_code=404, detail="Prop not found")
    repo.delete(PropId(prop_id))


@router.get("/{novel_id}/props/{prop_id}/events", response_model=List[PropEventDTO])
async def list_prop_events(
    novel_id: str,
    prop_id: str,
    novel_service=Depends(get_novel_service),
    event_repo=Depends(get_prop_event_repository),
):
    _check_novel(novel_id, novel_service)
    events = event_repo.list_for_prop(prop_id)
    return [PropEventDTO(
        id=e.id, prop_id=e.prop_id, chapter_number=e.chapter_number,
        event_type=e.event_type.value, source=e.source.value,
        description=e.description, actor_character_id=e.actor_character_id,
        from_holder_id=e.from_holder_id, to_holder_id=e.to_holder_id,
        created_at=e.created_at,
    ) for e in events]


@router.post("/{novel_id}/props/{prop_id}/events", response_model=PropEventDTO, status_code=201)
async def create_prop_event(
    novel_id: str,
    prop_id: str,
    body: CreateEventBody,
    novel_service=Depends(get_novel_service),
    repo=Depends(get_unified_prop_repository),
    event_repo=Depends(get_prop_event_repository),
):
    _check_novel(novel_id, novel_service)
    from domain.prop.value_objects.prop_id import PropId
    from domain.prop.value_objects.prop_event import PropEvent, PropEventType, PropEventSource
    prop = repo.get(PropId(prop_id))
    if not prop or prop.novel_id != novel_id:
        raise HTTPException(status_code=404, detail="Prop not found")
    try:
        event = PropEvent(
            id=str(uuid.uuid4()),
            prop_id=prop_id,
            novel_id=novel_id,
            chapter_number=body.chapter_number,
            event_type=PropEventType(body.event_type),
            source=PropEventSource.MANUAL,
            description=body.description,
            actor_character_id=body.actor_character_id,
            from_holder_id=body.from_holder_id,
            to_holder_id=body.to_holder_id,
        )
        prop.apply_event(event)
        repo.save(prop)
        event_repo.save(event)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
    return PropEventDTO(
        id=event.id, prop_id=event.prop_id, chapter_number=event.chapter_number,
        event_type=event.event_type.value, source=event.source.value,
        description=event.description, created_at=event.created_at,
    )
