"""导出服务"""
import io
from typing import Tuple, Optional

from domain.novel.repositories.novel_repository import NovelRepository
from domain.novel.repositories.chapter_repository import ChapterRepository
from domain.novel.entities.novel import Novel
from domain.novel.entities.chapter import Chapter
from domain.novel.value_objects.novel_id import NovelId
from domain.novel.value_objects.chapter_id import ChapterId


class ExportService:
    """导出服务"""
    
    def __init__(self, novel_repository: NovelRepository, chapter_repository: ChapterRepository):
        """
        初始化导出服务
        
        Args:
            novel_repository: 小说仓库
            chapter_repository: 章节仓库
        """
        self.novel_repository = novel_repository
        self.chapter_repository = chapter_repository
    
    def export_novel(self, novel_id: str, format: str) -> Tuple[bytes, str, str]:
        """
        导出小说
        
        Args:
            novel_id: 小说ID
            format: 导出格式
            
        Returns:
            Tuple[bytes, str, str]: (文件内容, 媒体类型, 文件名)
        """
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            logger.info(f"开始导出小说: {novel_id}, 格式: {format}")
            
            # 获取小说信息
            novel = self.novel_repository.get_by_id(NovelId(novel_id))
            if not novel:
                raise ValueError(f"小说不存在: {novel_id}")
            
            logger.info(f"获取到小说: {novel.title}")
            
            # 获取小说的所有章节
            chapters = self.chapter_repository.list_by_novel(NovelId(novel_id))
            logger.info(f"获取到章节数量: {len(chapters)}")
            
            # 按章节号排序
            chapters.sort(key=lambda x: x.number)
            
            # 根据格式执行导出
            if format == "epub":
                result = self._export_to_epub(novel, chapters)
            elif format == "pdf":
                result = self._export_to_pdf(novel, chapters)
            elif format == "docx":
                result = self._export_to_docx(novel, chapters)
            elif format == "markdown":
                result = self._export_to_markdown(novel, chapters)
            else:
                raise ValueError(f"不支持的导出格式: {format}")
            
            logger.info(f"导出成功，文件大小: {len(result[0])} 字节")
            return result
        except Exception as e:
            logger.error(f"导出小说失败: {str(e)}")
            raise
    
    def export_chapter(self, chapter_id: str, format: str) -> Tuple[bytes, str, str]:
        """
        导出章节
        
        Args:
            chapter_id: 章节ID
            format: 导出格式
            
        Returns:
            Tuple[bytes, str, str]: (文件内容, 媒体类型, 文件名)
        """
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            logger.info(f"开始导出章节: {chapter_id}, 格式: {format}")
            
            # 获取章节信息
            chapter = self.chapter_repository.get_by_id(ChapterId(chapter_id))
            if not chapter:
                raise ValueError(f"章节不存在: {chapter_id}")
            
            logger.info(f"获取到章节: {chapter.title}")
            
            # 获取小说信息
            novel_id = chapter.novel_id.value if hasattr(chapter.novel_id, 'value') else chapter.novel_id
            novel = self.novel_repository.get_by_id(NovelId(novel_id))
            if not novel:
                raise ValueError(f"小说不存在: {novel_id}")
            
            logger.info(f"获取到小说: {novel.title}")
            
            # 根据格式执行导出
            if format == "epub":
                result = self._export_to_epub(novel, [chapter])
            elif format == "pdf":
                result = self._export_to_pdf(novel, [chapter])
            elif format == "docx":
                result = self._export_to_docx(novel, [chapter])
            elif format == "markdown":
                result = self._export_to_markdown(novel, [chapter])
            else:
                raise ValueError(f"不支持的导出格式: {format}")
            
            logger.info(f"导出成功，文件大小: {len(result[0])} 字节")
            return result
        except Exception as e:
            logger.error(f"导出章节失败: {str(e)}")
            raise
    
    def _export_to_epub(self, novel: Novel, chapters: list[Chapter]) -> Tuple[bytes, str, str]:
        """导出为EPUB格式"""
        # 这里使用临时实现，实际需要使用专业的EPUB生成库
        content = f"EPUB Export for {novel.title}\n\n"
        for chapter in chapters:
            content += f"# {chapter.title}\n\n{chapter.content}\n\n"
        
        file_content = content.encode('utf-8')
        media_type = "application/epub+zip"
        filename = f"{novel.title.replace(' ', '_')}.epub"
        
        return file_content, media_type, filename
    
    def _export_to_pdf(self, novel: Novel, chapters: list[Chapter]) -> Tuple[bytes, str, str]:
        """导出为PDF格式"""
        # 这里使用临时实现，实际需要使用PDF生成库
        content = f"PDF Export for {novel.title}\n\n"
        for chapter in chapters:
            content += f"# {chapter.title}\n\n{chapter.content}\n\n"
        
        file_content = content.encode('utf-8')
        media_type = "application/pdf"
        filename = f"{novel.title.replace(' ', '_')}.pdf"
        
        return file_content, media_type, filename
    
    def _export_to_docx(self, novel: Novel, chapters: list[Chapter]) -> Tuple[bytes, str, str]:
        """导出为DOCX格式"""
        # 这里使用临时实现，实际需要使用DOCX生成库
        content = f"DOCX Export for {novel.title}\n\n"
        for chapter in chapters:
            content += f"# {chapter.title}\n\n{chapter.content}\n\n"
        
        file_content = content.encode('utf-8')
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        filename = f"{novel.title.replace(' ', '_')}.docx"
        
        return file_content, media_type, filename
    
    def _export_to_markdown(self, novel: Novel, chapters: list[Chapter]) -> Tuple[bytes, str, str]:
        """导出为Markdown格式"""
        content = f"# {novel.title}\n\n"
        content += f"## 作者: {novel.author}\n\n"
        content += f"## 简介\n{novel.premise}\n\n"
        
        for chapter in chapters:
            content += f"## {chapter.title}\n\n{chapter.content}\n\n"
        
        file_content = content.encode('utf-8')
        media_type = "text/markdown"
        filename = f"{novel.title.replace(' ', '_')}.md"
        
        return file_content, media_type, filename
