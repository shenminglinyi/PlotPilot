"""
知识图谱推断 API 路由
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional

from application.world.services.knowledge_graph_service import KnowledgeGraphService
from infrastructure.persistence.database.triple_repository import TripleRepository
from infrastructure.persistence.database.chapter_element_repository import ChapterElementRepository
from infrastructure.persistence.database.story_node_repository import StoryNodeRepository
from application.paths import get_db_path
from domain.bible.triple import SourceType
from infrastructure.persistence.database.sqlite_knowledge_repository import SqliteKnowledgeRepository
from interfaces.api.dependencies import get_knowledge_repository


router = APIRouter(prefix="/api/v1/knowledge-graph", tags=["knowledge-graph"])


# ==================== 依赖注入 ====================

def get_kg_service() -> KnowledgeGraphService:
    """获取知识图谱服务"""
    db_path = get_db_path()
    return KnowledgeGraphService(
        TripleRepository(),
        ChapterElementRepository(db_path),
        StoryNodeRepository(db_path),
    )


def get_triple_repo() -> TripleRepository:
    """获取三元组仓储"""
    return TripleRepository()


# ==================== API 端点 ====================

@router.get("/novels/{novel_id}/chapters/by-number/{chapter_number}/inference-evidence")
async def get_chapter_inference_evidence(
    novel_id: str,
    chapter_number: int,
    kr: SqliteKnowledgeRepository = Depends(get_knowledge_repository),
):
    """
    按正文章节号解析 story_nodes 章节节点，返回本章关联的推断三元组及证据行（chapter_inferred）。
    """
    try:
        snid = kr.find_story_node_id_for_chapter_number(novel_id, chapter_number)
        if not snid:
            return {
                "success": True,
                "data": {
                    "story_node_id": None,
                    "chapter_number": chapter_number,
                    "facts": [],
                    "hint": "未找到对应故事结构中的章节节点（需在规划中维护 chapter 类型节点且 number 与正文章节号一致）",
                },
            }
        facts = kr.list_chapter_inference_evidence(novel_id, snid)
        return {
            "success": True,
            "data": {
                "story_node_id": snid,
                "chapter_number": chapter_number,
                "facts": facts,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"加载本章推断证据失败: {str(e)}")


@router.delete("/novels/{novel_id}/chapters/by-number/{chapter_number}/inference")
async def revoke_chapter_inference_for_chapter_number(
    novel_id: str,
    chapter_number: int,
    kr: SqliteKnowledgeRepository = Depends(get_knowledge_repository),
):
    """
    撤销本章下的推断：删除 triple_provenance 中本 story_node 的证据；
    若某三元组不再有任何证据且为 chapter_inferred，则删除该三元组。
    """
    try:
        snid = kr.find_story_node_id_for_chapter_number(novel_id, chapter_number)
        if not snid:
            raise HTTPException(
                status_code=404,
                detail="未找到故事结构章节节点，无法按章撤销推断",
            )
        stats = kr.revoke_chapter_inference_for_story_node(novel_id, snid)
        return {"success": True, "data": stats}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"撤销本章推断失败: {str(e)}")


@router.delete("/novels/{novel_id}/inferred-triples/{triple_id}")
async def revoke_single_chapter_inferred_triple(
    novel_id: str,
    triple_id: str,
    kr: SqliteKnowledgeRepository = Depends(get_knowledge_repository),
):
    """仅删除 source_type=chapter_inferred 的三元组（级联删除其 triple_provenance）。"""
    try:
        outcome = kr.try_delete_chapter_inferred_triple(novel_id, triple_id)
        if outcome == "not_found":
            raise HTTPException(status_code=404, detail="三元组不存在")
        if outcome == "not_inferred":
            raise HTTPException(
                status_code=400,
                detail="只能撤销 chapter_inferred 来源的推断三元组",
            )
        return {"success": True, "message": "已撤销该条推断"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"撤销推断失败: {str(e)}")


@router.post("/novels/{novel_id}/infer")
async def infer_novel_knowledge_graph(
    novel_id: str,
    service: KnowledgeGraphService = Depends(get_kg_service)
):
    """
    推断整部小说的知识图谱

    分析所有章节的元素关联，自动生成三元组关系。
    这是一个耗时操作，建议在后台执行。
    """
    try:
        stats = await service.infer_from_novel(novel_id)

        return {
            "success": True,
            "data": stats
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"推断知识图谱失败: {str(e)}")


@router.post("/chapters/{chapter_id}/infer")
async def infer_chapter_knowledge_graph(
    chapter_id: str,
    service: KnowledgeGraphService = Depends(get_kg_service)
):
    """
    推断单个章节的知识图谱

    分析章节的元素关联，自动生成三元组关系。
    """
    try:
        triples = await service.infer_from_chapter(chapter_id)

        return {
            "success": True,
            "data": {
                "chapter_id": chapter_id,
                "inferred_triples": len(triples),
                "triples": [triple.to_dict() for triple in triples]
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"推断章节知识图谱失败: {str(e)}")


@router.get("/novels/{novel_id}/triples")
async def get_novel_triples(
    novel_id: str,
    source_type: Optional[str] = None,
    min_confidence: float = 0.0,
):
    """
    获取小说的所有三元组

    🔥 优化：从共享内存读取，不阻塞事件循环。

    可选参数：
    - source_type: 过滤来源类型 (manual/auto_inferred/ai_generated)
    - min_confidence: 最低置信度阈值 (0.0-1.0)
    """
    from application.engine.services.query_service import get_query_service

    try:
        query = get_query_service()
        triples_raw = query.get_triples(novel_id)

        # 过滤来源类型
        if source_type:
            triples_raw = [t for t in triples_raw if t.get("source_type") == source_type]

        # 过滤置信度
        if min_confidence > 0:
            triples_raw = [t for t in triples_raw if t.get("confidence", 1.0) >= min_confidence]

        return {
            "success": True,
            "data": {
                "total": len(triples_raw),
                "triples": triples_raw
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取三元组失败: {str(e)}")


@router.get("/chapters/{chapter_id}/triples")
async def get_chapter_triples(
    chapter_id: str,
    repo: TripleRepository = Depends(get_triple_repo)
):
    """
    获取章节相关的三元组

    返回该章节推断出的所有三元组。
    """
    try:
        triples = await repo.get_by_chapter(chapter_id)

        return {
            "success": True,
            "data": {
                "chapter_id": chapter_id,
                "total": len(triples),
                "triples": [triple.to_dict() for triple in triples]
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取章节三元组失败: {str(e)}")


@router.post("/triples/{triple_id}/confirm")
async def confirm_triple(
    triple_id: str,
    repo: TripleRepository = Depends(get_triple_repo)
):
    """
    确认三元组

    将自动推断的三元组确认为手动创建，置信度设为 1.0。
    """
    try:
        triple = await repo.get_by_id(triple_id)
        if not triple:
            raise HTTPException(status_code=404, detail="三元组不存在")

        triple.confirm()
        await repo.update(triple)

        return {
            "success": True,
            "data": triple.to_dict()
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"确认三元组失败: {str(e)}")


@router.delete("/triples/{triple_id}")
async def delete_triple(
    triple_id: str,
    repo: TripleRepository = Depends(get_triple_repo)
):
    """
    删除三元组

    用于拒绝自动推断的错误关系。
    """
    try:
        success = await repo.delete(triple_id)

        if not success:
            raise HTTPException(status_code=404, detail="三元组不存在")

        return {
            "success": True,
            "message": "删除成功"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除三元组失败: {str(e)}")


@router.get("/elements/{element_type}/{element_id}/relations")
async def get_element_relations(
    element_type: str,
    element_id: str,
    repo: TripleRepository = Depends(get_triple_repo)
):
    """
    获取元素的所有关系

    查询某个元素（人物、地点等）的所有三元组关系。
    包括作为主体和客体的关系。
    """
    try:
        # 获取作为主体的关系
        subject_triples = await repo.get_by_subject(
            novel_id="",  # 需要从元素 ID 推断
            subject_type=element_type,
            subject_id=element_id
        )

        # 获取作为客体的关系
        object_triples = await repo.get_by_object(
            novel_id="",  # 需要从元素 ID 推断
            object_type=element_type,
            object_id=element_id
        )

        return {
            "success": True,
            "data": {
                "element_type": element_type,
                "element_id": element_id,
                "as_subject": [t.to_dict() for t in subject_triples],
                "as_object": [t.to_dict() for t in object_triples],
                "total": len(subject_triples) + len(object_triples)
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取元素关系失败: {str(e)}")


@router.get("/novels/{novel_id}/statistics")
async def get_knowledge_graph_statistics(novel_id: str):
    """
    获取知识图谱统计信息

    🔥 优化：从共享内存读取，不阻塞事件循环。

    返回三元组的统计数据，包括总数、来源分布、置信度分布等。
    """
    from application.engine.services.query_service import get_query_service

    try:
        query = get_query_service()
        kg_data = query.get_knowledge_graph(novel_id)
        triples_raw = query.get_triples(novel_id)

        # 统计来源类型
        source_stats = {}
        for triple in triples_raw:
            source = triple.get("source_type", "unknown")
            source_stats[source] = source_stats.get(source, 0) + 1

        # 统计置信度分布
        confidence_ranges = {
            "high": 0,      # >= 0.8
            "medium": 0,    # 0.6 - 0.8
            "low": 0        # < 0.6
        }
        for triple in triples_raw:
            conf = triple.get("confidence", 1.0)
            if conf >= 0.8:
                confidence_ranges["high"] += 1
            elif conf >= 0.6:
                confidence_ranges["medium"] += 1
            else:
                confidence_ranges["low"] += 1

        # 统计关系类型
        predicate_stats = {}
        for triple in triples_raw:
            pred = triple.get("predicate", "")
            predicate_stats[pred] = predicate_stats.get(pred, 0) + 1

        return {
            "success": True,
            "data": {
                "total_triples": kg_data.get("total_triples", len(triples_raw)),
                "source_distribution": source_stats,
                "confidence_distribution": confidence_ranges,
                "predicate_distribution": predicate_stats
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取统计信息失败: {str(e)}")


# ==================== 向量索引与语义检索 ====================

@router.post("/novels/{novel_id}/index")
async def index_novel_triples(
    novel_id: str,
    repo: TripleRepository = Depends(get_triple_repo)
):
    """
    将小说的所有三元组索引到向量数据库
    
    建立向量索引后，支持通过语义相似度检索三元组。
    这是一个耗时操作，建议在后台执行。
    """
    try:
        from interfaces.api.dependencies import get_triple_indexing_service
        
        indexing_service = get_triple_indexing_service()
        if indexing_service is None:
            raise HTTPException(
                status_code=503, 
                detail="向量索引服务不可用，请检查 EMBEDDING_SERVICE 配置"
            )
        
        # 获取所有三元组
        triples = await repo.get_by_novel(novel_id)
        if not triples:
            return {
                "success": True,
                "message": "没有需要索引的三元组",
                "data": {"indexed_count": 0}
            }
        
        # 转换为字典格式
        triple_dicts = []
        for t in triples:
            triple_dicts.append({
                "id": t.id,
                "subject": t.subject_id,
                "predicate": t.predicate,
                "object": t.object_id,
                "subject_type": t.subject_type,
                "object_type": t.object_type,
                "description": t.description,
                "chapter_number": t.first_appearance,
                "confidence": t.confidence,
            })
        
        # 批量索引
        indexed_count = await indexing_service.index_triples_batch(novel_id, triple_dicts)
        
        return {
            "success": True,
            "message": f"成功索引 {indexed_count} 个三元组",
            "data": {
                "total_triples": len(triples),
                "indexed_count": indexed_count
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"索引三元组失败: {str(e)}")


@router.post("/novels/{novel_id}/search")
async def semantic_search_triples(
    novel_id: str,
    query: str,
    limit: int = 10,
    min_score: float = 0.5,
):
    """
    语义检索三元组
    
    使用向量相似度搜索找到与查询语义相关的三元组。
    需要先调用 /novels/{novel_id}/index 建立索引。
    
    Args:
        novel_id: 小说 ID
        query: 查询文本（如 "战斗技能"、"武器属性"）
        limit: 返回结果数量（默认 10）
        min_score: 最小相似度阈值（默认 0.5）
    """
    try:
        from interfaces.api.dependencies import get_triple_indexing_service
        
        indexing_service = get_triple_indexing_service()
        if indexing_service is None:
            raise HTTPException(
                status_code=503,
                detail="向量索引服务不可用，请检查 EMBEDDING_SERVICE 配置"
            )
        
        results = await indexing_service.search_triples(
            novel_id=novel_id,
            query=query,
            limit=limit,
            min_score=min_score,
        )
        
        return {
            "success": True,
            "data": {
                "query": query,
                "total": len(results),
                "results": results
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"语义检索失败: {str(e)}")
