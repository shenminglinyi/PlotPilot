from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from application.governance.service import NarrativeGovernanceService
from infrastructure.persistence.database.connection import get_database
from infrastructure.persistence.database.sqlite_governance_repository import (
    SqliteGovernanceRepository,
)

router = APIRouter(prefix="/novels/{novel_id}/governance", tags=["narrative-governance"])


class ContractPayload(BaseModel):
    title_promise: str | None = None
    core_question: str | None = None
    theme_anchors: list[str] | None = None
    forbidden_early_payoffs: list[str] | None = None
    reveal_budget: dict[str, Any] | None = None


class MergeStorylinesPayload(BaseModel):
    source_ids: list[str] = Field(default_factory=list)
    target_id: str | None = None
    title: str | None = None
    aliases: list[str] = Field(default_factory=list)
    promise_tags: list[str] = Field(default_factory=list)


class BudgetPreviewPayload(BaseModel):
    chapter_number: int | None = None


class ReviewActionPayload(BaseModel):
    report_id: str
    action: str = "accepted"
    patch: dict[str, Any] | None = None


def _service() -> NarrativeGovernanceService:
    db = get_database()
    repo = SqliteGovernanceRepository(db)
    novel_repo = None
    storyline_repo = None
    try:
        from interfaces.api.dependencies import get_novel_repository

        novel_repo = get_novel_repository()
    except Exception:
        novel_repo = None
    try:
        from infrastructure.persistence.database.sqlite_storyline_repository import SqliteStorylineRepository

        storyline_repo = SqliteStorylineRepository(db)
    except Exception:
        storyline_repo = None
    return NarrativeGovernanceService(repo, novel_repo, storyline_repo, db)


def _payload_dict(model: BaseModel, *, exclude_none: bool = False) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(exclude_none=exclude_none)  # type: ignore[attr-defined]
    return model.dict(exclude_none=exclude_none)


@router.get("/state")
async def get_governance_state(novel_id: str) -> dict[str, Any]:
    try:
        return _service().get_state(novel_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"governance state failed: {exc}") from exc


@router.post("/contract")
async def update_governance_contract(novel_id: str, payload: ContractPayload) -> dict[str, Any]:
    try:
        return _service().update_contract(novel_id, _payload_dict(payload, exclude_none=True)).to_dict()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"governance contract update failed: {exc}") from exc


@router.post("/storylines/merge")
async def merge_governance_storylines(novel_id: str, payload: MergeStorylinesPayload) -> dict[str, Any]:
    try:
        return _service().merge_storylines(novel_id, _payload_dict(payload)).to_dict()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"governance storyline merge failed: {exc}") from exc


@router.post("/chapter-budget/preview")
async def preview_governance_budget(novel_id: str, payload: BudgetPreviewPayload) -> dict[str, Any]:
    try:
        return _service().prepare_chapter(novel_id, payload.chapter_number)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"governance budget preview failed: {exc}") from exc


@router.post("/review-action")
async def apply_governance_review_action(novel_id: str, payload: ReviewActionPayload) -> dict[str, Any]:
    try:
        return _service().review_action(novel_id, _payload_dict(payload))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"governance review action failed: {exc}") from exc
