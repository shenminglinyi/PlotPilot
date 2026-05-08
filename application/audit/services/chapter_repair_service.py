"""章节修复服务：扫描短章节 + AI 扩写 + 批量修复"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncIterator, Optional, TYPE_CHECKING

from application.audit.dtos.chapter_repair_dto import ChapterRepairScanResult, ShortChapterDTO
from application.core.services.chapter_service import ChapterService
from application.ai.llm_output_sanitize import strip_reasoning_artifacts
from domain.ai.services.llm_service import GenerationConfig, LLMService
from domain.ai.value_objects.prompt import Prompt
from domain.novel.repositories.chapter_repository import ChapterRepository
from domain.novel.repositories.novel_repository import NovelRepository
from domain.novel.value_objects.novel_id import NovelId

if TYPE_CHECKING:
    from application.engine.services.chapter_aftermath_pipeline import ChapterAftermathPipeline

logger = logging.getLogger(__name__)

# 严重程度阈值
_CRITICAL_THRESHOLD = 1000
_WARNING_THRESHOLD = 2500

# 前后章节摘录长度
_PREV_CHAPTER_TAIL_CHARS = 2000
_NEXT_CHAPTER_HEAD_CHARS = 500


class ChapterRepairService:
    """章节修复服务"""

    def __init__(
        self,
        chapter_repository: ChapterRepository,
        novel_repository: NovelRepository,
        llm_service: LLMService,
        chapter_service: ChapterService,
        aftermath_pipeline: Optional["ChapterAftermathPipeline"] = None,
    ):
        self._chapter_repo = chapter_repository
        self._novel_repo = novel_repository
        self._llm = llm_service
        self._chapter_svc = chapter_service
        self._aftermath = aftermath_pipeline

    def scan_short_chapters(
        self, novel_id: str, threshold: int = 4000
    ) -> ChapterRepairScanResult:
        """扫描字数不足的章节"""
        chapters = self._chapter_repo.list_by_novel(NovelId(novel_id))
        short_chapters: list[ShortChapterDTO] = []
        summary = {"critical": 0, "warning": 0, "info": 0}

        for ch in chapters:
            wc = ch.word_count.value
            if wc >= threshold:
                continue

            if wc < _CRITICAL_THRESHOLD:
                severity = "critical"
            elif wc < _WARNING_THRESHOLD:
                severity = "warning"
            else:
                severity = "info"

            summary[severity] += 1
            content = ch.content or ""
            short_chapters.append(ShortChapterDTO(
                chapter_number=ch.number,
                title=ch.title or f"第{ch.number}章",
                word_count=wc,
                status=ch.status.value if hasattr(ch.status, "value") else ch.status,
                content_preview=content[:200],
                severity=severity,
            ))

        return ChapterRepairScanResult(
            novel_id=novel_id,
            threshold=threshold,
            total_chapters=len(chapters),
            short_chapters=short_chapters,
            summary=summary,
        )

    async def expand_chapter(
        self,
        novel_id: str,
        chapter_number: int,
        target_words: int = 4000,
    ) -> AsyncIterator[dict[str, Any]]:
        """扩写单个章节，SSE 事件流"""
        yield {"type": "phase", "phase": "loading", "chapter_number": chapter_number}

        # 加载当前章
        current = self._chapter_svc.get_chapter_by_novel_and_number(novel_id, chapter_number)
        if not current:
            yield {"type": "error", "message": f"章节 {chapter_number} 不存在"}
            return

        existing_content = current.content or ""
        title = current.title or f"第{chapter_number}章"
        outline = self._get_chapter_outline(novel_id, chapter_number, title, existing_content)

        # 加载前后章
        prev_tail = self._get_prev_chapter_tail(novel_id, chapter_number)
        next_head = self._get_next_chapter_head(novel_id, chapter_number)

        yield {"type": "phase", "phase": "context", "chapter_number": chapter_number}

        # 构建 prompt
        prompt = self._build_expand_prompt(
            chapter_number=chapter_number,
            title=title,
            outline=outline,
            existing_content=existing_content,
            prev_tail=prev_tail,
            next_head=next_head,
            target_words=target_words,
        )

        yield {"type": "phase", "phase": "llm", "chapter_number": chapter_number}

        # 流式 LLM 生成
        config = GenerationConfig(max_tokens=min(target_words * 3, 16384), temperature=0.7)
        chunks: list[str] = []
        try:
            async for piece in self._llm.stream_generate(prompt, config):
                chunks.append(piece)
                yield {"type": "chunk", "text": piece, "chapter_number": chapter_number}
        except Exception as e:
            logger.error(f"章节 {chapter_number} 扩写 LLM 失败: {e}")
            yield {"type": "error", "message": f"LLM 生成失败: {e}"}
            return

        # 拼接并清理
        expanded = strip_reasoning_artifacts("".join(chunks)).strip()
        if not expanded:
            yield {"type": "error", "message": "LLM 返回空内容"}
            return

        yield {"type": "phase", "phase": "saving", "chapter_number": chapter_number}

        # 保存
        try:
            chapter_entity = self._chapter_repo.get_by_novel_and_number(
                NovelId(novel_id), chapter_number
            )
            if chapter_entity:
                chapter_entity.update_content(expanded)
                self._chapter_repo.save(chapter_entity)
        except Exception as e:
            logger.error(f"章节 {chapter_number} 保存失败: {e}")
            yield {"type": "error", "message": f"保存失败: {e}"}
            return

        # 后处理（异步，不阻塞 SSE）
        self._schedule_aftermath(novel_id, chapter_number, expanded)

        yield {
            "type": "done",
            "chapter_number": chapter_number,
            "content": expanded,
            "word_count": len(expanded),
        }

    async def batch_expand_chapters(
        self,
        novel_id: str,
        chapter_numbers: list[int],
        target_words: int = 4000,
    ) -> AsyncIterator[dict[str, Any]]:
        """批量扩写章节（顺序执行，保证前后衔接）"""
        total = len(chapter_numbers)
        yield {
            "type": "session",
            "novel_id": novel_id,
            "chapters": chapter_numbers,
            "total": total,
        }

        for i, ch_num in enumerate(chapter_numbers, 1):
            yield {"type": "chapter_start", "chapter_number": ch_num, "index": i, "total": total}
            async for event in self.expand_chapter(novel_id, ch_num, target_words):
                yield event
            yield {"type": "chapter_done", "chapter_number": ch_num, "index": i, "total": total}

        yield {"type": "session_done"}

    # ── 内部方法 ──

    def _get_chapter_outline(self, novel_id: str, chapter_number: int, title: str, content: str) -> str:
        """获取章节大纲，优先从 DB 读取，否则从内容合成"""
        chapter = self._chapter_repo.get_by_novel_and_number(NovelId(novel_id), chapter_number)
        if chapter and chapter.outline and chapter.outline.strip():
            return chapter.outline.strip()
        # 合成大纲
        preview = content[:200] if content else ""
        return f"【{title}】\n{preview}" if preview else f"【{title}】\n（大纲缺失，请根据已有内容和上下文扩写）"

    def _get_prev_chapter_tail(self, novel_id: str, chapter_number: int) -> str:
        """获取上一章尾部内容"""
        if chapter_number <= 1:
            return ""
        prev = self._chapter_svc.get_chapter_by_novel_and_number(novel_id, chapter_number - 1)
        if not prev or not prev.content:
            return ""
        content = prev.content.strip()
        if len(content) <= _PREV_CHAPTER_TAIL_CHARS:
            return f"【第{chapter_number - 1}章末尾】\n{content}"
        return f"【第{chapter_number - 1}章末尾】\n{content[-_PREV_CHAPTER_TAIL_CHARS:]}"

    def _get_next_chapter_head(self, novel_id: str, chapter_number: int) -> str:
        """获取下一章开头内容"""
        nxt = self._chapter_svc.get_chapter_by_novel_and_number(novel_id, chapter_number + 1)
        if not nxt or not nxt.content:
            return ""
        content = nxt.content.strip()
        if len(content) <= _NEXT_CHAPTER_HEAD_CHARS:
            return f"【第{chapter_number + 1}章开头】\n{content}"
        return f"【第{chapter_number + 1}章开头】\n{content[:_NEXT_CHAPTER_HEAD_CHARS]}"

    def _build_expand_prompt(
        self,
        chapter_number: int,
        title: str,
        outline: str,
        existing_content: str,
        prev_tail: str,
        next_head: str,
        target_words: int,
    ) -> Prompt:
        """构建扩写 prompt"""
        system = (
            "你是一位资深小说编辑，擅长扩写和修复因技术问题被截断的章节。\n\n"
            "必须遵守：\n"
            "1. 保留所有已有剧情事件、因果顺序、角色关系、伏笔信息。\n"
            "2. 基于章节大纲扩写，补充缺失的场景描写、对话、心理活动、环境细节。\n"
            "3. 确保与上一章末尾自然衔接，为下一章开头做好铺垫。\n"
            "4. 输出只能是扩写后的完整章节正文，不要解释，不要加章节标题。\n"
            f"5. 目标字数：{target_words} 字左右。\n"
        )

        user_parts = [f"第 {chapter_number} 章，标题：{title}\n"]
        user_parts.append(f"章节大纲：\n{outline}\n")

        if prev_tail:
            user_parts.append(f"\n上一章末尾（请确保你的开头自然衔接这段内容）：\n{prev_tail}\n")

        user_parts.append(f"\n当前章节正文（需要扩写）：\n{existing_content}\n")

        if next_head:
            user_parts.append(f"\n下一章开头（请确保你的结尾能自然过渡到这段内容）：\n{next_head}\n")

        user_parts.append(f"\n请将上述章节正文扩写至约 {target_words} 字，保持剧情连贯，直接输出正文：")

        return Prompt(system=system, user="\n".join(user_parts))

    def _schedule_aftermath(self, novel_id: str, chapter_number: int, content: str) -> None:
        """异步触发章后管线"""
        if not self._aftermath or not content.strip():
            return

        async def _run() -> None:
            try:
                await self._aftermath.run_after_chapter_saved(novel_id, chapter_number, content)
            except Exception as e:
                logger.warning(f"章节修复后管线失败 novel={novel_id} ch={chapter_number}: {e}")

        try:
            asyncio.create_task(_run())
        except Exception as e:
            logger.warning(f"章节修复后管线未调度: {e}")
