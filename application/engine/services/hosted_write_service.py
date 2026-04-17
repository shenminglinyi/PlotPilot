"""托管连写：自动规划大纲 + 按章流式生成 + 可选落库，上下文由 ContextBuilder 维护。"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncIterator, Dict, Optional, TYPE_CHECKING

from application.core.services.chapter_service import ChapterService
from application.core.services.novel_service import NovelService
from application.workflows.auto_novel_generation_workflow import AutoNovelGenerationWorkflow
from domain.shared.exceptions import EntityNotFoundError
if TYPE_CHECKING:
    from application.engine.services.chapter_aftermath_pipeline import ChapterAftermathPipeline

logger = logging.getLogger(__name__)


class HostedWriteService:
    """多章连续托管写作（单连接 SSE 推送全程事件）。"""

    def __init__(
        self,
        workflow: AutoNovelGenerationWorkflow,
        chapter_service: ChapterService,
        novel_service: NovelService,
        chapter_aftermath_pipeline: Optional["ChapterAftermathPipeline"] = None,
    ):
        self._workflow = workflow
        self._chapter = chapter_service
        self._novel = novel_service
        self._aftermath = chapter_aftermath_pipeline

    def _schedule_chapter_aftermath(self, novel_id: str, chapter_number: int, content: str) -> None:
        """与 HTTP 保存同源：叙事/向量、文风、KG（不阻塞 SSE）；三元组与伏笔在叙事同步单次 LLM 中落库。"""
        if not self._aftermath or not content.strip():
            return

        async def _run() -> None:
            try:
                dto = self._chapter.get_chapter_by_novel_and_number(novel_id, chapter_number)
                if not dto:
                    return
                await self._aftermath.run_after_chapter_saved(novel_id, chapter_number, content)
            except Exception as e:
                logger.warning(
                    "托管章后管线失败 novel=%s ch=%s: %s", novel_id, chapter_number, e
                )

        try:
            asyncio.create_task(_run())
        except Exception as e:
            logger.warning("托管章后管线未调度: %s", e)

    def _fallback_outline(self, novel_id: str, chapter_number: int) -> str:
        dto = self._chapter.get_chapter_by_novel_and_number(novel_id, chapter_number)
        title = dto.title if dto else f"第{chapter_number}章"
        return (
            f"【托管】{title}\n\n"
            "承接已有正文与设定，推进本章情节与人物；保持人称、时态与全书一致。"
        )

    async def stream_hosted_write(
        self,
        novel_id: str,
        from_chapter: int,
        to_chapter: int,
        auto_save: bool = True,
        auto_outline: bool = True,
    ) -> AsyncIterator[Dict[str, Any]]:
        """按章节区间连续生成；每章先大纲（LLM 或模板），再复用 generate_chapter_stream。

        事件在单章事件上增加 ``chapter``；并可能发出 ``session`` / ``chapter_start`` /
        ``outline`` / ``saved``。
        """
        logger.info(f"========================================")
        logger.info(f"开始托管连写: 小说={novel_id}, 章节范围={from_chapter}-{to_chapter}")
        logger.info(f"配置: auto_save={auto_save}, auto_outline={auto_outline}")
        logger.info(f"========================================")

        if from_chapter < 1 or to_chapter < 1 or to_chapter < from_chapter:
            logger.error(f"无效的章节范围: {from_chapter}-{to_chapter}")
            yield {"type": "error", "message": "invalid chapter range"}
            return

        total = to_chapter - from_chapter + 1
        logger.info(f"总计需要生成 {total} 个章节")

        yield {
            "type": "session",
            "novel_id": novel_id,
            "from_chapter": from_chapter,
            "to_chapter": to_chapter,
            "total": total,
        }

        for index, n in enumerate(range(from_chapter, to_chapter + 1), start=1):
            logger.info(f"----------------------------------------")
            logger.info(f"开始处理章节 {n} ({index}/{total})")
            logger.info(f"----------------------------------------")

            yield {"type": "chapter_start", "chapter": n, "index": index, "total": total}

            if auto_outline:
                try:
                    logger.info(f"  → 使用 LLM 生成章节 {n} 的大纲")
                    outline = await self._workflow.suggest_outline(novel_id, n)
                    logger.info(f"  ✓ 大纲生成成功: {len(outline)} 字符")
                except Exception as e:
                    logger.warning(f"  × 大纲生成失败: {e}, 使用默认模板")
                    outline = self._fallback_outline(novel_id, n)
            else:
                logger.info(f"  → 使用默认大纲模板")
                outline = self._fallback_outline(novel_id, n)

            yield {"type": "outline", "chapter": n, "text": outline}

            async for ev in self._workflow.generate_chapter_stream(novel_id, n, outline, enable_beats=True):
                merged: Dict[str, Any] = dict(ev)
                merged["chapter"] = n
                yield merged

                if ev.get("type") == "done" and auto_save:
                    content = ev.get("content") or ""
                    generation_metrics = ev.get("word_control")
                    if isinstance(generation_metrics, dict):
                        generation_metrics = {
                            **generation_metrics,
                            "generated_via": "hosted",
                        }
                    logger.info(f"  → 尝试保存章节 {n} ({len(content)} 字符)")
                    try:
                        # 先尝试更新已存在的章节
                        self._chapter.update_chapter_by_novel_and_number(
                            novel_id, n, content, generation_metrics
                        )
                        logger.info(f"  ✓ 章节 {n} 更新成功")
                        self._schedule_chapter_aftermath(novel_id, n, content)
                        yield {"type": "saved", "chapter": n, "ok": True}
                    except EntityNotFoundError as e:
                        # 章节不存在，创建新章节
                        logger.info(f"  → 章节 {n} 不存在，创建新章节")
                        try:
                            chapter_id = f"chapter-{novel_id}-{n}"
                            title = f"第{n}章"
                            self._novel.add_chapter(
                                novel_id=novel_id,
                                chapter_id=chapter_id,
                                number=n,
                                title=title,
                                content=content
                            )
                            if generation_metrics:
                                self._chapter.save_chapter_generation_metrics(
                                    novel_id,
                                    n,
                                    generation_metrics,
                                )
                            logger.info(f"  ✓ 章节 {n} 创建成功")
                            self._schedule_chapter_aftermath(novel_id, n, content)
                            yield {"type": "saved", "chapter": n, "ok": True, "created": True}
                        except (ValueError, Exception) as create_ex:
                            logger.error(f"  × 创建章节 {n} 失败: {type(create_ex).__name__}: {create_ex}")
                            yield {
                                "type": "saved",
                                "chapter": n,
                                "ok": False,
                                "message": f"创建章节失败: {create_ex}",
                            }
                    except Exception as ex:
                        logger.error(f"  × 保存章节 {n} 时发生异常: {type(ex).__name__}: {ex}")
                        yield {
                            "type": "saved",
                            "chapter": n,
                            "ok": False,
                            "message": str(ex),
                        }

                if ev.get("type") == "error":
                    logger.error(f"  × 章节 {n} 生成失败，终止托管连写")
                    return

        logger.info(f"========================================")
        logger.info(f"托管连写完成: 小说={novel_id}, 共生成 {total} 个章节")
        logger.info(f"========================================")
        yield {"type": "session_done", "novel_id": novel_id}
