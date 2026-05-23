from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from application.evolution.services.gate_service import EvolutionGateService
from application.evolution.services.override_service import EvolutionOverrideService, PatchConflictError
from application.evolution.services.snapshot_service import EvolutionSnapshotService
from infrastructure.persistence.database.sqlite_evolution_repository import SqliteEvolutionRepository
from interfaces.api.dependencies import (
    get_evolution_gate_service,
    get_evolution_override_service,
    get_evolution_repository,
    get_evolution_snapshot_service,
)


router = APIRouter(prefix="/novels/{novel_id}/evolution", tags=["evolution"])


class GateRequest(BaseModel):
    chapter_number: int
    branch_id: str = "main"
    outline_content: str = ""
    pov_character_id: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class OverrideRequest(BaseModel):
    branch_id: str = "main"
    patches: List[Dict[str, Any]] = Field(default_factory=list)


class ReplayRequest(BaseModel):
    branch_id: str = "main"


class ConflictResolutionRequest(BaseModel):
    resolution_status: str = "resolved"


@router.get("/snapshots")
async def list_snapshots(
    novel_id: str,
    branch_id: str = "main",
    status: Optional[str] = None,
    repo: SqliteEvolutionRepository = Depends(get_evolution_repository),
) -> Dict[str, Any]:
    snapshots = repo.list_snapshots(novel_id, branch_id=branch_id, status=status, limit=100)
    return {
        "novel_id": novel_id,
        "branch_id": branch_id,
        "snapshots": [s.to_dict() for s in snapshots],
        "counts": repo.count_by_status(novel_id, branch_id),
    }


@router.get("/snapshots/{chapter_number}")
async def get_snapshot(
    novel_id: str,
    chapter_number: int,
    branch_id: str = "main",
    repo: SqliteEvolutionRepository = Depends(get_evolution_repository),
) -> Dict[str, Any]:
    snapshot = repo.get_by_chapter(novel_id, branch_id, chapter_number)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="snapshot_not_found")
    return snapshot.to_dict()


@router.post("/gate")
async def gate(
    novel_id: str,
    req: GateRequest,
    service: EvolutionGateService = Depends(get_evolution_gate_service),
) -> Dict[str, Any]:
    report = service.check(
        novel_id=novel_id,
        chapter_number=req.chapter_number,
        branch_id=req.branch_id,
        outline_content=req.outline_content,
        pov_character_id=req.pov_character_id,
        tags=req.tags,
    ).to_dict()
    try:
        from application.governance.service import NarrativeGovernanceService
        from infrastructure.persistence.database.connection import get_database
        from infrastructure.persistence.database.sqlite_governance_repository import (
            SqliteGovernanceRepository,
        )
        from infrastructure.persistence.database.sqlite_storyline_repository import (
            SqliteStorylineRepository,
        )
        from interfaces.api.dependencies import get_novel_repository

        db = get_database()
        governance = NarrativeGovernanceService(
            SqliteGovernanceRepository(db),
            get_novel_repository(),
            SqliteStorylineRepository(db),
            db,
        )
        prepared = governance.prepare_chapter(novel_id, req.chapter_number)
        budget = prepared.get("budget") or {}
        tags_to_serve = list(budget.get("must_serve_promise_tags") or [])
        outline = req.outline_content or ""
        missing_tags = [tag for tag in tags_to_serve if tag and tag not in outline]
        report["governance_budget"] = budget
        report["governance_context_request"] = prepared.get("context_request") or {}
        if missing_tags:
            report.setdefault("violations", []).append(
                {
                    "level": "warning",
                    "type": "GOVERNANCE_PROMISE_TAG_MISSING",
                    "message": "下一章大纲尚未服务治理预算要求的承诺标签：" + "、".join(missing_tags[:4]),
                    "suggestion": "至少让一个承诺标签进入行动、代价或发现，而不是只停留在设定说明。",
                }
            )
            report.setdefault("repair_plan", []).append(
                "补入承诺标签：" + "、".join(missing_tags[:4])
            )
    except Exception:
        report["governance_budget"] = None
        report["governance_context_request"] = {}
    return report


@router.post("/snapshots/{chapter_number}/overrides")
async def apply_overrides(
    novel_id: str,
    chapter_number: int,
    req: OverrideRequest,
    service: EvolutionOverrideService = Depends(get_evolution_override_service),
) -> Dict[str, Any]:
    try:
        return service.apply_overrides(novel_id, chapter_number, req.patches, req.branch_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PatchConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/replay-from/{chapter_number}")
async def replay_from(
    novel_id: str,
    chapter_number: int,
    req: ReplayRequest,
    service: EvolutionSnapshotService = Depends(get_evolution_snapshot_service),
) -> Dict[str, Any]:
    return service.replay_from(novel_id, chapter_number, branch_id=req.branch_id)


@router.post("/conflicts/{conflict_id}/resolve")
async def resolve_conflict(
    novel_id: str,
    conflict_id: str,
    req: ConflictResolutionRequest,
    repo: SqliteEvolutionRepository = Depends(get_evolution_repository),
) -> Dict[str, Any]:
    ok = repo.update_conflict_resolution(conflict_id, req.resolution_status)
    if not ok:
        raise HTTPException(status_code=404, detail="conflict_not_found")
    return {"novel_id": novel_id, "conflict_id": conflict_id, "resolution_status": req.resolution_status}
