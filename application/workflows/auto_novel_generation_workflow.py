"""自动小说生成工作流

整合所有子项目组件，实现完整的章节生成流程。
"""
import logging
import json
import os
import re
from typing import Tuple, Dict, Any, AsyncIterator, Optional, List
from application.ai.llm_json_extract import (
    extract_outer_json_object,
    repair_json,
    strip_json_fences,
)
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
from domain.novel.value_objects.consistency_report import (
    ConsistencyReport,
    Issue,
    IssueType,
    Severity,
)
from domain.novel.value_objects.chapter_state import ChapterState
from domain.novel.value_objects.consistency_context import ConsistencyContext
from domain.novel.value_objects.novel_id import NovelId
from domain.ai.services.llm_service import LLMService, GenerationConfig
from domain.ai.value_objects.prompt import Prompt
from application.ai.llm_output_sanitize import strip_reasoning_artifacts
from application.workflows.beat_continuation import format_prior_draft_for_prompt

logger = logging.getLogger(__name__)

# 与 ContextBuilder.build_structured_context 映射：Layer1≈T0+T1，Layer2=T2，Layer3=T3
# 段名与语义对齐，避免「SMART RETRIEVAL」贴在近期正文等历史误标
CHAPTER_CONTEXT_LAYER2_HEADER = "RECENT CHAPTERS"  # T2 近期章节正文
CHAPTER_CONTEXT_LAYER3_HEADER = "VECTOR RECALL"  # T3 向量召回
CHAPTER_GENERATION_MAX_TOKENS = 8192
CHAPTER_GENERATION_TEMPERATURE = 0.92
DEFAULT_CHAPTER_TARGET_WORDS = 2500
DEFAULT_WORD_TOLERANCE_RATIO = 0.05
MIN_WORD_TOLERANCE_RATIO = 0.02
MAX_WORD_TOLERANCE_RATIO = 0.20
LONG_CHAPTER_NEXT_SETUP_MIN_WORDS = 3800
NEXT_CHAPTER_SETUP_MAX_CHARS = 260
SCENE_BUDGET_MAX_SEGMENTS = 6
SCENE_BUDGET_MIN_SEGMENTS = 2
LONG_DRAFT_SPLIT_MIN = 2
LONG_DRAFT_SPLIT_MAX = 4


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
        style_prompt_overlay_service: Optional[Any] = None,
        prop_ledger_service: Optional[Any] = None,
        coc_canon_service: Optional[Any] = None,
        coc_clue_service: Optional[Any] = None,
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
            style_prompt_overlay_service: 写作手法知识库 overlay 服务（可选）
            prop_ledger_service: 道具账本服务（可选，用于章节生成前注入当前道具状态）
            coc_canon_service: CoC 正典 overlay 服务（可选）
            coc_clue_service: CoC 线索边界 overlay 服务（可选）
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
        self.style_prompt_overlay_service = style_prompt_overlay_service
        self.prop_ledger_service = prop_ledger_service
        self.coc_canon_service = coc_canon_service
        self.coc_clue_service = coc_clue_service
        self._current_coc_canon_overlay: str = ""
        self._current_coc_absolute_titles: list[str] = []
        self._current_coc_clue_overlay: str = ""
        self._current_coc_author_only_clue_keys: list[str] = []
        self._current_coc_cognition_overlay: str = ""
        self._current_coc_author_truth_snippets: list[str] = []
        self._coc_hard_guard_enabled: bool = True

    def precheck_coc_cognition_boundary(
        self,
        *,
        novel_id: str,
        chapter_number: int,
        outline: str,
    ) -> dict[str, Any]:
        """章节生成前的 CoC 认知边界预检。"""
        text = str(outline or "").strip()
        if not text:
            return {
                "checked": False,
                "allow_generate": True,
                "risk_level": "none",
                "blocking_issues": [],
                "warnings": [],
                "matched_tokens": [],
            }

        canon_layers: dict[str, Any] = {}
        clue_layers: dict[str, Any] = {}
        if self.coc_canon_service:
            try:
                layers = self.coc_canon_service.get_cognition_layers(novel_id) or {}
                canon_layers = layers if isinstance(layers, dict) else {}
            except Exception as e:
                logger.warning("coc precheck(canon) unavailable: %s", e)
        if self.coc_clue_service:
            try:
                layers = self.coc_clue_service.get_cognition_layers(novel_id) or {}
                clue_layers = layers if isinstance(layers, dict) else {}
            except Exception as e:
                logger.warning("coc precheck(clue) unavailable: %s", e)

        if not (canon_layers or clue_layers):
            return {
                "checked": False,
                "allow_generate": True,
                "risk_level": "none",
                "blocking_issues": [],
                "warnings": [],
                "matched_tokens": [],
            }

        blocking_issues: list[str] = []
        warnings: list[str] = []
        matched_tokens: list[str] = []

        author_truth_snippets = self._extract_coc_author_truth_snippets(
            canon_layers,
            [str(line or "") for line in (canon_layers.get("author_truth") or []) + (clue_layers.get("author_truth") or [])],
        )
        for snippet in author_truth_snippets:
            if snippet and snippet in text:
                token = snippet[:40]
                matched_tokens.append(token)
                blocking_issues.append(
                    f"命中作者真相片段：{token}...（建议改为伏笔/误导表达）"
                )

        author_only_keys: list[str] = []
        for line in clue_layers.get("author_truth") or []:
            raw = str(line or "").strip()
            if "：" in raw:
                key = raw.split("：", 1)[0].strip()
                if key and key not in author_only_keys:
                    author_only_keys.append(key)
        for key in author_only_keys:
            if key and key in text:
                matched_tokens.append(key)
                blocking_issues.append(
                    f"命中 author_only 线索键：{key}（大纲不应直接暴露）"
                )

        for line in clue_layers.get("character_known") or []:
            raw = str(line or "").strip()
            if not raw:
                continue
            hint = raw.split("：", 1)[0].strip() if "：" in raw else raw[:20]
            if hint and hint in text:
                warnings.append(
                    f"命中角色层线索：{hint}（生成时请通过角色视角逐步揭示）"
                )

        allow_generate = len(blocking_issues) == 0
        if blocking_issues:
            risk_level = "block"
        elif warnings:
            risk_level = "warning"
        else:
            risk_level = "none"
        return {
            "checked": True,
            "allow_generate": allow_generate,
            "risk_level": risk_level,
            "blocking_issues": blocking_issues,
            "warnings": warnings,
            "matched_tokens": matched_tokens,
            "chapter_number": int(chapter_number),
        }

    def rewrite_outline_for_coc_boundary(
        self,
        *,
        novel_id: str,
        chapter_number: int,
        outline: str,
        rewrite_mode: str = "conservative",
        rewrite_style: str = "generic",
    ) -> dict[str, Any]:
        """将命中 CoC 边界阻断的大纲改写为“可生成版本”。"""
        mode = str(rewrite_mode or "conservative").strip().lower()
        if mode not in {"conservative", "aggressive"}:
            mode = "conservative"
        style = str(rewrite_style or "generic").strip().lower()
        if style not in {"generic", "suspense", "coc"}:
            style = "generic"
        original = str(outline or "").strip()
        precheck = self.precheck_coc_cognition_boundary(
            novel_id=novel_id,
            chapter_number=chapter_number,
            outline=original,
        )
        if not original:
            return {
                "original_outline": original,
                "rewritten_outline": original,
                "changed": False,
                "rewrite_mode": mode,
                "rewrite_style": style,
                "applied_rules": [],
                "precheck_before": precheck,
                "precheck_after": precheck,
            }

        rewritten = original
        applied_rules: list[str] = []

        tokens = [str(item or "").strip() for item in precheck.get("matched_tokens") or []]
        tokens = [item for item in tokens if item]
        for token in sorted(set(tokens), key=len, reverse=True):
            if token and token in rewritten:
                rewritten = rewritten.replace(token, "未公开线索")
                applied_rules.append(f"替换敏感片段：{token[:24]}")

        replace_pairs = [
            (r"真实身份是", "身份成谜，疑似与"),
            (r"其实是", "疑似是"),
            (r"真相是", "线索指向"),
            (r"确认是", "怀疑是"),
            (r"明确写出", "通过异常细节暗示"),
        ]
        if mode == "aggressive":
            replace_pairs.extend(
                [
                    (r"揭露", "侧面触发"),
                    (r"揭示", "暗示"),
                    (r"证明", "疑似指向"),
                    (r"彻底查明", "暂时逼近"),
                    (r"最终确定", "阶段性判断"),
                    (r"直接说明", "以细节带出"),
                    (r"一口气说出", "话到嘴边又收住"),
                ]
            )
            if style == "suspense":
                replace_pairs.extend(
                    [
                        (r"凶手", "目标人物"),
                        (r"证据链完整", "证据链出现缺口"),
                        (r"确认作案", "动机与时机仍有反差"),
                        (r"全部真相", "关键一环"),
                    ]
                )
            elif style == "coc":
                replace_pairs.extend(
                    [
                        (r"神明", "不可名状存在"),
                        (r"邪神", "高位存在"),
                        (r"仪式成功", "仪式迹象增强"),
                        (r"san值归零", "精神状态急坠"),
                        (r"完全理解", "仅触及表层"),
                    ]
                )
        for pattern, target in replace_pairs:
            updated, count = re.subn(pattern, target, rewritten)
            if count > 0:
                rewritten = updated
                applied_rules.append(f"弱化直述表达：{pattern}→{target}")

        rewritten = re.sub(r"未公开线索(?:\s*未公开线索)+", "未公开线索", rewritten).strip()
        changed = rewritten != original
        postcheck = self.precheck_coc_cognition_boundary(
            novel_id=novel_id,
            chapter_number=chapter_number,
            outline=rewritten,
        )
        return {
            "original_outline": original,
            "rewritten_outline": rewritten,
            "changed": changed,
            "rewrite_mode": mode,
            "rewrite_style": style,
            "applied_rules": applied_rules,
            "precheck_before": precheck,
            "precheck_after": postcheck,
        }

    def validate_coc_content_boundary(
        self,
        *,
        novel_id: str,
        chapter_number: int,
        content: str,
    ) -> dict[str, Any]:
        """正文级 CoC 边界校验（用于保存前/生成后硬约束）。"""
        text = str(content or "").strip()
        if not text:
            return {
                "checked": False,
                "allow_save": True,
                "risk_level": "none",
                "blocking_issues": [],
                "warnings": [],
                "chapter_number": int(chapter_number),
            }

        # 复用 CoC overlay 解析逻辑，确保 author_only / author_truth / absolute 关键词集就绪
        self._current_novel_id = novel_id
        self._build_coc_canon_overlay()
        self._build_coc_clue_overlay()
        self._build_coc_cognition_overlay()

        canon_conflicts = self._detect_coc_canon_conflicts(text)
        clue_conflicts = self._detect_coc_clue_conflicts(text)
        truth_leaks = self._detect_coc_author_truth_leaks(text)
        blocking_issues = canon_conflicts + clue_conflicts + truth_leaks

        # strict/absolute 条目附近出现“否定重写词”时也视为阻断
        if self.coc_canon_service:
            try:
                overview = self.coc_canon_service.get_overview(novel_id) or {}
                entries = overview.get("entries") if isinstance(overview, dict) else []
                rewrite_terms = ("不是", "并非", "伪造", "作假", "推翻", "篡改", "虚构")
                for item in entries or []:
                    if not isinstance(item, dict):
                        continue
                    lock_level = str(item.get("lock_level") or "").strip().lower()
                    title = str(item.get("title") or "").strip()
                    if lock_level not in {"strict", "absolute"} or not title or title not in text:
                        continue
                    pattern = (
                        rf"(?:{re.escape(title)}[\s\S]{{0,16}}(?:{'|'.join(map(re.escape, rewrite_terms))}))"
                        rf"|(?:(?:{'|'.join(map(re.escape, rewrite_terms))})[\s\S]{{0,16}}{re.escape(title)})"
                    )
                    if re.search(pattern, text):
                        blocking_issues.append(
                            f"CoC正典硬约束冲突：{lock_level} 条目「{title}」附近出现否定重写表达。"
                        )
            except Exception as e:
                logger.warning("coc content validation(canon) unavailable: %s", e)

        blocking_issues = list(dict.fromkeys(blocking_issues))
        return {
            "checked": True,
            "allow_save": len(blocking_issues) == 0,
            "risk_level": "block" if blocking_issues else "none",
            "blocking_issues": blocking_issues,
            "warnings": [],
            "chapter_number": int(chapter_number),
        }

    @staticmethod
    def _chapter_generation_config() -> GenerationConfig:
        """章节首稿需要足够输出空间，避免被 profile 小 token 配置压成摘要稿。"""
        return GenerationConfig(
            max_tokens=CHAPTER_GENERATION_MAX_TOKENS,
            temperature=CHAPTER_GENERATION_TEMPERATURE,
        )

    @staticmethod
    def _bounded_word_target(target_word_count: Optional[int]) -> Optional[int]:
        if target_word_count is None:
            return None
        try:
            target = int(target_word_count)
        except (TypeError, ValueError):
            return None
        return max(800, min(12000, target))

    @staticmethod
    def _effective_word_target(target_word_count: Optional[int]) -> int:
        return AutoNovelGenerationWorkflow._bounded_word_target(target_word_count) or DEFAULT_CHAPTER_TARGET_WORDS

    @staticmethod
    def _resolve_word_tolerance_ratio(word_tolerance_ratio: Optional[float] = None) -> float:
        raw = word_tolerance_ratio
        if raw is None:
            env_ratio = (os.getenv("PLOTPILOT_WORD_TOLERANCE_RATIO") or "").strip()
            env_percent = (os.getenv("PLOTPILOT_WORD_TOLERANCE_PERCENT") or "").strip()
            chosen = env_ratio or env_percent
            if chosen:
                try:
                    raw = float(chosen)
                except (TypeError, ValueError):
                    raw = None
        if raw is None:
            return DEFAULT_WORD_TOLERANCE_RATIO
        ratio = float(raw)
        if ratio > 1:
            ratio = ratio / 100.0
        return max(MIN_WORD_TOLERANCE_RATIO, min(MAX_WORD_TOLERANCE_RATIO, ratio))

    @staticmethod
    def _target_word_range(
        target_word_count: Optional[int],
        word_tolerance_ratio: Optional[float] = None,
    ) -> Optional[tuple[int, int]]:
        target = AutoNovelGenerationWorkflow._effective_word_target(target_word_count)
        tolerance_ratio = AutoNovelGenerationWorkflow._resolve_word_tolerance_ratio(word_tolerance_ratio)
        tolerance = max(80, int(target * tolerance_ratio))
        return max(500, target - tolerance), target + tolerance

    @staticmethod
    def _config_for_target_words(
        target_word_count: Optional[int],
        word_tolerance_ratio: Optional[float] = None,
    ) -> GenerationConfig:
        if target_word_count is None:
            return AutoNovelGenerationWorkflow._chapter_generation_config()

        target = AutoNovelGenerationWorkflow._effective_word_target(target_word_count)
        tolerance_ratio = AutoNovelGenerationWorkflow._resolve_word_tolerance_ratio(word_tolerance_ratio)
        token_ratio = 1.10 + min(0.12, tolerance_ratio * 0.8)
        return GenerationConfig(
            max_tokens=max(1000, min(CHAPTER_GENERATION_MAX_TOKENS, int(target * token_ratio))),
            temperature=CHAPTER_GENERATION_TEMPERATURE,
        )

    @staticmethod
    def _env_flag(name: str, default: bool = False) -> bool:
        raw = (os.getenv(name) or "").strip().lower()
        if not raw:
            return default
        return raw in {"1", "true", "yes", "on"}

    def _is_scene_budget_enforced(self) -> bool:
        return self._env_flag("PLOTPILOT_SCENE_BUDGET_ENFORCED", True)

    def _is_ending_closer_enabled(self) -> bool:
        return self._env_flag("PLOTPILOT_ENDING_CLOSER_ENABLED", True)

    def _is_style_anchor_rag_enabled(self) -> bool:
        return self._env_flag("PLOTPILOT_STYLE_ANCHOR_RAG_ENABLED", True)

    @staticmethod
    def _normalize_long_draft_split_count(split_count: Optional[int]) -> int:
        try:
            count = int(split_count or LONG_DRAFT_SPLIT_MIN)
        except (TypeError, ValueError):
            count = LONG_DRAFT_SPLIT_MIN
        return max(LONG_DRAFT_SPLIT_MIN, min(LONG_DRAFT_SPLIT_MAX, count))

    def _resolve_scene_budget_plan(
        self,
        *,
        chapter_strategy: Optional[Dict[str, Any]],
        target_word_count: Optional[int],
        word_tolerance_ratio: Optional[float],
        beat_count: int,
    ) -> List[Dict[str, Any]]:
        if not self._is_scene_budget_enforced():
            return []
        if not isinstance(chapter_strategy, dict):
            return []
        raw_scenes = chapter_strategy.get("scene_plan")
        if not isinstance(raw_scenes, list):
            return []

        scenes: list[dict[str, Any]] = []
        for index, item in enumerate(raw_scenes[:SCENE_BUDGET_MAX_SEGMENTS], start=1):
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or item.get("title") or f"场景 {index}").strip() or f"场景 {index}"
            task = str(item.get("task") or "推进冲突").strip() or "推进冲突"
            resistance = str(item.get("resistance") or "出现阻力").strip() or "出现阻力"
            info_shift = str(item.get("info_shift") or "局势发生变化").strip() or "局势发生变化"
            relationship_shift = str(item.get("relationship_shift") or "无明显变化").strip() or "无明显变化"
            hook = str(item.get("hook") or "留下下一步追问").strip() or "留下下一步追问"
            anchor = str(item.get("anchor") or "一个可见动作或道具变化").strip() or "一个可见动作或道具变化"
            visible_action = str(item.get("visible_action") or anchor or "用具体动作推进").strip() or "用具体动作推进"
            subtext_dialogue = str(item.get("subtext_dialogue") or "对白必须有试探、遮掩或信息差").strip() or "对白必须有试探、遮掩或信息差"
            unspoken_emotion = str(item.get("unspoken_emotion") or "情绪不能直说").strip() or "情绪不能直说"
            object_or_clue_change = str(item.get("object_or_clue_change") or "线索或道具状态必须变化").strip() or "线索或道具状态必须变化"
            try:
                target = int(item.get("target_words") or 0)
            except (TypeError, ValueError):
                target = 0
            scenes.append(
                {
                    "label": label,
                    "task": task,
                    "resistance": resistance,
                    "info_shift": info_shift,
                    "relationship_shift": relationship_shift,
                    "hook": hook,
                    "anchor": anchor,
                    "visible_action": visible_action,
                    "subtext_dialogue": subtext_dialogue,
                    "unspoken_emotion": unspoken_emotion,
                    "object_or_clue_change": object_or_clue_change,
                    "target_words": target,
                }
            )
        if len(scenes) < SCENE_BUDGET_MIN_SEGMENTS:
            return []

        target_total = self._effective_word_target(target_word_count)
        min_words, max_words = self._target_word_range(target_word_count, word_tolerance_ratio)
        tolerance_ratio = self._resolve_word_tolerance_ratio(word_tolerance_ratio)
        scene_count = len(scenes)
        min_scene = max(260, int(target_total * 0.08))
        max_scene = max(min_scene + 80, min(2200, int(target_total * 0.62)))
        fallback_scene = max(min_scene, int(target_total / scene_count))

        weights: list[int] = []
        for scene in scenes:
            raw = int(scene.get("target_words") or 0)
            if raw <= 0:
                raw = fallback_scene
            raw = max(min_scene, min(max_scene, raw))
            weights.append(raw)
        total = sum(weights) or 1

        normalized: list[int] = []
        for raw in weights:
            val = int(round(raw * target_total / total))
            val = max(min_scene, min(max_scene, val))
            normalized.append(val)

        drift = target_total - sum(normalized)
        cursor = 0
        while drift != 0 and normalized:
            i = cursor % len(normalized)
            if drift > 0 and normalized[i] < max_scene:
                normalized[i] += 1
                drift -= 1
            elif drift < 0 and normalized[i] > min_scene:
                normalized[i] -= 1
                drift += 1
            cursor += 1
            if cursor > target_total * 2:
                break

        plan: list[Dict[str, Any]] = []
        for index, scene in enumerate(scenes):
            tw = normalized[index]
            per_scene_tolerance = max(45, int(tw * min(0.2, tolerance_ratio * 1.5)))
            scene_min = max(180, tw - per_scene_tolerance)
            scene_max = min(max_words, tw + per_scene_tolerance)
            plan.append(
                {
                    **scene,
                    "target_words": tw,
                    "min_words": scene_min,
                    "max_words": scene_max,
                }
            )

        if beat_count > 0 and len(plan) != beat_count:
            base_scene = plan
            expanded: list[Dict[str, Any]] = []
            for i in range(beat_count):
                source = base_scene[min(len(base_scene) - 1, int(i * len(base_scene) / beat_count))]
                expanded.append({**source})
            plan = expanded
        return plan

    @staticmethod
    def _scene_hint_from_budget_plan(
        scene_budget_plan: List[Dict[str, Any]],
        index: int,
    ) -> Optional[Dict[str, Any]]:
        if not scene_budget_plan:
            return None
        if index < 0 or index >= len(scene_budget_plan):
            return None
        scene = scene_budget_plan[index]
        if not isinstance(scene, dict):
            return None
        return scene

    @staticmethod
    def _build_scene_budget_overlay(scene_hint: Optional[Dict[str, Any]]) -> str:
        if not scene_hint:
            return ""
        label = str(scene_hint.get("label") or "场景").strip() or "场景"
        task = str(scene_hint.get("task") or "推进冲突").strip() or "推进冲突"
        resistance = str(scene_hint.get("resistance") or "出现阻力").strip() or "出现阻力"
        info_shift = str(scene_hint.get("info_shift") or "局势变化").strip() or "局势变化"
        relation = str(scene_hint.get("relationship_shift") or "无明显变化").strip() or "无明显变化"
        anchor = str(scene_hint.get("anchor") or "动作/道具锚点").strip() or "动作/道具锚点"
        hook = str(scene_hint.get("hook") or "留下追问").strip() or "留下追问"
        visible_action = str(scene_hint.get("visible_action") or "用具体动作推进").strip() or "用具体动作推进"
        subtext_dialogue = str(scene_hint.get("subtext_dialogue") or "对白保留潜台词").strip() or "对白保留潜台词"
        unspoken_emotion = str(scene_hint.get("unspoken_emotion") or "情绪不能直说").strip() or "情绪不能直说"
        object_or_clue_change = str(scene_hint.get("object_or_clue_change") or "线索或道具状态变化").strip() or "线索或道具状态变化"
        target_words = int(scene_hint.get("target_words") or 0)
        min_words = int(scene_hint.get("min_words") or 0)
        max_words = int(scene_hint.get("max_words") or 0)
        if target_words > 0 and min_words > 0 and max_words > 0:
            budget_line = f"本段预算 {target_words} 字，允许 {min_words}-{max_words} 字。"
        elif target_words > 0:
            budget_line = f"本段预算 {target_words} 字。"
        else:
            budget_line = "本段预算以当前场景推进为准。"
        return (
            "【场景包执行（预算锁定）】\n"
            f"- 场景：{label}\n"
            f"- 任务：{task}\n"
            f"- 阻力：{resistance}\n"
            f"- 信息变化：{info_shift}\n"
            f"- 关系变化：{relation}\n"
            f"- 场景锚点：{anchor}\n"
            f"- 可见动作：{visible_action}\n"
            f"- 潜台词对白：{subtext_dialogue}\n"
            f"- 未说出口的情绪：{unspoken_emotion}\n"
            f"- 道具/线索变化：{object_or_clue_change}\n"
            f"- 结尾钩子：{hook}\n"
            f"- {budget_line}\n"
            "- 禁止把本段写成解释总结，必须通过动作/对白/细节推进。"
        )

    @staticmethod
    def _story_text_units(text: str) -> int:
        return len(re.sub(r"\s+", "", text or ""))

    @staticmethod
    def _is_sentence_tail_complete(text: str) -> bool:
        sample = (text or "").rstrip()
        if not sample:
            return True
        enders = "。！？!?…"
        closers = "”’」』）】\"'"
        tail = sample[-1]
        if tail in enders:
            return True
        if tail in closers and len(sample) >= 2 and sample[-2] in enders:
            return True
        return False

    def _smooth_truncated_tail(self, text: str, *, min_words: int) -> str:
        """避免章节在硬上限后停在半句，优先回退到最近完整句。"""
        sample = (text or "").rstrip()
        if not sample or self._is_sentence_tail_complete(sample):
            return sample

        # 优先在末尾窗口内寻找最近的句末边界；只要不明显低于目标下限即可回退。
        fallback = None
        for m in re.finditer(r"[。！？!?…](?:[”’」』）】\"'])*", sample):
            if len(sample) - m.end() <= 260:
                fallback = m.end()
        if fallback is not None:
            candidate = sample[:fallback].rstrip()
            if self._story_text_units(candidate) >= max(500, min_words - 180):
                return candidate

        # 找不到合适边界时，最小修复为补句号，避免裸半句。
        trimmed = sample.rstrip("，,、；;：:")
        if not trimmed:
            return sample
        if trimmed[-1].isspace():
            return trimmed.rstrip() + "。"
        # 以“替换末字符”为优先，避免收束动作把字数上限顶穿 +1。
        return trimmed[:-1] + "。"

    @staticmethod
    def _extract_tail_segment(text: str, *, window_chars: int = 460) -> tuple[str, str]:
        source = text or ""
        if not source:
            return "", ""
        start = max(0, len(source) - window_chars)
        para_break = source.rfind("\n\n", start)
        if para_break >= 0:
            start = para_break + 2
        return source[:start], source[start:]

    async def _soft_land_chapter_ending_if_needed(
        self,
        *,
        content: str,
        outline: str,
        min_words: int,
        max_words: int,
        force: bool = False,
    ) -> str:
        """章末软着陆：在不增设定、不突破字数的前提下，让结尾更自然有钩子。"""
        draft = (content or "").strip()
        if not draft:
            return content
        total_units = self._story_text_units(draft)
        if total_units < 900:
            return content

        # 仅在接近上限或被硬截断后触发，避免每章额外调用一次 LLM。
        near_cap = (max_words - total_units) <= 90
        if not force and not near_cap:
            return content

        head, tail = self._extract_tail_segment(draft, window_chars=520)
        tail_units = self._story_text_units(tail)
        if tail_units < 120:
            return content

        prompt = Prompt(
            system=(
                "你是中文小说主编。只改写章节最后一段，让结尾自然收束且保留追读钩子。"
                "只输出改写后的“最后一段”，不要标题，不要解释。"
            ),
            user=(
                "约束：\n"
                "1) 不改变既有事实，不新增角色或世界观设定；\n"
                "2) 维持当前悬念方向，不把真相提前说破；\n"
                "3) 字数控制在原尾段的 80%-110%，且必须以完整句收尾；\n"
                "4) 保留人物语气和现场动作感，避免总结腔。\n\n"
                f"【本章大纲】\n{outline}\n\n"
                f"【当前尾段】\n{tail}\n\n"
                "请输出改写后的尾段："
            ),
        )
        try:
            result = await self.llm_service.generate(
                prompt,
                GenerationConfig(max_tokens=max(220, min(900, int(tail_units * 1.35))), temperature=0.72),
            )
            rewritten_tail = strip_reasoning_artifacts((result.content or "").strip())
        except Exception as exc:
            logger.warning("ending soft-landing skipped: %s", exc)
            return content

        if not rewritten_tail:
            return content
        rewritten_units = self._story_text_units(rewritten_tail)
        if rewritten_units < max(80, int(tail_units * 0.8)):
            return content
        if rewritten_units > int(tail_units * 1.15) + 40:
            return content
        if not self._is_sentence_tail_complete(rewritten_tail):
            rewritten_tail = self._smooth_truncated_tail(rewritten_tail, min_words=max(80, min_words // 4))

        merged = (head.rstrip() + "\n\n" + rewritten_tail.lstrip()).strip() if head.strip() else rewritten_tail
        merged_units = self._story_text_units(merged)
        if merged_units > max_words:
            merged = self._truncate_to_story_text_units(merged, max_words)
            merged = self._smooth_truncated_tail(merged, min_words=min_words)
            merged_units = self._story_text_units(merged)
        if merged_units < max(500, min_words - 220):
            return content
        return merged

    @staticmethod
    def _truncate_to_story_text_units(text: str, limit: int) -> str:
        source = text or ""
        if limit <= 0:
            return ""
        current = 0
        cut_index = len(source)
        for idx, ch in enumerate(source):
            if not ch.isspace():
                current += 1
            if current >= limit:
                cut_index = idx + 1
                break
        if cut_index >= len(source):
            return source.strip()

        lookahead = source[cut_index: cut_index + 120]
        stop = re.search(r"[。！？!?…\n]", lookahead)
        if stop:
            cut_index += stop.start() + 1
        trimmed = source[:cut_index].strip()
        while trimmed and AutoNovelGenerationWorkflow._story_text_units(trimmed) > limit:
            trimmed = trimmed[:-1].rstrip()
        return trimmed

    async def _expand_to_min_word_target(
        self,
        *,
        content: str,
        outline: str,
        min_words: int,
    ) -> str:
        current_words = self._story_text_units(content)
        if current_words >= min_words:
            return content
        needed = min_words - current_words
        if needed < 120:
            return content

        prompt = Prompt(
            system=(
                "你是中文小说续写编辑。只负责在不改动前文事实的前提下补足章节长度。"
                "只输出续写正文，不要解释，不要标题，不要总结。"
            ),
            user=(
                f"目标：在现有正文后补写 {needed}-{needed + 160} 字，让总字数至少达到 {min_words} 字。\n"
                "约束：承接前文冲突，不重述已写情节，不新增世界观设定。\n\n"
                f"【本章大纲】\n{outline}\n\n"
                f"【已写正文】\n{content}\n\n"
                "请直接续写："
            ),
        )
        try:
            max_tokens = max(500, min(2200, int(needed * 1.3)))
            result = await self.llm_service.generate(
                prompt,
                GenerationConfig(max_tokens=max_tokens, temperature=0.88),
            )
            appendix = strip_reasoning_artifacts((result.content or "").strip())
            if not appendix:
                return content
            merged = (content.rstrip() + "\n\n" + appendix.lstrip()).strip()
            return merged
        except Exception as exc:
            logger.warning("word target expansion skipped: %s", exc)
            return content

    async def _enforce_chapter_word_target(
        self,
        *,
        content: str,
        outline: str,
        target_word_count: Optional[int],
        word_tolerance_ratio: Optional[float] = None,
    ) -> str:
        if target_word_count is None:
            return (content or "").strip()

        min_words, max_words = self._target_word_range(target_word_count, word_tolerance_ratio)
        normalized = (content or "").strip()
        current_words = self._story_text_units(normalized)
        was_trimmed = False

        if current_words > max_words:
            normalized = self._truncate_to_story_text_units(normalized, max_words)
            current_words = self._story_text_units(normalized)
            was_trimmed = True
            logger.info(
                "word target clamp: trimmed to <= %s, now=%s",
                max_words,
                current_words,
            )

        if current_words < min_words:
            normalized = await self._expand_to_min_word_target(
                content=normalized,
                outline=outline,
                min_words=min_words,
            )
            current_words = self._story_text_units(normalized)
            if current_words > max_words:
                normalized = self._truncate_to_story_text_units(normalized, max_words)
                current_words = self._story_text_units(normalized)
            logger.info(
                "word target clamp: expanded to >= %s, now=%s",
                min_words,
                current_words,
            )

        normalized = self._smooth_truncated_tail(normalized, min_words=min_words)
        current_words = self._story_text_units(normalized)
        if current_words > max_words:
            normalized = self._truncate_to_story_text_units(normalized, max_words)
            normalized = self._smooth_truncated_tail(normalized, min_words=min_words)
            current_words = self._story_text_units(normalized)

        near_cap = (max_words - current_words) <= 120
        if self._is_ending_closer_enabled() and near_cap:
            normalized = await self._soft_land_chapter_ending_if_needed(
                content=normalized,
                outline=outline,
                min_words=min_words,
                max_words=max_words,
                force=False,
            )
            current_words = self._story_text_units(normalized)
            if current_words > max_words:
                normalized = self._truncate_to_story_text_units(normalized, max_words)
                normalized = self._smooth_truncated_tail(normalized, min_words=min_words)
                current_words = self._story_text_units(normalized)

        if was_trimmed:
            normalized = await self._soft_land_chapter_ending_if_needed(
                content=normalized,
                outline=outline,
                min_words=min_words,
                max_words=max_words,
                force=True,
            )
            current_words = self._story_text_units(normalized)
            if current_words > max_words:
                normalized = self._truncate_to_story_text_units(normalized, max_words)
                normalized = self._smooth_truncated_tail(normalized, min_words=min_words)
        return normalized

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
        coc_conflict_warnings = self._detect_coc_canon_conflicts(content)
        coc_clue_warnings = self._detect_coc_clue_conflicts(content)
        coc_truth_warnings = self._detect_coc_author_truth_leaks(content)
        all_coc_warnings = coc_conflict_warnings + coc_clue_warnings + coc_truth_warnings
        if self._coc_hard_guard_enabled and all_coc_warnings:
            joined = "；".join(all_coc_warnings[:4])
            raise ValueError(f"CoC硬约束阻断：{joined}")
        if all_coc_warnings:
            merged_warnings = list(consistency_report.warnings)
            for warning_text in all_coc_warnings:
                merged_warnings.append(
                    Issue(
                        type=IssueType.EVENT_LOGIC_ERROR,
                        severity=Severity.MINOR,
                        description=warning_text,
                        location=max(1, chapter_number),
                    )
                )
            consistency_report = ConsistencyReport(
                issues=list(consistency_report.issues),
                warnings=merged_warnings,
                suggestions=list(consistency_report.suggestions),
            )
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
        enable_beats: bool = True,
        style_profile_id: str = "",
        scene_type: str = "",
        chapter_strategy: Optional[Dict[str, Any]] = None,
        target_word_count: Optional[int] = None,
        word_tolerance_ratio: Optional[float] = None,
    ) -> GenerationResult:
        """生成章节（完整工作流）

        Args:
            novel_id: 小说 ID
            chapter_number: 章节号
            outline: 章节大纲
            scene_director: 可选的场记分析结果，用于过滤角色和地点
            style_profile_id: 可选写作手法档案 ID

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
        style_overlay = self._build_style_overlay(novel_id, style_profile_id, scene_type)
        next_chapter_bridge = self._build_next_chapter_bridge_overlay(
            novel_id=novel_id,
            chapter_number=chapter_number,
            target_word_count=target_word_count,
            chapter_strategy=None,
        )
        logger.info(f"  ✓ 上下文已构建: {len(context)} 字符, 约 {context_tokens} tokens")

        logger.info("阶段 3: 生成 - 调用 LLM")
        config = self._config_for_target_words(target_word_count, word_tolerance_ratio)
        
        # 如果使用节拍模式，先放大节拍
        beats = []
        scene_budget_plan: list[dict[str, Any]] = []
        if enable_beats:
            logger.info("  → 启用节拍模式，拆分大纲为微观节拍")
            beats = self.context_builder.magnify_outline_to_beats(
                chapter_number,
                outline,
                target_chapter_words=self._effective_word_target(target_word_count),
            )
            if not isinstance(beats, list):
                logger.warning("  ⚠ 微观节拍拆分返回异常，回退到单段生成")
                beats = []
            logger.info(f"  ✓ 已拆分为 {len(beats)} 个微观节拍")
            scene_budget_plan = self._resolve_scene_budget_plan(
                chapter_strategy=chapter_strategy,
                target_word_count=target_word_count,
                word_tolerance_ratio=word_tolerance_ratio,
                beat_count=len(beats),
            )
            if scene_budget_plan:
                logger.info(
                    "  ✓ 场景包预算已生效: %s 段，预算合计 %s 字",
                    len(scene_budget_plan),
                    sum(int(item.get("target_words") or 0) for item in scene_budget_plan),
                )
        
        # 根据是否使用节拍选择不同的生成策略
        if enable_beats and beats:
            # 按节拍生成
            content_parts: list[str] = []
            for i, beat in enumerate(beats):
                prior_draft = "\n\n".join(content_parts)
                scene_hint = self._scene_hint_from_budget_plan(scene_budget_plan, i)
                beat_prompt_text = self.context_builder.build_beat_prompt(beat, i, len(beats))
                scene_budget_overlay = self._build_scene_budget_overlay(scene_hint)
                if scene_budget_overlay:
                    beat_prompt_text = f"{beat_prompt_text}\n\n{scene_budget_overlay}"
                beat_target_words = int(scene_hint.get("target_words")) if scene_hint else int(beat.target_words)
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
                    beat_target_words=beat_target_words,
                    target_word_count=target_word_count,
                    word_tolerance_ratio=word_tolerance_ratio,
                    voice_anchors=bundle.get("voice_anchors") or "",
                    chapter_draft_so_far=prior_draft,
                    style_overlay=style_overlay,
                    chapter_strategy=chapter_strategy,
                    next_chapter_bridge=next_chapter_bridge,
                )
                
                llm_result = await self.llm_service.generate(
                    prompt,
                    self._config_for_target_words(beat_target_words, word_tolerance_ratio),
                )
                beat_content = llm_result.content
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
                style_overlay=style_overlay,
                chapter_strategy=chapter_strategy,
                next_chapter_bridge=next_chapter_bridge,
                target_word_count=target_word_count,
                word_tolerance_ratio=word_tolerance_ratio,
            )
            logger.info(f"  → 发送请求到 LLM (max_tokens={config.max_tokens}, temperature={config.temperature})")
            llm_result = await self.llm_service.generate(prompt, config)
            content = strip_reasoning_artifacts(llm_result.content or "")
            logger.info(f"  ✓ LLM 响应已接收: {len(content)} 字符")

        content = await self._naturalize_ai_flavor_if_needed(
            content=content,
            outline=outline,
            style_overlay=style_overlay,
        )
        content = await self._enforce_chapter_word_target(
            content=content,
            outline=outline,
            target_word_count=target_word_count,
            word_tolerance_ratio=word_tolerance_ratio,
        )
        
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
        style_profile_id: str = "",
        scene_type: str = "",
        direct_writing_mode: bool = False,
        direct_light_polish: bool = False,
        chapter_strategy: Optional[Dict[str, Any]] = None,
        target_word_count: Optional[int] = None,
        word_tolerance_ratio: Optional[float] = None,
        long_draft_mode: bool = False,
        long_draft_split_count: Optional[int] = None,
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

            logger.info(f"========================================")
            logger.info(f"开始流式生成章节: 小说={novel_id}, 章节={chapter_number}")
            logger.info(f"========================================")

            split_count = self._normalize_long_draft_split_count(long_draft_split_count)
            effective_target_word_count = target_word_count
            effective_word_tolerance_ratio = word_tolerance_ratio
            effective_outline = outline
            if long_draft_mode:
                base_target = self._effective_word_target(target_word_count)
                effective_target_word_count = int(base_target * split_count)
                effective_word_tolerance_ratio = max(
                    0.08,
                    self._resolve_word_tolerance_ratio(word_tolerance_ratio),
                )
                effective_outline = (
                    f"{outline.strip()}\n\n"
                    "【长稿母本灰度模式】\n"
                    f"- 本次先写连续母稿，目标约 {effective_target_word_count} 字，后续将拆分为 {split_count} 章。\n"
                    "- 文内至少形成与拆章数量一致的自然转折点；每个转折点前要有冲突推进，转折后要有新代价或新目标。\n"
                    "- 结尾不要封死，要留下可切分的追读钩子。"
                ).strip()
                yield {
                    "type": "long_draft_plan",
                    "enabled": True,
                    "split_count": split_count,
                    "target_word_count": effective_target_word_count,
                }

            yield {"type": "phase", "phase": "planning"}
            yield {"type": "phase", "phase": "context"}
            logger.info("阶段 1-2: prepare_chapter_generation（规划 + 结构化上下文）")
            bundle = self.prepare_chapter_generation(
                novel_id, chapter_number, effective_outline, scene_director=scene_director
            )
            context = bundle["context"]
            context_tokens = bundle["context_tokens"]
            style_overlay = self._build_style_overlay(novel_id, style_profile_id, scene_type)
            next_chapter_bridge = self._build_next_chapter_bridge_overlay(
                novel_id=novel_id,
                chapter_number=chapter_number,
                target_word_count=effective_target_word_count,
                chapter_strategy=chapter_strategy,
            )
            logger.info(f"  ✓ 上下文已构建: {len(context)} 字符, 约 {context_tokens} tokens")

            yield {"type": "phase", "phase": "llm"}
            logger.info("阶段 3: 生成 - 调用 LLM 流式生成")
            config = self._config_for_target_words(effective_target_word_count, effective_word_tolerance_ratio)
            chunk_count = 0
            total_chars = 0
            _, max_words = self._target_word_range(effective_target_word_count, effective_word_tolerance_ratio)
            # 流式阶段先做硬上限截断，避免前端先看到超长正文（例如 5k+）再等待章后钳制。
            stream_unit_hard_limit = max(max_words + 120, int(max_words * 1.18))
            emitted_story_units = 0
            hit_stream_hard_limit = False

            def _slice_piece_for_stream_limit(piece: str) -> str:
                nonlocal emitted_story_units, hit_stream_hard_limit
                if not piece or hit_stream_hard_limit:
                    return ""
                remain = stream_unit_hard_limit - emitted_story_units
                if remain <= 0:
                    hit_stream_hard_limit = True
                    return ""
                piece_units = self._story_text_units(piece)
                if piece_units <= remain:
                    emitted_story_units += piece_units
                    return piece
                # 仅保留剩余配额内的正文片段，防止流式阶段暴涨。
                clipped = self._truncate_to_story_text_units(piece, remain)
                emitted_story_units += self._story_text_units(clipped)
                hit_stream_hard_limit = True
                return clipped

            if direct_writing_mode:
                logger.info("  → 直接写作模式：跳过节拍拆分、自然化后处理与章后质检")
                prompt = self._build_direct_writing_prompt(
                    context=context,
                    outline=effective_outline,
                    storyline_context=bundle["storyline_context"],
                    plot_tension=bundle["plot_tension"],
                    style_summary=bundle["style_summary"],
                    voice_anchors=bundle.get("voice_anchors") or "",
                    chapter_strategy=chapter_strategy,
                    next_chapter_bridge=next_chapter_bridge,
                    target_word_count=effective_target_word_count,
                    word_tolerance_ratio=effective_word_tolerance_ratio,
                )
                parts: list[str] = []
                total_chars = 0
                async for piece in self.llm_service.stream_generate(prompt, config):
                    clipped_piece = _slice_piece_for_stream_limit(piece)
                    if clipped_piece:
                        parts.append(clipped_piece)
                        chunk_count += 1
                        total_chars += len(clipped_piece)
                    if not clipped_piece:
                        if hit_stream_hard_limit:
                            logger.info(
                                "stream hard limit reached (direct): limit=%s, emitted=%s",
                                stream_unit_hard_limit,
                                emitted_story_units,
                            )
                            break
                        continue
                    yield {
                        "type": "chunk",
                        "text": clipped_piece,
                        "stats": {
                            "chars": total_chars,
                            "chunks": chunk_count,
                            "estimated_tokens": int(total_chars / 1.5),
                        },
                    }
                    if hit_stream_hard_limit:
                        logger.info(
                            "stream hard limit reached (direct): limit=%s, emitted=%s",
                            stream_unit_hard_limit,
                            emitted_story_units,
                        )
                        break

                content = strip_reasoning_artifacts("".join(parts))
                if not content.strip():
                    logger.error("  × 模型返回空内容")
                    yield {"type": "error", "message": "模型返回空内容"}
                    return

                if direct_light_polish:
                    yield {"type": "phase", "phase": "polish"}
                    content = await self._apply_direct_light_polish_if_needed(
                        content=content,
                        outline=effective_outline,
                    )
                content = await self._enforce_chapter_word_target(
                    content=content,
                    outline=effective_outline,
                    target_word_count=effective_target_word_count,
                    word_tolerance_ratio=effective_word_tolerance_ratio,
                )

                coc_boundary = self.validate_coc_content_boundary(
                    novel_id=novel_id,
                    chapter_number=chapter_number,
                    content=content,
                )
                if not coc_boundary.get("allow_save", True):
                    reasons = coc_boundary.get("blocking_issues") or []
                    reason = reasons[0] if reasons else "命中 CoC 硬约束"
                    yield {"type": "error", "message": f"CoC硬约束阻断：{reason}"}
                    return

                output_tokens = int(len(content) / 1.5)
                total_tokens = context_tokens + output_tokens
                yield {
                    "type": "done",
                    "content": content,
                    "consistency_report": _consistency_report_to_dict(
                        ConsistencyReport(issues=[], warnings=[], suggestions=[])
                    ),
                    "token_count": context_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": total_tokens,
                    "chars": len(content),
                    "ghost_annotations": [],
                    "style_warnings": [],
                    "direct_writing_mode": True,
                    "direct_light_polish": direct_light_polish,
                    "long_draft_mode": long_draft_mode,
                    "long_draft_split_count": split_count if long_draft_mode else None,
                }
                return
            
            # 如果使用节拍模式，先放大节拍
            beats = []
            scene_budget_plan: list[dict[str, Any]] = []
            if enable_beats:
                logger.info("  → 启用节拍模式，拆分大纲为微观节拍")
                beats = self.context_builder.magnify_outline_to_beats(
                    chapter_number,
                    effective_outline,
                    target_chapter_words=self._effective_word_target(effective_target_word_count),
                )
                if not isinstance(beats, list):
                    logger.warning("  ⚠ 微观节拍拆分返回异常，回退到单段生成")
                    beats = []
                logger.info(f"  ✓ 已拆分为 {len(beats)} 个微观节拍")
                scene_budget_plan = self._resolve_scene_budget_plan(
                    chapter_strategy=chapter_strategy,
                    target_word_count=effective_target_word_count,
                    word_tolerance_ratio=effective_word_tolerance_ratio,
                    beat_count=len(beats),
                )
                if scene_budget_plan:
                    logger.info(
                        "  ✓ 场景包预算已生效: %s 段，预算合计 %s 字",
                        len(scene_budget_plan),
                        sum(int(item.get("target_words") or 0) for item in scene_budget_plan),
                    )
                
                # 发送节拍信息用于前端展示
                yield {
                    "type": "beats_generated",
                    "beats": [
                        {
                            "description": beat.description,
                            "target_words": beat.target_words,
                            "focus": beat.focus
                        } for beat in beats
                    ],
                    "scene_budget_plan": scene_budget_plan,
                }
            
            # 根据是否使用节拍选择不同的生成策略
            if enable_beats and beats:
                # 按节拍生成
                content_parts: list[str] = []
                for i, beat in enumerate(beats):
                    prior_draft = "\n\n".join(content_parts)
                    scene_hint = self._scene_hint_from_budget_plan(scene_budget_plan, i)
                    beat_prompt_text = self.context_builder.build_beat_prompt(beat, i, len(beats))
                    scene_budget_overlay = self._build_scene_budget_overlay(scene_hint)
                    if scene_budget_overlay:
                        beat_prompt_text = f"{beat_prompt_text}\n\n{scene_budget_overlay}"
                    beat_target_words = int(scene_hint.get("target_words")) if scene_hint else int(beat.target_words)
                    logger.info(f"生成节拍 {i+1}/{len(beats)}: {beat.focus} - {beat.description[:50]}...")
                    
                    prompt = self._build_prompt(
                        context,
                        effective_outline,
                        storyline_context=bundle["storyline_context"],
                        plot_tension=bundle["plot_tension"],
                        style_summary=bundle["style_summary"],
                        beat_prompt=beat_prompt_text,
                        beat_index=i,
                        total_beats=len(beats),
                        beat_target_words=beat_target_words,
                        voice_anchors=bundle.get("voice_anchors") or "",
                        chapter_draft_so_far=prior_draft,
                        style_overlay=style_overlay,
                        chapter_strategy=chapter_strategy,
                        next_chapter_bridge=next_chapter_bridge,
                        target_word_count=effective_target_word_count,
                        word_tolerance_ratio=effective_word_tolerance_ratio,
                    )
                    
                    beat_content = ""
                    async for piece in self.llm_service.stream_generate(
                        prompt,
                        self._config_for_target_words(beat_target_words, effective_word_tolerance_ratio),
                    ):
                        clipped_piece = _slice_piece_for_stream_limit(piece)
                        if clipped_piece:
                            chunk_count += 1
                            beat_content += clipped_piece
                            total_chars += len(clipped_piece)
                        if not clipped_piece:
                            if hit_stream_hard_limit:
                                logger.info(
                                    "stream hard limit reached (beats): limit=%s, emitted=%s",
                                    stream_unit_hard_limit,
                                    emitted_story_units,
                                )
                                break
                            continue
                        yield {
                            "type": "chunk", 
                            "text": clipped_piece,
                            "beat_index": i,
                            "beat_focus": beat.focus,
                            "stats": {
                                "chars": total_chars,
                                "chunks": chunk_count,
                                "estimated_tokens": int(total_chars / 1.5),
                            },
                        }
                        if hit_stream_hard_limit:
                            logger.info(
                                "stream hard limit reached (beats): limit=%s, emitted=%s",
                                stream_unit_hard_limit,
                                emitted_story_units,
                            )
                            break
                    
                    content_parts.append(beat_content)
                    yield {"type": "beat_done", "beat_index": i, "beat_content_length": len(beat_content)}
                    if hit_stream_hard_limit:
                        break
                
                content = strip_reasoning_artifacts("".join(content_parts))
            else:
                # 传统单段生成
                prompt = self._build_prompt(
                    context,
                    effective_outline,
                    storyline_context=bundle["storyline_context"],
                    plot_tension=bundle["plot_tension"],
                    style_summary=bundle["style_summary"],
                    voice_anchors=bundle.get("voice_anchors") or "",
                    style_overlay=style_overlay,
                    chapter_strategy=chapter_strategy,
                    next_chapter_bridge=next_chapter_bridge,
                    target_word_count=effective_target_word_count,
                    word_tolerance_ratio=effective_word_tolerance_ratio,
                )
                
                logger.info(f"  → 发送流式请求到 LLM")
                parts: list[str] = []
                total_chars = 0
                async for piece in self.llm_service.stream_generate(prompt, config):
                    clipped_piece = _slice_piece_for_stream_limit(piece)
                    if clipped_piece:
                        parts.append(clipped_piece)
                        chunk_count += 1
                        total_chars += len(clipped_piece)
                    if not clipped_piece:
                        if hit_stream_hard_limit:
                            logger.info(
                                "stream hard limit reached (single): limit=%s, emitted=%s",
                                stream_unit_hard_limit,
                                emitted_story_units,
                            )
                            break
                        continue
                    # 增强事件：包含累计字数和预估 token（中文约 1.5 字/token，英文约 4 字/token）
                    estimated_tokens = int(total_chars / 1.5)  # 简化估算
                    yield {
                        "type": "chunk", 
                        "text": clipped_piece,
                        "stats": {
                            "chars": total_chars,
                            "chunks": chunk_count,
                            "estimated_tokens": estimated_tokens,
                        }
                    }
                    if hit_stream_hard_limit:
                        logger.info(
                            "stream hard limit reached (single): limit=%s, emitted=%s",
                            stream_unit_hard_limit,
                            emitted_story_units,
                        )
                        break

                content = strip_reasoning_artifacts("".join(parts))
            logger.info(f"  ✓ LLM 流式响应完成: {chunk_count} 个块, {len(content)} 字符")

            if not content.strip():
                logger.error("  × 模型返回空内容")
                yield {"type": "error", "message": "模型返回空内容"}
                return

            content = await self._naturalize_ai_flavor_if_needed(
                content=content,
                outline=effective_outline,
                style_overlay=style_overlay,
            )
            content = await self._enforce_chapter_word_target(
                content=content,
                outline=effective_outline,
                target_word_count=effective_target_word_count,
                word_tolerance_ratio=effective_word_tolerance_ratio,
            )

            yield {"type": "phase", "phase": "post"}
            logger.info("阶段 4: post_process_generated_chapter")
            post = await self.post_process_generated_chapter(
                novel_id, chapter_number, effective_outline, content, scene_director=scene_director
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
                "long_draft_mode": long_draft_mode,
                "long_draft_split_count": split_count if long_draft_mode else None,
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

    async def _naturalize_ai_flavor_if_needed(
        self,
        *,
        content: str,
        outline: str,
        style_overlay: str = "",
    ) -> str:
        """对生成正文做一次自然化改写，避免只停留在事后告警。"""
        draft = (content or "").strip()
        if not draft or not self.cliche_scanner:
            return content

        try:
            initial_hits = self.cliche_scanner.scan_cliches(draft)
        except Exception as e:
            logger.warning("AI味预扫描失败，跳过自然化改写: %s", e)
            return content

        # 长正文即使未命中有限正则，也常会被检测器判定为“整齐、解释、模板化”。
        # 因此生产链路默认对长章节做一次编辑型自然化；短文本只在明确命中俗套时处理。
        should_naturalize = bool(initial_hits) or len(draft) >= 500
        if not should_naturalize:
            return content

        rewrite_prompt = self._build_ai_flavor_rewrite_prompt(draft=draft, outline=outline)
        max_tokens = max(1024, min(12000, int(len(draft) * 1.4)))
        try:
            result = await self.llm_service.generate(
                rewrite_prompt,
                GenerationConfig(max_tokens=max_tokens, temperature=0.9),
            )
            revised = strip_reasoning_artifacts(result.content or "").strip()
        except Exception as e:
            logger.warning("AI味自然化改写失败，保留原文: %s", e)
            return content

        if not revised:
            return content
        if len(revised) < max(80, len(draft) * 0.45):
            logger.warning("AI味自然化改写疑似过度压缩，保留原文")
            return content
        revised = await self._apply_human_texture_pass_if_needed(
            content=revised,
            outline=outline,
        )
        revised = await self._apply_human_residue_pass_if_needed(
            content=revised,
            outline=outline,
        )
        revised = await self._apply_structural_audit_pass_if_needed(
            content=revised,
            outline=outline,
        )
        revised = await self._apply_style_bible_pass_if_needed(
            content=revised,
            outline=outline,
            style_overlay=style_overlay,
        )
        revised = await self._apply_forbidden_pattern_gate_if_needed(
            content=revised,
            outline=outline,
            style_overlay=style_overlay,
        )
        return self._soft_cap_detector_motifs(revised)

    async def _apply_structural_audit_pass_if_needed(self, *, content: str, outline: str) -> str:
        """把“设定说明连发”改成证据动作链，避免自然化后仍像提纲解释。"""
        draft = (content or "").strip()
        if not draft or not self._needs_structural_audit_pass(draft):
            return content

        logger.info("  → 触发结构审稿清理：削弱说明流/共识流/概念连发")
        prompt = self._build_structural_audit_prompt(draft=draft, outline=outline)
        max_tokens = max(1024, min(12000, int(len(draft) * 1.2)))
        try:
            result = await self.llm_service.generate(
                prompt,
                GenerationConfig(max_tokens=max_tokens, temperature=0.82),
            )
            candidate = strip_reasoning_artifacts(result.content or "").strip()
        except Exception as e:
            logger.warning("结构审稿清理失败，保留当前正文: %s", e)
            return content

        if not candidate:
            return content
        if len(candidate) < max(80, len(draft) * 0.5):
            logger.warning("结构审稿清理疑似过度压缩，保留当前正文")
            return content
        if (
            self._needs_structural_audit_pass(candidate)
            and self._structural_audit_score(candidate) >= self._structural_audit_score(draft)
        ):
            logger.warning("结构审稿清理未降低说明流风险，保留当前正文")
            return content
        if self._human_texture_risk_score(candidate) > max(2, self._human_texture_risk_score(draft) + 2):
            logger.warning("结构审稿清理引入句法风险，保留当前正文")
            return content
        return candidate

    async def _apply_style_bible_pass_if_needed(self, *, content: str, outline: str, style_overlay: str) -> str:
        """章后将低 AI 味改写稿再贴合选中的写作手法档案。"""
        overlay = (style_overlay or "").strip()
        draft = (content or "").strip()
        if not overlay or not draft:
            return content

        try:
            prompt = self._build_style_bible_rewrite_prompt(
                draft=draft,
                outline=outline,
                style_overlay=overlay,
            )
        except Exception as e:
            logger.warning("Style Bible 章后贴合提示词不可用，保留当前正文: %s", e)
            return content

        max_tokens = max(1024, min(12000, int(len(draft) * 1.2)))
        try:
            result = await self.llm_service.generate(
                prompt,
                GenerationConfig(max_tokens=max_tokens, temperature=0.78),
            )
            candidate = strip_reasoning_artifacts(result.content or "").strip()
        except Exception as e:
            logger.warning("Style Bible 章后贴合失败，保留当前正文: %s", e)
            return content

        if not candidate:
            return content
        if len(candidate) < max(80, len(draft) * 0.55):
            logger.warning("Style Bible 章后贴合疑似过度压缩，保留当前正文")
            return content
        if self._human_texture_risk_score(candidate) > max(2, self._human_texture_risk_score(draft) + 2):
            logger.warning("Style Bible 章后贴合引入句法风险，保留当前正文")
            return content
        return candidate

    async def _apply_human_texture_pass_if_needed(self, *, content: str, outline: str) -> str:
        """对外部检测器常判为 AI 的“过度工整精修稿”做一次节奏破整。"""
        draft = (content or "").strip()
        if not draft or not self._needs_human_texture_pass(draft):
            return content

        logger.info("  → 触发人工纹理破整：降低过度工整/对称句式风险")
        prompt = self._build_human_texture_rewrite_prompt(draft=draft, outline=outline)
        max_tokens = max(1024, min(12000, int(len(draft) * 1.25)))
        try:
            result = await self.llm_service.generate(
                prompt,
                GenerationConfig(max_tokens=max_tokens, temperature=0.95),
            )
            textured = strip_reasoning_artifacts(result.content or "").strip()
        except Exception as e:
            logger.warning("人工纹理破整改写失败，保留自然化正文: %s", e)
            return content

        if not textured:
            return content
        if len(textured) < max(80, len(draft) * 0.45):
            logger.warning("人工纹理破整疑似过度压缩，保留自然化正文")
            return content
        if self._is_detector_signature_improved(textured, draft) and not self._needs_human_texture_pass(textured):
            return textured

        best = textured if self._is_detector_signature_improved(textured, draft) else draft
        if best is textured:
            logger.warning("人工纹理破整已降低但仍高风险，继续严格清理检测器敏感句法")
        else:
            logger.warning("人工纹理破整未降低检测风险，尝试严格清理检测器敏感句法")
        strict_textured = await self._apply_strict_detector_signature_pass(draft=best, outline=outline)
        if self._is_detector_signature_improved(strict_textured, best, strict=True):
            return strict_textured

        if best is textured:
            logger.warning("严格句法清理仍未达标，保留首轮改善稿")
            return textured

        logger.warning("严格句法清理仍未达标，保留自然化正文")
        return content

    async def _apply_direct_light_polish_if_needed(self, *, content: str, outline: str) -> str:
        """直接写作后的轻修：只小幅局部编辑，不进入 PP 全套后处理。"""
        draft = (content or "").strip()
        if len(draft) < 500:
            return content

        prompt = self._build_direct_light_polish_prompt(draft=draft, outline=outline)
        max_tokens = max(2048, min(12000, int(len(draft) * 1.12)))
        try:
            result = await self.llm_service.generate(
                prompt,
                GenerationConfig(max_tokens=max_tokens, temperature=0.76),
            )
            candidate = strip_reasoning_artifacts(result.content or "").strip()
        except Exception as e:
            logger.warning("直接写作轻修失败，保留直接稿: %s", e)
            return content

        if not candidate:
            return content
        if len(candidate) < max(120, len(draft) * 0.75):
            logger.warning("直接写作轻修疑似过度压缩，保留直接稿")
            return content
        if self._human_texture_risk_score(candidate) > self._human_texture_risk_score(draft) + 2:
            logger.warning("直接写作轻修引入句法风险，保留直接稿")
            return content
        if self._human_residue_score(candidate) + 2 < self._human_residue_score(draft):
            logger.warning("直接写作轻修抹平人工余量，保留直接稿")
            return content
        return candidate

    async def _apply_human_residue_pass_if_needed(self, *, content: str, outline: str) -> str:
        """降低过度统一的母题词复现，给文本留出更像人工取舍的余量。"""
        draft = (content or "").strip()
        terms = self._detector_repetition_terms(draft)
        if not draft or not terms:
            return content

        logger.info("  → 触发人工余量降噪：降低母题词过密复现 %s", "/".join(terms[:8]))
        prompt = self._build_human_residue_prompt(draft=draft, outline=outline, terms=terms)
        max_tokens = max(1024, min(12000, int(len(draft) * 1.2)))
        try:
            result = await self.llm_service.generate(
                prompt,
                GenerationConfig(max_tokens=max_tokens, temperature=0.88),
            )
            candidate = strip_reasoning_artifacts(result.content or "").strip()
        except Exception as e:
            logger.warning("人工余量降噪失败，保留当前正文: %s", e)
            return content

        if not candidate:
            return content
        if len(candidate) < max(80, len(draft) * 0.55):
            logger.warning("人工余量降噪疑似过度压缩，保留当前正文")
            return content
        if not self._is_motif_repetition_improved(candidate, draft, terms):
            logger.warning("人工余量降噪未降低母题重复，保留当前正文")
            return content
        if self._needs_human_residue_pass(candidate):
            logger.warning("人工余量降噪已降低但仍高频，继续严格压低母题词")
            strict_candidate = await self._apply_strict_motif_cap_pass(
                draft=candidate,
                outline=outline,
            )
            if strict_candidate and self._is_motif_repetition_improved(
                strict_candidate,
                candidate,
                self._detector_repetition_terms(candidate),
            ):
                candidate = strict_candidate
        if self._human_texture_risk_score(candidate) > max(2, self._human_texture_risk_score(draft) + 2):
            logger.warning("人工余量降噪引入句法风险，保留当前正文")
            return content
        return candidate

    async def _apply_strict_motif_cap_pass(self, *, draft: str, outline: str) -> str:
        terms = self._detector_repetition_terms(draft)
        if not terms:
            return draft
        prompt = self._build_strict_motif_cap_prompt(draft=draft, outline=outline, terms=terms)
        max_tokens = max(1024, min(12000, int(len(draft) * 1.2)))
        try:
            result = await self.llm_service.generate(
                prompt,
                GenerationConfig(max_tokens=max_tokens, temperature=0.78),
            )
            candidate = strip_reasoning_artifacts(result.content or "").strip()
        except Exception as e:
            logger.warning("严格母题压词失败，保留当前正文: %s", e)
            return draft
        if len(candidate) < max(80, len(draft) * 0.55):
            logger.warning("严格母题压词疑似过度压缩，保留当前正文")
            return draft
        return candidate

    async def _apply_strict_detector_signature_pass(self, *, draft: str, outline: str) -> str:
        prompt = self._build_strict_detector_signature_prompt(draft=draft, outline=outline)
        max_tokens = max(1024, min(12000, int(len(draft) * 1.25)))
        try:
            result = await self.llm_service.generate(
                prompt,
                GenerationConfig(max_tokens=max_tokens, temperature=0.82),
            )
            return strip_reasoning_artifacts(result.content or "").strip()
        except Exception as e:
            logger.warning("严格句法清理失败，保留自然化正文: %s", e)
            return draft

    @staticmethod
    def _needs_human_texture_pass(text: str) -> bool:
        """识别外部 AI 检测常抓的过度对称、过度精修行文。"""
        return AutoNovelGenerationWorkflow._human_texture_risk_score(text) >= 5

    @staticmethod
    def _needs_human_residue_pass(text: str) -> bool:
        return bool(AutoNovelGenerationWorkflow._detector_repetition_terms(text))

    @staticmethod
    def _needs_structural_audit_pass(text: str) -> bool:
        return AutoNovelGenerationWorkflow._structural_audit_score(text) >= 10

    @staticmethod
    def _structural_audit_score(text: str) -> int:
        """识别“解释/说明/讲完就达成共识”的结构型 AI 味。"""
        if len(text or "") < 500:
            return 0
        paragraphs = [p.strip() for p in text.splitlines() if p.strip()]
        score = 0
        explain_terms = ("解释", "说明", "讲述", "补充", "机制", "规则", "背景", "原理")
        score += min(sum(text.count(term) for term in explain_terms), 6)
        score += min(text.count("很快达成共识") * 2, 4)
        score += min(text.count("明白了") + text.count("听完后"), 4)
        score += min(len(re.findall(r"(?:于是|随后|接着).{0,18}(?:解释|说明|补充|讲述)", text)), 4)
        if len(paragraphs) >= 8:
            dialogue_like = sum(1 for p in paragraphs if "“" in p or '"' in p)
            if dialogue_like / len(paragraphs) < 0.12:
                score += 2
        return score

    @staticmethod
    def _detector_repetition_terms(text: str) -> List[str]:
        """检测外部 AI 检测器常抓的高密度母题词复现。"""
        if len(text or "") < 500:
            return []

        watch_terms = (
            "呼吸", "虹彩", "拓片", "节点", "坐标", "频率", "节律", "调谐",
            "孔洞", "灰白", "甜腻", "结晶", "脐带", "肺泡", "肺叶",
            "十七", "十九", "每分钟", "同步", "共振",
            "像", "雨", "水", "冷", "潮", "湿", "铁锈味",
        )
        counts = {term: text.count(term) for term in watch_terms}
        counts.update(AutoNovelGenerationWorkflow._dynamic_motif_counts(text))
        threshold = 8 if len(text) < 3500 else 10
        generic_terms = {"像", "雨", "水", "冷", "潮", "湿", "铁锈味"}
        generic_chars = set("雨水冷潮湿")
        generic_threshold = 24 if len(text) < 3500 else 28
        dynamic_threshold = 14 if len(text) < 3500 else 18

        def threshold_for(term: str) -> int:
            if term in generic_terms or any(ch in generic_chars for ch in term):
                return generic_threshold
            if term not in watch_terms:
                return dynamic_threshold
            return threshold

        terms = [
            term for term, count in counts.items()
            if count >= threshold_for(term)
        ]
        if len(terms) >= 3:
            return sorted(terms, key=lambda item: counts[item], reverse=True)
        if any(count >= threshold_for(term) * 2 for term, count in counts.items()):
            return sorted(terms, key=lambda item: counts[item], reverse=True)
        if any(term == "像" and count >= generic_threshold for term, count in counts.items()):
            return sorted(terms, key=lambda item: counts[item], reverse=True)
        return []

    @staticmethod
    def _dynamic_motif_counts(text: str) -> Dict[str, int]:
        """从正文中动态抽取疑似题材意象词，避免每个题材都手写词表。"""
        if len(text or "") < 500:
            return {}

        marker_chars = set(
            "雨水冷潮湿雾霜雪风火光影灯血骨肉皮纸票门锁屏电机车"
            "剑刀枪刃甲丹田经脉灵气威压符阵石壁墙镜"
        )
        stop_chars = set("的一是在了和也就都而及与把被让给对上下中里个这那他她它我你们来去着过没又还只很更最")
        stop_terms = {
            "他们", "她们", "这个", "那个", "什么", "不是", "没有", "已经",
            "一下", "一点", "一声", "一样", "时候", "里面", "外面",
        }
        counts: Dict[str, int] = {}
        for segment in re.findall(r"[\u4e00-\u9fff]{2,}", text):
            for size in (2, 3):
                if len(segment) < size:
                    continue
                for index in range(0, len(segment) - size + 1):
                    term = segment[index:index + size]
                    if term in stop_terms:
                        continue
                    if any(ch in stop_chars for ch in term):
                        continue
                    if not any(ch in marker_chars for ch in term):
                        continue
                    counts[term] = counts.get(term, 0) + 1
        return counts

    @staticmethod
    def _is_motif_repetition_improved(candidate: str, baseline: str, terms: List[str]) -> bool:
        if not candidate.strip() or not baseline.strip() or not terms:
            return False
        baseline_score = sum(baseline.count(term) for term in terms)
        candidate_score = sum(candidate.count(term) for term in terms)
        return candidate_score < baseline_score

    @staticmethod
    def _soft_cap_detector_motifs(text: str) -> str:
        """保留旧入口，但不再做机械字符串替换。

        之前的收尾替换会把数字和母题词拼成“三旧值”“上一组读数”等怪异表达；
        母题降噪改由 LLM 编辑型 pass 完成，避免破坏小说正文。
        """
        return text

    @staticmethod
    def _is_detector_signature_improved(candidate: str, baseline: str, *, strict: bool = False) -> bool:
        candidate = (candidate or "").strip()
        baseline = (baseline or "").strip()
        if not candidate:
            return False
        if len(candidate) < max(80, len(baseline) * 0.45):
            return False

        candidate_score = AutoNovelGenerationWorkflow._human_texture_risk_score(candidate)
        baseline_score = AutoNovelGenerationWorkflow._human_texture_risk_score(baseline)
        if candidate_score >= baseline_score:
            return False
        if candidate.count("不是") > baseline.count("不是"):
            return False

        if strict:
            max_not = max(4, baseline.count("不是") // 3)
            max_like_some = max(1, baseline.count("像某种") // 3)
            max_some = max(4, baseline.count("某种") // 2)
            if candidate.count("不是") > max_not:
                return False
            if candidate.count("像某种") > max_like_some:
                return False
            if candidate.count("某种") > max_some:
                return False

        return True

    @staticmethod
    def _human_texture_risk_score(text: str) -> int:
        """给二次改写前后做同一把尺子的轻量风险评分。"""
        if len(text) < 500:
            return 0

        score = 0
        score += min(len(re.findall(r"不是[^。！？\n]{1,28}[，,]是", text)), 4)
        score += min(text.count("像某种"), 4)
        score += min(text.count("像") // 12, 5)
        score += min(text.count("某种") // 4, 3)
        score += min(len(re.findall(r"没有[^。！？\n]{1,24}[，,]?(?:只是|而是)", text)), 2)
        score += min(len(re.findall(r"不是[^。！？\n]{1,24}(?:而是|而是在)", text)), 2)
        score += min(text.count("不是") // 4, 5)
        score += min(len(re.findall(r"(?:^|\n)\s*不是", text)), 4)

        paragraphs = [p.strip() for p in text.splitlines() if p.strip()]
        if len(paragraphs) >= 18:
            short_ratio = sum(1 for p in paragraphs if len(p) <= 18) / len(paragraphs)
            if short_ratio >= 0.45:
                score += 2
            elif short_ratio >= 0.35:
                score += 1
            if short_ratio >= 0.28:
                score += 1
            starts = [p[:2] for p in paragraphs if len(p) >= 2]
            if starts:
                most_common_start = max(starts.count(s) for s in set(starts))
                if most_common_start / len(starts) >= 0.16:
                    score += 1

        return score

    @staticmethod
    def _human_residue_score(text: str) -> int:
        """轻量估算正文是否还保留了人工草稿的局部余量。"""
        if len(text or "") < 500:
            return 0

        paragraphs = [p.strip() for p in text.splitlines() if p.strip()]
        score = 0
        score += min(len(re.findall(r"[“”\"']", text)) // 2, 6)
        score += min(len(re.findall(r"[？?!！]", text)), 5)
        score += min(len(re.findall(r"(?:顿了顿|停了|没接|没问|没说|咽回去|伸手|缩回|低头|抬眼|偏头)", text)), 8)
        score += min(len(re.findall(r"(?:半寸|半秒|两步|三步|指节|袖口|杯沿|门缝|纸角|鞋底|抽屉|钥匙|票据|录音笔|证物袋)", text)), 8)
        if len(paragraphs) >= 12:
            lengths = [len(p) for p in paragraphs]
            short = sum(1 for length in lengths if length <= 24)
            long = sum(1 for length in lengths if length >= 90)
            if short and long:
                score += 2
            unique_starts = len({p[:2] for p in paragraphs if len(p) >= 2})
            if unique_starts / len(paragraphs) >= 0.75:
                score += 2
        return score

    @staticmethod
    def _build_human_texture_rewrite_prompt(*, draft: str, outline: str) -> Prompt:
        target_not_count = min(4, max(1, draft.count("不是") // 2))
        variables = {
            "draft": draft,
            "rhythm_goal": (
                "保留剧情事实和本章大纲，重点削弱过度工整、过度对称、过度镜头化的AI式精修感；"
                "减少连续的“不是X，是Y”“像某种”结构，让段落更像人工作者现场取舍后的表达；"
                f"全文“不是”不超过{target_not_count}次，“像某种”尽量为0，“某种”不超过4次；"
                "普通“像……”比喻不超过每千字3处，重复场景词不要压成同一组雨/水/冷意象；"
                "优先改成直接动作、物证变化、短对白或角色误判，不要新增新的排比式否定句。"
            ),
        }
        try:
            from infrastructure.ai.prompt_manager import get_prompt_manager

            manager = get_prompt_manager()
            manager.ensure_seeded()
            rendered = manager.render("rewrite-prose-irregularity", variables)
            if rendered and (rendered.get("system") or "").strip() and (rendered.get("user") or "").strip():
                return Prompt(
                    system=rendered["system"].strip(),
                    user=rendered["user"].strip(),
                )
        except Exception as e:
            logger.warning("句式节奏破整提示词节点不可用，回退内置提示词: %s", e)

        return Prompt(
            system=(
                "你是中文小说行文节奏编辑。请保留原剧情事实、人物、时间线和伏笔，"
                "只削弱过度工整、过度对称、过度解释的AI式精修感。减少连续的固定句式，"
                "让句长、停顿、段落和细节取舍更像人工作者写作。只输出改写后的正文。"
            ),
            user=(
                f"【本章大纲】\n{outline.strip()}\n\n"
                "【需要破整的正文】\n"
                f"{draft}\n\n"
                "请只输出调整后的小说正文："
            ),
        )

    @staticmethod
    def _build_strict_detector_signature_prompt(*, draft: str, outline: str) -> Prompt:
        target_not_count = min(4, max(1, draft.count("不是") // 3))
        return Prompt(
            system=(
                "你是中文小说检测器指纹清理编辑。只做表达层改写，不能改剧情、人物、道具、地点、"
                "时间线、伏笔和结尾钩子。目标是删除外部AI检测器常抓的重复句法。只输出正文。"
            ),
            user=(
                f"【本章大纲】\n{outline.strip()}\n\n"
                "【硬性指标】\n"
                f"- 全文“不是”不超过 {target_not_count} 次。\n"
                "- “像某种”尽量为 0 次。\n"
                "- “某种”不超过 4 次。\n"
                "- 普通“像……”比喻不超过每千字 3 处；删掉可有可无的比喻，改成直接动作或物理后果。\n"
                "- 同一场景母题词不要过密复现；雨、水、冷、铁锈味、潮湿等词重复过多时，改成光线、脚步、设备、纸张、手部动作或对白反应。\n"
                "- 不用“不是X，是Y”做连续纠偏；改成直接描写、动作后果、对白停顿或角色误判。\n"
                "- 保留原文已出现的关键名词、线索、坐标、道具和因果顺序。\n"
                "- 不要写修改说明。\n\n"
                "【待清理正文】\n"
                f"{draft}\n\n"
                "请输出清理后的小说正文："
            ),
        )

    @staticmethod
    def _build_human_residue_prompt(*, draft: str, outline: str, terms: List[str]) -> Prompt:
        term_text = "、".join(terms[:10])
        return Prompt(
            system=(
                "你是中文小说人工余量编辑。你的目标不是把文本改粗糙，而是削弱模型文常见的"
                "单一母题过密、意象过度统一、每段都精准服务悬念的机器感。只输出正文。"
            ),
            user=(
                f"【本章大纲】\n{outline.strip()}\n\n"
                f"【需要降噪的高频母题词】\n{term_text}\n\n"
                "【改写要求】\n"
                "- 保留剧情事实、人物关系、关键道具、坐标、危机和结尾钩子。\n"
                "- 不要把高频词全部删除；把一部分重复名词改成动作后果、场景物、人物误判或短对白。\n"
                "- 如果高频词是“像、雨、水、冷、潮、湿、铁锈味”等通用词，优先删掉可有可无的比喻和重复氛围句；保留必要物证信息。\n"
                "- 加入少量合理的现场摩擦：脚滑、光线失真、衣料湿冷、设备误报、门锁卡顿、旁人一句不合时宜的话。\n"
                "- 允许信息释放不那么整齐：有些细节先被误读，有些句子停在动作上，不每段都收成同一组意象。\n"
                "- 不新增核心设定，不解释修改过程。\n\n"
                "【原文】\n"
                f"{draft}\n\n"
                "请输出降噪后的小说正文："
            ),
        )

    @staticmethod
    def _build_structural_audit_prompt(*, draft: str, outline: str) -> Prompt:
        return Prompt(
            system=(
                "你是中文商业小说结构审稿编辑。只做删改和重排，不改变剧情事实、人物、道具、地点、"
                "时间线、伏笔和结尾钩子。目标是把说明流、设定解释流、很快达成共识的摘要流，"
                "改成读者能跟着看的行动链、证据链和对白试探。只输出正文。"
            ),
            user=(
                f"【本章大纲】\n{outline.strip()}\n\n"
                "【结构删改要求】\n"
                "- 删掉或打散连续解释、背景讲述、规则说明，把必要信息落到角色接触证据、试错、误判和短对白里。\n"
                "- 每 800 字内至少出现一次能改变判断的动作或物证变化。\n"
                "- 不用“一番交谈后 / 很快达成共识 / 听完后明白了”跳过过程。\n"
                "- 对话不要负责完整解释，只负责试探、核对、遮掩、反问或露出破绽。\n"
                "- 保留原文关键信息，但允许换出现顺序，让信息更像现场逐步被发现。\n"
                "- 不输出审稿说明。\n\n"
                "【待删改正文】\n"
                f"{draft}\n\n"
                "请输出结构删改后的小说正文："
            ),
        )

    @staticmethod
    def _build_style_bible_rewrite_prompt(*, draft: str, outline: str, style_overlay: str) -> Prompt:
        variables = {
            "style_overlay": style_overlay,
            "must_keep": f"本章大纲：{outline.strip()}；保留剧情事实、关键线索、道具状态和结尾钩子。",
            "draft": draft,
        }
        from infrastructure.ai.prompt_manager import get_prompt_manager

        manager = get_prompt_manager()
        manager.ensure_seeded()
        rendered = manager.render("style-bible-imitation-pass", variables)
        if rendered and (rendered.get("system") or "").strip() and (rendered.get("user") or "").strip():
            return Prompt(
                system=rendered["system"].strip(),
                user=rendered["user"].strip(),
            )
        return Prompt(
            system=(
                "你是中文小说文风贴合编辑。学习风格约束中的节奏、细节选择、句式倾向和叙述距离，"
                "但不能复刻样本文字。保留剧情事实和关键线索，只输出改写后的正文。"
            ),
            user=(
                f"【风格约束】\n{style_overlay.strip()}\n\n"
                f"【必须保留】\n{variables['must_keep']}\n\n"
                f"【原文】\n{draft}\n\n"
                "请按风格约束轻度贴合，只输出正文："
            ),
        )

    @staticmethod
    def _build_strict_motif_cap_prompt(*, draft: str, outline: str, terms: List[str]) -> Prompt:
        caps = []
        for term in terms[:10]:
            current = draft.count(term)
            target = min(7, max(2, current // 3))
            caps.append(f"- “{term}”：当前 {current} 次，改后不超过 {target} 次")
        return Prompt(
            system=(
                "你是中文小说重复母题压词编辑。你的任务是保留剧情事实，但显著减少同一批关键词的"
                "机械复现，让文本像人工写作时会自然换说法、略过、误读和留白。只输出正文。"
            ),
            user=(
                f"【本章大纲】\n{outline.strip()}\n\n"
                "【硬性词频上限】\n"
                + "\n".join(caps)
                + "\n\n【替换方式】\n"
                "- 第一次出现可保留关键词，后续尽量改成代词、动作、声音、设备读数、角色反应或干脆省略。\n"
                "- 数字和坐标只在关键处出现；重复处改成角色动作、核对过程或具体载体，不要用“那个数”“旧值”等生硬占位。\n"
                "- 生理/异常名词不要每段重复，改成现场后果：地面变滑、灯闪、门锁卡住、衣领发潮、设备误报。\n"
                "- 加入少量生活摩擦，但不要新增核心人物、核心设定或改变结尾危机。\n"
                "- 不要输出修改说明。\n\n"
                "【原文】\n"
                f"{draft}\n\n"
                "请输出压词后的小说正文："
            ),
        )

    @staticmethod
    def _build_ai_flavor_rewrite_prompt(*, draft: str, outline: str) -> Prompt:
        variables = {
            "draft": draft,
            "must_keep": f"本章大纲：{outline.strip()}",
            "rewrite_goal": "降低AI味，保留剧情事实，增强阅读沉浸",
            "taboo_phrases": (
                "空气凝固、时间静止、心中五味杂陈、某种说不清的东西、"
                "命运齿轮、一切才刚刚开始、再也回不去了、一番交谈后、很快达成共识、"
                "不是X，是Y、像某种、连续排比式否定句；全文“不是”不超过4次，"
                "“像某种”尽量为0，“某种”不超过4次"
            ),
        }
        try:
            from infrastructure.ai.prompt_manager import get_prompt_manager

            manager = get_prompt_manager()
            manager.ensure_seeded()
            rendered = manager.render("rewrite-ai-flavor-naturalizer", variables)
            if rendered and (rendered.get("system") or "").strip() and (rendered.get("user") or "").strip():
                return Prompt(
                    system=rendered["system"].strip(),
                    user=rendered["user"].strip(),
                )
        except Exception as e:
            logger.warning("AI味改写提示词节点不可用，回退内置提示词: %s", e)

        system = (
            "你是中文商业小说自然化改稿编辑。目标是降低AI味，保留原剧情事实、人物、地点、"
            "因果顺序、伏笔和关键信息，不新增剧情，不解释修改过程。\n\n"
            "硬要求：\n"
            "1. 删除抽象情绪说明、模板总结、万能比喻和说明文腔。\n"
            "2. 把情绪落到动作、物件、声音、停顿、视线和身体反应。\n"
            "3. 对话更像真人：允许半句、回避、反问、误解和沉默，不要人人把动机说透。\n"
            "4. 保留章节长度与节奏，不能压缩成摘要。\n"
            "5. 首选上一轮效果较好的路线：调查动作清楚、物证逐步出现、对白试探、临场判断；"
            "不要刻意粗糙化，不制造错别字或奇怪口癖。\n"
            "6. 少用“不是X，是Y”结构，禁止连续排比式否定。\n"
            "7. 只输出改写后的小说正文。"
        )
        user = (
            f"【本章大纲】\n{outline.strip()}\n\n"
            "【需要自然化改写的正文】\n"
            f"{draft}\n\n"
            "请在不改变剧情事实的前提下降低AI味，只输出正文："
        )
        return Prompt(system=system, user=user)

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
        chapter_draft_so_far: str = "",
        style_overlay: str = "",
        chapter_strategy: Optional[Dict[str, Any]] = None,
        next_chapter_bridge: str = "",
        target_word_count: Optional[int] = None,
        word_tolerance_ratio: Optional[float] = None,
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
            style_overlay=style_overlay,
            chapter_strategy=chapter_strategy,
            next_chapter_bridge=next_chapter_bridge,
            target_word_count=target_word_count,
            word_tolerance_ratio=word_tolerance_ratio,
        )

    def _build_style_overlay(
        self,
        novel_id: str,
        style_profile_id: str,
        scene_type: str = "",
    ) -> str:
        if not self.style_prompt_overlay_service or not (style_profile_id or "").strip():
            return ""
        try:
            overlay = self.style_prompt_overlay_service.build_overlay(
                novel_id,
                style_profile_id,
                scene_type=scene_type,
            )
            return overlay.prompt
        except Exception as e:
            logger.warning("style bible overlay unavailable: %s", e)
            return ""

    @staticmethod
    def _extract_forbidden_patterns_from_style_overlay(style_overlay: str) -> List[str]:
        text = str(style_overlay or "").strip()
        if not text:
            return []
        lines = [line.strip() for line in text.splitlines()]
        in_forbidden = False
        patterns: list[str] = []
        for line in lines:
            if line.startswith("禁用项："):
                in_forbidden = True
                continue
            if in_forbidden and line.endswith("：") and not line.startswith("-"):
                break
            if in_forbidden and line.startswith("-"):
                item = line[1:].strip()
                if item and item not in patterns:
                    patterns.append(item)
        return patterns[:10]

    async def _apply_forbidden_pattern_gate_if_needed(
        self,
        *,
        content: str,
        outline: str,
        style_overlay: str,
    ) -> str:
        if not self._is_style_anchor_rag_enabled():
            return content
        draft = (content or "").strip()
        if not draft:
            return content
        patterns = self._extract_forbidden_patterns_from_style_overlay(style_overlay)
        if not patterns:
            return content
        hit_patterns = [p for p in patterns if p and p in draft]
        if not hit_patterns:
            return content

        prompt = Prompt(
            system=(
                "你是中文小说修文编辑。你只能做局部改写：替换命中禁忌模板句，保持事实、剧情和人物关系不变。"
                "只输出修订后的完整正文，不要解释。"
            ),
            user=(
                "请按以下要求修订正文：\n"
                "1) 只处理命中禁忌项的句子，不要全篇重写；\n"
                "2) 保留剧情事件顺序、人物立场与道具状态；\n"
                "3) 用动作、对白、停顿替代模板化总结句；\n"
                "4) 禁止使用下列表达：\n"
                + "\n".join(f"- {item}" for item in hit_patterns)
                + "\n\n"
                f"【本章大纲】\n{outline}\n\n"
                f"【正文】\n{draft}\n\n"
                "输出修订后的正文："
            ),
        )
        max_tokens = max(1200, min(12000, int(len(draft) * 1.25)))
        try:
            result = await self.llm_service.generate(
                prompt,
                GenerationConfig(max_tokens=max_tokens, temperature=0.76),
            )
            revised = strip_reasoning_artifacts((result.content or "").strip())
        except Exception as e:
            logger.warning("forbidden pattern gate failed: %s", e)
            return content

        if not revised:
            return content
        if len(revised) < max(80, int(len(draft) * 0.55)):
            logger.warning("forbidden pattern gate over-compressed, keep draft")
            return content
        return revised

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
        style_overlay: str = "",
        chapter_strategy: Optional[Dict[str, Any]] = None,
        next_chapter_bridge: str = "",
        target_word_count: Optional[int] = None,
        word_tolerance_ratio: Optional[float] = None,
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
            chapter_draft_so_far: 同章内当前节拍之前已生成的正文（拼接后传入，避免后续节拍重复）
            style_overlay: 写作手法知识库提示词片段

        Returns:
            Prompt 对象
        """
        sc = (storyline_context or "").strip()
        pt = (plot_tension or "").strip()
        ss = (style_summary or "").strip()
        va = (voice_anchors or "").strip()
        so = (style_overlay or "").strip()
        prop_overlay = self._build_prop_ledger_overlay()
        coc_overlay = self._build_coc_canon_overlay()
        coc_clue_overlay = self._build_coc_clue_overlay()
        coc_cognition_overlay = self._build_coc_cognition_overlay()
        planning_parts: list[str] = []
        if sc and sc not in ("Storyline context unavailable",):
            planning_parts.append(f"【故事线 / 里程碑】\n{sc}")
        if pt and pt not in ("Plot tension unavailable",):
            planning_parts.append(f"【情节节奏 / 期望张力】\n{pt}")
        if ss:
            planning_parts.append(f"【风格约束】\n{ss}")
        if so:
            planning_parts.append(so)
        if prop_overlay:
            planning_parts.append(prop_overlay)
        if coc_overlay:
            planning_parts.append(coc_overlay)
        if coc_clue_overlay:
            planning_parts.append(coc_clue_overlay)
        if coc_cognition_overlay:
            planning_parts.append(coc_cognition_overlay)
        strategy_overlay = self._build_strategy_overlay(chapter_strategy)
        if strategy_overlay:
            planning_parts.append(strategy_overlay)
        if (next_chapter_bridge or "").strip():
            planning_parts.append(next_chapter_bridge.strip())
        chapter_contract = self._build_chapter_contract_overlay(context=context, outline=outline)
        if chapter_contract:
            planning_parts.append(chapter_contract)
        detector_calibration = self._build_detector_calibration_overlay(context=context, outline=outline)
        if detector_calibration:
            planning_parts.append(detector_calibration)
        genre_overlay = self._build_genre_overlay(context=context, outline=outline)
        if genre_overlay:
            planning_parts.append(genre_overlay)
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
        target_range = self._target_word_range(target_word_count, word_tolerance_ratio)
        if beat_target_words:
            beat_range = self._target_word_range(beat_target_words, word_tolerance_ratio)
            if beat_range:
                min_words, max_words = beat_range
                length_rule = (
                    f"7. 【硬性字数】本段目标 {beat_target_words} 字，允许 {min_words}-{max_words} 字；"
                    "接近上限时立即收束，不要为了补气氛继续扩写。"
                )
            else:
                length_rule = f"7. 【硬性字数上限】本段最多 {beat_target_words} 字，超出将被截断，请精炼叙述。"
        elif target_range:
            min_words, max_words = target_range
            target = self._effective_word_target(target_word_count)
            length_rule = (
                f"7. 【硬性字数】本章目标 {target} 字，允许 {min_words}-{max_words} 字；"
                "少于下限时补关键冲突和人物互动，接近上限时收束，不要继续铺陈。"
            )
        else:
            default_target = self._effective_word_target(target_word_count)
            min_words, max_words = self._target_word_range(default_target, word_tolerance_ratio)
            length_rule = (
                f"7. 【硬性字数】本章目标 {default_target} 字，允许 {min_words}-{max_words} 字；"
                if not beat_mode
                else "7. 按下方节拍说明控制篇幅，勿写章节标题"
            )
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

        prior_draft_block = ""
        if beat_mode and prior_in_chapter:
            prior_draft_block = f"""

【本章已生成正文（仅承接；禁止复述、改写或重复已交代的情节与对白；勿写章节标题）】
{prior_in_chapter}
"""

        beat_section = ""
        if beat_mode:
            bi = beat_index if beat_index is not None else 0
            tb = total_beats if total_beats is not None else 1
            beat_tail = (
                "本段只写该节拍对应正文，紧接上文已写正文之后继续，衔接自然。"
                if prior_in_chapter
                else "本段只写该节拍对应正文，与全章其它节拍情节连贯。"
            )
            beat_section = f"""

【节拍 {bi + 1}/{tb}】
{(beat_prompt or '').strip()}

{beat_tail}"""

        render_variables = {
            "planning_section": planning_section,
            "voice_block": voice_block,
            "context": context,
            "fact_lock": fact_lock,
            "length_rule": length_rule,
            "beat_extra": beat_extra,
            "outline": outline,
            "prior_draft": prior_draft_block,
            "beat_section": beat_section,
            "style_overlay": so,
            "next_chapter_bridge": next_chapter_bridge,
            "genre_overlay": genre_overlay,
            "chapter_contract": chapter_contract,
            "detector_calibration": detector_calibration,
        }

        visible_prompt = self._render_visible_workflow_prompt(render_variables)
        if visible_prompt:
            return Prompt(
                system=visible_prompt["system"],
                user=self._ensure_generation_start_suffix(visible_prompt["user"]),
            )

        system_message = f"""你是一位专业的网络小说作家。根据以下上下文撰写章节内容。

{planning_section}{voice_block}{context}

{fact_lock}
写作要求：
1. 必须有多个人物互动（至少2-3个角色出场）
2. 必须有对话（不能只有独白和叙述）
3. 必须有冲突或张力（人物之间的矛盾、目标阻碍、悬念等）
4. 保持人物性格一致
5. 推进情节发展
6. 使用生动的场景描写和细节
{length_rule}
8. 用中文写作，使用第三人称叙事{beat_extra}"""

        user_message = f"""请根据以下大纲撰写本章内容：

{outline}

关键要求（必须遵守）：
- 至少2-3个角色出场并互动
- 必须包含对话场景（不少于3段对话）
- 必须有明确的冲突或戏剧张力
- 场景要具体生动，不要空泛叙述
- 推进主线情节，不要原地踏步
- 结尾要有悬念或转折"""

        user_message += prior_draft_block
        user_message += beat_section

        user_message += "\n\n开始撰写："

        return Prompt(system=system_message, user=user_message)

    def _build_direct_writing_prompt(
        self,
        *,
        context: str,
        outline: str,
        storyline_context: str = "",
        plot_tension: str = "",
        style_summary: str = "",
        voice_anchors: str = "",
        chapter_strategy: Optional[Dict[str, Any]] = None,
        next_chapter_bridge: str = "",
        target_word_count: Optional[int] = None,
        word_tolerance_ratio: Optional[float] = None,
    ) -> Prompt:
        """用于对照测试的直接写作提示词：少流程、少后处理，接近单次人工写作。"""
        planning_parts: list[str] = []
        for title, value in (
            ("故事线 / 里程碑", storyline_context),
            ("情节节奏 / 期望张力", plot_tension),
            ("风格约束", style_summary),
            ("角色声线与肢体语言", voice_anchors),
        ):
            text = value.strip() if isinstance(value, str) else ""
            if text and "unavailable" not in text.lower():
                planning_parts.append(f"【{title}】\n{text}")

        fact_lock = ""
        if self.memory_engine:
            try:
                parts = [
                    self.memory_engine.build_fact_lock_section(
                        self._current_novel_id or "", self._current_chapter_number or 0
                    ),
                    self.memory_engine.get_completed_beats_section(self._current_novel_id or ""),
                    self.memory_engine.get_revealed_clues_section(self._current_novel_id or ""),
                ]
                fact_lock = "\n\n".join(p for p in parts if p and p.strip())
            except Exception as e:
                logger.warning("direct writing fact_lock skipped: %s", e)

        planning_section = "\n\n".join(planning_parts)
        genre_overlay = self._build_genre_overlay(context=context, outline=outline)
        detector_calibration = self._build_detector_calibration_overlay(context=context, outline=outline)
        prop_overlay = self._build_prop_ledger_overlay()
        coc_overlay = self._build_coc_canon_overlay()
        coc_clue_overlay = self._build_coc_clue_overlay()
        coc_cognition_overlay = self._build_coc_cognition_overlay()
        strategy_overlay = self._build_strategy_overlay(chapter_strategy)
        constraints = "\n\n".join(
            part
            for part in (
                planning_section,
                fact_lock,
                detector_calibration,
                genre_overlay,
                prop_overlay,
                coc_overlay,
                coc_clue_overlay,
                coc_cognition_overlay,
                strategy_overlay,
                (next_chapter_bridge or "").strip(),
            )
            if part
        )
        target_range = self._target_word_range(target_word_count, word_tolerance_ratio)
        if target_range:
            min_words, max_words = target_range
            target = self._effective_word_target(target_word_count)
        else:
            target = self._effective_word_target(target_word_count)
            tolerance = max(120, int(target * 0.05))
            min_words = max(500, target - tolerance)
            max_words = target + tolerance
        direct_length_rule = (
            f"本章目标 {target} 中文字，允许 {min_words}-{max_words} 字。"
            "少于下限时补角色互动或阻力升级，接近上限时立刻收束。"
        )

        system_message = f"""你是一个长期连载中文小说作者。现在进入“直接写作模式”：只写正文，不解释写法，不输出大纲，不做总结报告。

你要像人在回忆一个具体场景，而不是像模型完成任务。请保持事实一致，但不要把所有信息都讲清楚；让动作、对话、停顿、误判和道具变化自己推进故事。

【直接写作规则】
1. 开头直接进入一个可见动作、声音、物件变化或人物反应，不先介绍背景。
2. 每一段只承担一个小动作或一次信息变化，避免段段收束成结论。
3. 对话要有遮掩、停顿、误解和试探；不要让人物把动机、世界观、推理过程一次说完。
4. 情绪不用抽象词解释，落到手、眼神、步伐、物件、声音、沉默和临时决定。
5. 保留一点不整齐：允许短句、半句、插入动作、轻微绕路；不要写成一篇被修得很光滑的稿子。
6. 少用万能比喻和统一意象。普通“像……”比喻全章控制在少量，重复场景词要主动换成动作或道具。
7. {direct_length_rule}

{constraints}

【上下文】
{context}"""

        user_message = f"""请直接写这一章正文：

{outline}

只输出小说正文。不要写章节标题，不要列项目，不要解释规则。

开始撰写："""
        return Prompt(system=system_message, user=user_message)

    @staticmethod
    def _build_direct_light_polish_prompt(*, draft: str, outline: str) -> Prompt:
        system_message = """你是中文小说轻修编辑。你的任务不是重写，不是润色成更华丽，而是把一篇已经写好的章节做少量人工化修补。

这次的优先级是“保留草稿感”，不是“修顺”。如果一段已经有现场动作、停顿、口语、物件细节或不完整的反应，就不要碰它。

硬性边界：
1. 保留 90% 以上原文句子、剧情事实、人物关系、道具状态和信息顺序。
2. 不新增角色，不新增设定，不改变结尾事件。
3. 只局部修改检测器敏感位置：抽象总结、心理直说、说明腔、段落过整、每段都收束成结论。
4. 把“他意识到/他明白/复杂情绪/某种感觉/一切都……”改成可见动作、停顿、物件变化、旁人反应或一句未说完的话。
5. 不要把句子修得更整齐，不要统一段落长度，不要给每段补结论，不要增加成套排比。
6. 不要故意写错别字，不要制造奇怪口癖，不要把全文改成同一种短句。
7. 只输出轻修后的小说正文。"""

        user_message = f"""本章大纲：
{outline}

请轻修下面正文，只做 5%-10% 的局部改动，目标是保留直接写作稿的松弛感，同时减少过度说明和过度工整。

不要为了“更通顺”而重写全章；没有明显问题的段落原样保留。

正文：
{draft}"""
        return Prompt(system=system_message, user=user_message)

    @staticmethod
    def _build_chapter_contract_overlay(*, context: str, outline: str) -> str:
        """给模型一个好看优先的章节戏剧任务，避免滑向说明文或检测器导向。"""
        outline_text = (outline or "").strip()
        lines = [
            "【好看优先：章节戏剧任务】",
            "写作前先在心里确定本章戏剧任务，但不要输出计划：",
            "- POV 角色此刻想要什么；",
            "- 谁或什么阻碍他；",
            "- 他手里有什么筹码、误判或不能说出口的动机；",
            "- 本章结束时读者获得什么兑现，又被什么新问题勾住。",
        ]
        if outline_text:
            lines.append("本章必须让大纲中的目标落成可见变化，不能只复述设定或解释背景。")
        else:
            lines.append("当前大纲为空或过短时，请从上下文里抽取一个最自然的短线任务来写：小证据、小阻碍、小试探、小代价，四者至少满足两项。")
        lines.extend([
            "",
            "【内部场景推进表（只在心里列，不输出）】",
            "把本章拆成 2-4 个场景或节拍，每个场景必须有：",
            "1. 场景任务：角色要拿到、确认、隐瞒、反制或失去什么；",
            "2. 阻力：人、制度、时间、误会、体力、道具、环境或旧关系至少一种；",
            "3. 新信息：读者对人物、线索、局势或关系的理解必须发生变化；",
            "4. 可见锚点：一个具体地点/物件/动作/记录/身体反应承载这次变化；",
            "5. 出口钩子：场景结束时留下下一步选择、未说完的话、反常细节或代价。",
            "",
            "解释信息前先让角色碰到证据、阻力或后果；不要让人物站着讲完机制。",
            "检测器分数不是写作目标。若“降低AI味”和“章节好看”冲突，优先保证人物欲望、冲突推进和追读钩子。",
            "",
            "【追读自检】",
            "输出前内部检查：开头是否有钩子，中段是否有阻力升级，结尾是否有未完成问题、关系裂口、危险升级或证据反转；没有就补一个具体钩子。",
        ])
        return "\n".join(lines)

    @staticmethod
    def _build_detector_calibration_overlay(*, context: str, outline: str) -> str:
        """从外部检测器真人样本提炼出的小说化事实锚点规则。"""
        source = f"{context or ''}\n{outline or ''}"
        genre_key = AutoNovelGenerationWorkflow._infer_genre_key(source)
        if genre_key in {"suspense", "urban", "cultivation", "comic_adaptation"}:
            anchor_examples = {
                "suspense": "门禁编号、票据抬头、摄像头角度、检测阈值、日志时间、证物封条、坐标误差",
                "urban": "合同条款、会议纪要、转账时间、项目编号、报价差额、审批流程、设备记录",
                "cultivation": "丹炉火候、阵纹编号、灵石刻度、伤口变化、功法层级、药液比例、巡山时辰",
                "comic_adaptation": "分镜位置、招牌文字、服装材质、镜头遮挡、榜单数据、道具特写、动作顺序",
            }[genre_key]
        else:
            anchor_examples = "时间、地点、材质、编号、票据、记录、流程、误差、阈值、旧物磨损、操作顺序"

        return "\n".join([
            "【检测器校准：事实锚点写法】",
            "外部检测器更容易把高密度、可核验、非抒情的事实链判为人工文本；请把这个特征小说化，而不是写成论文。",
            f"本章每 700-1000 字至少嵌入 1 个非文学性事实锚点，可选：{anchor_examples}。",
            "事实锚点必须由角色看见、摸到、核对、误读或操作出来；不要站出来说明背景。",
            "优先写“数据/物件/流程 -> 角色判断 -> 出错或受阻 -> 新动作”的因果链，少写纯氛围和纯情绪。",
            "允许少量不那么文学化的句子：记录式短句、半截术语、口头修正、旧标签、错位标点或中英缩写，但不能故意写错别字，也不能破坏可读性。",
        ])

    @staticmethod
    def _build_genre_overlay(*, context: str, outline: str) -> str:
        """根据现有上下文和本章大纲生成类型化网文写法规则。"""
        source = f"{context or ''}\n{outline or ''}"
        genre_key = AutoNovelGenerationWorkflow._infer_genre_key(source)
        if not genre_key:
            return ""

        overlays = {
            "suspense": (
                "悬疑/调查",
                [
                    "开头先给异常或后果，不先解释异常来源。",
                    "本章至少出现一个线索、一个误判、一个暂时被遮住的事实。",
                    "信息释放分层：角色看到的、角色误解的、读者可疑的、真相暂不说破的。",
                    "紧张感来自现场后果、证物变化和人物反应，不靠抽象氛围形容词。",
                ],
            ),
            "urban": (
                "都市爽文",
                [
                    "开头必须有现实压力：钱、权、身份、资源、名声、家人、安全或机会被夺。",
                    "主角不能只被动挨打，至少做出一次判断、试探或反制。",
                    "爽点按“被压制、找破口、小范围兑现、更大对手出现”推进。",
                    "配角要代表资源、阻碍或利益立场，不要只做解释和捧场。",
                ],
            ),
            "cultivation": (
                "玄幻/仙侠",
                [
                    "每章至少让修为、资源、敌我差距或规则限制中的一个发生变化。",
                    "设定只在行动中出现：功法、法器、血脉、禁地规则通过使用、失败或代价展示。",
                    "战斗重点写判断、破绽、代价、环境变化和旁观者反应，不堆招式说明。",
                    "阶段性兑现后留下更高层级压力，避免一章把问题收干净。",
                ],
            ),
            "historical_romance": (
                "古言/宅斗",
                [
                    "冲突落在身份、礼法、婚约、家族利益、名声、继承或权力站队上。",
                    "对话要藏刀，人物不能把真实目的直接说完。",
                    "细节写规矩和位置：谁坐哪、谁先开口、谁不能接话、谁被迫低头。",
                    "爽点不是吵赢，而是让局势、名分、证据或人心发生偏移。",
                ],
            ),
            "romance": (
                "情感/关系流",
                [
                    "每章推进关系温度：靠近、误会、试探、退让、暴露弱点或边界变化。",
                    "情绪不要解释成“心动/难过/复杂”，要落到动作、回避、停顿、没说完的话。",
                    "CP 拉扯要有外部事件承载，不要纯聊天。",
                    "人物魅力来自选择和克制，不来自作者替他夸。",
                ],
            ),
            "comic_adaptation": (
                "漫画转小说",
                [
                    "优先保留漫画题材里的第一眼冲突：身份反差、画面奇观、关系张力、强设定物件。",
                    "把视觉冲击转成小说场景：动作、空间、道具、表情、停顿和围观反应。",
                    "不照搬漫画夸张对白，改成更有潜台词的互动。",
                    "第一章必须让读者看见核心卖点，而不是只读到设定说明。",
                ],
            ),
        }
        title, rules = overlays[genre_key]
        return "\n".join(["【类型写法规则】", f"当前类型：{title}", *[f"- {rule}" for rule in rules]])

    @staticmethod
    def _infer_genre_key(text: str) -> str:
        source = (text or "").lower()
        checks: list[tuple[str, tuple[str, ...]]] = [
            ("comic_adaptation", ("漫画", "分镜", "快看", "腾讯动漫", "视觉冲突")),
            ("historical_romance", ("古言", "宅斗", "宫斗", "侯府", "王爷", "嫡女", "庶女", "婚约", "礼法")),
            ("cultivation", ("玄幻", "仙侠", "修仙", "宗门", "灵气", "功法", "境界", "法器", "血脉")),
            ("suspense", ("悬疑", "推理", "案件", "凶案", "调查", "档案", "线索", "嫌疑", "证物", "异常事件")),
            ("urban", ("都市", "逆袭", "职场", "商战", "系统", "神豪", "赘婿", "校花", "夺功", "上司")),
            ("romance", ("现言", "甜宠", "豪门", "总裁", "先婚", "替身", "破镜重圆", "双男", "女频", "情感")),
        ]
        for key, keywords in checks:
            if any(keyword in source for keyword in keywords):
                return key
        return ""

    @staticmethod
    def _build_strategy_overlay(chapter_strategy: Optional[Dict[str, Any]]) -> str:
        if not isinstance(chapter_strategy, dict):
            return ""
        contract = chapter_strategy.get("chapter_contract") or {}
        dramatic = chapter_strategy.get("dramatic_task") or {}
        scenes = chapter_strategy.get("scene_plan") or []
        focus_points = chapter_strategy.get("writing_focus") or []
        lines = ["【本章写作策略（已确认，必须执行）】"]
        if isinstance(contract, dict) and contract:
            lines.extend([
                "章节合同：",
                f"- 本章问题：{str(contract.get('chapter_question') or '未说明').strip()}",
                f"- 主角想要：{str(contract.get('protagonist_want') or '未说明').strip()}",
                f"- 阻力来源：{str(contract.get('opposition') or '未说明').strip()}",
                f"- 信息变化：{str(contract.get('required_information_change') or '未说明').strip()}",
                f"- 关系变化：{str(contract.get('required_relationship_change') or '未说明').strip()}",
                f"- 章末追问：{str(contract.get('ending_question') or '未说明').strip()}",
                "展示优先：",
            ])
            rules = contract.get("show_dont_tell_rules") if isinstance(contract.get("show_dont_tell_rules"), list) else []
            for rule in rules[:5]:
                text = str(rule or "").strip()
                if text:
                    lines.append(f"- {text}")
        if dramatic:
            lines.extend([
                "戏剧任务：",
                f"- 角色想要：{str(dramatic.get('goal') or '未说明').strip()}",
                f"- 主要阻碍：{str(dramatic.get('obstacle') or '未说明').strip()}",
                f"- 读者期待：{str(dramatic.get('reader_expectation') or '未说明').strip()}",
                f"- 章末钩子：{str(dramatic.get('ending_hook') or '未说明').strip()}",
            ])
        if scenes:
            lines.append("场景推进：")
            for index, scene in enumerate(scenes[:4], start=1):
                if not isinstance(scene, dict):
                    continue
                title = str(scene.get("label") or scene.get("title") or f"场景 {index}").strip()
                task = str(scene.get("task") or "未说明").strip()
                resistance = str(scene.get("resistance") or "未说明").strip()
                info_shift = str(scene.get("info_shift") or "未说明").strip()
                relation_shift = str(scene.get("relationship_shift") or "未说明").strip()
                visible_action = str(scene.get("visible_action") or scene.get("anchor") or "未说明").strip()
                subtext_dialogue = str(scene.get("subtext_dialogue") or "未说明").strip()
                unspoken_emotion = str(scene.get("unspoken_emotion") or "未说明").strip()
                clue_change = str(scene.get("object_or_clue_change") or "未说明").strip()
                hook = str(scene.get("hook") or "未说明").strip()
                lines.append(
                    f"{index}. {title}｜任务：{task}｜阻力：{resistance}｜变化：{info_shift}｜关系：{relation_shift}｜动作：{visible_action}｜潜台词：{subtext_dialogue}｜不直说：{unspoken_emotion}｜线索/道具：{clue_change}｜钩子：{hook}"
                )
        if focus_points:
            lines.append("执行提醒：")
            for item in focus_points[:4]:
                text = str(item or "").strip()
                if text:
                    lines.append(f"- {text}")
        lines.append("正文必须围绕这份策略推进，不能写成与策略无关的设定说明或平铺叙述。")
        return "\n".join(lines)

    def _build_next_chapter_bridge_overlay(
        self,
        *,
        novel_id: str,
        chapter_number: int,
        target_word_count: Optional[int],
        chapter_strategy: Optional[Dict[str, Any]],
    ) -> str:
        manual_notes = self._extract_manual_next_chapter_notes(chapter_strategy)
        auto_enabled = self._should_enable_next_chapter_bridge(target_word_count)
        if not manual_notes and not auto_enabled:
            return ""

        lines: list[str] = ["【下一章承接设定（长章前摄）】"]
        if manual_notes:
            lines.append("手动设定：")
            for note in manual_notes[:4]:
                lines.append(f"- {note}")

        if auto_enabled:
            next_seed = self._resolve_next_chapter_seed(novel_id, chapter_number + 1)
            if next_seed:
                title = next_seed.get("title") or f"第{chapter_number + 1}章"
                outline = next_seed.get("outline") or ""
                lines.append(f"下一章预设：第{chapter_number + 1}章《{title}》")
                if outline:
                    lines.append(f"- 核心设定：{outline}")
            elif not manual_notes:
                lines.append(f"下一章预设：第{chapter_number + 1}章尚未有明确大纲，请在本章末尾预留转场钩子。")

        lines.extend(
            [
                "执行要求：",
                "- 本章后 20% 要埋入 1-2 个可承接锚点（人物决定 / 道具状态 / 风险升级）。",
                "- 只埋钩子，不提前完整剧透下一章核心反转。",
                "- 锚点必须可见可写（动作、对白、道具、时间点），不能只写抽象预告。",
            ]
        )
        return "\n".join(lines)

    def _should_enable_next_chapter_bridge(self, target_word_count: Optional[int]) -> bool:
        return self._effective_word_target(target_word_count) >= LONG_CHAPTER_NEXT_SETUP_MIN_WORDS

    @staticmethod
    def _extract_manual_next_chapter_notes(chapter_strategy: Optional[Dict[str, Any]]) -> List[str]:
        if not isinstance(chapter_strategy, dict):
            return []
        notes: list[str] = []

        def _append_text(value: Any) -> None:
            if isinstance(value, str):
                text = value.strip()
                if text and text not in notes:
                    notes.append(text)
            elif isinstance(value, list):
                for item in value:
                    _append_text(item)
            elif isinstance(value, dict):
                compact = "；".join(
                    f"{k}: {str(v).strip()}"
                    for k, v in value.items()
                    if str(v).strip()
                )
                if compact and compact not in notes:
                    notes.append(compact)

        for key in ("next_chapter_setup", "next_chapter_bridge", "next_chapter_hint", "next_setup", "next_chapter"):
            if key in chapter_strategy:
                _append_text(chapter_strategy.get(key))
        return notes

    def _resolve_next_chapter_seed(self, novel_id: str, next_chapter_number: int) -> Optional[Dict[str, str]]:
        story_node_repo = getattr(self.context_builder, "story_node_repository", None)
        if story_node_repo and hasattr(story_node_repo, "get_by_novel_sync"):
            try:
                nodes = story_node_repo.get_by_novel_sync(novel_id) or []
                for node in nodes:
                    node_type = getattr(node, "node_type", None)
                    node_type_value = getattr(node_type, "value", node_type)
                    if str(node_type_value or "").lower() != "chapter":
                        continue
                    number = getattr(node, "number", None)
                    if number is None or int(number) != int(next_chapter_number):
                        continue
                    title = str(getattr(node, "title", "") or "").strip()
                    outline_raw = (
                        getattr(node, "outline", None)
                        or getattr(node, "description", None)
                        or getattr(node, "content", None)
                        or ""
                    )
                    outline = self._compact_prompt_text(str(outline_raw), NEXT_CHAPTER_SETUP_MAX_CHARS)
                    if title or outline:
                        return {"title": title, "outline": outline}
                    break
            except Exception as e:
                logger.debug("next chapter seed from story nodes skipped: %s", e)

        chapter_repo = getattr(self.context_builder, "chapter_repository", None)
        if chapter_repo and hasattr(chapter_repo, "list_by_novel"):
            try:
                chapters = chapter_repo.list_by_novel(NovelId(novel_id)) or []
                for chapter in chapters:
                    if int(getattr(chapter, "number", -1)) != int(next_chapter_number):
                        continue
                    title = str(getattr(chapter, "title", "") or "").strip()
                    outline_raw = getattr(chapter, "outline", None) or ""
                    if not outline_raw:
                        outline_raw = getattr(chapter, "content", None) or ""
                    outline = self._compact_prompt_text(str(outline_raw), NEXT_CHAPTER_SETUP_MAX_CHARS)
                    if title or outline:
                        return {"title": title, "outline": outline}
                    break
            except Exception as e:
                logger.debug("next chapter seed from chapters skipped: %s", e)
        return None

    @staticmethod
    def _compact_prompt_text(text: str, max_chars: int) -> str:
        raw = " ".join(str(text or "").strip().split())
        if len(raw) <= max_chars:
            return raw
        return raw[: max_chars - 1].rstrip() + "…"

    @staticmethod
    def _coerce_llm_content_to_text(raw: Any) -> str:
        if raw is None:
            return ""
        if isinstance(raw, str):
            return raw
        if isinstance(raw, list):
            text_parts: list[str] = []
            looks_like_content_parts = False
            for item in raw:
                if isinstance(item, str):
                    looks_like_content_parts = True
                    if item.strip():
                        text_parts.append(item.strip())
                    continue
                if isinstance(item, dict):
                    item_type = str(item.get("type") or "").lower()
                    if item_type in {"reasoning", "thinking", "refusal"}:
                        looks_like_content_parts = True
                        continue
                    text_value = item.get("text")
                    content_value = item.get("content")
                    if item_type or isinstance(text_value, str) or isinstance(content_value, (str, list)):
                        looks_like_content_parts = True
                        if isinstance(text_value, str) and text_value.strip():
                            text_parts.append(text_value.strip())
                        elif isinstance(content_value, str) and content_value.strip():
                            text_parts.append(content_value.strip())
                        elif isinstance(content_value, list):
                            nested = AutoNovelGenerationWorkflow._coerce_llm_content_to_text(content_value)
                            if nested.strip():
                                text_parts.append(nested.strip())
                    continue
                text_attr = getattr(item, "text", None)
                if isinstance(text_attr, str):
                    looks_like_content_parts = True
                    if text_attr.strip():
                        text_parts.append(text_attr.strip())
            if looks_like_content_parts:
                return "\n".join(text_parts)
            try:
                import json
                return json.dumps(raw, ensure_ascii=False)
            except Exception:
                return str(raw)
        if isinstance(raw, dict):
            try:
                import json
                return json.dumps(raw, ensure_ascii=False)
            except Exception:
                return str(raw)
        return str(raw)

    def _parse_llm_json_payload(self, raw: Any) -> Tuple[Optional[Dict[str, Any]], List[str]]:
        text = self._coerce_llm_content_to_text(raw)
        try:
            cleaned = strip_json_fences(text if isinstance(text, str) else str(text))
            outer = extract_outer_json_object(cleaned if isinstance(cleaned, str) else str(cleaned))
            repaired = repair_json(outer if isinstance(outer, str) else str(outer))
            parsed = json.loads(repaired)
        except json.JSONDecodeError as e:
            return None, [f"JSON 解析失败: {e}"]
        except Exception as e:
            return None, [
                "预处理失败: "
                f"{e} (raw={type(raw).__name__}, text={type(locals().get('text')).__name__}, "
                f"cleaned={type(locals().get('cleaned')).__name__}, outer={type(locals().get('outer')).__name__})"
            ]

        if isinstance(parsed, dict):
            return parsed, []
        if isinstance(parsed, list):
            for item in parsed:
                if isinstance(item, dict):
                    return item, ["根节点为列表，已自动取首个对象"]
            return None, ["根节点为列表，但未包含对象"]
        return None, [f"根节点类型不支持: {type(parsed).__name__}"]

    async def generate_chapter_strategy(
        self,
        novel_id: str,
        chapter_number: int,
        outline: str,
        *,
        scene_director: Optional[SceneDirectorAnalysis] = None,
        style_profile_id: str = "",
        scene_type: str = "",
        target_word_count: Optional[int] = None,
        word_tolerance_ratio: Optional[float] = None,
    ) -> Dict[str, Any]:
        bundle = self.prepare_chapter_generation(
            novel_id,
            chapter_number,
            outline,
            scene_director=scene_director,
            max_tokens=12000,
        )
        context = bundle["context"]
        style_overlay = self._build_style_overlay(novel_id, style_profile_id, scene_type)
        prompt = self._build_strategy_prompt(
            context=context,
            outline=outline,
            storyline_context=bundle["storyline_context"],
            plot_tension=bundle["plot_tension"],
            style_summary=bundle["style_summary"],
            style_overlay=style_overlay,
            target_word_count=target_word_count,
            word_tolerance_ratio=word_tolerance_ratio,
        )
        data: Dict[str, Any] = {}
        try:
            result = await self.llm_service.generate(
                prompt,
                GenerationConfig(max_tokens=1200, temperature=0.35),
            )
            parsed, errs = self._parse_llm_json_payload(result.content)
            if parsed:
                data = parsed
            else:
                logger.warning("chapter strategy JSON parse failed: %s", errs)
        except Exception as e:
            logger.warning("chapter strategy generation failed, fallback will be used: %s", e)
        return self._normalize_strategy_payload(
            data,
            outline=outline,
            target_word_count=target_word_count,
            word_tolerance_ratio=word_tolerance_ratio,
        )

    async def review_generated_chapter_editorially(
        self,
        *,
        novel_id: str,
        chapter_number: int,
        outline: str,
        content: str,
        chapter_strategy: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        bundle = self.prepare_chapter_generation(novel_id, chapter_number, outline)
        prompt = self._build_editorial_review_prompt(
            context=bundle["context"],
            outline=outline,
            content=content,
            chapter_strategy=chapter_strategy,
        )
        data: Dict[str, Any] = {}
        try:
            result = await self.llm_service.generate(
                prompt,
                GenerationConfig(max_tokens=1800, temperature=0.35),
            )
            parsed, errs = self._parse_llm_json_payload(result.content)
            if parsed:
                data = parsed
            else:
                logger.warning("editorial review JSON parse failed: %s", errs)
        except Exception as e:
            logger.warning("editorial review generation failed, fallback will be used: %s", e)
        return self._normalize_editorial_review_payload(data)

    def _build_strategy_prompt(
        self,
        *,
        context: str,
        outline: str,
        storyline_context: str = "",
        plot_tension: str = "",
        style_summary: str = "",
        style_overlay: str = "",
        target_word_count: Optional[int] = None,
        word_tolerance_ratio: Optional[float] = None,
    ) -> Prompt:
        target = self._effective_word_target(target_word_count)
        tolerance_ratio = self._resolve_word_tolerance_ratio(word_tolerance_ratio)
        tolerance = max(80, int(target * tolerance_ratio))
        min_words = max(500, target - tolerance)
        max_words = target + tolerance
        system = """你是资深网文主编。你的任务不是直接写正文，而是先给作者一份本章写作策略。

请只输出 JSON，不要加解释，不要加 Markdown 代码块。

JSON 结构：
{
  "chapter_contract": {
    "chapter_question": "本章读者最想知道的问题",
    "protagonist_want": "主角最具体想拿到/确认/避免什么",
    "opposition": "谁或什么阻碍他",
    "reader_expectation": "读者期待看到的具体场面",
    "required_information_change": "本章必须交付的信息变化",
    "required_relationship_change": "本章必须发生的人物关系变化",
    "ending_question": "章末留下的追问",
    "show_dont_tell_rules": ["本章禁止直说的情绪/动机/解释，改用动作、停顿、物件、对白表现"]
  },
  "dramatic_task": {
    "goal": "角色这章最具体想拿到/确认/隐瞒什么",
    "obstacle": "谁或什么阻碍他",
    "reader_expectation": "读者这一章最期待看到什么兑现",
    "ending_hook": "章末要留下什么追读钩子"
  },
  "scene_plan": [
    {
      "label": "场景标题",
      "task": "这个场景的任务",
      "resistance": "阻力",
      "info_shift": "新信息或局势变化",
      "relationship_shift": "人物关系变化，没有就写无明显变化",
      "anchor": "一个具体物件/动作/地点锚点",
      "visible_action": "必须出现的具体动作",
      "subtext_dialogue": "对白表面内容和真实意图",
      "unspoken_emotion": "不能直说的情绪",
      "object_or_clue_change": "道具或线索状态变化",
      "hook": "场景结尾钩子",
      "target_words": 800
    }
  ],
  "writing_focus": ["3-4 条执行提醒"]
}

硬性要求：
1. scene_plan 只能有 2-4 段。
2. 每段都必须推动故事，不准只有解释。
3. 写法优先级：开头钩子、冲突推进、人物选择、结尾追读。
4. target_words 总和尽量接近目标字数。
5. 所有字段必须填中文字符串，target_words 为整数。
6. 展示优先：少解释，多展示；少总结，多动作和细节；少金句，多具体反应。
7. 不要直接写“复杂情绪”，必须要求正文通过动作、停顿、回避、物件处理来表现。
8. 对话不要每句都完整、礼貌、逻辑闭环；允许打断、反问、避重就轻。"""
        user = (
            f"目标字数：约 {target} 字（容差 {min_words}-{max_words}）\n\n"
            f"【故事线】\n{storyline_context or '（无）'}\n\n"
            f"【情节张力】\n{plot_tension or '（无）'}\n\n"
            f"【风格约束】\n{style_summary or '（无）'}\n\n"
            f"{style_overlay}\n\n"
            f"【上下文】\n{context}\n\n"
            f"【本章大纲】\n{outline}\n\n"
            "请生成本章写作策略 JSON："
        )
        return Prompt(system=system, user=user)

    def _build_editorial_review_prompt(
        self,
        *,
        context: str,
        outline: str,
        content: str,
        chapter_strategy: Optional[Dict[str, Any]] = None,
    ) -> Prompt:
        strategy_overlay = self._build_strategy_overlay(chapter_strategy)
        system = """你是网络小说主编，负责章后审稿。重点不是检查 AI 味，而是判断这章是否好看、是否能让人继续追读。

只输出 JSON，不要加解释，不要加 Markdown 代码块。

JSON 结构：
{
  "summary": "一句话总结这章的阅读效果",
  "scores": {
    "opening": 0-100,
    "conflict": 0-100,
    "character": 0-100,
    "dialogue": 0-100,
    "hook": 0-100,
    "pacing": 0-100,
    "showing": 0-100
  },
  "strengths": ["2-4 条亮点"],
  "problems": ["2-4 条最关键问题"],
  "actions": ["2-4 条可执行修改建议"],
  "verdict": "保留 / 可优化后使用 / 建议重写"
}

评分标准：
- opening：开头是否迅速进入具体情境
- conflict：冲突和阻力是否真实推进
- character：人物欲望、选择、代价是否成立
- dialogue：对白是否有潜台词和信息变化
- hook：章末是否形成追读点
- pacing：场景切换、轻重缓急是否合适
- showing：是否少解释、多展示；情绪是否通过动作/细节/潜台词表现；对白是否避免完整礼貌闭环

展示优先专项检查：
- 扣解释句过密、总结句替代场景、直接命名情绪。
- 扣客服式完整对白和段尾金句。
- 修改动作必须说明如何把解释改成动作或潜台词。"""
        user = (
            f"【上下文】\n{context}\n\n"
            f"【本章大纲】\n{outline}\n\n"
            f"{strategy_overlay}\n\n"
            f"【本章正文】\n{content}\n\n"
            "请给出主编审稿 JSON："
        )
        return Prompt(system=system, user=user)

    @staticmethod
    def _clean_text(value: Any, fallback: str) -> str:
        text = str(value or "").strip()
        return text or fallback

    @staticmethod
    def _clean_text_list(value: Any, fallback: List[str], *, limit: int = 4) -> List[str]:
        if isinstance(value, list):
            cleaned = [str(item).strip() for item in value if str(item).strip()]
            if cleaned:
                return cleaned[:limit]
        return fallback[:limit]

    @staticmethod
    def _normalize_strategy_payload(
        data: Dict[str, Any],
        *,
        outline: str,
        target_word_count: Optional[int] = None,
        word_tolerance_ratio: Optional[float] = None,
    ) -> Dict[str, Any]:
        dramatic = data.get("dramatic_task") if isinstance(data.get("dramatic_task"), dict) else {}
        target = AutoNovelGenerationWorkflow._effective_word_target(target_word_count)
        tolerance_ratio = AutoNovelGenerationWorkflow._resolve_word_tolerance_ratio(word_tolerance_ratio)
        min_scene_words = max(400, int(target * max(0.18, 0.22 - tolerance_ratio * 0.2)))
        default_scene_words = max(600, int(target / 3))
        raw_contract = data.get("chapter_contract") if isinstance(data.get("chapter_contract"), dict) else {}
        chapter_contract = {
            "chapter_question": AutoNovelGenerationWorkflow._clean_text(
                raw_contract.get("chapter_question"),
                "本章的关键问题必须在具体行动中被推进。",
            ),
            "protagonist_want": AutoNovelGenerationWorkflow._clean_text(
                raw_contract.get("protagonist_want"),
                dramatic.get("goal") or outline[:36] or "主角要确认一条关键线索。",
            ),
            "opposition": AutoNovelGenerationWorkflow._clean_text(
                raw_contract.get("opposition"),
                dramatic.get("obstacle") or "有人或流程阻碍主角。",
            ),
            "reader_expectation": AutoNovelGenerationWorkflow._clean_text(
                raw_contract.get("reader_expectation"),
                dramatic.get("reader_expectation") or "读者要看到冲突推进，而不是解释背景。",
            ),
            "required_information_change": AutoNovelGenerationWorkflow._clean_text(
                raw_contract.get("required_information_change"),
                "至少交付一条会改变判断的新信息。",
            ),
            "required_relationship_change": AutoNovelGenerationWorkflow._clean_text(
                raw_contract.get("required_relationship_change"),
                "至少让主要人物的立场或信任关系发生细微变化。",
            ),
            "ending_question": AutoNovelGenerationWorkflow._clean_text(
                raw_contract.get("ending_question"),
                dramatic.get("ending_hook") or "章末留下新的追问。",
            ),
            "show_dont_tell_rules": AutoNovelGenerationWorkflow._clean_text_list(
                raw_contract.get("show_dont_tell_rules"),
                [
                    "不能直接命名复杂情绪，必须写动作、停顿、回避或身体反应。",
                    "不能用总结句跳过冲突过程，必须让读者看到试探和阻力。",
                    "对白不能每句都完整礼貌，允许打断、反问、答非所问。",
                ],
                limit=5,
            ),
        }
        raw_scenes = data.get("scene_plan") if isinstance(data.get("scene_plan"), list) else []
        scenes: List[Dict[str, Any]] = []
        for index, item in enumerate(raw_scenes[:4], start=1):
            if not isinstance(item, dict):
                continue
            try:
                scene_target = int(item.get("target_words") or default_scene_words)
            except (TypeError, ValueError):
                scene_target = default_scene_words
            scenes.append({
                "label": str(item.get("label") or f"场景 {index}").strip() or f"场景 {index}",
                "task": str(item.get("task") or "推进当前矛盾").strip() or "推进当前矛盾",
                "resistance": str(item.get("resistance") or "出现具体阻力").strip() or "出现具体阻力",
                "info_shift": str(item.get("info_shift") or "读者对局势理解发生变化").strip() or "读者对局势理解发生变化",
                "relationship_shift": str(item.get("relationship_shift") or "无明显变化").strip() or "无明显变化",
                "anchor": str(item.get("anchor") or "一个具体物件或动作").strip() or "一个具体物件或动作",
                "visible_action": AutoNovelGenerationWorkflow._clean_text(
                    item.get("visible_action"),
                    str(item.get("anchor") or "用一个具体动作承载情绪和信息。"),
                ),
                "subtext_dialogue": AutoNovelGenerationWorkflow._clean_text(
                    item.get("subtext_dialogue"),
                    "对白表面推进事实，底层保留试探、遮掩或误判。",
                ),
                "unspoken_emotion": AutoNovelGenerationWorkflow._clean_text(
                    item.get("unspoken_emotion"),
                    "不要直接命名情绪，用动作和反应表现。",
                ),
                "object_or_clue_change": AutoNovelGenerationWorkflow._clean_text(
                    item.get("object_or_clue_change"),
                    "本场景至少让一个线索、道具或判断发生变化。",
                ),
                "hook": str(item.get("hook") or "留下下一步动作或异常细节").strip() or "留下下一步动作或异常细节",
                "target_words": max(min_scene_words, min(1800, scene_target)),
            })
        if len(scenes) < 2:
            fallback_scenes = [
                {
                    "label": "开场推进",
                    "task": "尽快把角色送进具体局面",
                    "resistance": "先给一个小阻力或误判",
                    "info_shift": "让读者知道本章核心问题",
                    "relationship_shift": "主要人物态度出现偏差",
                    "anchor": "现场动作或道具变化",
                    "visible_action": "角色用一个可见动作进入冲突，而不是先解释心情。",
                    "subtext_dialogue": "对白表面确认事实，底层互相试探。",
                    "unspoken_emotion": "紧张、怀疑或不安不能被直接命名。",
                    "object_or_clue_change": "一个现场线索从背景物变成问题核心。",
                    "hook": "把问题推向下一场景",
                    "target_words": default_scene_words,
                },
                {
                    "label": "兑现与钩子",
                    "task": "兑现一部分预期，同时抬高代价",
                    "resistance": "阻力升级或旧问题反扑",
                    "info_shift": "补一条改变判断的新信息",
                    "relationship_shift": "人物关系留下一道裂口",
                    "anchor": "证据、表情、动作或记录",
                    "visible_action": "角色必须做出选择或处理证据，留下可见后果。",
                    "subtext_dialogue": "对白不把动机说透，保留遮掩和反问。",
                    "unspoken_emotion": "代价和犹豫用停顿、回避或动作表现。",
                    "object_or_clue_change": "证据、道具或判断在章末改变状态。",
                    "hook": "章末留追读点",
                    "target_words": default_scene_words,
                },
            ]
            scenes.extend(fallback_scenes[len(scenes):])
        focus = data.get("writing_focus") if isinstance(data.get("writing_focus"), list) else []
        normalized_focus = [str(item).strip() for item in focus if str(item).strip()]
        if not normalized_focus:
            normalized_focus = [
                "开头直接进入具体动作或异常细节，不先解释背景。",
                "每个场景都要让人物做选择，不只接受信息。",
                "对白里保留试探和遮掩，不把动机一次说完。",
            ]
        return {
            "chapter_contract": chapter_contract,
            "dramatic_task": {
                "goal": str(dramatic.get("goal") or outline[:24] or "拿到或确认一条关键线索").strip() or "拿到或确认一条关键线索",
                "obstacle": str(dramatic.get("obstacle") or "有人、时间或局势阻碍角色").strip() or "有人、时间或局势阻碍角色",
                "reader_expectation": str(dramatic.get("reader_expectation") or "看到问题被推进，而不是原地解释").strip() or "看到问题被推进，而不是原地解释",
                "ending_hook": str(dramatic.get("ending_hook") or "章末留下新的疑点、代价或关系裂口").strip() or "章末留下新的疑点、代价或关系裂口",
            },
            "scene_plan": scenes,
            "writing_focus": normalized_focus[:4],
        }

    @staticmethod
    def _normalize_editorial_review_payload(data: Dict[str, Any]) -> Dict[str, Any]:
        scores = data.get("scores") if isinstance(data.get("scores"), dict) else {}
        def score_of(key: str) -> int:
            try:
                value = int(round(float(scores.get(key, 0))))
            except (TypeError, ValueError):
                value = 0
            return max(0, min(100, value))
        verdict = str(data.get("verdict") or "可优化后使用").strip() or "可优化后使用"
        def text_list(key: str, fallback: List[str]) -> List[str]:
            raw = data.get(key)
            if isinstance(raw, list):
                cleaned = [str(item).strip() for item in raw if str(item).strip()]
                if cleaned:
                    return cleaned[:4]
            return fallback
        return {
            "summary": str(data.get("summary") or "本章完成了推进，但仍有可继续压实的空间。").strip() or "本章完成了推进，但仍有可继续压实的空间。",
            "scores": {
                "opening": score_of("opening"),
                "conflict": score_of("conflict"),
                "character": score_of("character"),
                "dialogue": score_of("dialogue"),
                "hook": score_of("hook"),
                "pacing": score_of("pacing"),
                "showing": score_of("showing"),
            },
            "strengths": text_list("strengths", ["至少有一处具体场景成立，能支撑继续加工。"]),
            "problems": text_list("problems", ["仍需检查冲突升级和章末钩子是否足够明确。"]),
            "actions": text_list("actions", ["优先补强最弱一场戏的阻力和信息变化。"]),
            "verdict": verdict,
        }

    def _build_prop_ledger_overlay(self) -> str:
        if not self.prop_ledger_service or not self._current_novel_id:
            return ""
        try:
            overview = self.prop_ledger_service.get_overview(self._current_novel_id)
        except Exception as e:
            logger.warning("prop ledger overlay unavailable: %s", e)
            return ""
        items = overview.get("items") or []
        if not items:
            return ""
        lines = [
            "【道具账本（必须保持一致）】",
            "写到相关道具时，必须遵守当前持有人、位置、状态；未在本章合理交代前，不得凭空改变去向或用途。",
        ]
        for item in items[:12]:
            chapter = item.get("last_seen_chapter") or item.get("first_seen_chapter") or "未登记"
            lines.append(
                "- "
                f"{item.get('name') or '未命名'}"
                f"｜状态：{item.get('status') or '未记录'}"
                f"｜持有人：{item.get('current_holder') or '未记录'}"
                f"｜位置：{item.get('current_location') or '未记录'}"
                f"｜最近：第{chapter}章"
            )
        return "\n".join(lines)

    def _build_coc_canon_overlay(self) -> str:
        if not self.coc_canon_service or not self._current_novel_id:
            self._current_coc_canon_overlay = ""
            self._current_coc_absolute_titles = []
            return ""
        try:
            overlay = self.coc_canon_service.build_overlay(self._current_novel_id)
        except Exception as e:
            logger.warning("coc canon overlay unavailable: %s", e)
            self._current_coc_canon_overlay = ""
            self._current_coc_absolute_titles = []
            return ""

        prompt = ""
        if isinstance(overlay, dict):
            prompt = str(overlay.get("prompt") or "")
        elif isinstance(overlay, str):
            prompt = overlay
        else:
            prompt = str(getattr(overlay, "prompt", "") or "")

        self._current_coc_canon_overlay = prompt.strip()
        self._current_coc_absolute_titles = self._extract_coc_absolute_titles(overlay, prompt)
        return self._current_coc_canon_overlay

    def _build_coc_clue_overlay(self) -> str:
        if not self.coc_clue_service or not self._current_novel_id:
            self._current_coc_clue_overlay = ""
            self._current_coc_author_only_clue_keys = []
            return ""
        try:
            overlay = self.coc_clue_service.build_overlay(self._current_novel_id)
        except Exception as e:
            logger.warning("coc clue overlay unavailable: %s", e)
            self._current_coc_clue_overlay = ""
            self._current_coc_author_only_clue_keys = []
            return ""

        prompt = ""
        if isinstance(overlay, dict):
            prompt = str(overlay.get("prompt") or "")
        elif isinstance(overlay, str):
            prompt = overlay
        else:
            prompt = str(getattr(overlay, "prompt", "") or "")

        self._current_coc_clue_overlay = prompt.strip()
        self._current_coc_author_only_clue_keys = self._extract_coc_author_only_clue_keys(overlay, prompt)
        return self._current_coc_clue_overlay

    def _build_coc_cognition_overlay(self) -> str:
        if not self._current_novel_id:
            self._current_coc_cognition_overlay = ""
            self._current_coc_author_truth_snippets = []
            return ""
        canon_layers: dict[str, Any] = {}
        clue_layers: dict[str, Any] = {}
        if self.coc_canon_service:
            try:
                layers = self.coc_canon_service.get_cognition_layers(self._current_novel_id) or {}
                canon_layers = layers if isinstance(layers, dict) else {}
            except Exception as e:
                logger.warning("coc cognition (canon) unavailable: %s", e)
        if self.coc_clue_service:
            try:
                layers = self.coc_clue_service.get_cognition_layers(self._current_novel_id) or {}
                clue_layers = layers if isinstance(layers, dict) else {}
            except Exception as e:
                logger.warning("coc cognition (clue) unavailable: %s", e)

        def _merge_lines(*groups: Any) -> list[str]:
            merged: list[str] = []
            for group in groups:
                if not isinstance(group, (list, tuple)):
                    continue
                for line in group:
                    text = str(line or "").strip()
                    if text and text not in merged:
                        merged.append(text)
            return merged

        reader_known = _merge_lines(
            canon_layers.get("reader_known") or [],
            clue_layers.get("reader_known") or [],
        )
        character_known = _merge_lines(clue_layers.get("character_known") or [])
        author_truth = _merge_lines(
            canon_layers.get("author_truth") or [],
            clue_layers.get("author_truth") or [],
        )
        self._current_coc_author_truth_snippets = self._extract_coc_author_truth_snippets(canon_layers, author_truth)

        if not (reader_known or character_known or author_truth):
            self._current_coc_cognition_overlay = ""
            return ""

        lines = [
            "【CoC认知边界（三层）】",
            "1) 读者已知：可直接写进正文；",
            "2) 角色已知：仅能通过角色视角与行动逐步呈现；",
            "3) 作者真相：禁止直接明说，只能以伏笔/误导/侧写方式间接处理。",
        ]
        if reader_known:
            lines.append("【读者已知】")
            for line in reader_known[:10]:
                lines.append(f"- {line}")
        if character_known:
            lines.append("【角色已知】")
            for line in character_known[:10]:
                lines.append(f"- {line}")
        if author_truth:
            lines.append("【作者真相（禁直出）】")
            for line in author_truth[:10]:
                lines.append(f"- {line}")
        self._current_coc_cognition_overlay = "\n".join(lines)
        return self._current_coc_cognition_overlay

    @staticmethod
    def _extract_coc_absolute_titles(overlay: Any, prompt: str) -> list[str]:
        titles: list[str] = []

        def _append_title(value: Any) -> None:
            text = str(value or "").strip()
            if text and text not in titles:
                titles.append(text)

        container = None
        if isinstance(overlay, dict):
            for key in ("entries", "items", "rules", "canon_items", "constraints"):
                if isinstance(overlay.get(key), list):
                    container = overlay.get(key)
                    break
        else:
            for key in ("entries", "items", "rules", "canon_items", "constraints"):
                value = getattr(overlay, key, None)
                if isinstance(value, list):
                    container = value
                    break

        if isinstance(container, list):
            for item in container:
                if isinstance(item, dict):
                    title = item.get("title") or item.get("name") or item.get("label") or item.get("key")
                    marker = (
                        item.get("marker")
                        or item.get("level")
                        or item.get("constraint_level")
                        or item.get("kind")
                        or item.get("scope")
                        or item.get("type")
                    )
                    is_absolute = bool(item.get("absolute") is True)
                else:
                    title = (
                        getattr(item, "title", None)
                        or getattr(item, "name", None)
                        or getattr(item, "label", None)
                        or getattr(item, "key", None)
                    )
                    marker = (
                        getattr(item, "marker", None)
                        or getattr(item, "level", None)
                        or getattr(item, "constraint_level", None)
                        or getattr(item, "kind", None)
                        or getattr(item, "scope", None)
                        or getattr(item, "type", None)
                    )
                    is_absolute = bool(getattr(item, "absolute", False) is True)

                marker_text = str(marker or "").strip().lower()
                if not is_absolute and marker_text:
                    is_absolute = ("absolute" in marker_text) or ("绝对" in marker_text)
                if is_absolute:
                    _append_title(title)

        for pattern in (
            r"(?:^|\n)\s*[-*]\s*(?:\[)?(?:absolute|绝对)(?:\])?\s*[:：\-]\s*([^\n]+)",
            r"(?:^|\n)\s*[-*]\s*([^\n（(]+?)\s*[（(]\s*(?:absolute|绝对)\s*[)）]",
            r"(?:^|\n)\s*[-*]\s*(?:\[[^\]]+\]\s*)?([^\n（(]+?)\s*[（(]\s*锁定\s*[:：]\s*(?:absolute|绝对)\s*[)）]",
        ):
            for match in re.findall(pattern, prompt or "", flags=re.IGNORECASE):
                _append_title(match.split("｜", 1)[0].split("|", 1)[0].strip())

        return titles

    @staticmethod
    def _extract_coc_author_only_clue_keys(overlay: Any, prompt: str) -> list[str]:
        keys: list[str] = []

        def _append_key(value: Any) -> None:
            text = str(value or "").strip()
            if text and text not in keys:
                keys.append(text)

        container = None
        if isinstance(overlay, dict):
            for name in ("clues", "entries", "items", "rules", "constraints"):
                if isinstance(overlay.get(name), list):
                    container = overlay.get(name)
                    break
        else:
            for name in ("clues", "entries", "items", "rules", "constraints"):
                value = getattr(overlay, name, None)
                if isinstance(value, list):
                    container = value
                    break

        if isinstance(container, list):
            for item in container:
                if isinstance(item, dict):
                    visibility = str(item.get("visibility") or "").strip().lower()
                    clue_key = item.get("clue_key") or item.get("key") or item.get("title") or item.get("name")
                else:
                    visibility = str(getattr(item, "visibility", "") or "").strip().lower()
                    clue_key = (
                        getattr(item, "clue_key", None)
                        or getattr(item, "key", None)
                        or getattr(item, "title", None)
                        or getattr(item, "name", None)
                    )
                if visibility == "author_only":
                    _append_key(clue_key)

        for pattern in (
            r"(?:^|\n)\s*[-*]\s*(?:\[[^\]]+\]\s*)?(?:clue_key|线索键)\s*[:：=]\s*([^\s|｜\n]+)[^\n]*(?:visibility|可见性)\s*[:：=]\s*author_only",
            r"(?:^|\n)\s*[-*]\s*(?:\[[^\]]*author_only[^\]]*\]\s*)?([^\s|｜\n]+)[^\n]*(?:author_only)",
        ):
            for match in re.findall(pattern, prompt or "", flags=re.IGNORECASE):
                _append_key(match.strip())

        return keys

    def _detect_coc_canon_conflicts(self, content: str) -> list[str]:
        text = str(content or "")
        if not text or not self._current_coc_absolute_titles:
            return []
        warnings: list[str] = []
        rewrite_markers = ("并非", "其实是", "原来是")
        for title in self._current_coc_absolute_titles:
            title_text = str(title or "").strip()
            if not title_text or title_text not in text:
                continue
            pattern = (
                rf"(?:{re.escape(title_text)}[\s\S]{{0,24}}(?:并非|其实是|原来是))"
                rf"|(?:(?:并非|其实是|原来是)[\s\S]{{0,24}}{re.escape(title_text)})"
            )
            if re.search(pattern, text):
                warnings.append(
                    f"CoC正典疑似冲突：绝对条目「{title_text}」附近出现改写词（{ '/'.join(rewrite_markers) }），请复核是否越界。"
                )
        return warnings

    def _detect_coc_clue_conflicts(self, content: str) -> list[str]:
        text = str(content or "")
        if not text or not self._current_coc_author_only_clue_keys:
            return []
        warnings: list[str] = []
        for clue_key in self._current_coc_author_only_clue_keys:
            key_text = str(clue_key or "").strip()
            if key_text and key_text in text:
                warnings.append(
                    f"CoC线索疑似越级：author_only 线索「{key_text}」出现在正文，请复核是否泄露。"
                )
        return warnings

    @staticmethod
    def _extract_coc_author_truth_snippets(canon_layers: dict[str, Any], author_truth_lines: list[str]) -> list[str]:
        snippets: list[str] = []
        for raw in canon_layers.get("author_truth_snippets") or []:
            text = str(raw or "").strip()
            if len(text) >= 8 and text not in snippets:
                snippets.append(text[:80])
        for line in author_truth_lines:
            text = str(line or "")
            if "：" in text:
                text = text.split("：", 1)[1]
            text = text.strip()
            if len(text) >= 12 and text not in snippets:
                snippets.append(text[:80])
        return snippets[:50]

    def _detect_coc_author_truth_leaks(self, content: str) -> list[str]:
        text = str(content or "")
        if not text or not self._current_coc_author_truth_snippets:
            return []
        warnings: list[str] = []
        for snippet in self._current_coc_author_truth_snippets:
            if snippet and snippet in text:
                warnings.append(
                    f"CoC作者真相疑似直出：正文出现作者层片段「{snippet[:30]}...」，建议改为伏笔或错位信息。"
                )
        return warnings

    @staticmethod
    def _ensure_generation_start_suffix(user_message: str) -> str:
        """给可视配置渲染出的 user prompt 补上统一的生成起笔标记。"""
        text = (user_message or "").rstrip()
        if text.endswith("开始撰写：") or text.endswith("开始撰写:"):
            return text
        return f"{text}\n\n开始撰写："

    @staticmethod
    def _render_visible_workflow_prompt(variables: Dict[str, Any]) -> Optional[Dict[str, str]]:
        """读取提示词广场中的工作流章节生成配置；不可用时返回 None 走内置兜底。"""
        try:
            from infrastructure.ai.prompt_manager import get_prompt_manager

            manager = get_prompt_manager()
            manager.ensure_seeded()
            rendered = manager.render("workflow-chapter-generation", variables)
        except Exception as e:
            logger.warning("workflow prompt config unavailable, using built-in fallback: %s", e)
            return None

        if not rendered:
            return None
        system = (rendered.get("system") or "").strip()
        user = (rendered.get("user") or "").strip()
        if not system or not user:
            return None
        return {"system": system, "user": user}

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
