"""Checkpoint + QualityGuardrail + StoryPhase + CharacterSoul 统一路由

前端新增面板的统一 API 出口：
- GET  /novels/{novel_id}/checkpoints         → 列出时间线
- POST /novels/{novel_id}/checkpoints         → 手动创建
- POST /novels/{novel_id}/checkpoints/{id}/rollback → 回滚
- GET  /novels/{novel_id}/checkpoints/branches → 平行宇宙
- GET  /novels/{novel_id}/checkpoints/head     → 当前HEAD

- POST /novels/{novel_id}/guardrail/check      → 六维度质检(advise)
- POST /novels/{novel_id}/guardrail/enforce    → 六维度质检(enforce)

- GET  /novels/{novel_id}/story-phase          → 获取故事阶段
- PUT  /novels/{novel_id}/story-phase          → 更新故事阶段

- GET  /novels/{novel_id}/character-souls       → 获取角色灵魂概览
- GET  /novels/{novel_id}/character-souls/{name}→ 单角色灵魂详情
- POST /novels/{novel_id}/character-souls/{name}/validate → 行为验证
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/novels", tags=["engine-core"])


# ─── Pydantic DTOs ────────────────────────────────────────────────

class CheckpointDTO(BaseModel):
    id: str
    story_id: str
    trigger_type: str
    trigger_reason: str = ""
    parent_id: Optional[str] = None
    chapter_number: Optional[int] = None
    created_at: str = ""
    is_head: bool = False


class CheckpointListResponse(BaseModel):
    checkpoints: List[CheckpointDTO] = Field(default_factory=list)
    head_id: Optional[str] = None


class CreateCheckpointRequest(BaseModel):
    reason: str = "手动创建"
    chapter_number: Optional[int] = None


class CreateCheckpointResponse(BaseModel):
    checkpoint_id: str
    message: str = "Checkpoint已创建"


class RollbackResponse(BaseModel):
    checkpoint_id: str
    trigger_reason: str = ""
    message: str = "已回滚"


class BranchDTO(BaseModel):
    branch_point_id: str
    reason: str = ""
    children: List[Dict[str, Any]] = Field(default_factory=list)


class BranchesResponse(BaseModel):
    branches: List[BranchDTO] = Field(default_factory=list)


class GuardrailCheckRequest(BaseModel):
    text: str
    character_names: List[str] = Field(default_factory=list)
    chapter_goal: str = ""
    era: str = "ancient"
    scene_type: str = "auto"
    mode: str = "advise"  # advise | enforce


class GuardrailDimensionScore(BaseModel):
    name: str
    key: str
    score: float
    weight: float


class GuardrailViolationDTO(BaseModel):
    dimension: str
    type: str = ""
    severity: str = "info"
    description: str = ""
    original: str = ""
    suggestion: str = ""
    character: str = ""


class GuardrailCheckResponse(BaseModel):
    overall_score: float = 0.0
    passed: bool = False
    dimensions: List[GuardrailDimensionScore] = Field(default_factory=list)
    violations: List[GuardrailViolationDTO] = Field(default_factory=list)


class StoryPhaseDTO(BaseModel):
    phase: str = "setup"
    progress: float = 0.0
    description: str = ""
    can_advance: bool = False


class CharacterSoulDTO(BaseModel):
    name: str
    role: str = ""
    core_belief: str = ""
    taboo: str = ""
    voice_tag: str = ""
    wound: str = ""
    trauma_count: int = 0


class CharacterSoulListResponse(BaseModel):
    characters: List[CharacterSoulDTO] = Field(default_factory=list)


class CharacterSoulDetailDTO(BaseModel):
    name: str
    role: str = ""
    core_belief: str = ""
    taboo: str = ""
    voice_tag: str = ""
    wound: str = ""
    trauma_count: int = 0
    emotion_ledger: Dict[str, Any] = Field(default_factory=dict)
    mask_summary: str = ""


class ValidateBehaviorRequest(BaseModel):
    action: str


class ValidateBehaviorResponse(BaseModel):
    valid: bool = True
    warnings: List[str] = Field(default_factory=list)
    suggestions: List[str] = Field(default_factory=list)


# ─── Helpers ───────────────────────────────────────────────────────

def _get_checkpoint_store():
    """获取 CheckpointStore（通过 DI）"""
    from interfaces.api.dependencies import get_checkpoint_store
    return get_checkpoint_store()


def _get_quality_guardrail():
    """获取 QualityGuardrail（通过 DI）"""
    from interfaces.api.dependencies import get_quality_guardrail
    return get_quality_guardrail()


def _get_cast_graph(novel_id: str):
    """从 CastService 获取角色图"""
    from interfaces.api.dependencies import get_cast_service
    cast_service = get_cast_service()
    return cast_service.get_cast(novel_id)


def _novel_exists(novel_id: str) -> bool:
    from interfaces.api.dependencies import get_novel_service
    return get_novel_service().get_novel(novel_id) is not None


# ─── Checkpoint Endpoints ──────────────────────────────────────────

@router.get("/{novel_id}/checkpoints", response_model=CheckpointListResponse)
async def list_checkpoints(novel_id: str, limit: int = 50):
    """列出小说的 Checkpoint 时间线"""
    if not _novel_exists(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")

    store = _get_checkpoint_store()
    try:
        head_id = await store.get_head(novel_id)
        checkpoints_data = await store.list_story_checkpoints(novel_id, limit=limit)
    except Exception as e:
        logger.warning("列出Checkpoint失败: %s", e)
        return CheckpointListResponse()

    dtos = []
    for cp in checkpoints_data:
        cp_id_str = cp.checkpoint_id.value if hasattr(cp.checkpoint_id, 'value') else str(cp.checkpoint_id)
        dtos.append(CheckpointDTO(
            id=cp_id_str,
            story_id=cp.story_id if hasattr(cp, 'story_id') else novel_id,
            trigger_type=cp.trigger_type.value if hasattr(cp.trigger_type, 'value') else str(cp.trigger_type),
            trigger_reason=cp.trigger_reason or "",
            parent_id=str(cp.parent_id) if cp.parent_id else None,
            chapter_number=cp.story_state.get("chapter_number") if isinstance(cp.story_state, dict) else None,
            created_at=cp.created_at.isoformat() if hasattr(cp, 'created_at') and cp.created_at else "",
            is_head=(cp_id_str == str(head_id)) if head_id else False,
        ))

    return CheckpointListResponse(checkpoints=dtos, head_id=str(head_id) if head_id else None)


@router.post("/{novel_id}/checkpoints", response_model=CreateCheckpointResponse)
async def create_checkpoint(novel_id: str, body: CreateCheckpointRequest):
    """手动创建 Checkpoint"""
    if not _novel_exists(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")

    from engine.application.checkpoint_manager.manager import CheckpointManager

    store = _get_checkpoint_store()
    manager = CheckpointManager(store)

    try:
        cp_id = await manager.on_chapter_completed(
            story_id=novel_id,
            chapter_number=body.chapter_number or 0,
            story_state={"manual": True, "reason": body.reason},
            character_masks={},
            emotion_ledger={},
            active_foreshadows=[],
            recent_summary=body.reason,
        )
        return CreateCheckpointResponse(checkpoint_id=cp_id.value if hasattr(cp_id, 'value') else str(cp_id))
    except Exception as e:
        logger.error("创建Checkpoint失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{novel_id}/checkpoints/{checkpoint_id}/rollback", response_model=RollbackResponse)
async def rollback_checkpoint(novel_id: str, checkpoint_id: str):
    """回滚到指定 Checkpoint"""
    if not _novel_exists(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")

    from engine.domain.value_objects.checkpoint import CheckpointId
    from engine.application.checkpoint_manager.manager import CheckpointManager

    store = _get_checkpoint_store()
    manager = CheckpointManager(store)

    try:
        cp = await manager.rollback(novel_id, CheckpointId(checkpoint_id))
        if cp is None:
            raise HTTPException(status_code=404, detail="Checkpoint not found")
        return RollbackResponse(
            checkpoint_id=checkpoint_id,
            trigger_reason=cp.trigger_reason,
            message=f"已回滚到: {cp.trigger_reason}",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("回滚失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{novel_id}/checkpoints/branches", response_model=BranchesResponse)
async def list_branches(novel_id: str):
    """列出平行宇宙分支"""
    if not _novel_exists(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")

    from engine.application.checkpoint_manager.manager import CheckpointManager

    store = _get_checkpoint_store()
    manager = CheckpointManager(store)

    try:
        branches = await manager.list_branches(novel_id)
        return BranchesResponse(branches=[
            BranchDTO(
                branch_point_id=b["branch_point"],
                reason=b.get("reason", ""),
                children=b.get("children", []),
            )
            for b in branches
        ])
    except Exception as e:
        logger.warning("列出分支失败: %s", e)
        return BranchesResponse()


@router.get("/{novel_id}/checkpoints/head")
async def get_head_checkpoint(novel_id: str):
    """获取当前 HEAD Checkpoint"""
    if not _novel_exists(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")

    store = _get_checkpoint_store()
    try:
        head_id = await store.get_head(novel_id)
        if not head_id:
            return {"head_id": None, "state": None}
        cp = await store.load(head_id)
        if not cp:
            return {"head_id": str(head_id), "state": None}
        return {
            "head_id": str(head_id),
            "state": {
                "trigger_type": cp.trigger_type.value if hasattr(cp.trigger_type, 'value') else str(cp.trigger_type),
                "trigger_reason": cp.trigger_reason,
                "story_state": cp.story_state,
                "active_foreshadows": cp.active_foreshadows,
            },
        }
    except Exception as e:
        logger.warning("获取HEAD失败: %s", e)
        return {"head_id": None, "state": None}


# ─── Guardrail Endpoints ───────────────────────────────────────────

@router.post("/{novel_id}/guardrail/check", response_model=GuardrailCheckResponse)
async def guardrail_check(novel_id: str, body: GuardrailCheckRequest):
    """六维度质量检查"""
    if not _novel_exists(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")

    guardrail = _get_quality_guardrail()

    # 尝试从 Cast 服务获取角色面具
    character_masks = {}
    try:
        cast_graph = _get_cast_graph(novel_id)
        from engine.domain.value_objects.character_mask import CharacterMask
        for ch in (cast_graph.characters or []):
            mask = CharacterMask(
                name=ch.name,
                role=ch.role,
                voice_tag="",
                core_belief="",
                taboo="",
            )
            character_masks[ch.name] = mask
    except Exception:
        pass  # Cast 服务不可用时用空面具

    try:
        if body.mode == "enforce":
            report = guardrail.enforce(
                text=body.text,
                character_masks=character_masks or None,
                chapter_goal=body.chapter_goal,
                character_names=body.character_names or None,
                era=body.era,
                scene_type=body.scene_type,
            )
        else:
            report = guardrail.advise(
                text=body.text,
                character_masks=character_masks or None,
                chapter_goal=body.chapter_goal,
                character_names=body.character_names or None,
                era=body.era,
                scene_type=body.scene_type,
            )

        DIMENSION_META = [
            ("language_style", "语言风格", 0.25),
            ("character_consistency", "角色一致性", 0.25),
            ("plot_density", "情节密度", 0.20),
            ("naming", "命名", 0.05),
            ("viewpoint", "视角", 0.10),
            ("rhythm", "节奏", 0.15),
        ]

        dimensions = []
        for key, name, weight in DIMENSION_META:
            score = getattr(report, f"{key}_score", 0.0)
            dimensions.append(GuardrailDimensionScore(name=name, key=key, score=round(score, 3), weight=weight))

        violations = []
        for v in report.all_violations:
            violations.append(GuardrailViolationDTO(
                dimension=v.get("dimension", ""),
                type=v.get("type", ""),
                severity=v.get("severity", "info"),
                description=v.get("description", ""),
                original=v.get("original", ""),
                suggestion=v.get("suggestion", ""),
                character=v.get("character", ""),
            ))

        return GuardrailCheckResponse(
            overall_score=round(report.overall_score, 3),
            passed=report.passed,
            dimensions=dimensions,
            violations=violations,
        )
    except Exception as e:
        # QualityViolationError 也返回报告（enforce模式）
        from engine.application.quality_guardrails.quality_guardrail import QualityViolationError
        if isinstance(e, QualityViolationError):
            return GuardrailCheckResponse(
                overall_score=round(e.overall_score, 3),
                passed=False,
                dimensions=[],
                violations=[GuardrailViolationDTO(
                    dimension=v.get("dimension", "") if isinstance(v, dict) else "",
                    type=v.get("type", "") if isinstance(v, dict) else "",
                    severity=v.get("severity", "error") if isinstance(v, dict) else "error",
                    description=v.get("description", str(v)) if isinstance(v, dict) else str(v),
                ) for v in e.violations],
            )
        logger.error("质量检查失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ─── StoryPhase Endpoints ──────────────────────────────────────────

@router.get("/{novel_id}/story-phase", response_model=StoryPhaseDTO)
async def get_story_phase(novel_id: str):
    """获取小说的故事阶段"""
    if not _novel_exists(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")

    # 尝试从 Novel 实体获取 StoryPhase
    try:
        from interfaces.api.dependencies import get_novel_service
        novel = get_novel_service().get_novel(novel_id)
        if novel and hasattr(novel, 'story_phase'):
            phase = novel.story_phase
            phase_value = phase.value if hasattr(phase, 'value') else str(phase)
            return StoryPhaseDTO(
                phase=phase_value,
                progress=getattr(phase, 'progress', 0.0) if hasattr(phase, 'progress') else 0.0,
                description=getattr(phase, 'description', '') if hasattr(phase, 'description') else '',
                can_advance=getattr(phase, 'can_advance', False) if hasattr(phase, 'can_advance') else False,
            )
    except Exception as e:
        logger.warning("获取StoryPhase失败: %s", e)

    # 回退：基于章节进度推算
    try:
        from interfaces.api.dependencies import get_chapter_repository
        chapter_repo = get_chapter_repository()
        chapters = chapter_repo.get_chapters_by_novel(novel_id)
        total = len(chapters) if chapters else 0
        if total == 0:
            return StoryPhaseDTO(phase="setup", progress=0.0, description="尚未开始")
        elif total <= 5:
            return StoryPhaseDTO(phase="setup", progress=total / 10, description="设定阶段")
        elif total <= 15:
            return StoryPhaseDTO(phase="rising_action", progress=0.3 + (total - 5) / 30, description="冲突升级")
        elif total <= 25:
            return StoryPhaseDTO(phase="crisis", progress=0.6 + (total - 15) / 30, description="高潮危机")
        else:
            return StoryPhaseDTO(phase="resolution", progress=0.85, description="收束阶段")
    except Exception:
        return StoryPhaseDTO(phase="setup", progress=0.0, description="未知阶段")


@router.put("/{novel_id}/story-phase", response_model=StoryPhaseDTO)
async def update_story_phase(novel_id: str, body: StoryPhaseDTO):
    """更新小说的故事阶段"""
    if not _novel_exists(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")

    try:
        from domain.novel.value_objects.story_phase import StoryPhase as StoryPhaseEnum
        new_phase = StoryPhaseEnum(body.phase)
    except (ValueError, ImportError):
        new_phase = body.phase

    try:
        from interfaces.api.dependencies import get_novel_service
        novel_service = get_novel_service()
        novel = novel_service.get_novel(novel_id)
        if novel and hasattr(novel, 'story_phase'):
            novel.story_phase = new_phase
            return StoryPhaseDTO(
                phase=body.phase,
                progress=body.progress,
                description=body.description,
                can_advance=body.can_advance,
            )
    except Exception as e:
        logger.warning("更新StoryPhase失败: %s", e)

    return body


# ─── Character Soul Endpoints ──────────────────────────────────────

@router.get("/{novel_id}/character-souls", response_model=CharacterSoulListResponse)
async def list_character_souls(novel_id: str):
    """获取角色灵魂概览列表"""
    if not _novel_exists(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")

    try:
        cast_graph = _get_cast_graph(novel_id)
        characters = []
        for ch in (cast_graph.characters or []):
            characters.append(CharacterSoulDTO(
                name=ch.name,
                role=ch.role,
                core_belief="",
                taboo="",
                voice_tag="",
                wound="",
                trauma_count=0,
            ))
        return CharacterSoulListResponse(characters=characters)
    except Exception as e:
        logger.warning("获取角色灵魂列表失败: %s", e)
        return CharacterSoulListResponse()


@router.get("/{novel_id}/character-souls/{character_name}", response_model=CharacterSoulDetailDTO)
async def get_character_soul(novel_id: str, character_name: str):
    """获取单个角色灵魂详情"""
    if not _novel_exists(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")

    try:
        cast_graph = _get_cast_graph(novel_id)
        target = None
        for ch in (cast_graph.characters or []):
            if ch.name == character_name:
                target = ch
                break

        if not target:
            raise HTTPException(status_code=404, detail=f"Character '{character_name}' not found")

        return CharacterSoulDetailDTO(
            name=target.name,
            role=target.role,
            core_belief="",
            taboo="",
            voice_tag="",
            wound="",
            trauma_count=0,
            emotion_ledger={},
            mask_summary=f"{target.name} ({target.role}): {target.traits[:60] if target.traits else ''}",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("获取角色灵魂详情失败: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{novel_id}/character-souls/{character_name}/validate", response_model=ValidateBehaviorResponse)
async def validate_character_behavior(novel_id: str, character_name: str, body: ValidateBehaviorRequest):
    """验证角色行为是否符合灵魂设定"""
    if not _novel_exists(novel_id):
        raise HTTPException(status_code=404, detail="Novel not found")

    try:
        from engine.domain.value_objects.character_mask import CharacterMask
        mask = CharacterMask(
            name=character_name,
            role="",
            voice_tag="",
            core_belief="",
            taboo="",
        )
        result = mask.validate_behavior(body.action)
        if isinstance(result, dict):
            return ValidateBehaviorResponse(
                valid=result.get("valid", True),
                warnings=result.get("warnings", []),
                suggestions=result.get("suggestions", []),
            )
        return ValidateBehaviorResponse(valid=bool(result))
    except Exception as e:
        logger.warning("行为验证失败: %s", e)
        return ValidateBehaviorResponse(valid=True, warnings=[f"验证服务不可用: {e}"])
