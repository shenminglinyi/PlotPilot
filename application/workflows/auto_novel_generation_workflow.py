"""自动小说生成工作流

整合所有子项目组件，实现完整的章节生成流程。
"""
import logging
from typing import Tuple, Dict, Any, AsyncIterator, Optional, List
from application.engine.services.context_builder import ContextBuilder
from application.analyst.services.state_extractor import StateExtractor
from application.analyst.services.state_updater import StateUpdater
from application.audit.services.conflict_detection_service import ConflictDetectionService
from application.engine.services.style_constraint_builder import build_style_summary
from application.engine.dtos.generation_result import GenerationResult
from application.engine.dtos.scene_director_dto import SceneDirectorAnalysis
from application.audit.dtos.ghost_annotation import GhostAnnotation
from domain.novel.services.consistency_checker import ConsistencyChecker
from domain.novel.services.storyline_manager import StorylineManager
from domain.novel.repositories.plot_arc_repository import PlotArcRepository
from domain.bible.repositories.bible_repository import BibleRepository
from domain.novel.repositories.foreshadowing_repository import ForeshadowingRepository
from domain.novel.value_objects.consistency_report import ConsistencyReport
from domain.novel.value_objects.chapter_state import ChapterState
from domain.novel.value_objects.consistency_context import ConsistencyContext
from domain.novel.value_objects.novel_id import NovelId
from domain.ai.services.llm_service import LLMService, GenerationConfig
from domain.ai.value_objects.prompt import Prompt
from application.ai.llm_output_sanitize import strip_reasoning_artifacts
from application.workflows.beat_continuation import format_prior_draft_for_prompt
from application.workflows.prose_discipline import build_prose_discipline_block
from application.engine.services.beat_coherence_enhancer import BeatCoherenceEnhancer, BeatContext

logger = logging.getLogger(__name__)


# ─── 模板安全渲染工具 ───

class _SafeDict(dict):
    """format_map 专用字典：未匹配的变量保留为 {name} 占位符，不抛 KeyError。"""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _safe_format(template: str, variables: Dict[str, Any]) -> str:
    """安全模板渲染：缺失变量保留占位符，不抛异常。

    Args:
        template: 含 {variable} 占位符的模板字符串
        variables: 变量字典

    Returns:
        渲染后的字符串
    """
    if not template:
        return ""
    try:
        return template.format_map(_SafeDict(variables))
    except (KeyError, ValueError, IndexError):
        return template


# CPMS: 主工作流提示词节点 key（与 prompt_packages 中节点 id 一致）
_WORKFLOW_CHAPTER_GEN_NODE_KEY = "chapter-generation-main"

# 硬编码回退：system 模板框架（仅在 PromptRegistry 不可用时使用）
_FALLBACK_SYSTEM_TEMPLATE = (
    "你是一位专业的网络小说作家。根据以下上下文撰写章节内容。\n"
    "{theme_persona}{theme_rules}\n"
    "{planning_section}{voice_block}{context}\n\n"
    "{fact_lock}\n"
    "{shuangwen_directive}"
    "{prose_discipline}"
    "写作要求：\n"
    "1. 必须有多个人物互动（至少2-3个角色出场）\n"
    "2. 必须有对话（不能只有独白和叙述）\n"
    "3. 必须有冲突或张力（人物之间的矛盾、目标阻碍、悬念等）\n"
    "4. 保持人物性格一致\n"
    "5. 推进情节发展\n"
    "6. 使用生动的场景描写和细节\n"
    "{length_rule}\n"
    "8. 用中文写作，使用第三人称叙事{beat_extra}\n"
    "{format_rules}"
)

# 硬编码回退：user 模板框架
_FALLBACK_USER_TEMPLATE = (
    "请根据以下大纲撰写本章内容：\n\n{outline}\n\n"
    "关键要求（必须遵守）：\n"
    "- 至少2-3个角色出场并互动\n"
    "- 必须包含对话场景（不少于3段对话）\n"
    "- 必须有明确的冲突或戏剧张力\n"
    "- 场景要具体生动，不要空泛叙述\n"
    "- 推进主线情节，不要原地踏步\n"
    "- 结尾要有悬念或转折\n\n"
    "{beat_section}"
)

# 与 ContextBuilder.build_structured_context 映射：Layer1≈T0+T1，Layer2=T2，Layer3=T3
# 段名与语义对齐，避免「SMART RETRIEVAL」贴在近期正文等历史误标
CHAPTER_CONTEXT_LAYER2_HEADER = "RECENT CHAPTERS"  # T2 近期章节正文
CHAPTER_CONTEXT_LAYER3_HEADER = "VECTOR RECALL"  # T3 向量召回


def _build_dynamic_coherence_rules(anchor) -> str:
    """基于前节拍尾部锚点动态生成连贯性建议（V9: 从约束变为参考）

    V9 改革：不再使用"必须"、"不能"等强制性语言。
    改为温和的建议，允许 AI 灵活处理节拍间过渡。

    Args:
        anchor: BeatTailAnchor 实例

    Returns:
        格式化的连贯性建议文本
    """
    # 基础规则（所有情况都适用）
    base_rules = [
        "1. 从上文最后的情节发展自然过渡",
    ]

    # 根据尾部状态追加建议（V9: 从"必须"变为"可以"）
    state_rules = {
        "对话中": [
            "2. 上文停在对白中间——你可以先回应/延续该对话",
            "3. 对话中的情绪弦外之音建议承接",
            "4. 对话自然结束后再推进新情节",
        ],
        "动作中": [
            "2. 上文停在动作进行中——你可以展示该动作的完成或结果",
            "3. 动作完成后写角色的反应（表情/心理/下一步）",
            "4. 也可以跳过动作结果，从后续反应开始",
        ],
        "悬念中": [
            "2. 上文留下了悬念——你可以延续悬念的紧张感",
            "3. 可以暂时搁置悬念，从另一条线索开篇",
            "4. 如果合适，也可以揭晓悬念",
        ],
        "叙述中": [
            "2. 承接叙述的情绪惯性自然过渡",
            "3. 从叙述自然过渡到具体场景或对话",
            "4. 用环境细节或角色动作作为过渡桥梁",
        ],
        "场景转换": [
            "2. 新场景可以先用感官细节（画面/声音/温度）站稳脚跟",
            "3. 也可以直接进入新场景的对话/动作",
            "4. 时间跳跃是合法的文学技法",
        ],
    }

    extra = state_rules.get(anchor.tail_state, [
        "2. 保持相同的场景设置，除非节拍明确要求转换场景",
        "3. 人物情绪和状态应与上文保持一致并合理发展",
        "4. 如果上文以对话结尾，继续该对话；如果以动作结尾，展示后续",
    ])
    base_rules.extend(extra)

    # 情绪基调参考（V9: 删除"不能"措辞）
    mood_hints = {
        '紧张': "5. 情绪参考：上文紧张，紧张感通常会延续一段时间",
        '愤怒': "5. 情绪参考：上文愤怒，余怒未消是常见的",
        '悲伤': "5. 情绪参考：上文悲伤，悲伤有惯性",
        '悬疑': "5. 情绪参考：上文悬疑，不要急于揭晓",
    }
    mood_hint = mood_hints.get(anchor.mood_tone)
    if mood_hint:
        base_rules.append(mood_hint)

    # 最后画面参考（V9: 不再说"必须接续"）
    if anchor.last_moment:
        base_rules.append(
            f"6. 📍 上文最后画面：……{anchor.last_moment}"
        )

    return "\n".join(base_rules)


def assemble_chapter_bundle_context_text(payload: Dict[str, Any]) -> str:
    """将 build_structured_context 的 payload 拼成章节主上下文块（与 prepare_chapter_generation 同源）。"""
    return (
        f"{payload['layer1_text']}\n\n=== {CHAPTER_CONTEXT_LAYER2_HEADER} ===\n{payload['layer2_text']}\n\n"
        f"=== {CHAPTER_CONTEXT_LAYER3_HEADER} ===\n{payload['layer3_text']}"
    )


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
        memory_engine: Optional['MemoryEngine'] = None,
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
            memory_engine: V6 记忆引擎（可选，提供 FACT_LOCK / BEATS / CLUES 注入与章后回写）
        """
        self.context_builder = context_builder
        self.consistency_checker = consistency_checker
        self.storyline_manager = storyline_manager
        self.plot_arc_repository = plot_arc_repository
        self.llm_service = llm_service

        # ★ V6 记忆引擎（跨章节状态机）
        self.memory_engine = memory_engine
        if memory_engine and bible_repository:
            # 将 memory_engine 注入 context_builder 的 budget_allocator
            if hasattr(self.context_builder, 'budget_allocator'):
                self.context_builder.budget_allocator.memory_engine = memory_engine
                logger.info("✓ MemoryEngine 已注入 ContextBudgetAllocator")

        # V6 运行时上下文缓存（供 _build_prompt 使用）
        self._current_novel_id: str = ""
        self._current_chapter_number: int = 0
        
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

        # 初始化节拍连贯性增强器
        self.coherence_enhancer = BeatCoherenceEnhancer()

        # ★ Theme 集成器（延迟初始化）
        self._theme_integrator = None
        self._genre: Optional[str] = None

    def set_genre(self, genre: str) -> None:
        """设置小说题材，激活对应的 Theme Agent"""
        self._genre = genre
        self._initialize_theme()

    def _initialize_theme(self) -> None:
        """延迟初始化 Theme 集成器"""
        if self._theme_integrator is not None:
            return

        try:
            from application.engine.theme.theme_integrator import ThemeIntegrator
            self._theme_integrator = ThemeIntegrator()
            if self._theme_integrator.initialize(self._genre):
                logger.info(f"✓ Theme 集成器已初始化，题材: {self._genre or 'default'}")
            else:
                self._theme_integrator = None
        except Exception as e:
            logger.warning(f"Theme 集成器初始化失败: {e}")
            self._theme_integrator = None

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
        context = assemble_chapter_bundle_context_text(payload)
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

    def _resolve_target_chapter_words(self, novel_id: str) -> int:
        """每章目标字数：与作品设置 target_words_per_chapter 一致（工作流 / API 单章生成）。"""
        try:
            novel = self.context_builder.novel_repository.get_by_id(NovelId(novel_id))
            if novel is not None:
                w = int(getattr(novel, "target_words_per_chapter", 2500) or 2500)
                return max(500, min(10000, w))
        except Exception as e:
            logger.debug("读取 target_words_per_chapter 失败，使用默认 2500: %s", e)
        return 2500

    def build_fallback_chapter_bundle(
        self,
        novel_id: str,
        chapter_number: int,
        outline: str,
        *,
        scene_director: Optional[SceneDirectorAnalysis] = None,
        max_tokens: int = 20000,
    ) -> Dict[str, Any]:
        """prepare_chapter_generation 失败时的降级：仍用三层洋葱 + 同段名拼接；叙事/文风各步独立容错。

        供全托管等场景在「故事线/张力等」子步骤异常时保持与主路径一致的上下文形态。
        """
        payload = self.context_builder.build_structured_context(
            novel_id=novel_id,
            chapter_number=chapter_number,
            outline=outline,
            max_tokens=max_tokens,
            scene_director=scene_director,
        )
        context = assemble_chapter_bundle_context_text(payload)
        context_tokens = payload["token_usage"]["total"]

        storyline_context = ""
        try:
            storyline_context = self._get_storyline_context(novel_id, chapter_number)
        except Exception as e:
            logger.warning("fallback storyline_context skipped: %s", e)

        plot_tension = ""
        try:
            plot_tension = self._get_plot_tension(novel_id, chapter_number)
        except Exception as e:
            logger.warning("fallback plot_tension skipped: %s", e)

        style_summary = ""
        try:
            style_summary = self._get_style_summary(novel_id)
        except Exception as e:
            logger.warning("fallback style_summary skipped: %s", e)

        voice_anchors = ""
        try:
            voice_anchors = self.context_builder.build_voice_anchor_system_section(novel_id)
        except Exception as e:
            logger.warning("fallback voice_anchors skipped: %s", e)

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
        """生成正文后的统一后处理：俗套扫描、状态提取、一致性、冲突批注、StateUpdater、MemoryEngine回写。"""
        style_warnings = self._scan_cliches(content)
        chapter_state = await self._extract_chapter_state(content, chapter_number)
        consistency_report = self._check_consistency(chapter_state, novel_id)
        ghost_annotations = self._detect_conflicts(novel_id, chapter_number, outline, scene_director)
        if self.state_updater:
            try:
                self.state_updater.update_from_chapter(novel_id, chapter_number, chapter_state)
            except Exception as e:
                logger.warning("StateUpdater 失败: %s", e)

        # ★ V6 新增：MemoryEngine 章后状态回写（LLM 驱动的增量提取）
        memory_delta = {}
        if self.memory_engine:
            try:
                memory_delta = await self.memory_engine.update_from_chapter(
                    novel_id=novel_id,
                    chapter_number=chapter_number,
                    content=content,
                    outline=outline,
                )
                if memory_delta.get("new_beats", 0) or memory_delta.get("new_clues", 0):
                    logger.info(
                        f"  🧠 MemoryEngine: +{memory_delta.get('new_beats', 0)} beats, "
                        f"+{memory_delta.get('new_clues', 0)} clues"
                    )
                if memory_delta.get("violations", 0):
                    logger.warning(
                        f"  ⚠️ MemoryEngine 检测到 {memory_delta['violations']} 个事实违反"
                    )
            except Exception as e:
                logger.warning("MemoryEngine 章后回写失败: %s", e)

        return {
            "style_warnings": style_warnings,
            "chapter_state": chapter_state,
            "consistency_report": consistency_report,
            "ghost_annotations": ghost_annotations,
            "memory_delta": memory_delta,
        }

    async def generate_chapter(
        self,
        novel_id: str,
        chapter_number: int,
        outline: str,
        scene_director: Optional[SceneDirectorAnalysis] = None,
        enable_beats: bool = True
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

        logger.info(f"========================================")
        logger.info(f"开始生成章节: 小说={novel_id}, 章节={chapter_number}")
        logger.info(f"大纲: {outline[:100]}...")
        logger.info(f"========================================")

        # ★ V6: 缓存当前 novel_id/chapter_number 供 _build_prompt 中 MemoryEngine 使用
        self._current_novel_id = novel_id
        self._current_chapter_number = chapter_number

        logger.info("阶段 1-2: 规划 + 结构化上下文（prepare_chapter_generation）")
        bundle = self.prepare_chapter_generation(
            novel_id, chapter_number, outline, scene_director=scene_director
        )
        context = bundle["context"]
        context_tokens = bundle["context_tokens"]
        logger.info(f"  ✓ 上下文已构建: {len(context)} 字符, 约 {context_tokens} tokens")

        logger.info("阶段 3: 生成 - 调用 LLM")
        config = GenerationConfig()
        target_words = self._resolve_target_chapter_words(novel_id)
        
        # 如果使用节拍模式，先放大节拍
        beats = []
        if enable_beats:
            logger.info("  → 启用节拍模式，拆分大纲为微观节拍")
            beats = self.context_builder.magnify_outline_to_beats(
                chapter_number, outline, target_chapter_words=target_words
            )
            logger.info(f"  ✓ 已拆分为 {len(beats)} 个微观节拍（整章目标 {target_words} 字）")
        
        # 根据是否使用节拍选择不同的生成策略
        if enable_beats and beats:
            # 按节拍生成
            content_parts: list[str] = []
            previous_context: Optional[BeatContext] = None
            
            for i, beat in enumerate(beats):
                prior_draft = "\n\n".join(content_parts)
                beat_prompt_text = self.context_builder.build_beat_prompt(beat, i, len(beats))
                
                # 连贯性增强：分析前一个节拍的上下文
                coherence_instructions = ""
                if previous_context and prior_draft:
                    # 分析当前节拍的连贯性要求
                    coherence_instructions = self.coherence_enhancer.generate_coherence_instructions(
                        previous_content=content_parts[-1] if content_parts else "",
                        current_beat_description=beat.description,
                        previous_context=previous_context,
                        beat_index=i,
                        total_beats=len(beats)
                    )
                    
                    # 如果检测到了连贯性问题，在提示词中增加修复指导
                    current_content_preview = f"将生成关于'{beat.description}'的内容"
                    issues = self.coherence_enhancer.check_coherence_between_beats(
                        previous_content=content_parts[-1] if content_parts else "",
                        current_content=current_content_preview,
                        previous_context=previous_context,
                        current_context=self.coherence_enhancer.analyze_beat_context(
                            current_content_preview, beat.focus
                        )
                    )
                    
                    if issues:
                        issue_descriptions = [f"- {issue.description}" for issue in issues if issue.severity in ['high', 'medium']]
                        if issue_descriptions:
                            coherence_instructions += "\n\n【连贯性修复要求】\n" + "\n".join(issue_descriptions[:3])  # 最多显示3个问题
                
                logger.info(f"生成节拍 {i+1}/{len(beats)}: {beat.focus} - {beat.description[:50]}...")
                
                prompt = self._build_prompt(
                    context,
                    outline,
                    storyline_context=bundle["storyline_context"],
                    plot_tension=bundle["plot_tension"],
                    style_summary=bundle["style_summary"],
                    beat_prompt=beat_prompt_text + ("\n\n" + coherence_instructions if coherence_instructions else ""),
                    beat_index=i,
                    total_beats=len(beats),
                    beat_target_words=beat.target_words,
                    voice_anchors=bundle.get("voice_anchors") or "",
                    chapter_draft_so_far=prior_draft,
                )
                
                llm_result = await self.llm_service.generate(prompt, config)
                beat_content = llm_result.content
                
                # 分析并保存当前节拍的上下文，为下一个节拍做准备
                if beat_content:
                    previous_context = self.coherence_enhancer.analyze_beat_context(beat_content, beat.focus)
                    logger.debug(f"节拍 {i+1} 上下文分析: 角色={previous_context.characters}, 场景={previous_context.scene}")
                
                content_parts.append(beat_content)
            
            content = strip_reasoning_artifacts("".join(content_parts))
            logger.info(f"  ✓ 节拍生成完成: {len(beats)} 个节拍, {len(content)} 字符")
        else:
            # 传统单段生成
            prompt = self._build_prompt(
                context,
                outline,
                storyline_context=bundle["storyline_context"],
                plot_tension=bundle["plot_tension"],
                style_summary=bundle["style_summary"],
                voice_anchors=bundle.get("voice_anchors") or "",
                chapter_target_words=target_words,
            )
            logger.info(f"  → 发送请求到 LLM (max_tokens={config.max_tokens}, temperature={config.temperature})")
            llm_result = await self.llm_service.generate(prompt, config)
            content = strip_reasoning_artifacts(llm_result.content or "")
            logger.info(f"  ✓ LLM 响应已接收: {len(content)} 字符")
        
        # 保存微观节拍用于后续处理
        if beats:
            bundle["micro_beats"] = [
                {
                    "description": beat.description,
                    "target_words": beat.target_words,
                    "focus": beat.focus
                } for beat in beats
            ]

        logger.info("阶段 4: 后处理（post_process_generated_chapter）")
        post = await self.post_process_generated_chapter(
            novel_id, chapter_number, outline, content, scene_director=scene_director
        )
        style_warnings = post["style_warnings"]
        consistency_report = post["consistency_report"]
        ghost_annotations = post["ghost_annotations"]
        if style_warnings:
            logger.info(f"  ✓ 俗套扫描: 检测到 {len(style_warnings)} 个俗套句式")

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
            style_warnings=style_warnings
        )

    async def generate_chapter_stream(
        self,
        novel_id: str,
        chapter_number: int,
        outline: str,
        scene_director: Optional[SceneDirectorAnalysis] = None,
        enable_beats: bool = True,
        regeneration_guidance: Optional[str] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """流式生成章节：阶段事件 + 正文 token 流 + 最终 done（含一致性报告）。

        事件类型：
        - phase: planning | context | llm | post
        - chunk: { text }
        - done: { content, consistency_report, token_count }
        - error: { message }

        Args:
            regeneration_guidance: 重写时的改进方向（可选）。非空时 AI 会在 prompt 中看到
                                   上一版本的问题描述，并被要求针对性改进。
        """
        try:
            if chapter_number < 1:
                raise ValueError("chapter_number must be positive")
            if not outline or not outline.strip():
                raise ValueError("outline cannot be empty")

            logger.info(f"========================================")
            logger.info(f"开始流式生成章节: 小说={novel_id}, 章节={chapter_number}")
            logger.info(f"========================================")

            yield {"type": "phase", "phase": "planning"}
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
            target_words = self._resolve_target_chapter_words(novel_id)
            
            # 如果使用节拍模式，先放大节拍
            beats = []
            if enable_beats:
                logger.info("  → 启用节拍模式，拆分大纲为微观节拍")
                beats = self.context_builder.magnify_outline_to_beats(
                    chapter_number, outline, target_chapter_words=target_words
                )
                logger.info(f"  ✓ 已拆分为 {len(beats)} 个微观节拍（整章目标 {target_words} 字）")
                
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
                content_parts: list[str] = []
                previous_context: Optional[BeatContext] = None
                
                for i, beat in enumerate(beats):
                    prior_draft = "\n\n".join(content_parts)
                    beat_prompt_text = self.context_builder.build_beat_prompt(beat, i, len(beats))
                    
                    # 连贯性增强：为流式生成添加连贯性指导
                    coherence_instructions = ""
                    if previous_context and prior_draft:
                        coherence_instructions = self.coherence_enhancer.generate_coherence_instructions(
                            previous_content=content_parts[-1] if content_parts else "",
                            current_beat_description=beat.description,
                            previous_context=previous_context,
                            beat_index=i,
                            total_beats=len(beats)
                        )
                    
                    logger.info(f"生成节拍 {i+1}/{len(beats)}: {beat.focus} - {beat.description[:50]}...")
                    
                    prompt = self._build_prompt(
                        context,
                        outline,
                        storyline_context=bundle["storyline_context"],
                        plot_tension=bundle["plot_tension"],
                        style_summary=bundle["style_summary"],
                        beat_prompt=beat_prompt_text + ("\n\n" + coherence_instructions if coherence_instructions else ""),
                        beat_index=i,
                        total_beats=len(beats),
                        beat_target_words=beat.target_words,
                        voice_anchors=bundle.get("voice_anchors") or "",
                        chapter_draft_so_far=prior_draft,
                        regeneration_guidance=regeneration_guidance if i == 0 else None,
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
                    
                    # 分析并保存当前节拍的上下文，为下一个节拍做准备
                    if beat_content:
                        previous_context = self.coherence_enhancer.analyze_beat_context(beat_content, beat.focus)
                    
                    content_parts.append(beat_content)
                    yield {"type": "beat_done", "beat_index": i, "beat_content_length": len(beat_content)}
                
                content = strip_reasoning_artifacts("".join(content_parts))
            else:
                # 传统单段生成
                prompt = self._build_prompt(
                    context,
                    outline,
                    storyline_context=bundle["storyline_context"],
                    plot_tension=bundle["plot_tension"],
                    style_summary=bundle["style_summary"],
                    voice_anchors=bundle.get("voice_anchors") or "",
                    regeneration_guidance=regeneration_guidance,
                    chapter_target_words=target_words,
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

                content = strip_reasoning_artifacts("".join(parts))
            logger.info(f"  ✓ LLM 流式响应完成: {chunk_count} 个块, {len(content)} 字符")

            if not content.strip():
                logger.error("  × 模型返回空内容")
                yield {"type": "error", "message": "模型返回空内容"}
                return

            yield {"type": "phase", "phase": "post"}
            logger.info("阶段 4: post_process_generated_chapter")
            post = await self.post_process_generated_chapter(
                novel_id, chapter_number, outline, content, scene_director=scene_director
            )
            style_warnings = post["style_warnings"]
            consistency_report = post["consistency_report"]
            ghost_annotations = post["ghost_annotations"]
            if style_warnings:
                logger.info(f"  ✓ 俗套扫描: 检测到 {len(style_warnings)} 个俗套句式")

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
            text = strip_reasoning_artifacts((out.content or "").strip())
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
        """获取情节张力信息——融合预设锚点 + 前章实际张力评分，形成闭环反馈。

        Args:
            novel_id: 小说 ID
            chapter_number: 章节号

        Returns:
            情节张力描述（含预设期望 + 前章实际 + 调整指令）
        """
        parts: list[str] = []

        # 1. 预设张力（来自 PlotArc 锚点）
        try:
            plot_arc = self.plot_arc_repository.get_by_novel_id(NovelId(novel_id))
            if plot_arc and plot_arc.key_points:
                tension = plot_arc.get_expected_tension(chapter_number)
                next_point = plot_arc.get_next_plot_point(chapter_number)
                # ★ Phase 3: 使用 PlotArc 的 get_expected_tension_100 方法（含非线性插值）
                tension_100 = plot_arc.get_expected_tension_100(chapter_number)
                parts.append(f"预设期望张力等级：{tension_100}/100（{tension.display_name}）")
                if next_point:
                    parts.append(
                        f"下一个锚点：第{next_point.chapter_number}章 - {next_point.description}"
                    )
        except Exception as e:
            logger.warning(f"Failed to get plot arc tension: {e}")

        # 2. 前章实际张力评分（闭环反馈的核心）
        prev_actual_tension = None
        try:
            from interfaces.api.dependencies import get_chapter_repository
            from domain.novel.value_objects.novel_id import NovelId as NId
            chapter_repo = get_chapter_repository()
            db = chapter_repo.db if hasattr(chapter_repo, 'db') else None
            if db is not None and chapter_number > 1:
                row = db.fetch_one(
                    "SELECT tension_score, plot_tension, emotional_tension, pacing_tension "
                    "FROM chapters WHERE novel_id = ? AND number = ?",
                    (novel_id, chapter_number - 1)
                )
                if row and row['tension_score'] is not None and row['tension_score'] != -1:
                    prev_actual_tension = float(row['tension_score'])
                    parts.append(
                        f"前章（第{chapter_number - 1}章）实际张力评分：{prev_actual_tension:.0f}/100"
                        f"（情节={float(row['plot_tension'] or 0):.0f} "
                        f"情绪={float(row['emotional_tension'] or 0):.0f} "
                        f"节奏={float(row['pacing_tension'] or 0):.0f}）"
                    )
        except Exception as e:
            logger.debug(f"Failed to get prev chapter tension: {e}")

        # 3. 张力调整指令（基于预设与实际的差距）
        # ★ Phase 1: 前三章硬编码高张力指令（冷启动保护）
        if chapter_number <= 3:
            early_chapter_directives = {
                1: (
                    "🔥【首章铁律】本章是读者决定是否继续阅读的关键！"
                    "综合张力目标：≥65。"
                    "必须在第一个节拍就制造强烈冲突/悬念/反转——"
                    "绝对禁止大段背景介绍、设定灌输、平淡日常！"
                    "主角必须在被压制/轻视后展露底牌，给读者第一次爽感冲击！"
                ),
                2: (
                    "⚡【次章加速】读者已被首章吸引，但不能松劲！"
                    "综合张力目标：≥55。"
                    "本章必须有至少一次实力验证/身份暗示/新冲突爆发。"
                    "继续升温，扩大主角展现出的特殊之处引发的反响。"
                ),
                3: (
                    "⚡【三章定乾坤】前三章决定了读者是否追读！"
                    "综合张力目标：≥60。"
                    "本章必须有一次真正的高潮场景——"
                    "第一次正式对抗/博弈/危机中的大逆转！"
                    "读者在这里应该获得明确的'这书好看'的正反馈！"
                ),
            }
            early_directive = early_chapter_directives.get(chapter_number, "")
            if early_directive:
                parts.append(early_directive)
        elif prev_actual_tension is not None:
            if prev_actual_tension <= 30:
                parts.append(
                    "⚠ 紧急指令：前章张力严重不足！本章必须制造至少一次核心冲突/反转/悬念，"
                    "将综合张力拉升到 55 以上。建议：引入新威胁、暴露隐藏信息、"
                    "让角色做出痛苦选择。"
                )
            elif prev_actual_tension <= 45:
                parts.append(
                    "⚡ 调整指令：前章张力偏低，读者可能正在流失。"
                    "本章应逐步升温——增加信息不对称、加深角色矛盾、"
                    "让阻碍变得更加紧迫。目标张力：50-65。"
                )
            elif prev_actual_tension >= 80:
                parts.append(
                    "📊 缓冲指令：前章已是高潮，本章应给读者喘息空间。"
                    "可以写角色消化冲击、盟友互动、新线索浮现，"
                    "但结尾要留一个钩子暗示更大的风暴即将到来。目标张力：40-55。"
                )
            elif prev_actual_tension >= 65:
                parts.append(
                    "📊 维持指令：前章张力较高，本章可以保持高压推进，"
                    "也可以适当喘息后再次攀升。避免连续高压导致读者疲劳。"
                )

        if not parts:
            return "No plot arc defined"

        return "\n".join(parts)

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
        chapter_draft_so_far: str = "",
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
            chapter_draft_so_far=chapter_draft_so_far,
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
        chapter_draft_so_far: str = "",
        regeneration_guidance: Optional[str] = None,
        chapter_target_words: Optional[int] = None,
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
            beat_target_words: 本段目标字数（分节拍时覆盖整章说明）
            voice_anchors: Bible 角色声线/小动作锚点（高优先级 System 提示）
            chapter_draft_so_far: 同章内当前节拍之前已生成的正文
            chapter_target_words: 非 beat 模式下的整章目标字数（覆盖默认硬编码值）

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
        if pt and pt not in ("Plot tension unavailable", "No plot arc defined"):
            planning_parts.append(f"【情节节奏 / 张力控制（必须遵守）】\n{pt}")
        if ss:
            planning_parts.append(f"【风格约束】\n{ss}")
        planning_section = ""
        if planning_parts:
            planning_section = (
                "\n".join(planning_parts)
                + "\n\n以上约束须与本章大纲及后文 Bible/摘要一致；不得与之矛盾。\n"
            )

        voice_block = ""
        if va:
            voice_block = (
                "\n【角色声线与肢体语言（Bible 锚点，必须遵守）】\n"
                f"{va}\n\n"
            )

        beat_mode = bool((beat_prompt or "").strip())
        prior_in_chapter = format_prior_draft_for_prompt(chapter_draft_so_far)
        # 字数控制：像小说家一样自然收束，而非粗暴截断
        if beat_target_words:
            length_rule = (
                f"7. 【字数指引】本节拍约 {beat_target_words} 字。"
                f"用有信息的对话、动作与因果推进填到目标附近，禁止为凑字重复描写同一致震撼或同一情绪；"
                f"收束用完整句，不要戛然而止。"
            )
        elif beat_mode:
            length_rule = "7. 按下方节拍说明控制篇幅，勿写章节标题"
        elif chapter_target_words:
            length_rule = (
                f"7. 【章节字数指引】本章目标约 {chapter_target_words} 字。"
                f"完整覆盖下方大纲的所有要点，字数不足时优先补充对话与场景细节，禁止重复情节水字；"
                f"用完整句收束，不要戛然而止。"
            )
        else:
            length_rule = "7. 章节长度：3000-4000字"
        beat_extra = ""
        if beat_mode and beat_index is not None and total_beats is not None and total_beats > 0:
            if prior_in_chapter:
                beat_extra = (
                    f"\n9. 本章第 {beat_index + 1}/{total_beats} 段：用户消息中「本章已生成正文」为当前章已写部分，"
                    "请从其**之后**自然续写，不得复述或改写其中对白与已发生情节。\n"
                )
            else:
                beat_extra = (
                    f"\n9. 本章第 {beat_index + 1}/{total_beats} 段：与前后节拍连贯，避免同章内重复铺垫或重复对白。\n"
                )

        # ★ V6: 从 MemoryEngine 获取 fact_lock 文本块（T0 注入）
        fact_lock = ""
        if self.memory_engine:
            try:
                # 从 context 中提取 novel_id（通过 budget_allocator 传递）
                # 这里用组合方式：FACT_LOCK + BEATS + CLUES 合并为一个文本块
                fl = self.memory_engine.build_fact_lock_section(
                    self._current_novel_id or "", self._current_chapter_number or 0
                )
                beats = self.memory_engine.get_completed_beats_section(
                    self._current_novel_id or ""
                )
                clues = self.memory_engine.get_revealed_clues_section(
                    self._current_novel_id or ""
                )
                parts = [p for p in [fl, beats, clues] if p.strip()]
                fact_lock = "\n\n".join(parts) if parts else ""
            except Exception as e:
                logger.warning(f"MemoryEngine fact_lock 构建失败: {e}")

        # ★ Theme 集成：获取系统人设和写作规则
        theme_persona = ""
        theme_rules = ""
        format_rules = ""
        battle_enhancement = ""

        if self._theme_integrator:
            try:
                theme_persona = self._theme_integrator.build_system_persona()
                theme_rules = self._theme_integrator.build_writing_rules()
                format_rules = self._theme_integrator.build_format_rules()

                # 战斗场景检测和增强
                if beat_mode and beat_prompt:
                    battle_enhancement = self._theme_integrator.build_beat_enhancement(
                        beat_prompt, beat_focus="", chapter_number=self._current_chapter_number or 0, outline=outline
                    )
            except Exception as e:
                logger.debug(f"Theme 增强构建失败: {e}")

        # ★★★ 爽文引擎: 动态 Prompt 模板方案 ★★★
        # 架构决策：不在 autopilot_daemon 中硬编码规则引擎，
        # 而是在 workflow 的 Prompt 构建层注入动态爽文约束。
        # 这样 LLM 在强约束下自行发挥爽点呈现形式，比硬编码更灵活。
        shuangwen_directive = self._build_shuangwen_directive(
            chapter_number=self._current_chapter_number or 0,
            beat_mode=beat_mode,
            beat_index=beat_index,
            total_beats=total_beats,
            beat_prompt=beat_prompt or "",
            outline=outline,
        )

        prose_discipline = build_prose_discipline_block(
            beat_mode=beat_mode,
            beat_target_words=beat_target_words,
        )

        # ⚡ 提示词集中管理说明：
        # 此模板对应 prompt_packages/nodes/chapter-generation-main（CPMS chapter-generation-main）
        # CPMS: 优先从 PromptRegistry 获取模板，不可用时使用硬编码回退
        system_template = self._get_workflow_system_template()
        user_template = self._get_workflow_user_template()

        # 使用模板渲染（兼容 CPMS 模板和硬编码回退）
        # SafeDict: 用户在提示词广场编辑模板时可能引入未知变量，
        # 需要安全降级——未匹配的变量保留为 {name} 占位符，而非抛出 KeyError
        system_vars = {
            "theme_persona": theme_persona,
            "theme_rules": theme_rules,
            "planning_section": planning_section,
            "voice_block": voice_block,
            "context": context,
            "fact_lock": fact_lock,
            "shuangwen_directive": shuangwen_directive,
            "prose_discipline": prose_discipline,
            "length_rule": length_rule,
            "beat_extra": beat_extra,
            "format_rules": format_rules,
        }
        system_message = _safe_format(system_template, system_vars)

        # 旧版 CPMS 模板可能未含 {prose_discipline} 占位符：仍注入反八股块，避免升级后长期不生效
        if "行文戒律（反八股 / 控水分）" not in system_message:
            system_message = system_message.rstrip() + "\n\n" + prose_discipline

        if "人名硬约束" not in system_message:
            system_message = system_message.rstrip() + (
                "\n\n【人名硬约束】上下文人物设定（Bible）中的姓名为唯一正典。"
                "若本章大纲、故事线摘要或节拍说明中出现不同的人名（含旧稿占位名），"
                "正文必须以 Bible 为准统一使用 Bible 姓名，不得继续使用大纲里的占位名。\n"
            )

        user_message = _safe_format(user_template, {"outline": outline, "beat_section": ""})

        if beat_mode and prior_in_chapter:
            # V2：基于锚点的动态连贯性要求
            try:
                from application.workflows.beat_continuation import extract_beat_tail_anchor
                anchor = extract_beat_tail_anchor(prior_in_chapter)
                coherence_rules = _build_dynamic_coherence_rules(anchor)
            except Exception:
                coherence_rules = (
                    "1. 紧接上文最后的情节发展，保持时间线和逻辑的连续性\n"
                    "2. 如果上文以对话结尾，本节拍应继续该对话或自然过渡\n"
                    "3. 如果上文以动作结尾，本节拍应展示该动作的结果\n"
                    "4. 保持相同的场景设置，除非节拍明确要求转换场景\n"
                    "5. 人物情绪和状态应与上文保持一致并合理发展"
                )

            user_message += f"""

【本章上文（近期全文精确衔接 + 远期回溯避免重复；禁止复述、改写或重复已交代的情节与对白；勿写章节标题）】
{prior_in_chapter}

【🔗 连贯性要求（基于上文尾部状态动态生成）】
{coherence_rules}
"""

        if beat_mode:
            bi = beat_index if beat_index is not None else 0
            tb = total_beats if total_beats is not None else 1
            beat_tail = (
                "本段只写该节拍对应正文，紧接上文已写正文之后继续，衔接自然。"
                if prior_in_chapter
                else "本段只写该节拍对应正文，与全章其它节拍情节连贯。"
            )

            # 节拍间过渡指导（V2：基于前节拍尾部锚点的精确衔接指令）
            transition_guide = ""
            if prior_in_chapter and bi > 0:
                try:
                    from application.workflows.beat_continuation import (
                        extract_beat_tail_anchor,
                        build_beat_transition_directive,
                    )
                    anchor = extract_beat_tail_anchor(prior_in_chapter)
                    next_beat_desc = (beat_prompt or "").strip()[:80] if beat_prompt else ""
                    transition_guide = "\n\n" + build_beat_transition_directive(
                        anchor, bi, tb, next_beat_desc,
                    )
                except Exception as e:
                    logger.debug(f"节拍衔接锚点提取失败，降级通用过渡: {e}")
                    transition_guide = f"\n\n【节拍过渡指导（第{bi}/{tb}节拍）】\n- 从上一节拍的结尾自然过渡到本节拍的焦点\n- 保持叙事的流畅性，避免突兀的情节跳跃\n- 如果场景改变，提供合理的过渡说明"

            # ★ 战斗场景增强
            battle_hint = ""
            if battle_enhancement:
                battle_hint = f"\n\n{battle_enhancement}"

            user_message += f"""

【节拍 {bi + 1}/{tb}】
{(beat_prompt or '').strip()}

{beat_tail}{transition_guide}{battle_hint}"""

        # 重写指导注入：告知 AI 这是重写任务，并提供改进方向
        if regeneration_guidance and regeneration_guidance.strip():
            user_message += (
                f"\n\n【重新生成指导】\n"
                f"本章为重新生成（已有旧版本）。请根据以下改进方向撰写全新版本，"
                f"不必沿袭旧版本的情节走向或措辞：\n{regeneration_guidance.strip()}"
            )

        user_message += "\n\n开始撰写："

        return Prompt(system=system_message, user=user_message)

    # ─── CPMS 模板获取辅助方法 ───

    def _get_workflow_system_template(self) -> str:
        """获取主工作流 system 模板（CPMS 优先 -> 硬编码回退）。

        设计决策：
        - 主工作流的 system prompt 包含大量动态变量（theme_persona, fact_lock 等），
          不适合直接用 Registry.render() 一步渲染，而是获取模板后由 _build_prompt 手动 format。
        - 如果 PromptRegistry 中注册了 workflow-chapter-generation 节点，
          用户可在提示词广场直接编辑此模板并实时生效。
        - 降级时使用模块级 _FALLBACK_SYSTEM_TEMPLATE 常量。

        Returns:
            system prompt 模板字符串（含 {variable} 占位符）
        """
        try:
            from infrastructure.ai.prompt_registry import get_prompt_registry
            registry = get_prompt_registry()
            system = registry.get_system(_WORKFLOW_CHAPTER_GEN_NODE_KEY)
            if system:
                logger.debug(
                    "CPMS: 使用 Registry 模板 (node_key=%s)", _WORKFLOW_CHAPTER_GEN_NODE_KEY
                )
                return system
        except Exception as exc:
            logger.debug(
                "PromptRegistry 不可用 (node_key=%s): %s", _WORKFLOW_CHAPTER_GEN_NODE_KEY, exc
            )

        logger.debug("CPMS: 使用硬编码回退 system 模板")
        return _FALLBACK_SYSTEM_TEMPLATE

    def _get_workflow_user_template(self) -> str:
        """获取主工作流 user 模板（CPMS 优先 -> 硬编码回退）。

        同 _get_workflow_system_template 的设计决策：
        - 获取模板文本，后续由 _build_prompt 根据节拍模式追加更多段落。
        - 降级时使用模块级 _FALLBACK_USER_TEMPLATE 常量。

        Returns:
            user prompt 模板字符串（含 {variable} 占位符）
        """
        try:
            from infrastructure.ai.prompt_registry import get_prompt_registry
            registry = get_prompt_registry()
            user_template = registry.get_user_template(_WORKFLOW_CHAPTER_GEN_NODE_KEY)
            if user_template:
                logger.debug(
                    "CPMS: 使用 Registry user_template (node_key=%s)", _WORKFLOW_CHAPTER_GEN_NODE_KEY
                )
                return user_template
        except Exception as exc:
            logger.debug(
                "PromptRegistry 不可用 (node_key=%s): %s", _WORKFLOW_CHAPTER_GEN_NODE_KEY, exc
            )

        logger.debug("CPMS: 使用硬编码回退 user_template")
        return _FALLBACK_USER_TEMPLATE

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

    # ──────────────────────────────────────────────────────────
    # ★★★ 爽文引擎: 动态 Prompt 模板方案 ★★★
    # ──────────────────────────────────────────────────────────

    # 爽点类型关键词检测表
    _SHUANGWEN_BEAT_PATTERNS = {
        "power_reveal": {
            "keywords": ["实力", "底牌", "爆发", "力量", "实力展现", "压倒性", "碾压", "秒杀",
                         "一招", "击败", "战胜", "震惊全场", "不可置信"],
            "directive": (
                "⚡【爽文引擎·实力爆发指令】本节拍为核心爽点——主角展现压倒性实力！\n"
                "必须遵守：\n"
                "① 蓄力充分：之前的轻视/质疑/压制必须让读者替主角憋着一口气\n"
                "② 爆发震撼：用最短的句子、最快的节奏、最有画面感的动作展现实力\n"
                "③ 反应炸裂：旁观者从轻视→震惊→敬畏的180度态度转变是爽感核心\n"
                "   - 至少3个具体人物的反应：瞳孔骤缩、倒吸凉气、双腿发软、脸色煞白\n"
                "④ 主角态度：云淡风轻/不以为意/波澜不惊——反差越大越爽\n"
                "⑤ 爽点靠节奏与反差呈现，禁止用同义反复、纠正式排比或破折号叠句硬凑字数；该展开时用动作与对白顶上去。"
            ),
        },
        "identity_reveal": {
            "keywords": ["身份", "真实身份", "揭露", "曝光", "隐藏身份", "背景", "来历",
                         "竟然是", "原来", "家世", "师承", "传承"],
            "directive": (
                "⚡【爽文引擎·身份反转指令】本节拍为身份曝光瞬间！\n"
                "必须遵守：\n"
                "① 铺垫清晰：之前的误解/低估/忽视必须完整呈现\n"
                "② 揭露戏剧性：一个动作、一句话、一枚信物——让真相轰然揭晓\n"
                "③ 震动全场：周围人态度180度反转——嘲讽者脸色煞白、高傲者弯腰行礼\n"
                "   - 至少3个具体人物的态度变化\n"
                "④ 反派懊悔：之前的对手/打压者必须表现出极度后悔和恐惧\n"
                "⑤ 主角态度：漫不经心、云淡风轻——身份含金量通过他人反应呈现\n"
                "⑥ 认知冲击要充分，但禁止车轱辘改述同一句「震撼」；用他人具体反应与一句锚点动作收束即可。"
            ),
        },
        "face_slap": {
            "keywords": ["打脸", "啪啪", "反转", "逆转", "实力证明", "出乎意料",
                         "不敢相信", "目瞪口呆", "瞠目结舌", "自食其果"],
            "directive": (
                "⚡【爽文引擎·打脸反转指令】本节拍为经典打脸场景！\n"
                "必须遵守：\n"
                "① 先扬后抑：让对手的嚣张达到顶峰，再狠狠打脸\n"
                "② 打脸要响：要写众人亲眼看到、亲耳听到的场面，别停在暗处小赢就收笔\n"
                "③ 链式反应：一个人的震惊引发第二个人的怀疑，第二个人的证实引发第三个人的恐惧\n"
                "④ 对手反应：从不屑→怀疑→震惊→恐惧→崩溃，要有层次递进\n"
                "⑤ 打脸之后主角不要得意洋洋——淡然处之更让人心生敬畏"
            ),
        },
    }

    # 前三章专属的强力爽文指令
    _EARLY_CHAPTER_SHUANGWEN = {
        1: (
            "🔥【首章爽文铁律】这是读者决定去留的关键！\n"
            "① 第一段必须是动作或对话，绝不能是背景介绍\n"
            "② 主角在300字内必须遭遇不公/质疑/压制\n"
            "③ 章节过半时主角必须展露第一张底牌——哪怕是冰山一角\n"
            "④ 结尾必须留下强烈的悬念钩子\n"
            "⑤ 全章张力不低于65/100——没有'平淡'的资格！"
        ),
        2: (
            "⚡【次章加速铁律】首章的爽感必须延续！\n"
            "① 承接首章悬念，不能重新铺垫\n"
            "② 主角必须有一次'小爆发'——让轻视者开始动摇\n"
            "③ 引入更大威胁/更强对手——爽点升级\n"
            "④ 结尾暗示主角真正的实力远不止于此\n"
            "⑤ 张力不低于55/100——读者耐心在流失！"
        ),
        3: (
            "⚡【三章定乾坤】这是决定追读率的关键章！\n"
            "① 必须有一次真正的高潮——第一次正式对抗中的大逆转\n"
            "② 轻视者必须付出代价——打脸要响、要彻底\n"
            "③ 主角的特殊之处必须让至少3个关键人物重新评估\n"
            "④ 结尾留下更大的悬念——更强大的对手、更深的秘密\n"
            "⑤ 读者看完必须产生'这书真爽'的明确正反馈！"
        ),
    }

    def _build_shuangwen_directive(
        self,
        chapter_number: int,
        beat_mode: bool,
        beat_index: Optional[int],
        total_beats: Optional[int],
        beat_prompt: str,
        outline: str,
    ) -> str:
        """★★★ 爽文引擎: 动态构建爽文约束指令

        架构决策核心实现：
        - 不在 autopilot_daemon 中硬编码规则引擎
        - 而是在 workflow 的 Prompt 构建层注入动态爽文约束
        - LLM 在强约束下自行发挥爽点呈现形式
        - 约束来自：章节位置、节拍类型、大纲关键词匹配

        Args:
            chapter_number: 当前章节号
            beat_mode: 是否为节拍模式
            beat_index: 节拍索引
            total_beats: 总节拍数
            beat_prompt: 节拍 Prompt
            outline: 章节大纲

        Returns:
            爽文引擎约束指令文本（注入 system_message）
        """
        parts: list[str] = []

        # ── 1. 前三章强力指令（冷启动保护）──
        if 1 <= chapter_number <= 3:
            early_directive = self._EARLY_CHAPTER_SHUANGWEN.get(chapter_number, "")
            if early_directive:
                parts.append(early_directive)

        # ── 2. 节拍级爽点检测与指令注入 ──
        if beat_mode and beat_prompt:
            beat_directive = self._detect_and_build_beat_directive(
                beat_prompt, outline
            )
            if beat_directive:
                parts.append(beat_directive)

        # ── 3. 节拍位置约束（基于 STEP 阶跃） ──
        if beat_mode and beat_index is not None and total_beats and total_beats > 0:
            position_hint = self._build_beat_position_hint(
                beat_index, total_beats, chapter_number
            )
            if position_hint:
                parts.append(position_hint)

        # ── 4. 通用爽文节奏约束（所有章节） ──
        parts.append(self._build_general_shuangwen_rules())

        if parts:
            return "\n\n━━━ ★ 爽文引擎约束（必须遵守）━━━\n\n" + "\n\n".join(parts)

        return ""

    def _detect_and_build_beat_directive(self, beat_prompt: str, outline: str) -> str:
        """检测节拍/大纲中的爽点关键词，返回对应的约束指令"""
        combined_text = f"{beat_prompt} {outline}"

        best_match = None
        best_score = 0

        for pattern_name, pattern_config in self._SHUANGWEN_BEAT_PATTERNS.items():
            score = sum(1 for kw in pattern_config["keywords"] if kw in combined_text)
            if score > best_score:
                best_score = score
                best_match = pattern_config

        if best_match and best_score >= 1:
            return best_match["directive"]

        return ""

    def _build_beat_position_hint(
        self, beat_index: int, total_beats: int, chapter_number: int
    ) -> str:
        """根据节拍在章节中的位置，返回节奏约束"""
        progress = beat_index / max(total_beats, 1)

        if progress < 0.2:
            return (
                "📍【节奏: 章节开篇】前20%篇幅——\n"
                "- 用画面/动作/对话抓住读者，禁止大段叙述\n"
                "- 埋下本章冲突的种子\n"
                "- 如果有前章悬念，必须在前三句内接住"
            )
        elif progress < 0.5:
            return (
                "📍【节奏: 升温蓄力】20%-50%篇幅——\n"
                "- 冲突逐步升级，每段都有信息增量\n"
                "- 读者应该感到'有什么大事要发生了'\n"
                "- 主角遭遇的压制要越来越让人憋屈"
            )
        elif progress < 0.8:
            return (
                "📍【节奏: 爽点爆发】50%-80%篇幅——核心爽区！\n"
                "- 这是本章最关键的部分——爽点必须在这里爆发\n"
                "- 节奏加快，短句为主，画面快速切换\n"
                "- 旁观者反应与对手崩溃要有，但每人一两笔具体动作/台词即可，禁止排比灌水"
            )
        else:
            return (
                "📍【节奏: 收尾钩子】最后20%篇幅——\n"
                "- 爽感余韵：让读者在满足中回味\n"
                "- 简洁收尾，不要拖沓\n"
                "- 必须留一个钩子：一个未解的悬念/一个更大的挑战/一句意味深长的话"
            )

    def _build_general_shuangwen_rules(self) -> str:
        """通用爽文节奏约束（适用于所有章节）"""
        return (
            "🎯【爽文核心法则】\n"
            "① 蓄力→爆发→余韵——每章必须有这个节奏循环\n"
            "② 读者的爽感 = 压抑程度 × 释放力度——没有足够的压抑就没有爽感\n"
            "③ 旁观者反应要有，但每人一两笔具体动作/台词即可，禁止复制粘贴式排比段\n"
            "④ 打脸要响、反转要快、悬念要紧——爽文三宝\n"
            "⑤ 主角永远不能主动炫耀——但实力总会不自觉地流露\n"
            "⑥ 每章至少一次让读者产生'好爽'的瞬间——靠信息与节奏，不靠同义反复堆字数"
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
