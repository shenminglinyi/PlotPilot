"""上下文配额分配器 - 洋葱模型优先级挤压 + 全局收敛沙漏

核心设计：
- T0 级（绝对不删减）：系统 Prompt、当前幕摘要、强制伏笔、角色锚点、**生命周期行为准则**
- T1 级（按比例压缩）：图谱子网、近期幕摘要
- T2 级（动态水位线）：最近章节内容
- T3 级（可牺牲泡沫）：向量召回片段

全局倒计时与收敛沙漏（V7）：
- 根据当前章节 / 目标总章节数 计算 progress (0.0 ~ 1.0)
- 根据 progress 自动切换行为模式：开局(0-25%) / 发展(25-75%) / 收敛(75-90%) / 终局(90-100%)
- 行为准则作为最高优先级 T0 槽位注入，引导 AI 自然收束笔墨

当 Token 预算紧张时，从 T3 → T2 → T1 逐层挤压，T0 绝对保护。
"""
import asyncio
import concurrent.futures
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from application.engine.dtos.scene_director_dto import SceneDirectorInput, coerce_scene_director

from domain.novel.value_objects.novel_id import NovelId
from domain.novel.value_objects.chapter_id import ChapterId
from engine.core.entities.story import StoryPhase
from domain.novel.repositories.foreshadowing_repository import ForeshadowingRepository
from domain.novel.repositories.chapter_repository import ChapterRepository
from domain.bible.repositories.bible_repository import BibleRepository
from infrastructure.persistence.database.story_node_repository import StoryNodeRepository
from infrastructure.persistence.database.worldbuilding_repository import WorldbuildingRepository
from domain.ai.services.vector_store import VectorStore
from domain.ai.services.embedding_service import EmbeddingService
from application.ai.vector_retrieval_facade import VectorRetrievalFacade
from application.engine.services.context_budget_models import (
    BudgetAllocation,
    ContextSlot,
    PriorityTier,
)
from application.engine.services.context_budget_policy import (
    allocate_tier,
    truncate_t0_slots,
)
from application.engine.services.context_brief import (
    build_bridge_hint,
    build_character_state_hint,
    build_context_brief,
    build_debt_hint,
    get_chapter_generation_hint,
)
from application.engine.services.context_lifecycle import (
    DEFAULT_PHASE_THRESHOLDS,
    build_lifecycle_directive,
    classify_phase,
    estimate_total_chapters,
    get_phase_directives,
    load_phase_thresholds,
)
from application.engine.services.recent_chapter_context import (
    build_recent_chapters_context,
    excerpt_immediate_previous_chapter,
)
from application.engine.services.context_slot_providers import (
    build_immersion_details_slot_content,
    build_key_props_slot_content,
    build_narrative_promise_slot_content,
    build_storyline_slot_content,
    build_worldbuilding_core_slot_content,
    format_storyline_context_block,
)
from infrastructure.ai.prompt_registry import get_prompt_registry

logger = logging.getLogger(__name__)


def _sync_run_async(coro):
    """在同步上下文中运行 async 协程（处理已有事件循环的情况）。"""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # 已在事件循环中：在新线程中运行
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(coro)).result()


class ContextBudgetAllocator:
    """上下文配额分配器
    
    使用示例：
    ```python
    allocator = ContextBudgetAllocator(
        foreshadowing_repo=...,
        bible_repo=...,
        story_node_repo=...,
        ...
    )
    
    allocation = allocator.allocate(
        novel_id="novel-001",
        chapter_number=150,
        outline="林羽发现玉佩发热...",
        total_budget=35000
    )
    
    # 获取组装好的上下文
    context = allocation.get_final_context()
    
    # 查看分配详情（通过 logger 或返回值获取）
    # allocation.t0_reserved, allocation.compression_log
    ```
    """
    
    # Token 估算常量
    CHARS_PER_TOKEN_ZH = 1.5  # 中文：1 token ≈ 1.5 字符
    CHARS_PER_TOKEN_EN = 4.0  # 英文：1 token ≈ 4 字符
    
    # 默认配额比例
    # V9 减法改革: T0 从 35% 降至 20% — 约束是药不是饭
    # 过多的 T0 强制内容导致注意力坍塌，AI 从"写故事"变成"满足约束条件"
    # 把叙事债务、因果链、伤疤执念等降级到 T1，用自然语言的"编辑手记"替代结构化槽位
    T0_BUDGET_RATIO = 0.20   # 20% 给 T0（仅保留：FACT_LOCK + ANCHOR + 角色锚点 + 编辑手记）
    T1_BUDGET_RATIO = 0.30   # 30% 给 T1（降级内容：伤疤/债务/因果链/已完成节拍/线索）
    T2_BUDGET_RATIO = 0.35   # 35% 给 T2（动态：最近章节——这才是 AI 应该关注的重点）
    T3_BUDGET_RATIO = 0.15   # 15% 给 T3（向量召回）
    
    # 各槽位的默认上限
    MAX_FORESHADOWING_TOKENS = 2000
    MAX_CHARACTER_ANCHORS_TOKENS = 1500
    MAX_GRAPH_SUBNETWORK_TOKENS = 1500
    MAX_ACT_SUMMARIES_TOKENS = 1500
    MAX_RECENT_CHAPTERS_TOKENS = 8000   # 扩容：N-1 完整 + N-2 半量 + N-3~5 预览
    MAX_VECTOR_RECALL_TOKENS = 5000
    MAX_NARRATIVE_CONTRACT_TOKENS = 1400  # 向导五维 + 文风公约 + Bible 规则条目

    # 最近章节槽位：紧邻上一章侧重章末承接；更早章节仅章首短预览以省预算
    # V8 优化：增加章末保留量，提升章节间连贯性
    PREV_CHAPTER_BRIDGE_HEAD_CHARS = 300   # 章首略览
    PREV_CHAPTER_BRIDGE_TAIL_CHARS = 2000  # 章末完整保留（原 1200 → 2000）
    OLDER_CHAPTER_HEAD_PREVIEW_CHARS = 500

    def __init__(
        self,
        foreshadowing_repository: Optional[ForeshadowingRepository] = None,
        chapter_repository: Optional[ChapterRepository] = None,
        bible_repository: Optional[BibleRepository] = None,
        story_node_repository: Optional[StoryNodeRepository] = None,
        chapter_element_repository = None,
        triple_repository = None,
        vector_store: Optional[VectorStore] = None,
        embedding_service: Optional[EmbeddingService] = None,
        memory_engine: Optional['MemoryEngine'] = None,
        # Phase 3: 沙漏阶段可配置阈值
        phase_thresholds: Optional[Dict[str, float]] = None,
        # V8 Feed-forward: 上下文反哺管线（因果图谱 + 人物状态 + 叙事债务）
        context_assembler: Optional[Any] = None,
        storyline_repository=None,
        confluence_point_repository=None,
        worldbuilding_repository: Optional[WorldbuildingRepository] = None,
        evolution_presenter: Optional[Any] = None,
        evolution_repository: Optional[Any] = None,
        character_narrative_kernel: Optional[Any] = None,
        novel_repository: Optional[Any] = None,
        character_projection_service: Optional[Any] = None,
    ):
        self.foreshadowing_repo = foreshadowing_repository
        self.chapter_repo = chapter_repository
        self.bible_repo = bible_repository
        self.story_node_repo = story_node_repository
        self.chapter_element_repo = chapter_element_repository
        self.triple_repo = triple_repository

        # V6 记忆引擎（可选，用于 T0 槽位注入 FACT_LOCK / BEATS / CLUES）
        self.memory_engine = memory_engine

        # V8 Feed-forward: 上下文反哺管线
        self.context_assembler = context_assembler
        self.storyline_repo = storyline_repository
        self.confluence_repo = confluence_point_repository
        self.worldbuilding_repo = worldbuilding_repository
        self.evolution_presenter = evolution_presenter
        self.evolution_repository = evolution_repository
        self.character_narrative_kernel = character_narrative_kernel
        self.novel_repository = novel_repository
        self.character_projection_service = character_projection_service

        # Phase 3: 沙漏阶段阈值（可由 CPMS 节点 lifecycle-phase-directives 的变量覆盖）
        self._phase_thresholds = phase_thresholds or self._load_phase_thresholds()

        # 向量检索门面
        self.vector_facade = None
        if vector_store and embedding_service:
            self.vector_facade = VectorRetrievalFacade(vector_store, embedding_service)
    
    def _build_storyline_slot(self, novel_id: str, chapter_number: int) -> str:
        """构建故事线上下文槽位内容（按汇流距离动态分级）。"""
        return build_storyline_slot_content(
            self.storyline_repo,
            self.confluence_repo,
            novel_id,
            chapter_number,
        )

    def _build_narrative_contract_slot(self, novel_id: str) -> str:
        """向导确认的五维世界观 + Bible 文风/规则；与 DB 同步，不读共享内存。"""
        from application.world.services.narrative_contract_loader import (
            build_narrative_contract_for_novel,
        )

        return build_narrative_contract_for_novel(
            novel_id,
            bible_repository=self.bible_repo,
            worldbuilding_repository=self.worldbuilding_repo,
        )

    def _build_narrative_promise_slot(self, novel_id: str, chapter_number: int) -> str:
        """Build the compact story promise lock from the existing Novel aggregate."""
        return build_narrative_promise_slot_content(
            self.novel_repository,
            novel_id,
            chapter_number,
        )

    def _format_storyline_block(self, sl, confluences, chapter_number: int) -> str:
        """格式化单条故事线的上下文块。"""
        return format_storyline_context_block(sl, confluences, chapter_number)

    def estimate_tokens(self, text: str) -> int:
        """估算文本的 Token 数量
        
        混合文本的估算策略：
        - 检测中文字符比例
        - 根据比例加权计算
        """
        if not text:
            return 0
        
        # 统计中文字符
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        total_chars = len(text)
        
        if total_chars == 0:
            return 0
        
        chinese_ratio = chinese_chars / total_chars
        
        # 加权估算
        zh_tokens = chinese_chars / self.CHARS_PER_TOKEN_ZH
        en_tokens = (total_chars - chinese_chars) / self.CHARS_PER_TOKEN_EN
        
        return int(zh_tokens * chinese_ratio + en_tokens * (1 - chinese_ratio) + 0.5)
    
    def allocate(
        self,
        novel_id: str,
        chapter_number: int,
        outline: str,
        total_budget: int = 35000,
        scene_director: SceneDirectorInput = None,
        current_beat_index: int = 0,
    ) -> BudgetAllocation:
        """执行预算分配

        Args:
            novel_id: 小说 ID
            chapter_number: 当前章节号
            outline: 章节大纲
            total_budget: 总 Token 预算
            scene_director: 场记（``SceneDirectorAnalysis`` / ``dict`` / ``None``），内部统一为 dict
            current_beat_index: 当前节拍索引（断点续写时 > 0）

        Returns:
            BudgetAllocation: 分配结果
        """
        allocation = BudgetAllocation(total_budget=total_budget)

        scene_director_dict = coerce_scene_director(scene_director)

        # ========== V7 全局收敛沙漏：计算进度与阶段 ==========
        total_chapters = self._estimate_total_chapters(novel_id)
        progress = chapter_number / max(total_chapters, 1)
        phase = self._classify_phase(progress)
        allocation.progress = round(progress, 4)
        allocation.phase = phase
        allocation.total_chapters = total_chapters

        logger.info(
            f"[沙漏 V7] 进度: {chapter_number}/{total_chapters} = {progress:.1%} | "
            f"阶段: {phase.value}"
        )

        # ========== 第一步：收集所有内容 ==========
        slots = self._collect_all_slots(novel_id, chapter_number, outline, scene_director_dict, current_beat_index)
        
        # 提取过期伏笔用于终端强制约束
        pending_fs_slot = slots.get("pending_foreshadowings")
        if pending_fs_slot and pending_fs_slot.content:
            for line in pending_fs_slot.content.split('\n'):
                if "已过期" in line:
                    desc = line.split(":", 1)[-1].strip() if ":" in line else line.strip()
                    allocation.expired_foreshadows.append(desc)
        
        # ========== 第二步：计算 T0 强制保留量 ==========
        t0_slots = {name: slot for name, slot in slots.items() if slot.tier == PriorityTier.T0_CRITICAL}
        t0_total = sum(slot.tokens for slot in t0_slots.values())
        
        # Phase 2: T0 动态阈值保护 — T0 最多占 40% 总预算
        # 防止伏笔/角色等 T0 内容无限膨胀挤占 T2/T3
        T0_MAX_RATIO = 0.40
        t0_max = int(total_budget * T0_MAX_RATIO)
        if t0_total > t0_max:
            logger.warning(
                f"T0 内容 {t0_total} tokens 超出动态阈值 {t0_max} ({T0_MAX_RATIO:.0%} 总预算)，"
                f"触发 T0 截断保护"
            )
            t0_total = self._truncate_t0_slots(t0_slots, t0_max)
            allocation.compression_log.append(f"T0 动态阈值保护：截断至 {T0_MAX_RATIO:.0%} 总预算")
        
        if t0_total > total_budget:
            # 极端情况：T0 超出总预算，只能截断
            logger.warning(f"T0 强制内容 {t0_total} tokens 超出总预算 {total_budget}")
            allocation.compression_log.append("T0 超预算，强制截断")
            t0_total = self._truncate_t0_slots(t0_slots, total_budget)
        
        allocation.t0_reserved = t0_total
        
        # ========== 第三步：分配剩余预算给 T1/T2/T3 ==========
        remaining = total_budget - t0_total
        
        # T1 配额
        t1_budget = int(remaining * self.T1_BUDGET_RATIO / (self.T1_BUDGET_RATIO + self.T2_BUDGET_RATIO + self.T3_BUDGET_RATIO))
        t1_slots = {name: slot for name, slot in slots.items() if slot.tier == PriorityTier.T1_COMPRESSIBLE}
        t1_actual = self._allocate_tier(t1_slots, t1_budget, allocation.compression_log)
        allocation.t1_allocated = t1_actual
        
        # T2 配额
        remaining_after_t1 = remaining - t1_actual
        t2_budget = int(remaining_after_t1 * self.T2_BUDGET_RATIO / (self.T2_BUDGET_RATIO + self.T3_BUDGET_RATIO))
        t2_slots = {name: slot for name, slot in slots.items() if slot.tier == PriorityTier.T2_DYNAMIC}
        t2_actual = self._allocate_tier(t2_slots, t2_budget, allocation.compression_log)
        allocation.t2_allocated = t2_actual
        
        # T3 配额（剩余全部）
        remaining_after_t2 = remaining_after_t1 - t2_actual
        # Phase 2: T3 最低保障 — 至少保留 5% 总预算给向量召回
        # 防止 T0 膨胀 + T1/T2 挤占导致 T3（跨幕记忆）完全丢失
        T3_MIN_RATIO = 0.05
        t3_min_tokens = int(total_budget * T3_MIN_RATIO)
        t3_slots = {name: slot for name, slot in slots.items() if slot.tier == PriorityTier.T3_SACRIFICIAL}
        if remaining_after_t2 < t3_min_tokens and t3_slots:
            # 从 T2 中回收部分配额给 T3
            shortfall = t3_min_tokens - remaining_after_t2
            if t2_actual > shortfall:
                logger.info(
                    f"T3 最低保障：从 T2 回收 {shortfall} tokens 给 T3 "
                    f"(确保跨幕记忆不断裂)"
                )
                t2_actual -= shortfall
                allocation.t2_allocated = t2_actual
                remaining_after_t2 = t3_min_tokens
                allocation.compression_log.append(
                    f"T3 最低保障：{T3_MIN_RATIO:.0%} 总预算 ({t3_min_tokens} tokens)"
                )
        t3_actual = self._allocate_tier(t3_slots, remaining_after_t2, allocation.compression_log)
        allocation.t3_allocated = t3_actual
        
        # ========== 第四步：组装最终结果 ==========
        allocation.slots = slots
        allocation.used_tokens = t0_total + t1_actual + t2_actual + t3_actual
        allocation.remaining_tokens = total_budget - allocation.used_tokens
        
        if allocation.compression_log:
            allocation.compression_applied = True
            logger.info(f"[BudgetAllocator] 压缩日志: {allocation.compression_log}")
        
        logger.info(
            f"[BudgetAllocator] 分配完成: "
            f"T0={allocation.t0_reserved}, T1={allocation.t1_allocated}, "
            f"T2={allocation.t2_allocated}, T3={allocation.t3_allocated}, "
            f"总使用={allocation.used_tokens}/{total_budget}"
        )
        
        return allocation
    
    def _collect_all_slots(
        self,
        novel_id: str,
        chapter_number: int,
        outline: str,
        scene_director: Optional[Dict[str, Any]] = None,
        current_beat_index: int = 0,
    ) -> Dict[str, ContextSlot]:
        """收集所有上下文槽位"""
        slots = {}

        # ==================== T0: 强制内容（V9 减法改革：14→4 核心 + 编辑手记） ====================
        # 原则：约束是药不是饭。T0 只保留"不可违背的基础事实"和"创作引导"。
        # 伤疤/债务/因果链/节拍锁/线索等降级到 T1——可参考但不强制。

        # ── T0-1: 生命周期行为准则（全局收敛沙漏）—— priority=130 ──
        # 保留：这是宏观创作节奏的引导，不属于"约束过载"
        lifecycle_directive = self._build_lifecycle_directive(novel_id, chapter_number)
        slots["lifecycle_directive"] = ContextSlot(
            name="⏳生命周期行为准则(SANDGLASS)",
            tier=PriorityTier.T0_CRITICAL,
            content=lifecycle_directive,
            tokens=self.estimate_tokens(lifecycle_directive),
            max_tokens=600,
            priority=130,
        )

        # ── T0-2: 全书主线锚点(ANCHOR) —— priority=125 ──
        # 保留：一句话主线，极低 token 消耗，极高价值
        anchor_content = ""
        if self.context_assembler:
            try:
                anchor_content = self.context_assembler.build_story_anchor(novel_id)
            except Exception as e:
                logger.warning(f"STORY_ANCHOR 构建失败: {e}")
        slots["story_anchor"] = ContextSlot(
            name="全书主线锚点(ANCHOR)",
            tier=PriorityTier.T0_CRITICAL,
            content=anchor_content,
            tokens=self.estimate_tokens(anchor_content),
            max_tokens=300,  # V9: 从 500 砍到 300——一句话主线，不需要更多
            priority=125,
        )

        # ── T0-2a: 叙事承诺锁 —— 从 title/premise 派生，不新增存储模型 ──
        narrative_promise = self._build_narrative_promise_slot(novel_id, chapter_number)
        slots["narrative_promise"] = ContextSlot(
            name="叙事承诺锁(NARRATIVE_PROMISE)",
            tier=PriorityTier.T0_CRITICAL,
            content=narrative_promise,
            tokens=self.estimate_tokens(narrative_promise),
            max_tokens=420,
            priority=123,
        )

        # ── T0-2b: 创作契约（向导五维 + 文风公约 + Bible 规则）—— priority=122 ──
        narrative_contract = self._build_narrative_contract_slot(novel_id)
        slots["narrative_contract"] = ContextSlot(
            name="创作契约(NARRATIVE_CONTRACT)",
            tier=PriorityTier.T0_CRITICAL,
            content=narrative_contract,
            tokens=self.estimate_tokens(narrative_contract),
            max_tokens=self.MAX_NARRATIVE_CONTRACT_TOKENS,
            priority=122,
        )

        # ── T0-3: FACT_LOCK（不可篡改事实块）—— priority=120 ──
        # 保留但瘦身：只保留角色白名单 + 死亡名单 + 核心关系，删除时间线锁定（交给 T1）
        fact_lock_content = ""
        if self.memory_engine:
            try:
                fact_lock_content = self.memory_engine.build_fact_lock_section(
                    novel_id, chapter_number
                )
            except Exception as e:
                logger.warning(f"FACT_LOCK 构建失败: {e}")
        slots["fact_lock"] = ContextSlot(
            name="绝对事实边界(FACT_LOCK)",
            tier=PriorityTier.T0_CRITICAL,
            content=fact_lock_content,
            tokens=self.estimate_tokens(fact_lock_content),
            max_tokens=1500,  # V9: 从 2500 砍到 1500
            priority=120,
        )

        # ── T0-4: 角色锚点（核心人设）—— priority=110 ──
        # 保留：角色声线和习惯动作是写作的基石
        character_anchors = self._get_character_anchors(novel_id, chapter_number, scene_director, outline)
        slots["character_anchors"] = ContextSlot(
            name="角色锚点",
            tier=PriorityTier.T0_CRITICAL,
            content=character_anchors,
            tokens=self.estimate_tokens(character_anchors),
            max_tokens=self.MAX_CHARACTER_ANCHORS_TOKENS,
            priority=110,
        )

        # ── T0-5: 编辑手记（CONTEXT_BRIEF）—— priority=100 ──
        # V9 核心创新：用一段自然语言"编辑手记"替代 8 个结构化 T0 槽位
        # 合并：SCARS + DEBT_DUE + BRIDGE_DIRECTIVE + PREVIOUSLY_ON +
        #        COMPLETED_BEATS(精简) + REVEALED_CLUES(精简) +
        #        ACTIVE_ENTITY_MEMORY + CHARACTER_STATE_LOCK
        # 设计哲学：一段自然语言比 8 个 === xxx === 分隔符更容易被 LLM 融入创作
        context_brief = self._build_context_brief(novel_id, chapter_number, outline)
        slots["context_brief"] = ContextSlot(
            name="编辑手记(CONTEXT_BRIEF)",
            tier=PriorityTier.T0_CRITICAL,
            content=context_brief,
            tokens=self.estimate_tokens(context_brief),
            max_tokens=800,  # V9: 800 tokens 的自然语言手记，替代原来 10,000+ tokens 的结构化槽位
            priority=100,
        )

        evolution_context = self._build_evolution_presenter_slot(novel_id, chapter_number)
        slots["evolution_presenter"] = ContextSlot(
            name="叙事状态锁(EVOLUTION_STATE)",
            tier=PriorityTier.T0_CRITICAL,
            content=evolution_context,
            tokens=self.estimate_tokens(evolution_context),
            max_tokens=1200,
            priority=98,
        )

        # ── T0-6: 当前幕摘要 —— priority=95 ──
        act_summary = self._get_current_act_summary(novel_id, chapter_number)
        slots["current_act_summary"] = ContextSlot(
            name="当前幕摘要",
            tier=PriorityTier.T0_CRITICAL,
            content=act_summary,
            tokens=self.estimate_tokens(act_summary),
            max_tokens=600,  # V9: 增加上限控制
            priority=95,
        )
        
        # ==================== T1: 可压缩内容（V9: 从 T0 降级的内容 + 原有 T1） ====================
        # 降级原则：这些内容是"参考"而非"约束"，AI 可以选择性采纳
        
        # ── V9 降级: 角色伤疤与执念(SCARS) —— 从 T0(p=118) → T1(p=78) ──
        scars_content = ""
        if self.context_assembler:
            try:
                scars_content = self.context_assembler.build_scars_and_motivations(novel_id)
            except Exception as e:
                logger.warning(f"SCARS_AND_MOTIVATIONS 构建失败: {e}")
        slots["scars_and_motivations"] = ContextSlot(
            name="角色伤疤与执念(SCARS)",
            tier=PriorityTier.T1_COMPRESSIBLE,
            content=scars_content,
            tokens=self.estimate_tokens(scars_content),
            max_tokens=800,  # V9: 从 1500 砍到 800
            priority=78,
        )

        # ── V9 降级: 已完成节拍锁(COMPLETED_BEATS) —— 从 T0(p=115) → T1(p=76) ──
        beats_content = ""
        if self.memory_engine:
            try:
                beats_content = self.memory_engine.get_completed_beats_section(novel_id)
            except Exception as e:
                logger.warning(f"COMPLETED_BEATS 构建失败: {e}")
        slots["completed_beats"] = ContextSlot(
            name="已完成节拍(COMPLETED_BEATS)",
            tier=PriorityTier.T1_COMPRESSIBLE,
            content=beats_content,
            tokens=self.estimate_tokens(beats_content),
            max_tokens=1000,  # V9: 从 2000 砍到 1000
            priority=76,
        )

        # ── V9 降级: 叙事债务到期提醒(DEBT_DUE) —— 从 T0(p=108) → T1(p=74) ──
        debt_due_content = ""
        if self.context_assembler:
            try:
                debt_due_content = self.context_assembler.build_debt_due_block(
                    novel_id, chapter_number, outline
                )
            except Exception as e:
                logger.warning(f"DEBT_DUE 构建失败: {e}")
        slots["debt_due"] = ContextSlot(
            name="叙事备忘(DEBT_DUE)",
            tier=PriorityTier.T1_COMPRESSIBLE,
            content=debt_due_content,
            tokens=self.estimate_tokens(debt_due_content),
            max_tokens=500,  # V9: 从 800 砍到 500
            priority=74,
        )

        # ── V9 降级: 已揭露线索清单(REVEALED_CLUES) —— 从 T0(p=110) → T1(p=72) ──
        clues_content = ""
        if self.memory_engine:
            try:
                clues_content = self.memory_engine.get_revealed_clues_section(novel_id)
            except Exception as e:
                logger.warning(f"REVEALED_CLUES 构建失败: {e}")
        slots["revealed_clues"] = ContextSlot(
            name="已揭露线索(REVEALED_CLUES)",
            tier=PriorityTier.T1_COMPRESSIBLE,
            content=clues_content,
            tokens=self.estimate_tokens(clues_content),
            max_tokens=800,  # V9: 从 2000 砍到 800
            priority=72,
        )

        # ── V9 降级: 待回收伏笔 —— 从 T0(p=90) → T1(p=70) ──
        foreshadowing_content = self._get_pending_foreshadowings(novel_id, chapter_number)
        slots["pending_foreshadowings"] = ContextSlot(
            name="待回收伏笔",
            tier=PriorityTier.T1_COMPRESSIBLE,
            content=foreshadowing_content,
            tokens=self.estimate_tokens(foreshadowing_content),
            max_tokens=1000,  # V9: 从 2000 砍到 1000
            priority=70,
        )

        # ── V9 降级: Anti-AI 行为协议 —— 从 T0(p=135) → T1(p=69) ──
        # 降级理由：Anti-AI 规则虽然重要，但放在 T0 最高优先级会严重占用注意力；
        # 放在 T1 仍然会被注入，只是可以被压缩，防止约束过载
        anti_ai_protocol_content = self._build_anti_ai_protocol_block(novel_id, chapter_number)
        slots["anti_ai_protocol"] = ContextSlot(
            name="Anti-AI 行为协议(ANTI_AI_PROTOCOL)",
            tier=PriorityTier.T1_COMPRESSIBLE,
            content=anti_ai_protocol_content,
            tokens=self.estimate_tokens(anti_ai_protocol_content),
            max_tokens=1000,  # V9: 从 2000 砍到 1000
            priority=69,
        )

        # ── 图谱子网（一度关系）──
        graph_content = self._get_graph_subnetwork(novel_id, chapter_number, outline)
        slots["graph_subnetwork"] = ContextSlot(
            name="图谱子网",
            tier=PriorityTier.T1_COMPRESSIBLE,
            content=graph_content,
            tokens=self.estimate_tokens(graph_content),
            max_tokens=self.MAX_GRAPH_SUBNETWORK_TOKENS,
            priority=68,
        )

        # ── V8 T1: 未闭环因果链(CAUSAL_CHAINS) ──
        causal_chains_content = ""
        if self.context_assembler:
            try:
                causal_chains_content = self.context_assembler.build_causal_chains(novel_id)
            except Exception as e:
                logger.warning(f"CAUSAL_CHAINS 构建失败: {e}")
        slots["causal_chains"] = ContextSlot(
            name="未闭环因果链(CAUSAL_CHAINS)",
            tier=PriorityTier.T1_COMPRESSIBLE,
            content=causal_chains_content,
            tokens=self.estimate_tokens(causal_chains_content),
            max_tokens=800,
            priority=67,
        )

        # ── V9 降级: 人设冲突提醒 —— 从 T0(p=85) → T1(p=65) ──
        diagnosis_breakpoints = self._get_diagnosis_breakpoints(novel_id, chapter_number)
        slots["diagnosis_breakpoints"] = ContextSlot(
            name="人设冲突提醒",
            tier=PriorityTier.T1_COMPRESSIBLE,
            content=diagnosis_breakpoints,
            tokens=self.estimate_tokens(diagnosis_breakpoints),
            max_tokens=800,  # V9: 从 1500 砍到 800
            priority=65,
        )

        # ── 近期幕摘要 ──
        recent_acts = self._get_recent_act_summaries(novel_id, chapter_number, limit=3)
        slots["recent_act_summaries"] = ContextSlot(
            name="近期幕摘要",
            tier=PriorityTier.T1_COMPRESSIBLE,
            content=recent_acts,
            tokens=self.estimate_tokens(recent_acts),
            max_tokens=self.MAX_ACT_SUMMARIES_TOKENS,
            priority=60,
        )

        # ── V9 降级: 角色状态锁向量 —— 从 T0(p=128) → T1(p=58) ──
        character_state_lock_content = self._build_character_state_lock_block(novel_id, chapter_number)
        slots["character_state_lock"] = ContextSlot(
            name="角色状态锁(CHARACTER_STATE_LOCK)",
            tier=PriorityTier.T1_COMPRESSIBLE,
            content=character_state_lock_content,
            tokens=self.estimate_tokens(character_state_lock_content),
            max_tokens=600,  # V9: 从 1000 砍到 600
            priority=58,
        )
        
        # ── 冗余伏笔参考 ──
        deferred_foreshadowing_content = self._get_deferred_foreshadowings(novel_id, chapter_number)
        slots["deferred_foreshadowings"] = ContextSlot(
            name="冗余伏笔参考(爽文GC降级)",
            tier=PriorityTier.T1_COMPRESSIBLE,
            content=deferred_foreshadowing_content,
            tokens=self.estimate_tokens(deferred_foreshadowing_content),
            max_tokens=800,
            priority=55,
        )
        
        # ==================== T2: 动态内容 ====================
        
        # 6. 最近章节内容（limit=5：N-1/N-2 做章末衔接，N-3~N-5 做章首预览）
        recent_chapters = self._get_recent_chapters(novel_id, chapter_number, limit=5, current_beat_index=current_beat_index)
        slots["recent_chapters"] = ContextSlot(
            name="最近章节",
            tier=PriorityTier.T2_DYNAMIC,
            content=recent_chapters,
            tokens=self.estimate_tokens(recent_chapters),
            max_tokens=self.MAX_RECENT_CHAPTERS_TOKENS,
            priority=50,
        )
        
        # ==================== T3: 可牺牲内容 ====================
        
        # 7. 向量召回片段
        vector_content = self._get_vector_recall(novel_id, chapter_number, outline)
        slots["vector_recall"] = ContextSlot(
            name="向量召回",
            tier=PriorityTier.T3_SACRIFICIAL,
            content=vector_content,
            tokens=self.estimate_tokens(vector_content),
            max_tokens=self.MAX_VECTOR_RECALL_TOKENS,
            priority=40,
        )

        # ── T1-N: 故事线上下文（按汇流距离分级）── priority=72 ──
        if self.storyline_repo and self.confluence_repo:
            try:
                sl_content = self._build_storyline_slot(novel_id, chapter_number)
                if sl_content:
                    slots["storyline_context"] = ContextSlot(
                        name="故事线上下文(STORYLINE_CONTEXT)",
                        tier=PriorityTier.T1_COMPRESSIBLE,
                        content=sl_content,
                        tokens=self.estimate_tokens(sl_content),
                        max_tokens=1200,
                        priority=72,
                    )
            except Exception as _sl_err:
                logger.warning(f"故事线上下文构建失败: {_sl_err}")

        # ── T1: 世界核心规则（核心法则维度）── priority=71 ──
        # 单独抽出最高约束维度，确保预算压缩时仍清晰可见；
        # narrative_contract 含全部五维但混合文风/文化，此槽位专注硬规则。
        worldbuilding_core = self._build_worldbuilding_core_slot(novel_id)
        if worldbuilding_core:
            slots["worldbuilding_core"] = ContextSlot(
                name="世界核心规则(WORLD_RULES)",
                tier=PriorityTier.T1_COMPRESSIBLE,
                content=worldbuilding_core,
                tokens=self.estimate_tokens(worldbuilding_core),
                max_tokens=600,
                priority=71,
            )

        # ── T1: 世界沉浸感细节── priority=66 ──
        # 单独槽位避免沉浸感维度被 narrative_contract 压缩
        immersion_details = self._build_immersion_details_slot(novel_id)
        if immersion_details:
            slots["immersion_details"] = ContextSlot(
                name="世界沉浸感细节(IMMERSION)",
                tier=PriorityTier.T1_COMPRESSIBLE,
                content=immersion_details,
                tokens=self.estimate_tokens(immersion_details),
                max_tokens=400,
                priority=66,
            )

        # ── T1: 本章关键道具（用户标记 is_key）── priority=64 ──
        key_props = self._build_key_props_slot(novel_id)
        if key_props:
            slots["key_props"] = ContextSlot(
                name="本章关键道具(KEY_PROPS)",
                tier=PriorityTier.T1_COMPRESSIBLE,
                content=key_props,
                tokens=self.estimate_tokens(key_props),
                max_tokens=500,
                priority=64,
            )

        return slots

    def _build_evolution_presenter_slot(self, novel_id: str, chapter_number: int) -> str:
        if not self.evolution_presenter or not self.evolution_repository:
            return ""
        try:
            snapshot = self.evolution_repository.get_latest_active_before(
                novel_id, "main", chapter_number
            )
            if not snapshot:
                return ""
            return self.evolution_presenter.present(snapshot.ending_state)
        except Exception as e:
            logger.warning("Evolution presenter 构建失败: %s", e)
            return ""
    
    def _build_worldbuilding_core_slot(self, novel_id: str) -> str:
        """提取世界观核心硬规则字段。

        narrative_contract 含全部五维，但混合了文风公约和文化细节。
        此方法单独格式化最高约束优先级的核心法则维度，供 T1 专用槽位注入。
        """
        return build_worldbuilding_core_slot_content(self.worldbuilding_repo, novel_id)

    def _build_immersion_details_slot(self, novel_id: str) -> str:
        """提取世界观沉浸感细节维度。

        该槽位避免沉浸感信息被 narrative_contract 压缩掉。
        """
        return build_immersion_details_slot_content(self.worldbuilding_repo, novel_id)

    def _build_key_props_slot(self, novel_id: str) -> str:
        """提取用户标记 is_key=1 的关键道具，注入 T1 上下文。"""
        return build_key_props_slot_content(novel_id)

    def _truncate_t0_slots(self, t0_slots: Dict[str, ContextSlot], budget: int) -> int:
        """极端情况：截断 T0 内容"""
        return truncate_t0_slots(
            t0_slots,
            budget,
            chars_per_token_zh=self.CHARS_PER_TOKEN_ZH,
        )
    
    def _allocate_tier(
        self,
        tier_slots: Dict[str, ContextSlot],
        budget: int,
        compression_log: List[str],
    ) -> int:
        """分配某一层级的预算
        
        策略：
        1. 按优先级排序
        2. 高优先级的尽量保留
        3. 超出预算的低优先级内容按比例压缩
        """
        return allocate_tier(
            tier_slots,
            budget,
            compression_log,
            chars_per_token_zh=self.CHARS_PER_TOKEN_ZH,
        )
    
    # ==================== 内容收集方法 ====================
    
    def _get_chapter_generation_hint(self, novel_id: str, chapter_number: int) -> str:
        """读取用户手写的本章生成约束（generation_hint）"""
        return get_chapter_generation_hint(novel_id, chapter_number)

    def _build_context_brief(
        self,
        novel_id: str,
        chapter_number: int,
        outline: str,
    ) -> str:
        """V9 减法改革核心：构建自然语言编辑手记

        替代原来 8 个独立的 T0 结构化槽位（SCARS/DEBT/BRIDGE/PREVIOUSLY_ON/
        COMPLETED_BEATS/REVEALED_CLUES/ACTIVE_ENTITY_MEMORY/CHARACTER_STATE_LOCK），
        用一段 200-400 字的自然语言"编辑手记"告诉 AI 当前状态。

        用户手写的 generation_hint 作为最高优先级约束前置插入，直接覆盖自动推断。
        """
        return build_context_brief(
            context_assembler=self.context_assembler,
            novel_id=novel_id,
            chapter_number=chapter_number,
            outline=outline,
            generation_hint_loader=self._get_chapter_generation_hint,
            bridge_hint_builder=self._get_bridge_hint,
        )

    def _get_bridge_hint(self, novel_id: str, chapter_number: int) -> str:
        """获取前章衔接提示（柔性建议，非铁律）"""
        return build_bridge_hint(novel_id, chapter_number)

    def _get_character_state_hint(self, novel_id: str) -> str:
        """获取角色状态概要（精简版，替代详细的结构化 SCARS 锁）"""
        return build_character_state_hint(self.context_assembler, novel_id)

    def _get_debt_hint(self, novel_id: str, chapter_number: int, outline: str) -> str:
        """获取叙事债务温和提醒（替代强制收束令）"""
        return build_debt_hint(
            self.context_assembler,
            novel_id,
            chapter_number,
            outline,
        )

    def _get_chapter_bridge_directive(self, novel_id: str, chapter_number: int) -> str:
        """衔接引擎：从 DB 读取前章桥段，生成首段衔接指令（V9: 降级为 T1 参考）"""
        if chapter_number <= 1:
            return ""

        try:
            from application.engine.services.chapter_bridge_service import ChapterBridgeService
            from application.paths import get_db_path

            svc = ChapterBridgeService(db_path=str(get_db_path()))
            prev_bridge = svc.get_prev_chapter_bridge(novel_id, chapter_number)
            if prev_bridge:
                directive = svc.build_opening_directive(prev_bridge)
                if directive:
                    logger.debug(
                        "衔接指令注入 novel=%s ch=%s hook=%s",
                        novel_id, chapter_number,
                        prev_bridge.suspense_hook[:30] if prev_bridge.suspense_hook else "(无)",
                    )
                    return directive
        except Exception as e:
            logger.debug("衔接指令获取失败（可忽略）novel=%s ch=%s: %s", novel_id, chapter_number, e)

        return ""

    def _get_current_act_summary(self, novel_id: str, chapter_number: int) -> str:
        """获取当前幕摘要"""
        if not self.story_node_repo:
            return ""
        
        try:
            nodes = self.story_node_repo.get_by_novel_sync(novel_id)
            act_nodes = [n for n in nodes if n.node_type.value == "act"]
            
            # 找到包含当前章节的幕
            current_act = None
            for act in act_nodes:
                if act.chapter_start and act.chapter_end:
                    if act.chapter_start <= chapter_number <= act.chapter_end:
                        current_act = act
                        break
            
            if current_act:
                parts = [f"【{current_act.title}】"]
                if current_act.description:
                    parts.append(current_act.description)
                if current_act.narrative_arc:
                    parts.append(f"叙事弧线: {current_act.narrative_arc}")
                return "\n".join(parts)
            
        except Exception as e:
            logger.warning(f"获取当前幕摘要失败: {e}")
        
        return ""
    
    # 爽文引擎: T0 伏笔最大展示数量（防止 T0 膨胀；+2 为用户星标条目留余量）
    MAX_T0_FORESHADOWING_ITEMS = 8

    def _get_pending_foreshadowings(self, novel_id: str, chapter_number: int) -> str:
        """获取待回收伏笔（轨道二核心）- 爽文引擎: 使用 T0 精选筛选，剥离冗长 pending。"""
        if not self.foreshadowing_repo:
            return ""
        
        try:
            nid = NovelId(novel_id)
            registry = self.foreshadowing_repo.get_by_novel_id(nid)
            
            if not registry:
                return ""
            
            # 爽文引擎: 使用 T0 筛选方法，剥离冗长 pending 伏笔
            pending_foreshadows = registry.get_t0_eligible_foreshadowings(
                current_chapter=chapter_number,
                max_items=self.MAX_T0_FORESHADOWING_ITEMS,
            )
            pending_subtext = registry.get_pending_subtext_entries()
            
            lines = []
            
            # 爽文引擎: get_t0_eligible_foreshadowings 已排序，无需再次排序
            if pending_foreshadows:
                lines.append("【待回收伏笔（爽文GC精选）】")
                for f in pending_foreshadows[:self.MAX_T0_FORESHADOWING_ITEMS]:
                    importance_mark = "重要" if f.importance.value >= 3 else ""
                    
                    # 构建状态标记
                    status_mark = ""
                    if f.suggested_resolve_chapter:
                        if f.suggested_resolve_chapter <= chapter_number:
                            status_mark = "已过期"
                        elif f.suggested_resolve_chapter <= chapter_number + 3:
                            status_mark = "即将到期"
                        else:
                            status_mark = f"预期Ch{f.suggested_resolve_chapter}"
                    
                    lines.append(
                        f"- Ch{f.planted_in_chapter} {importance_mark} {status_mark}: {f.description}"
                    )
            
            # 对潜台词按星标 > 预期回收章节排序
            def subtext_sort_key(e):
                suggested = getattr(e, 'suggested_resolve_chapter', None)
                importance = getattr(e, 'importance', 'medium')
                importance_val = {'low': 1, 'medium': 2, 'high': 3, 'critical': 4}.get(importance, 2)
                # 用户标记「本章重点」→ 最高优先级
                is_priority = getattr(e, 'is_priority_for_chapter', False)
                priority_tier = 0 if is_priority else 1

                if suggested:
                    if suggested <= chapter_number:
                        return (priority_tier, 0, -importance_val, suggested)
                    else:
                        return (priority_tier, 1, -importance_val, suggested)
                else:
                    return (priority_tier, 2, -importance_val, 9999)
            
            sorted_subtext = sorted(pending_subtext, key=subtext_sort_key)
            
            if sorted_subtext:
                lines.append("\n【伏笔手账本·待兑现疑问】")
                for entry in sorted_subtext[:5]:  # 最多 5 个
                    importance = getattr(entry, 'importance', 'medium')
                    suggested = getattr(entry, 'suggested_resolve_chapter', None)
                    
                    status_mark = ""
                    if suggested:
                        if suggested <= chapter_number:
                            status_mark = "已过期"
                        elif suggested <= chapter_number + 3:
                            status_mark = "即将到期"
                        else:
                            status_mark = f"预期Ch{suggested}"
                    
                    lines.append(
                        f"- Ch{entry.chapter} [{entry.character_id}] {status_mark}: {entry.question}"
                    )
            
            return "\n".join(lines)
            
        except Exception as e:
            logger.warning(f"获取待回收伏笔失败: {e}")
        
        return ""
    
    def _get_deferred_foreshadowings(self, novel_id: str, chapter_number: int) -> str:
        """爽文引擎: 获取被 T0 剥离的冗长 pending 伏笔（降级到 T1）"""
        if not self.foreshadowing_repo:
            return ""
        
        try:
            nid = NovelId(novel_id)
            registry = self.foreshadowing_repo.get_by_novel_id(nid)
            
            if not registry:
                return ""
            
            deferred = registry.get_deferred_foreshadowings(current_chapter=chapter_number)
            
            if not deferred:
                return ""
            
            lines = ["【冗余伏笔参考（爽文GC降级，非紧急）】"]
            for f in deferred[:8]:  # 最多 8 个
                age = chapter_number - f.planted_in_chapter
                lines.append(
                    f"- Ch{f.planted_in_chapter} [age={age}] {f.importance.name}: {f.description[:60]}"
                )
            
            return "\n".join(lines)
            
        except Exception as e:
            logger.warning(f"获取冗余伏笔参考失败: {e}")
        
        return ""
    
    def _get_character_anchors(
        self,
        novel_id: str,
        chapter_number: int,
        scene_director: Optional[Dict[str, Any]] = None,
        outline: str = "",
    ) -> str:
        """获取角色锚点（轨道二核心 - 集成智能调度）
        
        核心改进：
        1. 从章节大纲中提取提及的角色（最高优先级）
        2. 从 chapter_elements 表查询最近出场的角色
        3. 根据重要性级别和活动度排序
        4. 检测刚登场的角色，添加连续性约束
        5. 应用 POV 防火墙规则
        """
        if not self.bible_repo:
            return ""
        
        try:
            kernel = self._get_character_kernel()
            if kernel:
                plan = kernel.plan_cast(
                    novel_id,
                    chapter_number,
                    outline,
                    scene_director=scene_director,
                )
                # Generation is allowed to auto-materialize the cast contract.
                kernel.apply_cast_plan(plan)
                locks = self._projection_locks_for_plan(novel_id, plan, tier="t0")
                if not locks:
                    locks = kernel.build_context_locks(novel_id, chapter_number, plan=plan).t0.strip()
                parts = []
                if locks:
                    parts.append("【角色状态锚点】\n" + locks)
                loc_hint = self._format_scene_location_hints(
                    self.bible_repo.get_by_novel_id(NovelId(novel_id)),
                    outline,
                    scene_director,
                )
                if loc_hint:
                    parts.append(loc_hint)
                if parts:
                    return "\n\n".join(parts)

            # 确保 novel_id 是正确的类型
            from domain.novel.value_objects.novel_id import NovelId
            if isinstance(novel_id, str):
                novel_id_obj = NovelId(novel_id)
            else:
                novel_id_obj = novel_id
                
            bible = self.bible_repo.get_by_novel_id(novel_id_obj)
            if not bible or not hasattr(bible, 'characters'):
                return ""
            
            # ========== Step 1: 智能角色调度 ==========
            selected_characters = self._schedule_characters(
                bible.characters,
                novel_id,
                chapter_number,
                outline,
                scene_director
            )
            
            # ========== Step 2: 构建角色锚点文本 ==========
            lines = ["【角色状态锚点】"]
            
            for char, is_recently_appeared in selected_characters:
                # POV 防火墙：检查是否应该显示隐藏信息
                profile_parts = []
                
                # 公开信息
                if hasattr(char, 'public_profile') and char.public_profile:
                    profile_parts.append(char.public_profile)
                elif char.description:
                    profile_parts.append(char.description[:100])  # 限制长度
                
                # 检查隐藏信息
                if hasattr(char, 'hidden_profile') and char.hidden_profile:
                    reveal_chapter = getattr(char, 'reveal_chapter', None)
                    if reveal_chapter is None or chapter_number >= reveal_chapter:
                        profile_parts.append(f"[隐藏面] {char.hidden_profile}")
                
                # 心理状态锚点（核心）
                if hasattr(char, 'mental_state') and char.mental_state:
                    mental_reason = getattr(char, 'mental_state_reason', '')
                    if mental_reason:
                        profile_parts.append(f"心理: {char.mental_state}（{mental_reason}）")
                    else:
                        profile_parts.append(f"心理: {char.mental_state}")
                
                # 口头禅/习惯动作
                if hasattr(char, 'verbal_tic') and char.verbal_tic:
                    profile_parts.append(f"口头禅: {char.verbal_tic}")
                if hasattr(char, 'idle_behavior') and char.idle_behavior:
                    profile_parts.append(f"习惯动作: {char.idle_behavior}")

                t0_psyche = self._format_character_t0_bible(char, chapter_number)
                if t0_psyche:
                    profile_parts.append(t0_psyche)

                # 刚登场标记
                if is_recently_appeared:
                    profile_parts.append("刚登场，需保持一致性")
                
                lines.append(f"\n- {char.name}: " + " | ".join(profile_parts))
            
            logger.info(
                f"[CharacterAnchors] 选中 {len(selected_characters)} 个角色, "
                f"包含 {sum(1 for _, r in selected_characters if r)} 个刚登场角色"
            )

            loc_hint = self._format_scene_location_hints(bible, outline, scene_director)
            if loc_hint:
                lines.append("\n" + loc_hint)

            return "\n".join(lines)
        
        except Exception as e:
            logger.warning(f"获取角色锚点失败: {e}")
        
        return ""
    
    def _format_character_t0_bible(self, char: Any, chapter_number: int) -> str:
        """四维心理与声线结构 — 小说家用法：信念/禁忌驱动分叉，创伤驱动节拍，声线交给对白而非旁白标签。"""
        parts: List[str] = []
        cb = (getattr(char, "core_belief", None) or "").strip()
        if cb:
            parts.append(f"T0·信念:{cb[:260]}")
        for tab in (getattr(char, "moral_taboos", None) or [])[:4]:
            ts = str(tab).strip()
            if ts:
                parts.append(f"T0·禁忌:{ts[:140]}")
        for w in (getattr(char, "active_wounds", None) or [])[:3]:
            if not isinstance(w, dict):
                continue
            trig = (w.get("trigger") or "").strip()[:100]
            eff = (w.get("effect") or "").strip()[:100]
            if trig or eff:
                parts.append(f"T0·创伤触发:{trig}→{eff}")
        vp = getattr(char, "voice_profile", None) or {}
        if isinstance(vp, dict) and vp:
            bits = [str(vp[k]) for k in ("style", "sentence_pattern", "speech_tempo") if vp.get(k)]
            if bits:
                parts.append("T0·声线结构:" + " / ".join(bits)[:140])
        if parts:
            return " · ".join(parts)
        return ""

    def _format_scene_location_hints(
        self,
        bible: Any,
        outline: str,
        scene_director: Optional[Dict[str, Any]],
    ) -> str:
        """大纲 / 场记中出现的地点与势力（文明）— 与正文 [[loc:…]] / faction 类型对齐。"""
        if not bible or not getattr(bible, "locations", None):
            return ""
        blob = outline or ""
        sd_locs: List[str] = []
        if scene_director and isinstance(scene_director.get("locations"), list):
            sd_locs = [str(x) for x in scene_director["locations"] if x]
        hits: List[str] = []
        for loc in bible.locations:
            nm = getattr(loc, "name", "") or ""
            if not nm:
                continue
            if nm in blob or nm in sd_locs:
                ltype = (getattr(loc, "location_type", None) or "other").lower()
                tag = "势力" if ltype == "faction" else "地点"
                desc = (getattr(loc, "description", None) or "")[:160]
                hits.append(f"- [{tag}] {nm}: {desc}")
        if not hits:
            return ""
        return "【本场空间 / 势力】\n" + "\n".join(hits[:10])

    def _schedule_characters(
        self,
        all_characters: List,
        novel_id: str,
        chapter_number: int,
        outline: str,
        scene_director: Optional[Dict[str, Any]] = None,
    ) -> List[tuple]:
        """智能角色调度（核心算法）

        优先级：
          1. chapter_elements 中预规划的选角（作者手动排班，或前次 StateUpdater 写入）
          2. 大纲 / 场记中提及的角色（AppearanceScheduler fallback）
          3. Bible 重要性 + 近期活跃度补位

        Returns:
            List[Tuple[Character, bool]]: [(角色, 是否刚登场), ...]
        """
        MAX_CHARACTERS = 7

        # Step 0: 读取当前章节预规划选角 {element_id → importance_priority}
        #         priority: 0=major, 1=normal, 2=minor
        planned_cast = self._get_planned_cast(novel_id, chapter_number)

        # Step 1: 大纲 + 场记提及名
        mentioned_names: set = set()
        if outline:
            for char in all_characters:
                if char.name in outline:
                    mentioned_names.add(char.name)
        if scene_director and scene_director.get("characters"):
            mentioned_names.update(scene_director["characters"])

        # Step 2: 最近 5 章活跃度
        recent_characters = self._get_recent_characters(novel_id, chapter_number)

        # Step 3: 分桶 — 预规划 vs 非预规划
        planned_list: List[tuple] = []    # (char, is_recent, planned_pri)
        unplanned_list: List[tuple] = []  # (char, is_recent, bible_pri, in_outline)

        for char in all_characters:
            char_id = char.character_id.value if hasattr(char, 'character_id') else None
            is_recent = self._is_recently_appeared(char, recent_characters, chapter_number)

            if char_id and char_id in planned_cast:
                planned_list.append((char, is_recent, planned_cast[char_id]))
            else:
                bible_pri = self._get_char_importance(char)
                in_outline = char.name in mentioned_names
                unplanned_list.append((char, is_recent, bible_pri, in_outline))

        # Step 4: 预规划按 importance 排序（major → normal → minor）
        planned_list.sort(key=lambda x: x[2])

        # Step 5: 非预规划按（大纲提及 → Bible 重要性 → 活跃度）排序
        unplanned_list.sort(key=lambda x: (
            not x[3],                                           # 大纲提及优先
            x[2],                                               # Bible 重要性
            -self._get_activity_score(x[0], recent_characters), # 活跃度降序
        ))

        # Step 6: 预规划优先填位，剩余槽位由 fallback 补充
        selected: List[tuple] = [(c, r) for c, r, _ in planned_list]
        remaining = MAX_CHARACTERS - len(selected)
        for char, is_recent, _, _ in unplanned_list[:remaining]:
            selected.append((char, is_recent))

        return selected[:MAX_CHARACTERS]

    def _get_planned_cast(self, novel_id: str, chapter_number: int) -> Dict[str, int]:
        """返回 {element_id: importance_priority} — priority: 0=major, 1=normal, 2=minor。

        如果没有预规划记录（作者还未排班），返回空字典 → fallback 到 AppearanceScheduler。
        """
        if not self.chapter_element_repo:
            return {}
        try:
            chapter_id = self._get_chapter_node_id(novel_id, chapter_number)
            if not chapter_id:
                return {}
            rows = self.chapter_element_repo.get_planned_cast_sync(chapter_id)
            importance_priority = {'major': 0, 'normal': 1, 'minor': 2}
            return {r['element_id']: importance_priority.get(r['importance'], 1) for r in rows}
        except Exception as e:
            logger.warning(f"读取预规划选角失败: {e}")
            return {}

    def _get_chapter_node_id(self, novel_id: str, chapter_number: int) -> Optional[str]:
        """通过 story_node_repo 获取指定章节的 story_nodes.id。"""
        if not self.story_node_repo:
            return None
        try:
            nodes = self.story_node_repo.get_by_novel_sync(novel_id)
            for node in nodes:
                nt = node.node_type
                nt_val = nt.value if hasattr(nt, 'value') else str(nt)
                if nt_val == 'chapter' and node.number == chapter_number:
                    return node.id
            return None
        except Exception as e:
            logger.warning(f"获取章节节点ID失败: {e}")
            return None
    
    def _get_recent_characters(self, novel_id: str, chapter_number: int) -> Dict[str, Dict]:
        """从 chapter_elements 表查询最近 5 章的角色活动统计。

        Returns:
            Dict[element_id, {"count": int, "last_chapter": int}]
        """
        if not self.chapter_element_repo:
            return {}
        try:
            rows = self.chapter_element_repo.get_recent_char_activity_sync(
                novel_id, chapter_number, window=5
            )
            return {r['element_id']: {'count': r['count'], 'last_chapter': r['last_chapter']} for r in rows}
        except Exception as e:
            logger.warning(f"查询最近角色活动失败: {e}")
            return {}
    
    def _is_recently_appeared(self, char, recent_characters: Dict, chapter_number: int) -> bool:
        """判断角色是否刚登场（最近1-2章首次出现）"""
        char_id = char.character_id.value
        
        if char_id not in recent_characters:
            # 角色从未出现过，可能是新角色
            return True
        
        activity = recent_characters[char_id]
        
        # 如果只出场过1次，且在最近2章内
        if activity["count"] == 1 and (chapter_number - activity["last_chapter"]) <= 2:
            return True
        
        return False
    
    def _get_char_importance(self, char) -> int:
        """获取角色重要性优先级（数字越小优先级越高）"""
        # 从 CharacterImportance 映射到优先级
        if hasattr(char, 'importance'):
            priority_map = {
                'protagonist': 0,
                'major_supporting': 1,
                'important_supporting': 2,
                'minor': 3,
                'background': 4
            }
            return priority_map.get(char.importance.value if hasattr(char.importance, 'value') else char.importance, 5)
        
        # 默认从描述推断
        if hasattr(char, 'description'):
            desc = char.description.lower()
            if '主角' in desc or '主人公' in desc:
                return 0
            elif '主要配角' in desc:
                return 1
            elif '配角' in desc:
                return 2
        
        return 3  # 默认次要角色
    
    def _get_activity_score(self, char, recent_characters: Dict) -> int:
        """获取角色活动度分数"""
        char_id = char.character_id.value
        
        if char_id not in recent_characters:
            return 0
        
        return recent_characters[char_id].get("count", 0)
    
    def _get_graph_subnetwork(
        self,
        novel_id: str,
        chapter_number: int,
        outline: str,
    ) -> str:
        """获取知识图谱子网（一度关系 + 触发词召回 + 向量语义检索）
        
        核心策略（参考设计文档）：
        1. 一度关系（必带）：出场人物/地点的直接关系
        2. 触发词条件召回（选带）：根据大纲关键词召回特定设定
        3. 向量语义检索：基于大纲内容进行语义相似度检索
        4. 章节范围筛选：优先返回当前章节前后相关的三元组
        
        Args:
            novel_id: 小说 ID
            chapter_number: 当前章节号
            outline: 章节大纲（用于触发词检测和语义检索）
        
        Returns:
            格式化的图谱子网文本
        """
        if not self.triple_repo:
            return ""
        
        try:
            # ========== Step 1: 从大纲中提取实体名称 ==========
            mentioned_entities = self._extract_entities_from_outline(outline)
            
            # ========== Step 2: 一度关系召回 ==========
            one_hop_triples = []
            if mentioned_entities:
                one_hop_triples = self.triple_repo.get_by_entity_ids_sync(
                    novel_id, mentioned_entities
                )
            
            # ========== Step 3: 触发词条件召回 ==========
            trigger_triples = self._get_trigger_based_triples(novel_id, outline, mentioned_entities)
            
            # ========== Step 4: 向量语义检索 ==========
            semantic_triples = self._get_semantic_triples(novel_id, outline)
            
            # ========== Step 5: 最近章节相关三元组（补充） ==========
            recent_triples = self.triple_repo.get_recent_triples_sync(
                novel_id, chapter_number, chapter_range=5, limit=20
            )
            
            # ========== Step 6: 合并去重 ==========
            all_triples = {}
            for t in one_hop_triples + trigger_triples + semantic_triples + recent_triples:
                if t.id not in all_triples:
                    all_triples[t.id] = t
            
            # 星标三元组优先，其次置信度和相关章节数
            starred_ids = set(self.triple_repo.get_starred_triple_ids_sync(novel_id))
            sorted_triples = sorted(
                all_triples.values(),
                key=lambda x: (
                    0 if x.id in starred_ids else 1,  # 星标优先
                    -(x.confidence or 0),
                    -len(x.related_chapters or []),
                )
            )[:30]  # 最多 30 条
            
            if not sorted_triples:
                return ""
            
            # ========== Step 7: 格式化输出 ==========
            return self._format_graph_subnetwork(sorted_triples, chapter_number)
            
        except Exception as e:
            logger.warning(f"获取图谱子网失败: {e}")
            return ""
    
    def _extract_entities_from_outline(self, outline: str) -> List[str]:
        """从大纲中提取实体名称
        
        简单实现：提取书名号《》中的内容作为作品名，
        引号「」『』中的内容可能为角色名或地点名。
        
        后续可以结合 Bible 的角色列表进行精确匹配。
        """
        entities = []
        
        # 提取书名号中的内容
        import re
        book_pattern = r'《([^》]+)》'
        entities.extend(re.findall(book_pattern, outline))
        
        # 提取单引号中的内容
        single_quote_pattern = r'「([^」]+)」'
        entities.extend(re.findall(single_quote_pattern, outline))
        
        # 提取双引号中的内容
        double_quote_pattern = r'『([^』]+)』'
        entities.extend(re.findall(double_quote_pattern, outline))
        
        # 如果有 Bible 仓库，尝试从角色列表中匹配
        if self.bible_repo:
            try:
                from domain.novel.value_objects.novel_id import NovelId
                bible = self.bible_repo.get_by_novel_id(NovelId(self._current_novel_id))
                if bible and hasattr(bible, 'characters'):
                    for char in bible.characters:
                        if char.name in outline:
                            entities.append(char.name)
                            # 也添加角色 ID
                            if hasattr(char, 'character_id'):
                                entities.append(char.character_id.value)
            except Exception:
                pass
        
        return list(set(entities))
    
    # 临时存储当前 novel_id（用于 _extract_entities_from_outline）
    _current_novel_id: str = ""
    
    def _get_trigger_based_triples(
        self,
        novel_id: str,
        outline: str,
        mentioned_entities: List[str],
    ) -> List:
        """基于触发词召回三元组
        
        触发词映射表（参考设计文档）：
        - "战斗" → 武器属性、战斗技能
        - "魔法" → 力量体系规则
        - "潜入" → 地形死角、安保规则
        - "交易" → 经济模式、货币设定
        """
        if not self.triple_repo:
            return []
        
        # 触发词到谓词的映射
        TRIGGER_PREDICATE_MAP = {
            "战斗": ["使用", "装备", "拥有", "擅长", "技能", "武器"],
            "打斗": ["使用", "装备", "拥有", "擅长", "技能", "武器"],
            "对决": ["使用", "装备", "拥有", "擅长", "技能", "武器"],
            "魔法": ["修炼", "掌握", "领悟", "功法", "法术", "属性"],
            "修炼": ["修炼", "掌握", "领悟", "功法", "法术", "境界"],
            "潜入": ["位于", "通往", "隐藏", "暗道", "出口"],
            "交易": ["拥有", "购买", "出售", "价值", "货币"],
            "争吵": ["关系", "敌对", "矛盾"],
            "冲突": ["关系", "敌对", "矛盾"],
        }
        
        triggered_predicates = []
        for trigger, predicates in TRIGGER_PREDICATE_MAP.items():
            if trigger in outline:
                triggered_predicates.extend(predicates)
        
        if not triggered_predicates:
            return []
        
        # 去重
        triggered_predicates = list(set(triggered_predicates))
        
        # 查询相关三元组
        return self.triple_repo.search_by_predicate_sync(
            novel_id,
            triggered_predicates,
            subject_ids=mentioned_entities if mentioned_entities else None,
            limit=20,
        )
    
    def _get_semantic_triples(
        self,
        novel_id: str,
        outline: str,
    ) -> List:
        """基于向量语义检索召回三元组
        
        使用向量相似度搜索找到与大纲语义相关的三元组。
        需要预先通过 TripleIndexingService 索引三元组。
        
        Args:
            novel_id: 小说 ID
            outline: 章节大纲
        
        Returns:
            相关的三元组列表
        """
        # 检查是否有向量检索门面
        if not self.vector_facade:
            return []
        
        try:
            from application.analyst.services.triple_indexing_service import TripleIndexingService
            
            # 创建三元组索引服务
            triple_indexing = TripleIndexingService(
                vector_store=self.vector_facade.vector_store,
                embedding_service=self.vector_facade.embedding_service,
            )
            
            # 执行语义检索
            results = triple_indexing.sync_search(
                novel_id=novel_id,
                query=outline,
                limit=10,
                min_score=0.5,
            )
            
            if not results:
                return []
            
            # 从结果中提取 triple_id，然后从数据库获取完整的三元组
            triple_ids = []
            for hit in results:
                payload = hit.get("payload", {})
                triple_id = payload.get("triple_id")
                if triple_id:
                    triple_ids.append(triple_id)
            
            # 从数据库获取三元组
            if not triple_ids:
                return []
            
            # 获取所有相关三元组
            all_triples = self.triple_repo.get_by_novel_sync(novel_id)
            id_to_triple = {t.id: t for t in all_triples}
            
            # 按检索顺序返回
            semantic_triples = []
            for tid in triple_ids:
                if tid in id_to_triple:
                    semantic_triples.append(id_to_triple[tid])
            
            logger.info(f"[SemanticSearch] 找到 {len(semantic_triples)} 个语义相关三元组")
            return semantic_triples
            
        except Exception as e:
            logger.debug(f"向量语义检索失败（可能未索引）: {e}")
            return []
    
    def _format_graph_subnetwork(self, triples: List, current_chapter: int) -> str:
        """格式化图谱子网为可读文本
        
        输出格式：
        【图谱子网】
        
        [人物关系]
        - 李明 —认识→ 王总 (第5章)
        - 李明 —师徒→ 柳月 (第2章)
        
        [人物状态]
        - 李明: 心理(愤怒边缘) | 当前状态(受伤)
        
        [地点信息]
        - 废弃工厂 —位于→ 城东郊区 | 地形(复杂)
        
        [道具/技能]
        - 李明 —装备→ 破军剑 | 属性(攻击+50)
        """
        lines = ["【图谱子网】"]
        
        # 按类型分组
        character_relations = []  # 人物关系
        character_states = []     # 人物状态
        location_info = []        # 地点信息
        item_skills = []          # 道具/技能
        other_info = []           # 其他
        
        for t in triples:
            subj = t.subject_id or ""
            pred = t.predicate or ""
            obj = t.object_id or ""
            
            # 格式化章节信息
            chapter_info = ""
            if t.first_appearance:
                chapter_info = f"首次出现:第{t.first_appearance}章"
            if t.related_chapters:
                chapters_str = ",".join(str(c) for c in t.related_chapters[:3])
                if chapter_info:
                    chapter_info += f" | 相关:第{chapters_str}章"
                else:
                    chapter_info = f"相关:第{chapters_str}章"
            
            # 描述信息
            desc = t.description or ""
            
            # 分类处理
            if t.subject_type == "character" and t.object_type == "character":
                # 人物-人物关系
                relation_str = f"- {subj} —{pred}→ {obj}"
                if chapter_info:
                    relation_str += f" ({chapter_info})"
                character_relations.append(relation_str)
                
            elif t.subject_type == "character" and t.object_type == "location":
                # 人物-地点关系
                loc_str = f"- {subj} —{pred}→ {obj}"
                if desc:
                    loc_str += f" | {desc[:50]}"
                location_info.append(loc_str)
                
            elif t.subject_type == "character" and t.object_type == "item":
                # 人物-道具关系
                item_str = f"- {subj} —{pred}→ {obj}"
                if desc:
                    item_str += f" | {desc[:50]}"
                item_skills.append(item_str)
                
            elif t.subject_type == "location":
                # 地点相关
                loc_str = f"- {subj} —{pred}→ {obj}"
                if desc:
                    loc_str += f" | {desc[:50]}"
                location_info.append(loc_str)
                
            elif pred in ["状态", "心理", "当前状态"]:
                # 人物状态
                state_str = f"- {subj}: {pred}({obj})"
                if desc:
                    state_str += f" | {desc[:30]}"
                character_states.append(state_str)
                
            else:
                # 其他关系
                other_str = f"- {subj} —{pred}→ {obj}"
                if chapter_info:
                    other_str += f" ({chapter_info})"
                other_info.append(other_str)
        
        # 组装输出
        if character_relations:
            lines.append("\n[人物关系]")
            lines.extend(character_relations[:10])
        
        if character_states:
            lines.append("\n[人物状态]")
            lines.extend(character_states[:5])
        
        if location_info:
            lines.append("\n[地点信息]")
            lines.extend(location_info[:5])
        
        if item_skills:
            lines.append("\n[道具/技能]")
            lines.extend(item_skills[:5])
        
        if other_info:
            lines.append("\n[其他设定]")
            lines.extend(other_info[:5])
        
        return "\n".join(lines)
    
    def _get_recent_act_summaries(
        self,
        novel_id: str,
        chapter_number: int,
        limit: int = 3,
    ) -> str:
        """获取近期幕摘要"""
        if not self.story_node_repo:
            return ""
        
        try:
            nodes = self.story_node_repo.get_by_novel_sync(novel_id)
            act_nodes = sorted(
                [n for n in nodes if n.node_type.value == "act" and n.number < chapter_number],
                key=lambda n: n.number,
                reverse=True
            )[:limit]
            
            if not act_nodes:
                return ""
            
            lines = ["【近期幕摘要】"]
            for act in reversed(act_nodes):  # 按时间顺序
                lines.append(f"\n{act.title}")
                if act.description:
                    lines.append(f"  {act.description[:200]}")
            
            return "\n".join(lines)
            
        except Exception as e:
            logger.warning(f"获取近期幕摘要失败: {e}")
        
        return ""

    def _excerpt_immediate_previous_chapter(self, content: str) -> str:
        """紧邻上一章正文：头短 + 章末长段，标明供本章开头承接。"""
        return excerpt_immediate_previous_chapter(
            content,
            head_chars=self.PREV_CHAPTER_BRIDGE_HEAD_CHARS,
            tail_chars=self.PREV_CHAPTER_BRIDGE_TAIL_CHARS,
        )

    def _get_recent_chapters(
        self,
        novel_id: str,
        chapter_number: int,
        limit: int = 5,
        current_beat_index: int = 0,
    ) -> str:
        """获取最近章节内容。

        N-1：章首略览 + 章末完整（PREV_CHAPTER_BRIDGE_TAIL_CHARS 字）
        N-2：章末中等片段（PREV_CHAPTER_BRIDGE_TAIL_CHARS // 2 字），帮助跨章一致性
        N-3 及更早：仅章首短预览（OLDER_CHAPTER_HEAD_PREVIEW_CHARS 字）

        断点续写时包含当前章节已生成部分，确保续写衔接。
        """
        if not self.chapter_repo:
            return ""

        try:
            nid = NovelId(novel_id)
            all_chapters = self.chapter_repo.list_by_novel(nid)

            return build_recent_chapters_context(
                all_chapters,
                chapter_number=chapter_number,
                limit=limit,
                current_beat_index=current_beat_index,
                prev_head_chars=self.PREV_CHAPTER_BRIDGE_HEAD_CHARS,
                prev_tail_chars=self.PREV_CHAPTER_BRIDGE_TAIL_CHARS,
                older_head_chars=self.OLDER_CHAPTER_HEAD_PREVIEW_CHARS,
            )

        except Exception as e:
            logger.warning(f"获取最近章节失败: {e}")

        return ""
    
    def _get_vector_recall(
        self,
        novel_id: str,
        chapter_number: int,
        outline: str,
    ) -> str:
        """获取向量召回片段"""
        if not self.vector_facade:
            return ""
        
        try:
            collection_name = f"novel_{novel_id}_chunks"

            # 新书首次运行时 collection 可能不存在，自动创建
            try:
                existing = _sync_run_async(self.vector_facade.vector_store.list_collections())
                if collection_name not in existing:
                    dimension = self.vector_facade.embedding_service.get_dimension()
                    if dimension and dimension > 0:
                        _sync_run_async(
                            self.vector_facade.vector_store.create_collection(
                                collection=collection_name, dimension=dimension
                            )
                        )
                        logger.info(f"向量召回：自动创建 collection {collection_name}")
            except Exception as _ce:
                logger.debug(f"向量召回 collection 检查/创建跳过: {_ce}")

            results = self.vector_facade.sync_search(
                collection=collection_name,
                query_text=outline,
                limit=5,
            )
            
            if not results:
                return ""
            
            # 过滤：排除当前章节，优先相近章节
            filtered = [
                hit for hit in results
                if hit.get("payload", {}).get("chapter_number") != chapter_number
            ]
            
            if not filtered:
                return ""
            
            lines = ["【相关上下文（向量召回）】"]
            for hit in filtered[:3]:  # 最多 3 个片段
                text = hit.get("payload", {}).get("text", "")
                ch_num = hit.get("payload", {}).get("chapter_number", "?")
                lines.append(f"\n[第 {ch_num} 章] {text}")
            
            return "\n".join(lines)
            
        except Exception as e:
            logger.warning(f"向量召回失败: {e}")
        
        return ""
    
    def _get_diagnosis_breakpoints(
        self,
        novel_id: str,
        chapter_number: int,
    ) -> str:
        """获取宏观诊断「系统叙事校准」补丁（静默注入 Context 头部，无前端交互）。

        仅只读查询 DB 中已写好的 context_patch；扫描/计算在后台任务中完成，不在 allocate 热路径重跑。
        优先使用后台 Map-Reduce 扫描后写入的 context_patch；对用户透明。
        已解决的诊断结果（resolved=1）不再注入。
        """
        try:
            from infrastructure.persistence.database.connection import get_database
            
            db = get_database()
            
            sql = """
                SELECT context_patch, breakpoints, trait, created_at
                FROM macro_diagnosis_results
                WHERE novel_id = ? AND status = 'completed' AND resolved = 0
                ORDER BY created_at DESC
                LIMIT 1
            """
            row = db.fetch_one(sql, (novel_id,))
            
            if not row:
                return ""
            
            cp = row.get("context_patch")
            if cp and str(cp).strip():
                return str(cp).strip()
            
            # 兼容旧库仅有 breakpoints 无 context_patch 时：不注入长列表，避免暴露「诊断」口吻
            return ""
            
        except Exception as e:
            logger.warning(f"获取宏观叙事校准补丁失败: {e}")
        
        return ""
    
    # ==================== V7 全局收敛沙漏方法 ====================
    
    def _estimate_total_chapters(self, novel_id: str) -> int:
        """估算目标总章节数
        
        优先级：
        1. 结构树根节点（part）的 chapter_end 字段
        2. 各 part 节点 suggested_chapter_count 之和
        3. 已有最大章节号 × 1.2（保守估算，假设已完成 80%+）
        4. 兜底返回 100
        """
        return estimate_total_chapters(self.story_node_repo, novel_id)
    
    # Phase 3: 沙漏阶段默认阈值
    _DEFAULT_PHASE_THRESHOLDS = DEFAULT_PHASE_THRESHOLDS

    from infrastructure.ai.prompt_keys import LIFECYCLE_PHASE_DIRECTIVES as _LIFECYCLE_PROMPT_ID

    def _load_phase_thresholds(self) -> Dict[str, float]:
        """Phase 3: 从 CPMS 节点加载沙漏阶段阈值（lifecycle-phase-directives 的 _phase_thresholds）。"""
        return load_phase_thresholds(
            get_prompt_registry(),
            self._LIFECYCLE_PROMPT_ID,
            self._DEFAULT_PHASE_THRESHOLDS,
        )

    def _classify_phase(self, progress: float) -> StoryPhase:
        """Phase 3: 根据可配置阈值判定当前生命周期阶段"""
        return classify_phase(progress, self._phase_thresholds)
    
    def _get_phase_directives(self) -> Dict[StoryPhase, str]:
        """从 PromptRegistry / CPMS 获取阶段指令字典。"""
        return get_phase_directives(get_prompt_registry(), self._LIFECYCLE_PROMPT_ID)

    def _build_lifecycle_directive(self, novel_id: str, chapter_number: int) -> str:
        """构建生命周期行为准则文本（指令来自 CPMS lifecycle-phase-directives）。"""
        return build_lifecycle_directive(
            story_node_repository=self.story_node_repo,
            novel_id=novel_id,
            chapter_number=chapter_number,
            thresholds=self._phase_thresholds,
            registry=get_prompt_registry(),
            prompt_id=self._LIFECYCLE_PROMPT_ID,
        )

    # ==================== Anti-AI T0 槽位构建方法 ====================

    def _build_anti_ai_protocol_block(self, novel_id: str, chapter_number: int) -> str:
        """构建 Anti-AI 行为协议文本块（T0 注入）。

        整合 Layer 1+2+3 的核心约束：
        - 正向行为映射规则
        - 核心协议 P1-P5
        - 场景化白名单
        """
        try:
            from application.engine.rules.rule_parser import get_rule_parser
            parser = get_rule_parser()
            # 使用默认场景类型，后续可从场记分析中获取
            protocol_block = parser.build_behavior_protocol_block(
                nervous_habits="",
                scene_type="default",
            )
            if protocol_block:
                return protocol_block
        except Exception as e:
            logger.debug("Anti-AI 行为协议构建失败: %s", e)

        return ""

    def _build_character_state_lock_block(self, novel_id: str, chapter_number: int) -> str:
        """构建角色状态锁文本块（T0 注入）。

        从本章 cast plan 读取 normal/minor 角色，避免 Bible 前 7 个角色污染上下文。
        """
        kernel = self._get_character_kernel()
        if kernel:
            try:
                plan = kernel.plan_cast(novel_id, chapter_number)
                projected = self._projection_locks_for_plan(novel_id, plan, tier="support")
                if projected:
                    return projected
                locks = kernel.build_context_locks(novel_id, chapter_number, plan=plan)
                parts = []
                if locks.t1.strip():
                    parts.append(locks.t1.strip())
                if locks.t2.strip():
                    parts.append(locks.t2.strip())
                return "\n\n".join(parts)
            except Exception as e:
                logger.debug("角色内核状态锁构建失败: %s", e)

        # Legacy fallback for tests or deployments without repositories.
        try:
            from application.engine.rules.character_state_vector import get_character_state_vector_manager

            manager = get_character_state_vector_manager()

            # 从 Bible 获取角色列表
            if self.bible_repo:
                from domain.novel.value_objects.novel_id import NovelId
                nid = NovelId(novel_id)
                bible = self.bible_repo.get_by_novel_id(nid)
                if bible and hasattr(bible, 'characters'):
                    # 更新角色状态向量
                    for char in bible.characters[:7]:  # 最多7个角色
                        char_data = {}
                        if hasattr(char, 'physical_state') and char.physical_state:
                            char_data["physical_state"] = char.physical_state
                        if hasattr(char, 'mental_state') and char.mental_state:
                            char_data["emotional_baseline"] = char.mental_state
                        if hasattr(char, 'verbal_tic') and char.verbal_tic:
                            char_data["voice_print"] = {
                                "common_expressions": [char.verbal_tic],
                                "vocabulary_style": "colloquial",
                            }
                        if hasattr(char, 'idle_behavior') and char.idle_behavior:
                            char_data["nervous_habit"] = {
                                "primary": char.idle_behavior,
                            }

                        if char_data:
                            manager.update_from_bible(char.name, char_data)

                    # 生成状态锁文本
                    names = [c.name for c in bible.characters[:7]]
                    lock_text = manager.generate_lock_block(names)
                    if lock_text:
                        return lock_text
        except Exception as e:
            logger.debug("角色状态锁构建失败: %s", e)

        return ""

    def _projection_locks_for_plan(self, novel_id: str, plan: Any, *, tier: str) -> str:
        """Prefer unified character projections for prompt locks; fallback callers handle empty."""
        try:
            service = self._get_character_projection_service()
            if not service:
                return ""
            lines: List[str] = []
            for slot in getattr(plan, "slots", []) or []:
                projection = service.get_projection(novel_id, slot.character_id)
                locks = projection.get("context_locks") or {}
                if tier == "t0" and slot.importance == "major" and locks.get("t0"):
                    lines.append(str(locks["t0"]))
                elif tier == "support":
                    key = "t1" if slot.importance == "normal" else "t2"
                    if locks.get(key):
                        lines.append(str(locks[key]))
            return "\n".join(lines)
        except Exception as e:
            logger.debug("角色 Projection 锁构建失败: %s", e)
            return ""

    def _get_character_projection_service(self):
        if self.character_projection_service is not None:
            return self.character_projection_service
        try:
            from application.memory.services.character_projection_service import CharacterProjectionService
            from application.memory.services.narrative_memory_service import NarrativeMemoryService
            from infrastructure.persistence.database.connection import get_database
            from infrastructure.persistence.database.sqlite_character_state_repository import (
                SqliteCharacterStateRepository,
            )
            from infrastructure.persistence.database.sqlite_memory_repository import (
                SqliteNarrativeMemoryRepository,
            )
            from infrastructure.persistence.database.sqlite_narrative_debt_repository import (
                SqliteNarrativeDebtRepository,
            )

            db = get_database()
            return CharacterProjectionService(
                memory_service=NarrativeMemoryService(SqliteNarrativeMemoryRepository(db)),
                bible_repository=self.bible_repo,
                character_state_repository=SqliteCharacterStateRepository(db),
                triple_repository=self.triple_repo,
                debt_repository=SqliteNarrativeDebtRepository(db),
            )
        except Exception as e:
            logger.debug("角色 Projection 服务不可用: %s", e)
            return None

    def _get_character_kernel(self):
        if self.character_narrative_kernel is not None:
            return self.character_narrative_kernel
        if not (self.bible_repo and self.chapter_element_repo and self.story_node_repo):
            return None
        try:
            from application.character.services.character_narrative_kernel import CharacterNarrativeKernel
            self.character_narrative_kernel = CharacterNarrativeKernel(
                bible_repository=self.bible_repo,
                chapter_element_repository=self.chapter_element_repo,
                story_node_repository=self.story_node_repo,
                triple_repository=self.triple_repo,
            )
            return self.character_narrative_kernel
        except Exception as e:
            logger.debug("角色叙事内核初始化失败: %s", e)
            return None
