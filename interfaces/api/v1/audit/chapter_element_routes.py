"""
章节元素管理 API 路由
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List, Optional

from domain.structure.chapter_element import ElementType, RelationType, Importance
from infrastructure.persistence.database.chapter_element_repository import ChapterElementRepository
from application.paths import get_db_path
import uuid


router = APIRouter(prefix="/chapters", tags=["chapter-elements"])


# ==================== DTOs ====================

class ChapterElementCreate(BaseModel):
    """创建章节元素关联"""
    element_type: str = Field(..., description="元素类型: character/location/item/organization/event")
    element_id: str = Field(..., description="元素 ID")
    relation_type: str = Field(..., description="关联类型: appears/mentioned/scene/uses/involved/occurs")
    importance: str = Field("normal", description="重要性: major/normal/minor")
    appearance_order: Optional[int] = Field(None, description="出场顺序")
    notes: Optional[str] = Field(None, description="备注")


class ChapterElementBatchUpdate(BaseModel):
    """批量更新章节元素"""
    elements: List[ChapterElementCreate] = Field(..., description="元素列表")


# ==================== 依赖注入 ====================

def get_chapter_element_repo() -> ChapterElementRepository:
    """获取章节元素仓储"""
    return ChapterElementRepository(get_db_path())


# ==================== API 端点 ====================

@router.post("/{chapter_id}/elements")
async def add_chapter_element(
    chapter_id: str,
    request: ChapterElementCreate,
    repo: ChapterElementRepository = Depends(get_chapter_element_repo)
):
    """
    添加章节元素关联

    为章节添加一个 Bible 元素关联（人物、地点、道具等）。
    """
    try:
        from domain.structure.chapter_element import ChapterElement
        from datetime import datetime

        # 检查是否已存在
        exists = await repo.exists(
            chapter_id,
            ElementType(request.element_type),
            request.element_id,
            RelationType(request.relation_type)
        )

        if exists:
            raise HTTPException(status_code=400, detail="该元素关联已存在")

        # 创建元素关联
        element = ChapterElement(
            id=f"elem-{uuid.uuid4().hex[:8]}",
            chapter_id=chapter_id,
            element_type=ElementType(request.element_type),
            element_id=request.element_id,
            relation_type=RelationType(request.relation_type),
            importance=Importance(request.importance),
            appearance_order=request.appearance_order,
            notes=request.notes,
            created_at=datetime.now()
        )

        await repo.save(element)

        # 触发知识图谱推断
        from application.world.services.knowledge_graph_service import KnowledgeGraphService
        from infrastructure.persistence.database.triple_repository import TripleRepository
        from infrastructure.persistence.database.story_node_repository import StoryNodeRepository

        kg_service = KnowledgeGraphService(
            TripleRepository(),
            repo,
            StoryNodeRepository(get_db_path()),
        )
        await kg_service.infer_from_chapter(chapter_id)

        return {
            "success": True,
            "data": element.to_dict()
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"添加元素关联失败: {str(e)}")


@router.get("/{chapter_id}/elements")
async def get_chapter_elements(
    chapter_id: str,
    element_type: Optional[str] = None,
    repo: ChapterElementRepository = Depends(get_chapter_element_repo)
):
    """
    获取章节的所有元素关联

    可选参数 element_type 用于过滤特定类型的元素。
    """
    try:
        if element_type:
            elements = await repo.get_by_chapter_and_type(
                chapter_id,
                ElementType(element_type)
            )
        else:
            elements = await repo.get_by_chapter(chapter_id)

        return {
            "success": True,
            "data": [elem.to_dict() for elem in elements]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取元素关联失败: {str(e)}")


@router.put("/{chapter_id}/elements")
async def batch_update_chapter_elements(
    chapter_id: str,
    request: ChapterElementBatchUpdate,
    repo: ChapterElementRepository = Depends(get_chapter_element_repo)
):
    """
    批量更新章节元素关联

    先删除章节的所有元素关联，再批量添加新的关联。
    """
    try:
        from domain.structure.chapter_element import ChapterElement
        from datetime import datetime

        # 删除现有关联
        await repo.delete_by_chapter(chapter_id)

        # 批量创建新关联
        elements = []
        for elem_data in request.elements:
            element = ChapterElement(
                id=f"elem-{uuid.uuid4().hex[:8]}",
                chapter_id=chapter_id,
                element_type=ElementType(elem_data.element_type),
                element_id=elem_data.element_id,
                relation_type=RelationType(elem_data.relation_type),
                importance=Importance(elem_data.importance),
                appearance_order=elem_data.appearance_order,
                notes=elem_data.notes,
                created_at=datetime.now()
            )
            elements.append(element)

        await repo.save_batch(elements)

        # 触发知识图谱推断
        from application.world.services.knowledge_graph_service import KnowledgeGraphService
        from infrastructure.persistence.database.triple_repository import TripleRepository
        from infrastructure.persistence.database.story_node_repository import StoryNodeRepository

        kg_service = KnowledgeGraphService(
            TripleRepository(),
            repo,
            StoryNodeRepository(get_db_path()),
        )
        await kg_service.infer_from_chapter(chapter_id)

        return {
            "success": True,
            "data": {
                "updated_count": len(elements),
                "elements": [elem.to_dict() for elem in elements]
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"批量更新元素关联失败: {str(e)}")


@router.delete("/{chapter_id}/elements/{element_id}")
async def delete_chapter_element(
    chapter_id: str,
    element_id: str,
    repo: ChapterElementRepository = Depends(get_chapter_element_repo)
):
    """
    删除章节元素关联
    """
    try:
        success = await repo.delete(element_id)

        if not success:
            raise HTTPException(status_code=404, detail="元素关联不存在")

        return {
            "success": True,
            "message": "删除成功"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除元素关联失败: {str(e)}")


@router.get("/elements/{element_type}/{element_id}/chapters")
async def get_element_chapters(
    element_type: str,
    element_id: str,
    repo: ChapterElementRepository = Depends(get_chapter_element_repo)
):
    """
    查询某个元素在哪些章节出现

    反向查询，用于分析人物出场频率、地点使用情况等。
    """
    try:
        elements = await repo.get_by_element(
            ElementType(element_type),
            element_id
        )

        # 获取章节信息
        from infrastructure.persistence.database.story_node_repository import StoryNodeRepository
        story_node_repo = StoryNodeRepository(get_db_path())

        chapters = []
        for elem in elements:
            chapter = await story_node_repo.get_by_id(elem.chapter_id)
            if chapter:
                chapters.append({
                    "chapter": chapter.to_dict(),
                    "relation": elem.to_dict()
                })

        return {
            "success": True,
            "data": {
                "element_type": element_type,
                "element_id": element_id,
                "appearance_count": len(chapters),
                "chapters": chapters
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询元素章节失败: {str(e)}")
