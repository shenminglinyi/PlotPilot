"""工作台聚合上下文：一次 GET 对齐「故事线·弧光 / 编年史 / 叙事知识 / 关系图 / 伏笔 / 宏观 / 沙盒依赖」只读数据。"""
import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status

from application.workbench.workbench_context_service import build_workbench_context_bundle
from domain.novel.repositories.plot_arc_repository import PlotArcRepository
from infrastructure.persistence.database.triple_repository import TripleRepository
from interfaces.api.dependencies import (
    get_bible_service,
    get_chapter_repository,
    get_database,
    get_foreshadowing_repository,
    get_knowledge_service,
    get_novel_service,
    get_plot_arc_repository,
    get_snapshot_service,
    get_storyline_manager,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/novels", tags=["workbench-context"])


def get_triple_repository() -> TripleRepository:
    return TripleRepository()


@router.get("/{novel_id}/workbench-context")
async def get_workbench_context(
    novel_id: str,
    novel_service=Depends(get_novel_service),
    bible_service=Depends(get_bible_service),
    chapter_repo=Depends(get_chapter_repository),
    snapshot_service=Depends(get_snapshot_service),
    storyline_manager=Depends(get_storyline_manager),
    plot_arc_repo: PlotArcRepository = Depends(get_plot_arc_repository),
    knowledge_service=Depends(get_knowledge_service),
    foreshadowing_repo=Depends(get_foreshadowing_repository),
    triple_repository: TripleRepository = Depends(get_triple_repository),
    db=Depends(get_database),
) -> Dict[str, Any]:
    """单次拉取多域数据，与各子路由使用相同仓储逻辑；前端可替代多次并行 GET。"""
    bundle = await build_workbench_context_bundle(
        novel_id,
        novel_service=novel_service,
        bible_service=bible_service,
        chapter_repo=chapter_repo,
        snapshot_service=snapshot_service,
        storyline_manager=storyline_manager,
        plot_arc_repo=plot_arc_repo,
        knowledge_service=knowledge_service,
        foreshadowing_repo=foreshadowing_repo,
        triple_repository=triple_repository,
        db_connection=db,
    )
    if bundle.get("error") == "novel_not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Novel not found")
    return bundle
