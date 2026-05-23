"""Cast API routes"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
import uuid
import logging
from datetime import datetime

from application.world.services.cast_service import CastService
from application.world.dtos.cast_dto import CastGraphDTO, CastSearchResultDTO, CastCoverageDTO
from interfaces.api.dependencies import get_cast_service

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


class CastScheduleResponse(BaseModel):
    chapter_number: int
    cast: List[ScheduledCharacterItem]
    new_character_hints: List[str] = Field(
        default_factory=list,
        description="大纲中出现但不在 Bible 的名字（潜在新角色提示）",
    )


# 重要性文字 → chapter_elements importance 值
_BIBLE_IMPORTANCE_MAP = {
    "protagonist": "major",
    "major_supporting": "normal",
    "important_supporting": "normal",
    "supporting": "normal",
    "minor": "minor",
    "background": "minor",
}


@router.post("/novels/{novel_id}/cast/schedule", response_model=CastScheduleResponse)
async def schedule_cast(novel_id: str, request: CastScheduleRequest):
    """章节选角调度

    - mode='suggest'：运行 AppearanceScheduler，返回建议，不写库
    - mode='apply'：同上 + 将建议写入 chapter_elements（仅插入，不覆盖已有作者设定）

    返回字段说明：
    - cast: 建议出场角色列表，importance 已按 Bible 角色重要性映射
    - new_character_hints: 大纲中出现但不在 Bible 的名字（提示作者添加新角色）
    """
    from interfaces.api.dependencies import get_bible_service, get_chapter_element_repository
    from infrastructure.persistence.database.story_node_repository import StoryNodeRepository
    from application.paths import get_db_path

    try:
        bible_service = get_bible_service()
        bible = bible_service.get_bible_by_novel(novel_id)
        if not bible:
            raise HTTPException(status_code=404, detail="Bible not found for this novel")

        characters = bible.characters or []

        # ── Step 1: 大纲名字匹配 ──────────────────────────────────────────
        outline = request.outline
        char_names = {c.name for c in characters}
        mentioned_ids: set = set()
        for char in characters:
            if char.name and char.name in outline:
                mentioned_ids.add(char.id)

        # ── Step 2: 新角色提示（大纲中出现但 Bible 无记录的名字） ────────────
        new_hints: List[str] = []
        if outline:
            import re
            # 简单启发：连续2-4个汉字，不在已知角色名中
            candidate_names = re.findall(r'[一-龥]{2,4}', outline)
            known_name_set = char_names
            seen: set = set()
            for n in candidate_names:
                if n not in known_name_set and n not in seen:
                    seen.add(n)
                    new_hints.append(n)

        # ── Step 3: 按 importance + 大纲提及排序，选最多 7 个 ────────────────
        IMPORTANCE_ORDER = {
            "protagonist": 0,
            "major_supporting": 1,
            "important_supporting": 2,
            "supporting": 3,
            "minor": 4,
            "background": 5,
        }

        def _char_sort_key(c):
            imp_raw = (getattr(c, "importance", None) or "").lower()
            imp_ord = IMPORTANCE_ORDER.get(imp_raw, 4)
            in_outline = 1 if c.id not in mentioned_ids else 0
            return (in_outline, imp_ord)

        sorted_chars = sorted(characters, key=_char_sort_key)
        selected = sorted_chars[:7]

        # ── Step 4: 构建响应 DTO ───────────────────────────────────────────
        cast_items: List[ScheduledCharacterItem] = []
        for char in selected:
            imp_raw = (getattr(char, "importance", None) or "supporting").lower()
            importance_val = _BIBLE_IMPORTANCE_MAP.get(imp_raw, "normal")
            cast_items.append(ScheduledCharacterItem(
                character_id=char.id,
                name=char.name,
                importance=importance_val,
                is_new_suggestion=True,
            ))

        # ── Step 5: apply 模式写入 chapter_elements ───────────────────────
        if request.mode == "apply":
            try:
                story_node_repo = StoryNodeRepository(get_db_path())
                nodes = story_node_repo.get_by_novel_sync(novel_id)
                chapter_id = None
                for node in nodes:
                    nt = node.node_type.value if hasattr(node.node_type, 'value') else str(node.node_type)
                    if nt == 'chapter' and node.number == request.chapter_number:
                        chapter_id = node.id
                        break

                if chapter_id:
                    elem_repo = get_chapter_element_repository()
                    db = elem_repo._db()
                    for item in cast_items:
                        elem_id = f"elem-{uuid.uuid4().hex[:8]}"
                        db.execute(
                            """
                            INSERT OR IGNORE INTO chapter_elements (
                                id, chapter_id, element_type, element_id,
                                relation_type, importance, created_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                elem_id,
                                chapter_id,
                                "character",
                                item.character_id,
                                "appears",
                                item.importance,
                                datetime.now().isoformat(),
                            ),
                        )
                    db.commit()
                    # 标记为算法建议（非作者手动设定）
                    for item in cast_items:
                        item.is_new_suggestion = True
            except Exception as apply_err:
                logger.warning(f"cast/schedule apply 写入失败: {apply_err}")

        return CastScheduleResponse(
            chapter_number=request.chapter_number,
            cast=cast_items,
            new_character_hints=new_hints[:10],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"cast/schedule 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
