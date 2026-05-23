"""Cast API routes"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
import logging

from application.world.services.cast_service import CastService
from application.world.dtos.cast_dto import CastGraphDTO, CastSearchResultDTO, CastCoverageDTO
from interfaces.api.dependencies import get_cast_service, get_character_narrative_kernel

logger = logging.getLogger(__name__)
router = APIRouter(tags=["cast"])


# Request Models
class StoryEventRequest(BaseModel):
    """Story event request"""
    id: str = Field(..., description="Event ID")
    summary: str = Field(..., description="Event summary")
    chapter_id: Optional[int] = Field(None, description="Chapter ID")
    importance: str = Field("normal", description="Importance level (normal/key)")


class CharacterRequest(BaseModel):
    """Character request"""
    id: str = Field(..., description="Character ID")
    name: str = Field(..., description="Character name")
    aliases: List[str] = Field(default_factory=list, description="Character aliases")
    role: str = Field("", description="Character role")
    traits: str = Field("", description="Character traits")
    note: str = Field("", description="Character note")
    story_events: List[StoryEventRequest] = Field(default_factory=list, description="Story events")


class RelationshipRequest(BaseModel):
    """Relationship request"""
    id: str = Field(..., description="Relationship ID")
    source_id: str = Field(..., description="Source character ID")
    target_id: str = Field(..., description="Target character ID")
    label: str = Field("", description="Relationship label")
    note: str = Field("", description="Relationship note")
    directed: bool = Field(True, description="Is directed relationship")
    story_events: List[StoryEventRequest] = Field(default_factory=list, description="Story events")


class UpdateCastGraphRequest(BaseModel):
    """Update cast graph request"""
    version: int = Field(2, description="Cast graph version")
    characters: List[CharacterRequest] = Field(..., description="Characters")
    relationships: List[RelationshipRequest] = Field(..., description="Relationships")


# Routes
@router.get("/novels/{novel_id}/cast", response_model=CastGraphDTO)
async def get_cast_graph(
    novel_id: str,
    service: CastService = Depends(get_cast_service)
):
    """获取人物关系图（从三元组自动生成）

    从 SQLite 知识库 triples 读取 facts。
    - 人物节点：predicate="是" 且宾语含角色词，或 entity_type=character 的主/客体
    - 人物关系：标准关系谓词，或谓词包含「师徒」「敌对」等子串，或 Bible 人物三元组

    Args:
        novel_id: Novel ID
        service: Cast service

    Returns:
        Cast graph DTO（自动生成）
    """
    return service.get_cast_graph(novel_id)


# PUT 接口已移除：关系图从 SQLite 知识库（GET/PUT /novels/{id}/knowledge）中的 facts 自动生成
#
# 人物节点规范：
# {
#   "subject": "张三",
#   "predicate": "是",
#   "object": "主角" | "配角" | "人物",
#   "note": "人物描述"
# }
#
# 人物关系规范：
# {
#   "subject": "张三",
#   "predicate": "师徒" | "父子" | "朋友" | "敌对" | ...,
#   "object": "李四",
#   "note": "关系说明"
# }


@router.get("/novels/{novel_id}/cast/search", response_model=CastSearchResultDTO)
async def search_cast(
    novel_id: str,
    q: str,
    service: CastService = Depends(get_cast_service)
):
    """Search characters and relationships in cast graph

    Args:
        novel_id: Novel ID
        q: Search query
        service: Cast service

    Returns:
        Search results DTO

    """
    return service.search_cast(novel_id, q)


@router.get("/novels/{novel_id}/cast/coverage", response_model=CastCoverageDTO)
async def get_cast_coverage(
    novel_id: str,
    service: CastService = Depends(get_cast_service)
):
    """Get cast coverage analysis for a novel

    Analyzes character mentions in chapters and compares with cast graph.

    Args:
        novel_id: Novel ID
        service: Cast service

    Returns:
        Cast coverage DTO

    """
    return service.get_cast_coverage(novel_id)


# ── /cast/schedule ─────────────────────────────────────────────────────────

class CastScheduleRequest(BaseModel):
    """章节选角调度请求"""
    chapter_number: int = Field(..., ge=1, description="章节号")
    outline: str = Field("", description="章节大纲（用于名字匹配和优先级提升）")
    mode: str = Field("suggest", description="suggest=仅建议，不写库；apply=建议并写入 chapter_elements")


class ScheduledCharacterItem(BaseModel):
    character_id: str
    name: str
    importance: str = Field(description="planned importance: major / normal / minor")
    is_new_suggestion: bool = Field(description="True 表示由算法建议（非作者手动设定）")
    scene_function: str = ""
    needs_review: bool = False


class CastScheduleResponse(BaseModel):
    chapter_number: int
    cast: List[ScheduledCharacterItem]
    new_character_hints: List[str] = Field(
        default_factory=list,
        description="大纲中出现但不在 Bible 的名字（潜在新角色提示）",
    )
    new_character_candidates: List[dict] = Field(default_factory=list)
    generated_context: str = ""
    scheduling_log: List[str] = Field(default_factory=list)


# 重要性文字 → chapter_elements importance 值
@router.post("/novels/{novel_id}/cast/schedule", response_model=CastScheduleResponse)
async def schedule_cast(
    novel_id: str,
    request: CastScheduleRequest,
    kernel = Depends(get_character_narrative_kernel),
):
    """章节选角调度

    - mode='suggest'：运行 AppearanceScheduler，返回建议，不写库
    - mode='apply'：同上 + 将建议写入 chapter_elements（仅插入，不覆盖已有作者设定）

    返回字段说明：
    - cast: 建议出场角色列表，importance 已按 Bible 角色重要性映射
    - new_character_hints: 大纲中出现但不在 Bible 的名字（提示作者添加新角色）
    """
    try:
        plan = kernel.plan_cast(
            novel_id=novel_id,
            chapter_number=request.chapter_number,
            outline=request.outline,
        )
        if request.mode == "apply":
            plan = kernel.apply_cast_plan(plan)

        cast_items = [
            ScheduledCharacterItem(
                character_id=slot.character_id,
                name=slot.name,
                importance=slot.importance,
                is_new_suggestion=slot.is_new_suggestion,
                scene_function=slot.notes.scene_function,
                needs_review=slot.notes.needs_review,
            )
            for slot in plan.slots
        ]

        return CastScheduleResponse(
            chapter_number=request.chapter_number,
            cast=cast_items,
            new_character_hints=[
                c.name for c in plan.new_character_candidates
                if c.recommendation in ("ephemeral", "create_bible_character")
            ][:10],
            new_character_candidates=[c.to_dict() for c in plan.new_character_candidates],
            generated_context=plan.generated_context,
            scheduling_log=plan.scheduling_log,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"cast/schedule 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/novels/{novel_id}/characters/{character_id}/narrative-profile")
async def get_character_narrative_profile(
    novel_id: str,
    character_id: str,
    kernel = Depends(get_character_narrative_kernel),
):
    """角色聚合 read model：角色档案 / 状态 / 知识库 / 出场史 / 风险。"""
    try:
        return kernel.get_character_narrative_profile(novel_id, character_id).to_dict()
    except Exception as e:
        logger.error("character narrative profile failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
