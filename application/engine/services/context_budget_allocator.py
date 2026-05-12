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
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from application.engine.dtos.scene_director_dto import SceneDirectorInput, coerce_scene_director

from domain.novel.value_objects.novel_id import NovelId
from domain.novel.value_objects.chapter_id import ChapterId
from domain.novel.repositories.foreshadowing_repository import ForeshadowingRepository
from domain.novel.repositories.chapter_repository import ChapterRepository
from domain.bible.repositories.bible_repository import BibleRepository
from infrastructure.persistence.database.story_node_repository import StoryNodeRepository
from domain.ai.services.vector_store import VectorStore
from domain.ai.services.embedding_service import EmbeddingService
from application.ai.vector_retrieval_facade import VectorRetrievalFacade
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


class PriorityTier(str, Enum):
    """优先级层级（洋葱模型）"""
    T0_CRITICAL = "t0_critical"      # 绝对不删减
    T1_COMPRESSIBLE = "t1_compressible"  # 按比例压缩
    T2_DYNAMIC = "t2_dynamic"        # 动态水位线
    T3_SACRIFICIAL = "t3_sacrificial"  # 可牺牲泡沫


class StoryPhase(str, Enum):
    """故事生命周期阶段 —— 全局收敛沙漏的核心状态机"""
    OPENING = "opening"       # 开局期 (0% - 25%)：尽情铺陈，抛出悬念
    DEVELOPMENT = "development" # 发展期 (25% - 75%)：激化矛盾，引入支线
    CONVERGENCE = "convergence" # 收敛期 (75% - 90%)：禁止开新坑，强制填坑
    FINALE = "finale"          # 终局期 (90% - 100%)：终极对决，切断日常


@dataclass
class ContextSlot:
    """上下文槽位"""
    name: str
    tier: PriorityTier
    content: str = ""
    tokens: int = 0
    max_tokens: Optional[int] = None  # None 表示无上限
    min_tokens: int = 0  # 最小保留量
    priority: int = 0  # 同层级内的优先级（越大越优先）
    
    @property
    def is_mandatory(self) -> bool:
        """是否强制保留"""
        return self.tier == PriorityTier.T0_CRITICAL


@dataclass
class BudgetAllocation:
    """预算分配结果"""
    slots: Dict[str, ContextSlot] = field(default_factory=dict)
    total_budget: int = 35000
    used_tokens: int = 0
    remaining_tokens: int = 0
    
    # 分配详情
    t0_reserved: int = 0
    t1_allocated: int = 0
    t2_allocated: int = 0
    t3_allocated: int = 0
    
    # 压缩标记
    compression_applied: bool = False
    compression_log: List[str] = field(default_factory=list)
    expired_foreshadows: List[str] = field(default_factory=list)
    
    # V7 全局收敛沙漏
    progress: float = 0.0           # 全局进度 0.0 ~ 1.0
    phase: StoryPhase = StoryPhase.OPENING  # 当前生命周期阶段
    total_chapters: int = 0         # 目标总章节数
    
    def get_final_context(self) -> str:
        """组装最终上下文"""
        parts = []
        
        # 按层级顺序组装（T0 → T1 → T2 → T3）
        for tier in [PriorityTier.T0_CRITICAL, PriorityTier.T1_COMPRESSIBLE, 
                     PriorityTier.T2_DYNAMIC, PriorityTier.T3_SACRIFICIAL]:
            tier_slots = [(name, slot) for name, slot in self.slots.items() if slot.tier == tier]
            tier_slots.sort(key=lambda x: x[1].priority, reverse=True)
            
            for name, slot in tier_slots:
                if slot.content.strip():
                    parts.append(f"\n=== {slot.name.upper()} ===\n{slot.content}")
        
        # 追加强制收束指令
        if self.expired_foreshadows:
            parts.append("\n=== 🚨强制剧情收束令🚨 ===\n" + 
                         "以下伏笔已超出预期揭晓章节，必须在本章或本节拍的行文中，通过回忆、对话、意外发展或直接揭露等方式去解答或明显推进悬念：\n" + 
                         "\n".join(f"- {f}" for f in self.expired_foreshadows) + 
                         "\n【如果你无视此指令，长篇小说的情节网将陷入崩溃】")
        
        return "\n".join(parts)


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
    # ★ V9 减法改革: T0 从 35% 降至 20% — 约束是药不是饭
    # 过多的 T0 强制内容导致注意力坍塌，AI 从"写故事"变成"满足约束条件"
    # 把叙事债务、因果链、伤疤执念等降级到 T1，用自然语言的"编辑手记"替代结构化槽位
    T0_BUDGET_RATIO = 0.20   # 20% 给 T0（仅保留：FACT_LOCK + ANCHOR + 角色锚点 + 编辑手记）
    T1_BUDGET_RATIO = 0.30   # 30% 给 T1（降级内容：伤疤/债务/因果链/已完成节拍/线索）
    T2_BUDGET_RATIO = 0.35   # 35% 给 T2（动态：最近章节——这才是 AI 应该关注的重点）
    T3_BUDGET_RATIO = 0.15   # 15% 给 T3（向量召回）
    
    # 各槽位的默认上限
    MAX_FORESHADOWING_TOKENS = 2000
    MAX_CHARACTER_ANCHORS_TOKENS = 1500
    MAX_GRAPH_SUBNETWORK_TOKENS = 1000
    MAX_ACT_SUMMARIES_TOKENS = 1500
    MAX_RECENT_CHAPTERS_TOKENS = 5000
    MAX_VECTOR_RECALL_TOKENS = 5000

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
        # ★ Phase 3: 沙漏阶段可配置阈值
        phase_thresholds: Optional[Dict[str, float]] = None,
        # ★ V8 Feed-forward: 上下文反哺管线（因果图谱 + 人物状态 + 叙事债务）
        context_assembler: Optional[Any] = None,
    ):
        self.foreshadowing_repo = foreshadowing_repository
        self.chapter_repo = chapter_repository
        self.bible_repo = bible_repository
        self.story_node_repo = story_node_repository
        self.chapter_element_repo = chapter_element_repository
        self.triple_repo = triple_repository

        # V6 记忆引擎（可选，用于 T0 槽位注入 FACT_LOCK / BEATS / CLUES）
        self.memory_engine = memory_engine

        # ★ V8 Feed-forward: 上下文反哺管线
        self.context_assembler = context_assembler

        # ★ Phase 3: 沙漏阶段阈值（可由 CPMS 节点 lifecycle-phase-directives 的变量覆盖）
        self._phase_thresholds = phase_thresholds or self._load_phase_thresholds()

        # 向量检索门面
        self.vector_facade = None
        if vector_store and embedding_service:
            self.vector_facade = VectorRetrievalFacade(vector_store, embedding_service)
    
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
                if "🔴已过期" in line:
                    desc = line.split(":", 1)[-1].strip() if ":" in line else line.strip()
                    allocation.expired_foreshadows.append(desc)
        
        # ========== 第二步：计算 T0 强制保留量 ==========
        t0_slots = {name: slot for name, slot in slots.items() if slot.tier == PriorityTier.T0_CRITICAL}
        t0_total = sum(slot.tokens for slot in t0_slots.values())
        
        # ★ Phase 2: T0 动态阈值保护 — T0 最多占 40% 总预算
        # 防止伏笔/角色等 T0 内容无限膨胀挤占 T2/T3
        T0_MAX_RATIO = 0.40
        t0_max = int(total_budget * T0_MAX_RATIO)
        if t0_total > t0_max:
            logger.warning(
                f"T0 内容 {t0_total} tokens 超出动态阈值 {t0_max} ({T0_MAX_RATIO:.0%} 总预算)，"
                f"触发 T0 截断保护"
            )
            t0_total = self._truncate_t0_slots(t0_slots, t0_max)
            allocation.compression_log.append(f"🛡️ T0 动态阈值保护：截断至 {T0_MAX_RATIO:.0%} 总预算")
        
        if t0_total > total_budget:
            # 极端情况：T0 超出总预算，只能截断
            logger.warning(f"T0 强制内容 {t0_total} tokens 超出总预算 {total_budget}")
            allocation.compression_log.append(f"⚠️ T0 超预算，强制截断")
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
        # ★ Phase 2: T3 最低保障 — 至少保留 5% 总预算给向量召回
        # 防止 T0 膨胀 + T1/T2 挤占导致 T3（跨幕记忆）完全丢失
        T3_MIN_RATIO = 0.05
        t3_min_tokens = int(total_budget * T3_MIN_RATIO)
        t3_slots = {name: slot for name, slot in slots.items() if slot.tier == PriorityTier.T3_SACRIFICIAL}
        if remaining_after_t2 < t3_min_tokens and t3_slots:
            # 从 T2 中回收部分配额给 T3
            shortfall = t3_min_tokens - remaining_after_t2
            if t2_actual > shortfall:
                logger.info(
                    f"🛡️ T3 最低保障：从 T2 回收 {shortfall} tokens 给 T3 "
                    f"(确保跨幕记忆不断裂)"
                )
                t2_actual -= shortfall
                allocation.t2_allocated = t2_actual
                remaining_after_t2 = t3_min_tokens
                allocation.compression_log.append(
                    f"🛡️ T3 最低保障：{T3_MIN_RATIO:.0%} 总预算 ({t3_min_tokens} tokens)"
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
            name="📖全书主线锚点(ANCHOR)",
            tier=PriorityTier.T0_CRITICAL,
            content=anchor_content,
            tokens=self.estimate_tokens(anchor_content),
            max_tokens=300,  # V9: 从 500 砍到 300——一句话主线，不需要更多
            priority=125,
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
            name="🔒绝对事实边界(FACT_LOCK)",
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
            name="📝编辑手记(CONTEXT_BRIEF)",
            tier=PriorityTier.T0_CRITICAL,
            content=context_brief,
            tokens=self.estimate_tokens(context_brief),
            max_tokens=800,  # V9: 800 tokens 的自然语言手记，替代原来 10,000+ tokens 的结构化槽位
            priority=100,
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
            name="💔角色伤疤与执念(SCARS)",
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
            name="✅已完成节拍(COMPLETED_BEATS)",
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
            name="📋叙事备忘(DEBT_DUE)",
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
            name="🔍已揭露线索(REVEALED_CLUES)",
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
            name="🛡️ Anti-AI 行为协议(ANTI_AI_PROTOCOL)",
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
            name="🔗未闭环因果链(CAUSAL_CHAINS)",
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
        character_state_lock_content = self._build_character_state_lock_block(novel_id)
        slots["character_state_lock"] = ContextSlot(
            name="🔒 角色状态锁(CHARACTER_STATE_LOCK)",
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
        
        # 6. 最近章节内容
        recent_chapters = self._get_recent_chapters(novel_id, chapter_number, limit=3, current_beat_index=current_beat_index)
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
        
        return slots
    
    def _truncate_t0_slots(self, t0_slots: Dict[str, ContextSlot], budget: int) -> int:
        """极端情况：截断 T0 内容"""
        total = 0
        for name, slot in t0_slots.items():
            if total + slot.tokens <= budget:
                total += slot.tokens
            else:
                # 截断到最后一个
                remaining = budget - total
                if remaining > 0:
                    target_chars = int(remaining * self.CHARS_PER_TOKEN_ZH)
                    slot.content = slot.content[:target_chars] + "..."
                    slot.tokens = remaining
                    total += remaining
                break
        return total
    
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
        # 按优先级排序
        sorted_slots = sorted(tier_slots.items(), key=lambda x: x[1].priority, reverse=True)
        
        total_used = 0
        for name, slot in sorted_slots:
            if total_used + slot.tokens <= budget:
                # 可以完整保留
                total_used += slot.tokens
            elif slot.max_tokens and slot.max_tokens > 0:
                # 可以部分保留
                remaining = budget - total_used
                if remaining > slot.min_tokens:
                    # 压缩内容
                    target_chars = int(remaining * self.CHARS_PER_TOKEN_ZH)
                    slot.content = slot.content[:target_chars] + "..."
                    slot.tokens = remaining
                    total_used += remaining
                    compression_log.append(f"压缩 {name}: {slot.tokens} → {remaining} tokens")
                else:
                    # 完全舍弃
                    slot.content = ""
                    slot.tokens = 0
                    compression_log.append(f"舍弃 {name}（预算不足）")
            else:
                # 没有设置上限，按预算截断
                remaining = budget - total_used
                if remaining > 0:
                    target_chars = int(remaining * self.CHARS_PER_TOKEN_ZH)
                    slot.content = slot.content[:target_chars] + "..."
                    slot.tokens = remaining
                    total_used += remaining
                    compression_log.append(f"截断 {name}: {remaining} tokens")
                else:
                    slot.content = ""
                    slot.tokens = 0
        
        return total_used
    
    # ==================== 内容收集方法 ====================
    
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

        设计哲学：
          一段自然语言比 8 个 === xxx === 分隔符更容易被 LLM 自然地融入创作。
          这不是"约束列表"，而是"编辑的转场笔记"——像真人的责编告诉你：
          "注意，上一章留了个悬念，有两个坑快到期了。"
        """
        parts = []

        # ── 1. 衔接信息（替代 BRIDGE_DIRECTIVE + PREVIOUSLY_ON）──
        if chapter_number > 1:
            bridge_hint = self._get_bridge_hint(novel_id, chapter_number)
            if bridge_hint:
                parts.append(bridge_hint)

        # ── 2. 角色状态概要（替代 SCARS + CHARACTER_STATE_LOCK）──
        character_state_hint = self._get_character_state_hint(novel_id)
        if character_state_hint:
            parts.append(character_state_hint)

        # ── 3. 叙事备忘（替代 DEBT_DUE）──
        debt_hint = self._get_debt_hint(novel_id, chapter_number, outline)
        if debt_hint:
            parts.append(debt_hint)

        if not parts:
            return ""

        return "【编辑手记】\n" + "\n".join(parts)

    def _get_bridge_hint(self, novel_id: str, chapter_number: int) -> str:
        """获取前章衔接提示（柔性建议，非铁律）"""
        try:
            from application.engine.services.chapter_bridge_service import ChapterBridgeService
            from application.paths import get_db_path

            svc = ChapterBridgeService(db_path=str(get_db_path()))
            prev_bridge = svc.get_prev_chapter_bridge(novel_id, chapter_number)
            if not prev_bridge:
                return ""

            hints = []
            if prev_bridge.suspense_hook:
                hints.append(f"上一章留了悬念：{prev_bridge.suspense_hook}")
            if prev_bridge.emotional_residue:
                hints.append(f"主角情绪：{prev_bridge.emotional_residue}")
            if prev_bridge.scene_state:
                hints.append(f"场景：{prev_bridge.scene_state}")
            if prev_bridge.unfinished_actions:
                hints.append(f"未完成：{prev_bridge.unfinished_actions}")

            if not hints:
                return ""

            return "衔接：" + "；".join(hints) + "。你可以自然接续，也可以时间跳跃或视角切换。"

        except Exception as e:
            logger.debug("衔接提示获取失败: %s", e)
            return ""

    def _get_character_state_hint(self, novel_id: str) -> str:
        """获取角色状态概要（精简版，替代详细的结构化 SCARS 锁）"""
        if not self.context_assembler:
            return ""

        try:
            # 尝试获取伤疤/执念，但压缩为自然语言
            scars_content = self.context_assembler.build_scars_and_motivations(novel_id)
            if not scars_content or not scars_content.strip():
                return ""

            # 从结构化文本中提取关键信息，压缩为 2-3 句话
            lines = [l.strip() for l in scars_content.split('\n') if l.strip()]
            # 过滤掉标题行和分隔符
            content_lines = [l for l in lines if not l.startswith('【') and not l.startswith('═') and not l.startswith('━━')]

            if not content_lines:
                return ""

            # 只保留前 3 行关键信息（防止膨胀）
            brief_lines = content_lines[:3]
            return "角色状态：" + "；".join(l.rstrip('。') for l in brief_lines if l) + "。"

        except Exception as e:
            logger.debug("角色状态概要获取失败: %s", e)
            return ""

    def _get_debt_hint(self, novel_id: str, chapter_number: int, outline: str) -> str:
        """获取叙事债务温和提醒（替代强制收束令）"""
        if not self.context_assembler:
            return ""

        try:
            debt_content = self.context_assembler.build_debt_due_block(
                novel_id, chapter_number, outline
            )
            if not debt_content or not debt_content.strip():
                return ""

            # 从结构化文本中提取债务描述
            lines = [l.strip() for l in debt_content.split('\n') if l.strip()]
            debt_lines = [l for l in lines if l.startswith('-') or l.startswith('•')]

            if not debt_lines:
                return ""

            # 只保留前 2 条债务（防止膨胀）
            brief_debts = [l.lstrip('-• ').rstrip() for l in debt_lines[:2]]
            return "叙事备忘：" + "；".join(brief_debts) + "。如果合适可以推进，不必强求回收。"

        except Exception as e:
            logger.debug("叙事备忘获取失败: %s", e)
            return ""

    def _get_chapter_bridge_directive(self, novel_id: str, chapter_number: int) -> str:
        """🔥 衔接引擎：从 DB 读取前章桥段，生成首段衔接指令（V9: 降级为 T1 参考）"""
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
    
    # ★ 爽文引擎: T0 伏笔最大展示数量（防止 T0 膨胀）
    MAX_T0_FORESHADOWING_ITEMS = 6

    def _get_pending_foreshadowings(self, novel_id: str, chapter_number: int) -> str:
        """获取待回收伏笔（轨道二核心）- 爽文引擎: 使用 T0 精选筛选，剥离冗长 pending。"""
        if not self.foreshadowing_repo:
            return ""
        
        try:
            nid = NovelId(novel_id)
            registry = self.foreshadowing_repo.get_by_novel_id(nid)
            
            if not registry:
                return ""
            
            # ★ 爽文引擎: 使用 T0 筛选方法，剥离冗长 pending 伏笔
            pending_foreshadows = registry.get_t0_eligible_foreshadowings(
                current_chapter=chapter_number,
                max_items=self.MAX_T0_FORESHADOWING_ITEMS,
            )
            pending_subtext = registry.get_pending_subtext_entries()
            
            lines = []
            
            # ★ 爽文引擎: get_t0_eligible_foreshadowings 已排序，无需再次排序
            if pending_foreshadows:
                lines.append("【待回收伏笔（爽文GC精选）】")
                for f in pending_foreshadows[:self.MAX_T0_FORESHADOWING_ITEMS]:
                    importance_mark = "⚠️" if f.importance.value >= 3 else ""
                    
                    # 构建状态标记
                    status_mark = ""
                    if f.suggested_resolve_chapter:
                        if f.suggested_resolve_chapter <= chapter_number:
                            status_mark = "🔴已过期"
                        elif f.suggested_resolve_chapter <= chapter_number + 3:
                            status_mark = "🟡即将到期"
                        else:
                            status_mark = f"⏳预期Ch{f.suggested_resolve_chapter}"
                    
                    lines.append(
                        f"- Ch{f.planted_in_chapter} {importance_mark} {status_mark}: {f.description}"
                    )
            
            # 对潜台词按预期回收章节排序
            def subtext_sort_key(e):
                suggested = getattr(e, 'suggested_resolve_chapter', None)
                importance = getattr(e, 'importance', 'medium')
                importance_val = {'low': 1, 'medium': 2, 'high': 3, 'critical': 4}.get(importance, 2)
                
                if suggested:
                    if suggested <= chapter_number:
                        return (0, -importance_val, suggested)
                    else:
                        return (1, -importance_val, suggested)
                else:
                    return (2, -importance_val, 9999)
            
            sorted_subtext = sorted(pending_subtext, key=subtext_sort_key)
            
            if sorted_subtext:
                lines.append("\n【伏笔手账本·待兑现疑问】")
                for entry in sorted_subtext[:5]:  # 最多 5 个
                    importance = getattr(entry, 'importance', 'medium')
                    suggested = getattr(entry, 'suggested_resolve_chapter', None)
                    
                    status_mark = ""
                    if suggested:
                        if suggested <= chapter_number:
                            status_mark = "🔴已过期"
                        elif suggested <= chapter_number + 3:
                            status_mark = "🟡即将到期"
                        else:
                            status_mark = f"⏳预期Ch{suggested}"
                    
                    lines.append(
                        f"- Ch{entry.chapter} [{entry.character_id}] {status_mark}: {entry.question}"
                    )
            
            return "\n".join(lines)
            
        except Exception as e:
            logger.warning(f"获取待回收伏笔失败: {e}")
        
        return ""
    
    def _get_deferred_foreshadowings(self, novel_id: str, chapter_number: int) -> str:
        """★ 爽文引擎: 获取被 T0 剥离的冗长 pending 伏笔（降级到 T1）"""
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
                    profile_parts.append("⚠️ 刚登场，需保持一致性")
                
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
        
        Returns:
            List[Tuple[Character, bool]]: [(角色, 是否刚登场), ...]
        """
        # 最大角色数限制
        MAX_CHARACTERS = 7
        
        # Step 1: 从大纲中提取提及的角色名
        mentioned_names = set()
        if outline:
            # 简单匹配：检查角色名是否在大纲中
            for char in all_characters:
                if char.name in outline:
                    mentioned_names.add(char.name)
        
        # 如果有场记分析，合并场记中的角色
        if scene_director and scene_director.get("characters"):
            mentioned_names.update(scene_director["characters"])
        
        # Step 2: 从 chapter_elements 表查询最近出场的角色
        recent_characters = self._get_recent_characters(novel_id, chapter_number)
        
        # Step 3: 分类：提及的 vs 未提及的
        mentioned_chars = []
        unmentioned_chars = []
        
        for char in all_characters:
            # 检查是否刚登场（最近1章出场次数<=1）
            is_recent = self._is_recently_appeared(char, recent_characters, chapter_number)
            
            if char.name in mentioned_names:
                mentioned_chars.append((char, is_recent, self._get_char_importance(char)))
            else:
                unmentioned_chars.append((char, is_recent, self._get_char_importance(char)))
        
        # Step 4: 排序未提及角色（重要性 > 活动度）
        unmentioned_chars.sort(key=lambda x: (
            x[2],  # 重要性优先级（越小越优先）
            -self._get_activity_score(x[0], recent_characters)  # 活动度降序
        ))
        
        # Step 5: 合并队列
        queue = mentioned_chars + unmentioned_chars
        
        # Step 6: 截断到最大数量
        selected = queue[:MAX_CHARACTERS]
        
        # 返回 (角色, 是否刚登场) 的列表
        return [(char, is_recent) for char, is_recent, _ in selected]
    
    def _get_recent_characters(self, novel_id: str, chapter_number: int) -> Dict[str, Dict]:
        """从 chapter_elements 表查询最近5章的角色活动
        
        Returns:
            Dict[char_id, {"count": int, "last_chapter": int}]
        """
        if not self.story_node_repo:
            return {}
        
        try:
            # 查询最近5章的 chapter_elements
            # 这里简化实现，实际应该查询 chapter_elements 表
            # SELECT element_id, COUNT(*) as count, MAX(chapter_number) as last_chapter
            # FROM chapter_elements
            # WHERE novel_id = ? AND element_type = 'character'
            # AND chapter_number >= ?
            # GROUP BY element_id
            
            # 暂时返回空字典，等待实际数据库查询
            return {}
            
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
            
            # 按置信度和相关性排序
            sorted_triples = sorted(
                all_triples.values(),
                key=lambda x: (
                    -x.confidence,  # 置信度降序
                    -len(x.related_chapters or []),  # 相关章节数降序
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
        raw = (content or "").strip()
        if not raw:
            return ""
        head_n = self.PREV_CHAPTER_BRIDGE_HEAD_CHARS
        tail_n = self.PREV_CHAPTER_BRIDGE_TAIL_CHARS
        if len(raw) <= tail_n:
            return f"【章末节选，供本章开头承接】\n{raw}"
        if len(raw) <= head_n + tail_n:
            return f"【章末节选，供本章开头承接】\n{raw}"
        head = raw[:head_n]
        tail = raw[-tail_n:]
        return (
            f"【章首略览】\n{head}……\n"
            f"【章末节选，供本章开头承接】\n{tail}"
        )

    def _get_recent_chapters(
        self,
        novel_id: str,
        chapter_number: int,
        limit: int = 3,
        current_beat_index: int = 0,
    ) -> str:
        """获取最近章节内容。

        紧邻上一章（chapter_number - 1）优先展示章末，便于两章衔接；更早章节仅章首短预览。

        新增：断点续写时包含当前章节已生成部分，确保续写衔接。
        """
        if not self.chapter_repo:
            return ""

        try:
            nid = NovelId(novel_id)
            all_chapters = self.chapter_repo.list_by_novel(nid)

            # 获取最近的已完成章节
            recent = sorted(
                [c for c in all_chapters if c.number < chapter_number],
                key=lambda c: c.number,
                reverse=True
            )[:limit]

            prev_num = chapter_number - 1
            older_cap = self.OLDER_CHAPTER_HEAD_PREVIEW_CHARS
            lines = ["【最近章节】"]

            # 历史章节
            for chapter in reversed(recent):  # 按时间顺序（旧 → 新）
                lines.append(f"\n第 {chapter.number} 章：{chapter.title}")
                body = (chapter.content or "").strip()
                if not body:
                    continue
                if chapter.number == prev_num:
                    excerpt = self._excerpt_immediate_previous_chapter(chapter.content or "")
                    if excerpt:
                        lines.append(excerpt)
                    continue
                preview = body[:older_cap]
                if len(body) > older_cap:
                    preview = f"{preview}..."
                lines.append(f"【章首预览】\n{preview}")

            # ★ 断点续写：包含当前章节已生成部分
            if current_beat_index > 0:
                current_chapter = next(
                    (c for c in all_chapters if c.number == chapter_number), None
                )
                if current_chapter and current_chapter.content:
                    current_content = current_chapter.content.strip()
                    if current_content:
                        # 取已生成内容的最后部分（最多2000字）
                        continuation_preview = current_content[-2000:] if len(current_content) > 2000 else current_content
                        lines.append(f"\n【本章已生成（断点续写上下文）】")
                        lines.append(f"当前节拍索引: {current_beat_index}")
                        lines.append(f"已生成 {len(current_content)} 字")
                        lines.append(f"---")
                        lines.append(continuation_preview)

            return "\n".join(lines)

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

            # 🔥 新书首次运行时 collection 可能不存在，自动创建
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
        if not self.story_node_repo:
            return 100
        
        try:
            nodes = self.story_node_repo.get_by_novel_sync(novel_id)
            if not nodes:
                return 100
            
            # 策略 1：找根 part 节点的 chapter_end
            part_nodes = [n for n in nodes if n.node_type.value == "part"]
            for part in part_nodes:
                if part.chapter_end and part.chapter_end > 0:
                    return part.chapter_end
            
            # 策略 2：suggested_chapter_count 求和
            total_suggested = sum(
                (p.suggested_chapter_count or 0) for p in part_nodes if p.suggested_chapter_count
            )
            if total_suggested > 0:
                return total_suggested
            
            # 策略 3：最大章节号 × 1.2
            chapter_nodes = [n for n in nodes if n.node_type.value == "chapter"]
            if chapter_nodes:
                max_ch = max(n.number for n in chapter_nodes)
                if max_ch > 0:
                    return max(int(max_ch * 1.2), max_ch + 10)
            
        except Exception as e:
            logger.warning(f"估算总章节数失败: {e}")
        
        return 100
    
    # ★ Phase 3: 沙漏阶段默认阈值
    _DEFAULT_PHASE_THRESHOLDS = {
        "opening": 0.25,      # 0% ~ 25%: 开局期
        "development": 0.75,   # 25% ~ 75%: 发展期
        "convergence": 0.90,   # 75% ~ 90%: 收敛期
        "finale": 1.01,        # 90% ~ 100%: 终局期（设为 1.01 确保边界）
    }

    _LIFECYCLE_PROMPT_ID = "lifecycle-phase-directives"

    def _load_phase_thresholds(self) -> Dict[str, float]:
        """★ Phase 3: 从 CPMS 节点加载沙漏阶段阈值（lifecycle-phase-directives 的 _phase_thresholds）。"""
        try:
            registry = get_prompt_registry()
            custom = registry.get_field(self._LIFECYCLE_PROMPT_ID, "_phase_thresholds", None)
            if isinstance(custom, dict):
                thresholds = dict(self._DEFAULT_PHASE_THRESHOLDS)
                for key in ["opening", "development", "convergence", "finale"]:
                    if key in custom:
                        val = float(custom[key])
                        if 0.0 <= val <= 1.01:
                            thresholds[key] = val
                logger.info(f"沙漏阶段阈值已从配置加载: {thresholds}")
                return thresholds
        except Exception as e:
            logger.debug(f"加载沙漏阶段阈值失败，使用默认值: {e}")

        return dict(self._DEFAULT_PHASE_THRESHOLDS)

    def _classify_phase(self, progress: float) -> StoryPhase:
        """★ Phase 3: 根据可配置阈值判定当前生命周期阶段"""
        t = self._phase_thresholds
        if progress >= t.get("convergence", 0.90):
            if progress >= t.get("finale", 1.01):
                return StoryPhase.FINALE
            return StoryPhase.CONVERGENCE
        elif progress >= t.get("opening", 0.25):
            return StoryPhase.DEVELOPMENT
        else:
            return StoryPhase.OPENING
    
    def _get_phase_directives(self) -> Dict[StoryPhase, str]:
        """从 PromptRegistry / CPMS 获取阶段指令字典。"""
        raw = get_prompt_registry().get_directives_dict(
            self._LIFECYCLE_PROMPT_ID, directives_key="_directives"
        )
        if not raw:
            logger.warning("沙漏阶段指令未找到 (id=%s)，使用空指令", self._LIFECYCLE_PROMPT_ID)
            return {}

        result: Dict[StoryPhase, str] = {}
        for key, value in raw.items():
            try:
                phase = StoryPhase[key]
                result[phase] = str(value)
            except KeyError:
                logger.debug("未知阶段 key=%s，跳过", key)
        return result

    def _build_lifecycle_directive(self, novel_id: str, chapter_number: int) -> str:
        """构建生命周期行为准则文本（指令来自 CPMS lifecycle-phase-directives）。"""
        total = self._estimate_total_chapters(novel_id)
        progress = chapter_number / max(total, 1)
        phase = self._classify_phase(progress)

        directives = self._get_phase_directives()
        base_directive = directives.get(phase, "")

        directive = f"{base_directive}\n\n"
        directive += f"——\n"
        directive += f"📊 全局进度：第 {chapter_number} 章 / 约 {total} 章 ({progress:.0%})\n"
        directive += f"🎯 当前阶段：{phase.value}\n"

        registry = get_prompt_registry()

        if phase == StoryPhase.CONVERGENCE:
            remaining = total - chapter_number
            extra_tpl = registry.get_field(self._LIFECYCLE_PROMPT_ID, "_convergence_extra", "")
            directive += (extra_tpl.format(remaining=remaining) if extra_tpl else f"⚠️ 剩余约 {remaining} 章完成收束，时间紧迫。\n")
        elif phase == StoryPhase.FINALE:
            remaining = total - chapter_number
            extra_tpl = registry.get_field(self._LIFECYCLE_PROMPT_ID, "_finale_extra", "")
            directive += (extra_tpl.format(remaining=remaining) if extra_tpl else f"🔥 剩余约 {remaining} 章，这是最后的冲刺。\n")

        return directive

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

    def _build_character_state_lock_block(self, novel_id: str) -> str:
        """构建角色状态锁文本块（T0 注入）。

        从 Bible 仓库读取当前章节出场角色的状态向量，
        生成防记忆漂移的锚点文本。
        """
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
