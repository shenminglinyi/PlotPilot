"""导出功能API路由"""
import urllib.parse
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from application.core.services.export_service import ExportService

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
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出失败: {str(e)}")


@router.get("/chapter/{chapter_id}")
async def export_chapter(
    chapter_id: str,
    format: str = "epub",
    novel_id: Optional[str] = None,
    chapter_number: Optional[int] = None,
    export_service: ExportService = Depends(get_export_service)
):
    """导出章节

    Args:
        chapter_id: 章节ID（UUID格式，如 chapter-novel1-1）
        format: 导出格式，支持 epub, pdf, docx, markdown
        novel_id: 小说ID（与 chapter_number 配合使用，替代 chapter_id）
        chapter_number: 章节编号（与 novel_id 配合使用，替代 chapter_id）

    Returns:
        流式响应，包含导出的文件
    """
    try:
        # 验证格式
        valid_formats = ["epub", "pdf", "docx", "markdown"]
        if format not in valid_formats:
            raise HTTPException(status_code=400, detail=f"不支持的导出格式: {format}")

        # 支持 novel_id + chapter_number 方式
        if novel_id and chapter_number is not None:
            from application.core.services.chapter_service import ChapterService
            from interfaces.api.dependencies import get_chapter_repository, get_novel_repository
            chapter_service = ChapterService(get_chapter_repository(), get_novel_repository())
            chapter_dto = chapter_service.get_chapter_by_novel_and_number(novel_id, chapter_number)
            if not chapter_dto:
                raise HTTPException(status_code=404, detail=f"章节不存在: 小说={novel_id}, 编号={chapter_number}")
            chapter_id = chapter_dto.id

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
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出失败: {str(e)}")
