"""工作台聚合上下文：一次 GET 对齐「故事线·弧光 / 编年史 / 叙事知识 / 关系图 / 伏笔 / 宏观 / 沙盒依赖」只读数据。

🔥 核心架构优化：纯内存读取，纳秒级响应，永不阻塞事件循环。

所有数据都从共享内存读取，完全不走 DB。
"""
import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, status

from application.engine.services.query_service import get_query_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/novels", tags=["workbench-context"])


@router.get("/{novel_id}/workbench-context")
async def get_workbench_context(novel_id: str) -> Dict[str, Any]:
    """单次拉取多域数据，与各子路由使用相同仓储逻辑；前端可替代多次并行 GET。

    🔥 核心架构优化：纯内存读取，纳秒级响应。

    所有数据都从共享内存读取，完全不走 DB。
    这是"内存优先读取"架构的核心端点之一。
    """
    query = get_query_service()

    # 检查小说是否存在
    novel_status = query.get_novel_status(novel_id)
    if novel_status is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Novel not found"
        )

    # 从共享内存获取所有数据
    context = query.get_workbench_context(novel_id)

    return context.to_dict()
