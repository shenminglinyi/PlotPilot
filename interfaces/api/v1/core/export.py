"""导出功能API路由"""
import urllib.parse
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from typing import Optional

from domain.novel.services.storyline_manager import StorylineManager
from infrastructure.persistence.database.sqlite_novel_repository import SqliteNovelRepository
from infrastructure.persistence.database.sqlite_chapter_repository import SqliteChapterRepository
from infrastructure.persistence.database.connection import get_database

from application.core.services.export_service import ExportService
from application.core.services.novel_service import NovelService
from application.core.services.chapter_service import ChapterService

from interfaces.api.dependencies import get_novel_repository, get_chapter_repository

router = APIRouter(prefix="/export", tags=["export"])


def get_export_service() -> ExportService:
    """获取导出服务"""
    return ExportService(
        novel_repository=get_novel_repository(),
        chapter_repository=get_chapter_repository()
    )


@router.get("/novel/{novel_id}")
async def export_novel(
    novel_id: str,
    format: str = "epub",
    export_service: ExportService = Depends(get_export_service)
):
    """导出小说
    
    Args:
        novel_id: 小说ID
        format: 导出格式，支持 epub, pdf, docx, markdown
        
    Returns:
        流式响应，包含导出的文件
    """
    try:
        # 验证格式
        valid_formats = ["epub", "pdf", "docx", "markdown"]
        if format not in valid_formats:
            raise HTTPException(status_code=400, detail=f"不支持的导出格式: {format}")
        
        # 执行导出
        file_content, media_type, filename = export_service.export_novel(novel_id, format)
        
        # 对文件名进行URL编码，避免中文编码错误
        encoded_filename = urllib.parse.quote(filename)
        
        # 返回流式响应
        return StreamingResponse(
            iter([file_content]),
            media_type=media_type,
            headers={
                "Content-Disposition": f"attachment; filename={encoded_filename}; filename*=UTF-8''{encoded_filename}"
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出失败: {str(e)}")


@router.get("/chapter/{chapter_id}")
async def export_chapter(
    chapter_id: str,
    format: str = "epub",
    export_service: ExportService = Depends(get_export_service)
):
    """导出章节
    
    Args:
        chapter_id: 章节ID
        format: 导出格式，支持 epub, pdf, docx, markdown
        
    Returns:
        流式响应，包含导出的文件
    """
    try:
        # 验证格式
        valid_formats = ["epub", "pdf", "docx", "markdown"]
        if format not in valid_formats:
            raise HTTPException(status_code=400, detail=f"不支持的导出格式: {format}")
        
        # 执行导出
        file_content, media_type, filename = export_service.export_chapter(chapter_id, format)
        
        # 对文件名进行URL编码，避免中文编码错误
        encoded_filename = urllib.parse.quote(filename)
        
        # 返回流式响应
        return StreamingResponse(
            iter([file_content]),
            media_type=media_type,
            headers={
                "Content-Disposition": f"attachment; filename={encoded_filename}; filename*=UTF-8''{encoded_filename}"
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出失败: {str(e)}")
