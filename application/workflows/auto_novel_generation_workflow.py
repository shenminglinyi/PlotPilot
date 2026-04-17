"""自动小说生成工作流

整合所有子项目组件，实现完整的章节生成流程。
"""
import logging
import re
from typing import Tuple, Dict, Any, AsyncIterator, Optional, List
from application.engine.services.context_builder import ContextBuilder
from application.engine.word_count_control import generate_with_word_control
from application.engine.services.word_control_service import (
    DEFAULT_MAX_TARGET,
    DEFAULT_MIN_TARGET,
    WordControlMetadata,
    WordControlService,
    effective_length,
)
from application.analyst.services.state_extractor import StateExtractor
from application.analyst.services.state_updater import StateUpdater
from application.audit.services.conflict_detection_service import ConflictDetectionService
from application.engine.services.style_constraint_builder import build_style_summary
from application.engine.dtos.generation_result import GenerationResult
from application.engine.dtos.scene_director_dto import SceneDirectorAnalysis
from application.engine.dtos.word_control_dto import WordControlDTO
from application.audit.dtos.ghost_annotation import GhostAnnotation
from domain.novel.services.consistency_checker import ConsistencyChecker
from domain.novel.services.storyline_manager import StorylineManager
from domain.novel.repositories.plot_arc_repository import PlotArcRepository
from domain.bible.repositories.bible_repository import BibleRepository
from domain.novel.repositories.foreshadowing_repository import ForeshadowingRepository
from domain.novel.value_objects.consistency_report import ConsistencyReport
from domain.novel.value_objects.consistency_report import Issue, IssueType, Severity
from domain.novel.value_objects.chapter_state import ChapterState
from domain.novel.value_objects.consistency_context import ConsistencyContext
from domain.novel.value_objects.novel_id import NovelId
from domain.ai.services.llm_service import LLMService, GenerationConfig
from domain.ai.value_objects.prompt import Prompt

logger = logging.getLogger(__name__)


def _consistency_report_to_dict(report: ConsistencyReport) -> Dict[str, Any]:
    """供 SSE / JSON 序列化。"""
    return {
        "issues": [
            {
                "type": issue.type.value,
                "severity": issue.severity.value,
                "description": issue.description,
                "location": issue.location,
            }
            for issue in report.issues
        ],
        "warnings": [
            {
                "type": w.type.value,
                "severity": w.severity.value,
                "description": w.description,
                "location": w.location,
            }
            for w in report.warnings
        ],
        "suggestions": list(report.suggestions),
    }


class AutoNovelGenerationWorkflow:
    """自动小说生成工作流

    整合所有组件完成完整的章节生成流程：
    1. Planning Phase: 获取故事线上下文、情节弧张力
    2. Pre-Generation: 使用 ContextBuilder 构建 35K token 上下文
    3. Generation: 调用 LLM 生成内容
    4. Post-Generation: 提取状态、检查一致性、更新状态
    5. Review Phase: 返回一致性报告
    """

    def __init__(
        self,
        context_builder: ContextBuilder,
        consistency_checker: ConsistencyChecker,
        storyline_manager: StorylineManager,
        plot_arc_repository: PlotArcRepository,
        llm_service: LLMService,
        state_extractor: Optional[StateExtractor] = None,
        state_updater: Optional[StateUpdater] = None,
        bible_repository: Optional[BibleRepository] = None,
        foreshadowing_repository: Optional[ForeshadowingRepository] = None,
        conflict_detection_service: Optional[ConflictDetectionService] = None,
        voice_fingerprint_service: Optional['VoiceFingerprintService'] = None,
        cliche_scanner: Optional['ClicheScanner'] = None,
        word_control_service: Optional[WordControlService] = None,
    ):
        """初始化工作流

        Args:
            context_builder: 上下文构建器
            consistency_checker: 一致性检查器
            storyline_manager: 故事线管理器
            plot_arc_repository: 情节弧仓储
            llm_service: LLM 服务
            state_extractor: 状态提取器（可选）
            state_updater: 状态更新器（可选）
            bible_repository: Bible 仓储（用于一致性检查，可选）
            foreshadowing_repository: Foreshadowing 仓储（用于一致性检查，可选）
            conflict_detection_service: 冲突检测服务（可选）
            voice_fingerprint_service: 风格指纹服务（可选）
            cliche_scanner: 俗套扫描器（可选）
        """
        self.context_builder = context_builder
        self.consistency_checker = consistency_checker
        self.storyline_manager = storyline_manager
        self.plot_arc_repository = plot_arc_repository
        self.llm_service = llm_service
        
        # 强制初始化 StateExtractor（如果未提供）
        if state_extractor is None:
            logger.info("StateExtractor not provided, creating default instance")
            self.state_extractor = StateExtractor(llm_service=llm_service)
        else:
            self.state_extractor = state_extractor
        
        # 强制初始化 StateUpdater（如果未提供且有所需仓储）
        if state_updater is None and bible_repository and foreshadowing_repository:
            logger.info("StateUpdater not provided, creating default instance")
            from infrastructure.persistence.database.connection import get_database
            db = get_database()
            self.state_updater = StateUpdater(
                bible_repository=bible_repository,
                foreshadowing_repository=foreshadowing_repository,
                db_connection=db.get_connection()
            )
        else:
            self.state_updater = state_updater
        
        self.bible_repository = bible_repository
        self.foreshadowing_repository = foreshadowing_repository
        self.conflict_detection_service = conflict_detection_service
        self.voice_fingerprint_service = voice_fingerprint_service
        self.cliche_scanner = cliche_scanner
        self.theme_agent = None  # ThemeAgent 插槽，由外部注入
        self.word_control_service = word_control_service or WordControlService()

    def prepare_chapter_generation(
        self,
        novel_id: str,
        chapter_number: int,
        outline: str,
        *,
        scene_director: Optional[SceneDirectorAnalysis] = None,
        max_tokens: int = 35000,
    ) -> Dict[str, Any]:
        """与单章 / 流式 / 托管按节拍写作同源：结构化三层上下文 + 故事线 + 张力 + 文风。

        托管守护进程与 HTTP 接口应复用此方法，避免「两套基建」。
        """
        storyline_context = self._get_storyline_context(novel_id, chapter_number)
        plot_tension = self._get_plot_tension(novel_id, chapter_number)
        payload = self.context_builder.build_structured_context(
            novel_id=novel_id,
            chapter_number=chapter_number,
            outline=outline,
            max_tokens=max_tokens,
            scene_director=scene_director,
        )
        context = (
            f"{payload['layer1_text']}\n\n=== SMART RETRIEVAL ===\n{payload['layer2_text']}\n\n"
            f"=== RECENT CONTEXT ===\n{payload['layer3_text']}"
        )
        context_tokens = payload["token_usage"]["total"]
        style_summary = self._get_style_summary(novel_id)
        voice_anchors = ""
        try:
            voice_anchors = self.context_builder.build_voice_anchor_system_section(novel_id)
        except Exception as e:
            logger.warning("voice_anchor section skipped: %s", e)
        return {
            "storyline_context": storyline_context,
            "plot_tension": plot_tension,
            "context": context,
            "context_tokens": context_tokens,
            "style_summary": style_summary,
            "voice_anchors": voice_anchors,
        }

    async def post_process_generated_chapter(
        self,
        novel_id: str,
        chapter_number: int,
        outline: str,
        content: str,
        scene_director: Optional[SceneDirectorAnalysis] = None,
    ) -> Dict[str, Any]:
        """生成正文后的统一后处理：俗套扫描、状态提取、一致性、冲突批注、StateUpdater。"""
        content, seam_rewrite_info = await self._apply_seam_rewrite_loop(
            novel_id=novel_id,
            chapter_number=chapter_number,
            outline=outline,
            content=content,
        )
        style_warnings = self._scan_cliches(content)
        chapter_state = await self._extract_chapter_state(content, chapter_number)
        consistency_report = self._check_consistency(chapter_state, novel_id)
        consistency_report = self._review_chapter_seam(
            novel_id=novel_id,
            chapter_number=chapter_number,
            content=content,
            base_report=consistency_report,
            rewrite_info=seam_rewrite_info,
        )
        ghost_annotations = self._detect_conflicts(novel_id, chapter_number, outline, scene_director)
        # 修复问题 9：只有章节通过 seam 检查后才持久化状态，避免被拒绝的章节污染知识库
        if self.state_updater and not self._requires_manual_seam_revision(seam_rewrite_info):
            try:
                self.state_updater.update_from_chapter(novel_id, chapter_number, chapter_state)
            except Exception as e:
                logger.warning("StateUpdater 失败: %s", e)
        return {
            "content": content,
            "style_warnings": style_warnings,
            "chapter_state": chapter_state,
            "consistency_report": consistency_report,
            "ghost_annotations": ghost_annotations,
            "seam_rewrite_info": seam_rewrite_info,
        }

    def _resolve_target_word_count(self, target_word_count: Optional[int]) -> Optional[int]:
        if target_word_count is None:
            return None
        self.word_control_service.validate_target(target_word_count)
        return target_word_count

    def _emit_word_control_warning(self, target_word_count: Optional[int]) -> Optional[Dict[str, Any]]:
        if target_word_count is None:
            return None
        if not self.word_control_service.target_requires_warning(target_word_count):
            return None
        return {
            "type": "warning",
            "warning_type": "target_word_count_extreme",
            "target_word_count": target_word_count,
            "recommended_min": DEFAULT_MIN_TARGET,
            "recommended_max": DEFAULT_MAX_TARGET,
            "message": f"目标字数 {target_word_count} 偏离常用范围（建议 {DEFAULT_MIN_TARGET}-{DEFAULT_MAX_TARGET} 字）。",
        }

    def _serialize_word_control(self, metadata: Optional[WordControlMetadata]) -> Optional[WordControlDTO]:
        if metadata is None:
            return None
        return WordControlDTO(
            target=metadata.target,
            actual=metadata.actual,
            tolerance=metadata.tolerance,
            delta=metadata.delta,
            status=metadata.status,
            within_tolerance=metadata.within_tolerance,
            action=metadata.action,
            expansion_attempts=metadata.expansion_attempts,
            trim_applied=metadata.trim_applied,
            fallback_used=metadata.fallback_used,
            min_allowed=metadata.min_allowed,
            max_allowed=metadata.max_allowed,
        )

    async def _generate_chapter_content(
        self,
        *,
        context: str,
        outline: str,
        bundle: Dict[str, Any],
        config: GenerationConfig,
        chapter_number: int,
        enable_beats: bool,
        target_word_count: Optional[int],
    ) -> tuple[str, list[dict[str, Any]]]:
        beats = []
        if enable_beats:
            logger.info("  → 启用节拍模式，拆分大纲为微观节拍")
            raw_beats = self.context_builder.magnify_outline_to_beats(chapter_number, outline)
            if isinstance(raw_beats, list):
                beats = raw_beats
            else:
                try:
                    beats = list(raw_beats or [])
                except TypeError:
                    beats = []
            logger.info(f"  ✓ 已拆分为 {len(beats)} 个微观节拍")

        if enable_beats and beats:
            content_parts = []
            for i, beat in enumerate(beats):
                beat_prompt_text = self.context_builder.build_beat_prompt(beat, i, len(beats))
                logger.info(f"生成节拍 {i+1}/{len(beats)}: {beat.focus} - {beat.description[:50]}...")
                prompt = self._build_prompt(
                    context,
                    outline,
                    storyline_context=bundle["storyline_context"],
                    plot_tension=bundle["plot_tension"],
                    style_summary=bundle["style_summary"],
                    beat_prompt=beat_prompt_text,
                    beat_index=i,
                    total_beats=len(beats),
                    beat_target_words=beat.target_words,
                    voice_anchors=bundle.get("voice_anchors") or "",
                )
                if target_word_count is not None:
                    prompt = self.word_control_service.inject_length_requirements(
                        prompt,
                        target=target_word_count,
                    )
                llm_result = await self.llm_service.generate(prompt, config)
                content_parts.append(llm_result.content)

            content = "".join(content_parts)
            logger.info(f"  ✓ 节拍生成完成: {len(beats)} 个节拍, {len(content)} 字符")
        else:
            prompt = self._build_prompt(
                context,
                outline,
                storyline_context=bundle["storyline_context"],
                plot_tension=bundle["plot_tension"],
                style_summary=bundle["style_summary"],
                voice_anchors=bundle.get("voice_anchors") or "",
            )
            if target_word_count is not None:
                prompt = self.word_control_service.inject_length_requirements(
                    prompt,
                    target=target_word_count,
                )
            logger.info(f"  → 发送请求到 LLM (max_tokens={config.max_tokens}, temperature={config.temperature})")
            llm_result = await self.llm_service.generate(prompt, config)
            content = llm_result.content
            logger.info(f"  ✓ LLM 响应已接收: {len(content)} 字符")

        micro_beats = []
        if beats:
            micro_beats = [
                {
                    "description": beat.description,
                    "target_words": beat.target_words,
                    "focus": beat.focus,
                }
                for beat in beats
            ]
        return content, micro_beats

    async def _apply_word_control(
        self,
        *,
        content: str,
        outline: str,
        target_word_count: Optional[int],
        emit_event: Optional[Any] = None,
    ) -> tuple[str, Optional[WordControlMetadata]]:
        if target_word_count is None:
            return content, None

        if emit_event:
            await emit_event(
                {
                    "type": "phase",
                    "phase": "post",
                    "status_text": "字数检测与修正中",
                    "word_control_step": "controlling",
                }
            )

        async def llm_caller(prompt: Prompt):
            return await self.llm_service.generate(prompt, GenerationConfig())

        result = await generate_with_word_control(
            prompt=Prompt(
                system="你是长篇小说续写助手，负责补写当前章节缺失内容。",
                user=outline,
            ),
            target_words=target_word_count,
            llm_caller=llm_caller,
            initial_content=content,
            emit_event=emit_event,
        )

        controlled_content = result["content"]

        metadata = WordControlMetadata(
            target=result["target_word_count"],
            actual=result["actual_word_count"],
            tolerance=result["tolerance"],
            delta=result["delta"],
            status=result["status"],
            within_tolerance=result["within_tolerance"],
            action=result["action"],
            expansion_attempts=result["expansion_attempts"],
            trim_applied=result["trim_applied"],
            fallback_used=result["fallback_used"],
            min_allowed=result["min_allowed"],
            max_allowed=result["max_allowed"],
        )
        return controlled_content, metadata

    async def generate_chapter(
        self,
        novel_id: str,
        chapter_number: int,
        outline: str,
        scene_director: Optional[SceneDirectorAnalysis] = None,
        enable_beats: bool = True,
        target_word_count: Optional[int] = None,
    ) -> GenerationResult:
        """生成章节（完整工作流）

        Args:
            novel_id: 小说 ID
            chapter_number: 章节号
            outline: 章节大纲
            scene_director: 可选的场记分析结果，用于过滤角色和地点

        Returns:
            GenerationResult 包含内容、一致性报告、上下文和 token 数

        Raises:
            ValueError: 如果参数无效
            RuntimeError: 如果生成失败
        """
        # 验证输入
        if chapter_number < 1:
            raise ValueError("chapter_number must be positive")
        if not outline or not outline.strip():
            raise ValueError("outline cannot be empty")
        target_word_count = self._resolve_target_word_count(target_word_count)

        logger.info(f"========================================")
        logger.info(f"开始生成章节: 小说={novel_id}, 章节={chapter_number}")
        logger.info(f"大纲: {outline[:100]}...")
        logger.info(f"========================================")

        logger.info("阶段 1-2: 规划 + 结构化上下文（prepare_chapter_generation）")
        bundle = self.prepare_chapter_generation(
            novel_id, chapter_number, outline, scene_director=scene_director
        )
        context = bundle["context"]
        context_tokens = bundle["context_tokens"]
        logger.info(f"  ✓ 上下文已构建: {len(context)} 字符, 约 {context_tokens} tokens")

        logger.info("阶段 3: 生成 - 调用 LLM")
        config = GenerationConfig()
        content, micro_beats = await self._generate_chapter_content(
            context=context,
            outline=outline,
            bundle=bundle,
            config=config,
            chapter_number=chapter_number,
            enable_beats=enable_beats,
            target_word_count=target_word_count,
        )
        if micro_beats:
            bundle["micro_beats"] = micro_beats

        content, word_control = await self._apply_word_control(
            content=content,
            outline=outline,
            target_word_count=target_word_count,
        )

        logger.info("阶段 4: 后处理（post_process_generated_chapter）")
        post = await self.post_process_generated_chapter(
            novel_id, chapter_number, outline, content, scene_director=scene_director
        )
        seam_rewrite_info = post.get("seam_rewrite_info") or {}
        content = post.get("content") or content
        style_warnings = post["style_warnings"]
        consistency_report = post["consistency_report"]
        ghost_annotations = post["ghost_annotations"]
        if style_warnings:
            logger.info(f"  ✓ 俗套扫描: 检测到 {len(style_warnings)} 个俗套句式")
        if seam_rewrite_info.get("applied"):
            logger.info(
                "  ✓ 接缝修复已执行: attempts=%s status=%s",
                seam_rewrite_info.get("attempts"),
                seam_rewrite_info.get("status"),
            )
        if self._requires_manual_seam_revision(seam_rewrite_info):
            raise RuntimeError("章节接缝复检未通过，需要人工修订后再保存")

        # Phase 5: Review - 返回结果
        logger.info(f"阶段 5: 完成 - 章节生成完成")
        token_count = context_tokens
        logger.info(f"  ✓ 总计: {len(content)} 字符, {token_count} tokens")
        logger.info(f"========================================")
        logger.info(f"章节生成完成: 小说={novel_id}, 章节={chapter_number}")
        logger.info(f"========================================")

        return GenerationResult(
            content=content,
            consistency_report=consistency_report,
            context_used=context,
            token_count=token_count,
            ghost_annotations=ghost_annotations,
            style_warnings=style_warnings,
            word_control=self._serialize_word_control(word_control),
        )

    async def generate_chapter_stream(
        self,
        novel_id: str,
        chapter_number: int,
        outline: str,
        scene_director: Optional[SceneDirectorAnalysis] = None,
        enable_beats: bool = True,
        target_word_count: Optional[int] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """流式生成章节：阶段事件 + 正文 token 流 + 最终 done（含一致性报告）。

        事件类型：
        - phase: planning | context | llm | post
        - chunk: { text }
        - done: { content, consistency_report, token_count }
        - error: { message }
        """
        try:
            if chapter_number < 1:
                raise ValueError("chapter_number must be positive")
            if not outline or not outline.strip():
                raise ValueError("outline cannot be empty")
            target_word_count = self._resolve_target_word_count(target_word_count)

            logger.info(f"========================================")
            logger.info(f"开始流式生成章节: 小说={novel_id}, 章节={chapter_number}")
            logger.info(f"========================================")

            yield {"type": "phase", "phase": "planning"}
            warning_event = self._emit_word_control_warning(target_word_count)
            if warning_event:
                yield warning_event
            yield {"type": "phase", "phase": "context"}
            logger.info("阶段 1-2: prepare_chapter_generation（规划 + 结构化上下文）")
            bundle = self.prepare_chapter_generation(
                novel_id, chapter_number, outline, scene_director=scene_director
            )
            context = bundle["context"]
            context_tokens = bundle["context_tokens"]
            logger.info(f"  ✓ 上下文已构建: {len(context)} 字符, 约 {context_tokens} tokens")

            yield {"type": "phase", "phase": "llm"}
            logger.info("阶段 3: 生成 - 调用 LLM 流式生成")
            config = GenerationConfig()
            chunk_count = 0
            
            # 如果使用节拍模式，先放大节拍
            beats = []
            if enable_beats:
                logger.info("  → 启用节拍模式，拆分大纲为微观节拍")
                raw_beats = self.context_builder.magnify_outline_to_beats(chapter_number, outline)
                if isinstance(raw_beats, list):
                    beats = raw_beats
                else:
                    try:
                        beats = list(raw_beats or [])
                    except TypeError:
                        beats = []
                logger.info(f"  ✓ 已拆分为 {len(beats)} 个微观节拍")
                
                # 发送节拍信息用于前端展示
                yield {
                    "type": "beats_generated",
                    "beats": [
                        {
                            "description": beat.description,
                            "target_words": beat.target_words,
                            "focus": beat.focus
                        } for beat in beats
                    ]
                }
            
            # 根据是否使用节拍选择不同的生成策略
            if enable_beats and beats:
                # 按节拍生成
                content_parts = []
                for i, beat in enumerate(beats):
                    beat_prompt_text = self.context_builder.build_beat_prompt(beat, i, len(beats))
                    logger.info(f"生成节拍 {i+1}/{len(beats)}: {beat.focus} - {beat.description[:50]}...")
                    
                    prompt = self._build_prompt(
                        context,
                        outline,
                        storyline_context=bundle["storyline_context"],
                        plot_tension=bundle["plot_tension"],
                        style_summary=bundle["style_summary"],
                        beat_prompt=beat_prompt_text,
                        beat_index=i,
                        total_beats=len(beats),
                        beat_target_words=beat.target_words,
                        voice_anchors=bundle.get("voice_anchors") or "",
                    )
                    if target_word_count is not None:
                        prompt = self.word_control_service.inject_length_requirements(
                            prompt,
                            target=target_word_count,
                        )
                    
                    beat_content = ""
                    async for piece in self.llm_service.stream_generate(prompt, config):
                        chunk_count += 1
                        beat_content += piece
                        yield {
                            "type": "chunk", 
                            "text": piece,
                            "beat_index": i,
                            "beat_focus": beat.focus
                        }
                    
                    content_parts.append(beat_content)
                    yield {"type": "beat_done", "beat_index": i, "beat_content_length": len(beat_content)}
                
                content = "".join(content_parts)
            else:
                # 传统单段生成
                prompt = self._build_prompt(
                    context,
                    outline,
                    storyline_context=bundle["storyline_context"],
                    plot_tension=bundle["plot_tension"],
                    style_summary=bundle["style_summary"],
                    voice_anchors=bundle.get("voice_anchors") or "",
                )
                if target_word_count is not None:
                    prompt = self.word_control_service.inject_length_requirements(
                        prompt,
                        target=target_word_count,
                    )
                
                logger.info(f"  → 发送流式请求到 LLM")
                parts: list[str] = []
                total_chars = 0
                async for piece in self.llm_service.stream_generate(prompt, config):
                    parts.append(piece)
                    chunk_count += 1
                    total_chars += len(piece)
                    # 增强事件：包含累计字数和预估 token（中文约 1.5 字/token，英文约 4 字/token）
                    estimated_tokens = int(total_chars / 1.5)  # 简化估算
                    yield {
                        "type": "chunk", 
                        "text": piece,
                        "stats": {
                            "chars": total_chars,
                            "chunks": chunk_count,
                            "estimated_tokens": estimated_tokens,
                        }
                    }

                content = "".join(parts)
            logger.info(f"  ✓ LLM 流式响应完成: {chunk_count} 个块, {len(content)} 字符")

            if not content.strip():
                logger.error("  × 模型返回空内容")
                yield {"type": "error", "message": "模型返回空内容"}
                return

            async def emit_word_control_event(event: Dict[str, Any]) -> None:
                yieldable = dict(event)
                if target_word_count is not None:
                    yieldable["target_word_count"] = target_word_count
                events_buffer.append(yieldable)

            yield {"type": "phase", "phase": "post"}
            logger.info("阶段 4: post_process_generated_chapter")
            events_buffer: List[Dict[str, Any]] = []
            content, word_control = await self._apply_word_control(
                content=content,
                outline=outline,
                target_word_count=target_word_count,
                emit_event=emit_word_control_event,
            )
            for buffered_event in events_buffer:
                yield buffered_event
            post = await self.post_process_generated_chapter(
                novel_id, chapter_number, outline, content, scene_director=scene_director
            )
            seam_rewrite_info = post.get("seam_rewrite_info") or {}
            original_content = content
            content = post.get("content") or content
            style_warnings = post["style_warnings"]
            consistency_report = post["consistency_report"]
            ghost_annotations = post["ghost_annotations"]
            if style_warnings:
                logger.info(f"  ✓ 俗套扫描: 检测到 {len(style_warnings)} 个俗套句式")
            if seam_rewrite_info.get("applied") and content != original_content:
                yield {
                    "type": "post_rewrite",
                    "scope": "opening",
                    "content": content,
                    "seam_rewrite_info": seam_rewrite_info,
                }
            if self._requires_manual_seam_revision(seam_rewrite_info):
                yield {
                    "type": "needs_manual_revision",
                    "reason": "seam_check_failed",
                    "message": "章节接缝复检未通过，需要人工修订开头后再保存。",
                    "content": content,
                    "consistency_report": _consistency_report_to_dict(consistency_report),
                    "token_count": context_tokens,
                    "ghost_annotations": [ann.to_dict() for ann in ghost_annotations],
                    "style_warnings": [
                        {
                            "pattern": hit.pattern,
                            "text": hit.text,
                            "start": hit.start,
                            "end": hit.end,
                            "severity": hit.severity,
                        }
                        for hit in style_warnings
                    ],
                    "seam_rewrite_info": seam_rewrite_info,
                }
                return

            token_count = context_tokens
            output_tokens = int(len(content) / 1.5)  # 预估输出 token
            total_tokens = token_count + output_tokens
            logger.info(f"========================================")
            logger.info(f"流式章节生成完成: 小说={novel_id}, 章节={chapter_number}")
            logger.info(f"  输出: {len(content)} 字符, 约 {output_tokens} tokens")
            logger.info(f"  总计: 约 {total_tokens} tokens (上下文 {token_count} + 输出 {output_tokens})")
            logger.info(f"========================================")

            yield {
                "type": "done",
                "content": content,
                "consistency_report": _consistency_report_to_dict(consistency_report),
                "token_count": token_count,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "chars": len(content),
                "target_word_count": target_word_count,
                "actual_word_count": effective_length(content),
                "word_control": self._serialize_word_control(word_control).to_dict() if word_control else None,
                "ghost_annotations": [ann.to_dict() for ann in ghost_annotations],
                "seam_rewrite_info": seam_rewrite_info,
                "style_warnings": [
                    {
                        "pattern": hit.pattern,
                        "text": hit.text,
                        "start": hit.start,
                        "end": hit.end,
                        "severity": hit.severity,
                    }
                    for hit in style_warnings
                ],
            }
        except ValueError as e:
            logger.error(f"参数错误: {e}")
            yield {"type": "error", "message": str(e)}
        except Exception as e:
            logger.exception("流式生成章节失败")
            yield {"type": "error", "message": str(e)}

    async def suggest_outline(self, novel_id: str, chapter_number: int) -> str:
        """托管模式：用全书上下文让模型生成本章要点大纲；失败则回退为简短占位。"""
        seed = f"第{chapter_number}章：承接前情，推进主线与人物节拍；保持人设与叙事节奏一致。"
        try:
            context = self.context_builder.build_context(
                novel_id=novel_id,
                chapter_number=chapter_number,
                outline=seed,
                max_tokens=28000,
            )
            cap = min(len(context), 28000)
            outline_prompt = Prompt(
                system=(
                    "你是小说主编。只输出本章的要点大纲（中文），用 1-6 条编号列表，"
                    "每条一行；不要写正文或对话。"
                ),
                user=(
                    f"以下为背景信息（节选）：\n\n{context[:cap]}\n\n"
                    f"请写第{chapter_number}章的要点大纲。"
                ),
            )
            cfg = GenerationConfig(max_tokens=1024, temperature=0.7)
            out = await self.llm_service.generate(outline_prompt, cfg)
            text = (out.content or "").strip()
            if text:
                return text
        except Exception as e:
            logger.warning("suggest_outline failed: %s", e)
        return seed

    async def generate_chapter_with_review(
        self,
        novel_id: str,
        chapter_number: int,
        outline: str
    ) -> Tuple[str, ConsistencyReport]:
        """生成章节并返回一致性审查

        Args:
            novel_id: 小说 ID
            chapter_number: 章节号
            outline: 章节大纲

        Returns:
            (content, consistency_report) 元组
        """
        result = await self.generate_chapter(novel_id, chapter_number, outline)
        return result.content, result.consistency_report

    def _get_storyline_context(self, novel_id: str, chapter_number: int) -> str:
        """获取故事线上下文

        Args:
            novel_id: 小说 ID
            chapter_number: 章节号

        Returns:
            故事线上下文字符串
        """
        try:
            # 检查 storyline_manager 是否有 repository 属性
            if not hasattr(self.storyline_manager, 'repository'):
                return "Storyline context unavailable"

            # 获取所有活跃的故事线
            storylines = self.storyline_manager.repository.get_by_novel_id(NovelId(novel_id))
            active_storylines = [
                s for s in storylines
                if s.status.value == "active"
                and s.estimated_chapter_start <= chapter_number <= s.estimated_chapter_end
            ]

            if not active_storylines:
                return "No active storylines for this chapter"

            context_parts = []
            for storyline in active_storylines:
                context = self.storyline_manager.get_storyline_context(storyline.id)
                context_parts.append(context)

            return "\n\n".join(context_parts)
        except Exception as e:
            logger.warning(f"Failed to get storyline context: {e}")
            return "Storyline context unavailable"

    def _get_plot_tension(self, novel_id: str, chapter_number: int) -> str:
        """获取情节张力信息

        Args:
            novel_id: 小说 ID
            chapter_number: 章节号

        Returns:
            情节张力描述
        """
        try:
            plot_arc = self.plot_arc_repository.get_by_novel_id(NovelId(novel_id))
            if plot_arc:
                tension = plot_arc.get_expected_tension(chapter_number)
                next_point = plot_arc.get_next_plot_point(chapter_number)

                tension_info = f"Expected tension: {tension.value}"
                if next_point:
                    tension_info += f"\nNext plot point at chapter {next_point.chapter_number}: {next_point.description}"

                return tension_info
            return "No plot arc defined"
        except Exception as e:
            logger.warning(f"Failed to get plot tension: {e}")
            return "Plot tension unavailable"

    def build_chapter_prompt(
        self,
        context: str,
        outline: str,
        *,
        storyline_context: str = "",
        plot_tension: str = "",
        style_summary: str = "",
        beat_prompt: Optional[str] = None,
        beat_index: Optional[int] = None,
        total_beats: Optional[int] = None,
        beat_target_words: Optional[int] = None,
        voice_anchors: str = "",
    ) -> Prompt:
        """构建与 HTTP 单章 / 流式 / 托管按节拍写作一致的 Prompt（对外 API）。"""
        return self._build_prompt(
            context,
            outline,
            storyline_context=storyline_context,
            plot_tension=plot_tension,
            style_summary=style_summary,
            beat_prompt=beat_prompt,
            beat_index=beat_index,
            total_beats=total_beats,
            beat_target_words=beat_target_words,
            voice_anchors=voice_anchors,
        )

    def _build_prompt(
        self,
        context: str,
        outline: str,
        *,
        storyline_context: str = "",
        plot_tension: str = "",
        style_summary: str = "",
        beat_prompt: Optional[str] = None,
        beat_index: Optional[int] = None,
        total_beats: Optional[int] = None,
        beat_target_words: Optional[int] = None,
        voice_anchors: str = "",
    ) -> Prompt:
        """构建 LLM 提示词

        Args:
            context: 完整上下文
            outline: 章节大纲
            storyline_context: 当前章相关故事线与里程碑（Phase 1）
            plot_tension: 情节弧期望张力与下一锚点（Phase 1）
            style_summary: 风格指纹摘要（Phase 2.5）
            beat_prompt: 非空时进入「分节拍」模式（托管断点续写）
            beat_index / total_beats: 节拍序号（0-based / 总数）
            beat_target_words: 本段目标字数（分节拍时覆盖「整章 2000-3000 字」说明）
            voice_anchors: Bible 角色声线/小动作锚点（高优先级 System 提示）

        Returns:
            Prompt 对象
        """
        sc = (storyline_context or "").strip()
        pt = (plot_tension or "").strip()
        ss = (style_summary or "").strip()
        va = (voice_anchors or "").strip()
        planning_parts: list[str] = []
        if sc and sc not in ("Storyline context unavailable",):
            planning_parts.append(f"【故事线 / 里程碑】\n{sc}")
        if pt and pt not in ("Plot tension unavailable",):
            planning_parts.append(f"【情节节奏 / 期望张力】\n{pt}")
        if ss:
            planning_parts.append(f"【风格约束】\n{ss}")
        planning_section = ""
        if planning_parts:
            planning_section = (
                "\n".join(planning_parts)
                + "\n\n以上约束须与本章大纲及后文 Bible/摘要一致；不得与之矛盾。\n"
            )

        # 题材专项指导（ThemeAgent 插槽）
        theme_section = ""
        if self.theme_agent:
            try:
                theme_directives = self.theme_agent.get_context_directives("", 0, outline)
                theme_text = theme_directives.to_context_text() if theme_directives else ""
                if theme_text:
                    theme_section = f"\n【题材专项指导】\n{theme_text}\n\n"
            except Exception as e:
                logger.warning(f"ThemeAgent.get_context_directives 失败（降级跳过）：{e}")

        voice_block = ""
        if va:
            voice_block = (
                "\n【角色声线与肢体语言（Bible 锚点，必须遵守）】\n"
                f"{va}\n\n"
            )

        beat_mode = bool((beat_prompt or "").strip())
        length_rule = (
            f"7. 本段约 {beat_target_words} 字（本章分多节输出之一，勿写章节标题）"
            if beat_target_words
            else ("7. 章节长度：3000-4000字" if not beat_mode else "7. 按下方节拍说明控制篇幅，勿写章节标题")
        )
        beat_extra = ""
        if beat_mode and beat_index is not None and total_beats is not None and total_beats > 0:
            beat_extra = (
                f"\n9. 这是本章第 {beat_index + 1}/{total_beats} 段输出；若非第一段，须承接上文语义，"
                "不要重复已写内容。\n"
            )

        # 题材人设：如有 ThemeAgent 且提供了专项人设，替换默认人设
        persona = "你是一位专业的网络小说作家。根据以下上下文撰写章节内容。"
        if self.theme_agent:
            try:
                custom_persona = self.theme_agent.get_system_persona()
                if custom_persona:
                    persona = f"{custom_persona}根据以下上下文撰写章节内容。"
            except Exception as e:
                logger.warning(f"ThemeAgent.get_system_persona 失败（使用默认人设）：{e}")

        # 题材专项写作规则
        theme_rules_text = ""
        if self.theme_agent:
            try:
                theme_rules = self.theme_agent.get_writing_rules()
                if theme_rules:
                    # 从第 9 条开始编号（默认规则 1-8 + beat_extra 可能占 9）
                    start_num = 10 if beat_extra else 9
                    theme_rules_lines = "\n".join(
                        f"{start_num + i}. {rule}" for i, rule in enumerate(theme_rules)
                    )
                    theme_rules_text = f"\n{theme_rules_lines}"
            except Exception as e:
                logger.warning(f"ThemeAgent.get_writing_rules 失败（降级跳过）：{e}")

        system_message = f"""{persona}

{planning_section}{theme_section}{voice_block}{context}

章节接缝约束：
1. 本章开头必须优先承接“最近章节”中离当前最近一章的结尾状态，不能像新故事一样重新起势。
2. 如果上一章结尾留下了动作、冲突、情绪或悬念，本章前 10%-15% 内容必须至少接住其中一项，并给出明确延续。
3. 本章开头的时间、地点、人物状态如果发生变化，必须写出过渡原因，不能无跳板切场。
4. 本章结尾必须同时做到两点：一是完成本章最核心的一步推进，二是留下可供下一章直接承接的钩子。
5. 下一章可承接的钩子优先使用以下类型之一：新信息暴露、关系变化、决定落地、危机逼近、行动即将开始。
6. 除非大纲明确要求大幅跳时空，否则不要让章节开头和上一章结尾在情绪、目标或局势上脱节。
7. 如果上下文里出现“章末状态 / 章末情绪 / 必须承接 / 下一章开场提示”，这些内容优先级高于泛化发挥，必须显式体现在本章开头。

写作要求：
1. 必须有多个人物互动（至少2-3个角色出场）
2. 必须有对话（不能只有独白和叙述）
3. 必须有冲突或张力（人物之间的矛盾、目标阻碍、悬念等）
4. 保持人物性格一致
5. 推进情节发展
6. 使用生动的场景描写和细节
{length_rule}
8. 用中文写作，使用第三人称叙事{beat_extra}{theme_rules_text}"""

        user_message = f"""请根据以下大纲撰写本章内容：

{outline}

关键要求（必须遵守）：
- 至少2-3个角色出场并互动
- 必须包含对话场景（不少于3段对话）
- 必须有明确的冲突或戏剧张力
- 场景要具体生动，不要空泛叙述
- 推进主线情节，不要原地踏步
- 开头先承接上一章末尾的局势/情绪/动作，不要重新铺一个无关开场
- 结尾要有悬念或转折"""

        if beat_mode:
            bi = beat_index if beat_index is not None else 0
            tb = total_beats if total_beats is not None else 1
            user_message += f"""

【节拍 {bi + 1}/{tb}】
{(beat_prompt or '').strip()}

本段只写该节拍对应正文，与上文衔接自然。"""

        user_message += "\n\n开始撰写："

        return Prompt(system=system_message, user=user_message)

    async def _extract_chapter_state(self, content: str, chapter_number: int) -> ChapterState:
        """从生成的内容中提取章节状态

        Args:
            content: 生成的章节内容
            chapter_number: 章节号

        Returns:
            ChapterState 对象
        """
        # 如果有 StateExtractor，使用它提取状态
        if self.state_extractor:
            try:
                logger.info(f"Extracting chapter state using StateExtractor for chapter {chapter_number}")
                return await self.state_extractor.extract_chapter_state(content)
            except Exception as e:
                logger.warning(f"StateExtractor failed: {e}, returning empty state")

        # 降级：返回空状态
        return ChapterState(
            new_characters=[],
            character_actions=[],
            relationship_changes=[],
            foreshadowing_planted=[],
            foreshadowing_resolved=[],
            events=[]
        )

    def _check_consistency(
        self,
        chapter_state: ChapterState,
        novel_id: str
    ) -> ConsistencyReport:
        """检查章节一致性

        Args:
            chapter_state: 章节状态
            novel_id: 小说 ID

        Returns:
            ConsistencyReport
        """
        from domain.bible.entities.bible import Bible
        from domain.bible.entities.character_registry import CharacterRegistry
        from domain.novel.entities.foreshadowing_registry import ForeshadowingRegistry
        from domain.novel.entities.plot_arc import PlotArc
        from domain.novel.value_objects.event_timeline import EventTimeline
        from domain.bible.value_objects.relationship_graph import RelationshipGraph

        novel_id_obj = NovelId(novel_id)

        try:
            # 尝试从仓储加载真实数据
            if self.bible_repository:
                bible = self.bible_repository.get_by_novel_id(novel_id_obj)
                logger.debug(f"Loaded real Bible for consistency check: {bible is not None}")
            else:
                bible = None

            if self.foreshadowing_repository:
                foreshadowing_registry = self.foreshadowing_repository.get_by_novel_id(novel_id_obj)
                logger.debug(f"Loaded real ForeshadowingRegistry for consistency check: {foreshadowing_registry is not None}")
            else:
                foreshadowing_registry = None

            context = ConsistencyContext(
                bible=bible or Bible(id="temp", novel_id=novel_id_obj),
                character_registry=CharacterRegistry(id="temp", novel_id=novel_id),
                foreshadowing_registry=foreshadowing_registry or ForeshadowingRegistry(id="temp", novel_id=novel_id_obj),
                plot_arc=PlotArc(id="temp", novel_id=novel_id_obj),
                event_timeline=EventTimeline(),
                relationship_graph=RelationshipGraph()
            )

            return self.consistency_checker.check_all(chapter_state, context)
        except Exception as e:
            logger.warning(f"Consistency check failed: {e}")
            return ConsistencyReport(issues=[], warnings=[], suggestions=[])

    def _review_chapter_seam(
        self,
        *,
        novel_id: str,
        chapter_number: int,
        content: str,
        base_report: ConsistencyReport,
        rewrite_info: Optional[Dict[str, Any]] = None,
    ) -> ConsistencyReport:
        """生成后自动检查本章开头是否承接上一章结尾。"""
        if chapter_number <= 1 or not content.strip():
            return base_report

        seam_context = self._get_previous_chapter_seam_context(novel_id, chapter_number)
        if seam_context is None:
            return base_report

        anchor_text = seam_context["anchor_text"]
        if not anchor_text:
            return base_report

        opening = self._extract_opening_for_seam_review(content)
        if not opening:
            return base_report

        if self._opening_matches_previous_seam(opening, anchor_text):
            return base_report

        warnings = list(base_report.warnings)
        suggestions = list(base_report.suggestions)
        seam_desc = (
            f"第{chapter_number}章开头未明显承接上一章收尾。"
            f"应优先接住上一章的章末状态/问题/开场提示，而不是另起场面。"
        )
        warnings.append(
            Issue(
                type=IssueType.EVENT_LOGIC_ERROR,
                severity=Severity.MINOR,
                description=seam_desc,
                location=chapter_number,
            )
        )
        suggestions.append(
            "重写本章前 10%-15%：直接回应上一章的章末状态、未解问题或下一章开场提示。"
        )
        if rewrite_info and rewrite_info.get("attempts", 0) > 0:
            suggestions.append(
                f"系统已尝试 {rewrite_info['attempts']} 次自动修复开头接缝，但仍未达到阈值，建议人工检查首段。"
            )
        return ConsistencyReport(
            issues=list(base_report.issues),
            warnings=warnings,
            suggestions=suggestions,
        )

    def _get_previous_chapter_seam_context(
        self,
        novel_id: str,
        chapter_number: int,
    ) -> Optional[Dict[str, Any]]:
        knowledge_repo = getattr(self.context_builder, "knowledge_repository", None)
        if knowledge_repo is None:
            return None

        try:
            knowledge = knowledge_repo.get_by_novel_id(novel_id)
        except Exception as e:
            logger.debug("chapter seam context load failed: %s", e)
            return None

        if not knowledge:
            return None

        previous = None
        for ch in knowledge.chapters:
            if getattr(ch, "chapter_id", None) == chapter_number - 1:
                previous = ch
                break
        if previous is None:
            return None

        anchors = [
            getattr(previous, "ending_state", "") or "",
            getattr(previous, "ending_emotion", "") or "",
            getattr(previous, "carry_over_question", "") or "",
            getattr(previous, "next_opening_hint", "") or "",
        ]
        anchor_text = "\n".join(x.strip() for x in anchors if x and x.strip()).strip()
        if not anchor_text:
            return None
        return {
            "previous": previous,
            "anchor_text": anchor_text,
        }

    async def _apply_seam_rewrite_loop(
        self,
        *,
        novel_id: str,
        chapter_number: int,
        outline: str,
        content: str,
    ) -> tuple[str, Dict[str, Any]]:
        info = {"attempts": 0, "applied": False, "status": "skipped"}
        if chapter_number <= 1 or not content.strip():
            return content, info

        seam_context = self._get_previous_chapter_seam_context(novel_id, chapter_number)
        if seam_context is None:
            return content, info

        current_content = content
        for attempt in range(1, 3):
            opening = self._extract_opening_for_seam_review(current_content)
            if opening and self._opening_matches_previous_seam(opening, seam_context["anchor_text"]):
                info["status"] = "passed"
                return current_content, info

            rewritten = await self._rewrite_chapter_opening_for_seam(
                novel_id=novel_id,
                chapter_number=chapter_number,
                outline=outline,
                content=current_content,
                seam_context=seam_context,
                attempt=attempt,
            )
            info["attempts"] = attempt
            if not rewritten or rewritten.strip() == current_content.strip():
                info["status"] = "failed_after_rewrite"
                return current_content, info
            current_content = rewritten
            info["applied"] = True

        final_opening = self._extract_opening_for_seam_review(current_content)
        info["status"] = (
            "passed_after_rewrite"
            if final_opening and self._opening_matches_previous_seam(final_opening, seam_context["anchor_text"])
            else "failed_after_rewrite"
        )
        return current_content, info

    async def _rewrite_chapter_opening_for_seam(
        self,
        *,
        novel_id: str,
        chapter_number: int,
        outline: str,
        content: str,
        seam_context: Dict[str, Any],
        attempt: int,
    ) -> Optional[str]:
        """重写章节开头以匹配上一章接缝

        根据上一章的接缝数据（ending_state, ending_emotion, carry_over_question 等）
        重写当前章节的开头，确保章节之间的连贯性。

        Args:
            novel_id: 小说 ID
            chapter_number: 章节号
            outline: 章节大纲
            content: 章节内容
            seam_context: 接缝上下文，包含上一章的摘要和接缝数据
            attempt: 重写尝试次数

        Returns:
            重写后的内容，如果重写失败则返回 None
        """
        # 修复问题 3：将冗余的防御性检查改为断言，明确不变量
        assert self.llm_service, "llm_service is required"

        opening, remainder = self._split_opening_for_rewrite(content)
        if not opening or not remainder:
            return None

        previous = seam_context["previous"]
        previous_block = "\n".join(
            [
                f"上一章摘要：{getattr(previous, 'summary', '') or '（无）'}",
                f"上一章未解问题：{getattr(previous, 'open_threads', '') or '（无）'}",
                f"上一章章末状态：{getattr(previous, 'ending_state', '') or '（无）'}",
                f"上一章章末情绪：{getattr(previous, 'ending_emotion', '') or '（无）'}",
                f"本章必须承接：{getattr(previous, 'carry_over_question', '') or '（无）'}",
                f"建议开场提示：{getattr(previous, 'next_opening_hint', '') or '（无）'}",
            ]
        )
        continuation = remainder[:700].strip()
        prompt = Prompt(
            system="""你是小说接缝修订编辑。你的任务不是重写整章，而是只修订章节开头，使其严密承接上一章结尾。

必须遵守：
1. 只输出“修订后的开头片段”，不要输出整章，不要解释。
2. 必须承接上一章的章末状态、情绪或未解问题，不能另起炉灶。
3. 不得改变本章既有剧情事实、角色关系、信息结论和后文走向。
4. 必须与后续正文自然衔接，不能和后文打架，不能重复后文已写内容。
5. 允许补一个过渡动作、承接对话、情绪延续或场景切换理由，但不要扩写新支线。""",
            user=f"""当前正在修订第 {chapter_number} 章开头，第 {attempt} 次尝试。

【上一章接缝卡】
{previous_block}

【本章大纲】
{outline}

【当前开头片段】
{opening}

【后续正文起始（仅供衔接，不可照抄重复）】
{continuation}

请只输出修订后的开头片段。""",
        )
        config = GenerationConfig(
            max_tokens=max(800, min(2200, int(len(opening) * 1.8))),
            temperature=0.3,
        )
        try:
            result = await self.llm_service.generate(prompt, config)
        except Exception as e:
            logger.warning("chapter seam rewrite failed novel=%s ch=%s attempt=%s: %s", novel_id, chapter_number, attempt, e)
            return None

        rewritten_opening = (result.content or "").strip()
        if not rewritten_opening:
            return None
        rewritten_opening = self._trim_duplicate_boundary(rewritten_opening, remainder)
        return rewritten_opening.rstrip() + "\n\n" + remainder.lstrip()

    @staticmethod
    def _split_opening_for_rewrite(content: str) -> tuple[str, str]:
        text = (content or "").strip()
        if not text:
            return "", ""
        split_idx = max(220, min(950, int(len(text) * 0.14)))
        boundary = text.rfind("\n\n", 0, split_idx + 120)
        if boundary == -1:
            boundary = text.find("\n\n", split_idx)
        if boundary == -1:
            boundary = split_idx
        opening = text[:boundary].strip()
        remainder = text[boundary:].strip()
        if len(opening) < 120 or len(remainder) < 120:
            return "", ""
        return opening, remainder

    @classmethod
    def _trim_duplicate_boundary(cls, rewritten_opening: str, remainder: str) -> str:
        candidate = rewritten_opening.rstrip()
        remainder_head = (remainder or "").lstrip()[:120]
        remainder_norm = cls._normalize_seam_text(remainder_head)
        if not remainder_norm:
            return candidate
        lines = [line.rstrip() for line in candidate.splitlines() if line.strip()]
        while lines:
            last = lines[-1]
            last_norm = cls._normalize_seam_text(last)
            if last_norm and (last_norm in remainder_norm or remainder_norm.startswith(last_norm)):
                lines.pop()
                continue
            break
        return "\n".join(lines).strip() or candidate

    @staticmethod
    def _extract_opening_for_seam_review(content: str, max_chars: int = 650) -> str:
        text = (content or "").strip()
        if not text:
            return ""
        head = text[:max_chars]
        parts = re.split(r"\n\s*\n", head)
        if parts:
            first_block = parts[0].strip()
            if len(first_block) >= 80:
                return first_block
        return head

    @staticmethod
    def _normalize_seam_text(text: str) -> str:
        return re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", (text or "").lower())

    @classmethod
    def _bigram_set(cls, text: str) -> set[str]:
        normalized = cls._normalize_seam_text(text)
        if len(normalized) < 2:
            return set()
        return {normalized[i:i + 2] for i in range(len(normalized) - 1)}

    @classmethod
    def _opening_matches_previous_seam(cls, opening: str, anchor_text: str) -> bool:
        opening_norm = cls._normalize_seam_text(opening)
        if not opening_norm:
            return False

        # 优先短语直接命中
        fragments = [
            frag.strip()
            for frag in re.split(r"[，。；：！？、“”\"'\s]+", anchor_text)
            if len(frag.strip()) >= 3
        ]
        direct_hits = 0
        for frag in fragments[:12]:
            norm_frag = cls._normalize_seam_text(frag)
            if norm_frag and norm_frag in opening_norm:
                direct_hits += 1
        if direct_hits >= 1:
            return True

        # 回退到双字片段重合，降低对措辞改写的敏感度
        opening_bigrams = cls._bigram_set(opening)
        anchor_bigrams = cls._bigram_set(anchor_text)
        if not opening_bigrams or not anchor_bigrams:
            return False
        overlap = opening_bigrams & anchor_bigrams
        overlap_ratio = len(overlap) / max(1, min(len(anchor_bigrams), 12))
        return len(overlap) >= 2 and overlap_ratio >= 0.2

    @staticmethod
    def _requires_manual_seam_revision(seam_rewrite_info: Optional[Dict[str, Any]]) -> bool:
        if not seam_rewrite_info:
            return False
        return str(seam_rewrite_info.get("status") or "") == "failed_after_rewrite"

    def _detect_conflicts(
        self,
        novel_id: str,
        chapter_number: int,
        outline: str,
        scene_director: Optional[SceneDirectorAnalysis] = None
    ) -> List[GhostAnnotation]:
        """检测冲突并生成幽灵批注

        Args:
            novel_id: 小说 ID
            chapter_number: 章节号
            outline: 章节大纲
            scene_director: 场记分析结果（可选）

        Returns:
            GhostAnnotation 列表
        """
        # 如果没有冲突检测服务，返回空列表
        if not self.conflict_detection_service:
            logger.debug("ConflictDetectionService not available, skipping conflict detection")
            return []

        try:
            # 构造 name_to_entity_id 映射（从 Bible 获取）
            name_to_entity_id = self._build_name_to_entity_id_mapping(novel_id)

            # 获取实体状态（从 Bible 或 NarrativeEntityStateService）
            entity_states = self._get_entity_states(novel_id, chapter_number, name_to_entity_id)

            # 调用冲突检测服务
            annotations = self.conflict_detection_service.detect(
                outline=outline,
                entity_states=entity_states,
                name_to_entity_id=name_to_entity_id,
                scene_director=scene_director
            )

            return annotations

        except Exception as e:
            logger.warning(f"Conflict detection failed: {e}", exc_info=True)
            return []

    def _build_name_to_entity_id_mapping(self, novel_id: str) -> Dict[str, str]:
        """构造实体名称到 ID 的映射

        Args:
            novel_id: 小说 ID

        Returns:
            {name: entity_id} 字典
        """
        name_to_id = {}

        try:
            if not self.bible_repository:
                return name_to_id

            novel_id_obj = NovelId(novel_id)
            bible = self.bible_repository.get_by_novel_id(novel_id_obj)

            if not bible:
                return name_to_id

            # 从 Bible 中提取角色名称和 ID
            for character in bible.characters:
                name_to_id[character.name] = character.id

            # 从 Bible 中提取地点名称和 ID
            for location in bible.locations:
                name_to_id[location.name] = location.id

        except Exception as e:
            logger.warning(f"Failed to build name_to_entity_id mapping: {e}")

        return name_to_id

    def _get_entity_states(
        self,
        novel_id: str,
        chapter_number: int,
        name_to_entity_id: Dict[str, str]
    ) -> Dict[str, Dict]:
        """获取实体状态

        Args:
            novel_id: 小说 ID
            chapter_number: 章节号
            name_to_entity_id: 实体名称到 ID 的映射

        Returns:
            {entity_id: {attribute: value}} 字典
        """
        entity_states = {}

        try:
            if not self.bible_repository:
                return entity_states

            novel_id_obj = NovelId(novel_id)
            bible = self.bible_repository.get_by_novel_id(novel_id_obj)

            if not bible:
                return entity_states

            # 从 Bible 中提取角色状态（简化版本，使用静态属性）
            for character in bible.characters:
                state = {}

                # 提取角色属性
                if hasattr(character, 'attributes') and character.attributes:
                    state.update(character.attributes)

                # 提取角色描述中的关键信息（简化版本）
                if hasattr(character, 'description') and character.description:
                    desc = character.description.lower()
                    # 检测魔法类型
                    if '火系' in desc or '火魔法' in desc:
                        state['magic_type'] = '火系'
                    elif '水系' in desc or '水魔法' in desc:
                        state['magic_type'] = '水系'
                    elif '冰系' in desc or '冰魔法' in desc:
                        state['magic_type'] = '冰系'
                    elif '雷系' in desc or '雷魔法' in desc:
                        state['magic_type'] = '雷系'
                    elif '风系' in desc or '风魔法' in desc:
                        state['magic_type'] = '风系'

                if state:
                    entity_states[character.id] = state

        except Exception as e:
            logger.warning(f"Failed to get entity states: {e}")

        return entity_states

    def _get_style_summary(self, novel_id: str) -> str:
        """获取风格指纹摘要

        Args:
            novel_id: 小说 ID

        Returns:
            风格指纹摘要字符串，如果不可用则返回空字符串
        """
        if not self.voice_fingerprint_service:
            return ""

        try:
            # 获取指纹数据
            fingerprint = self.voice_fingerprint_service.fingerprint_repo.get_by_novel(
                novel_id, pov_character_id=None
            )
            if not fingerprint:
                return ""

            # 构建摘要
            summary = build_style_summary(fingerprint)
            return summary

        except Exception as e:
            logger.warning(f"Failed to get style summary: {e}")
            return ""

    def _scan_cliches(self, content: str) -> List['ClicheHit']:
        """扫描俗套句式

        Args:
            content: 生成的内容

        Returns:
            俗套句式列表，如果扫描器不可用则返回空列表
        """
        if not self.cliche_scanner:
            return []

        try:
            return self.cliche_scanner.scan_cliches(content)
        except Exception as e:
            logger.warning(f"Failed to scan cliches: {e}")
            return []
