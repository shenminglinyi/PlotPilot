"""上下文配额分配器 - 洋葱模型优先级挤压

核心设计：
- T0 级（绝对不删减）：系统 Prompt、当前幕摘要、强制伏笔、角色锚点
- T1 级（按比例压缩）：图谱子网、近期幕摘要
- T2 级（动态水位线）：最近章节内容
- T3 级（可牺牲泡沫）：向量召回片段

当 Token 预算紧张时，从 T3 → T2 → T1 逐层挤压，T0 绝对保护。
"""
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

from domain.novel.value_objects.novel_id import NovelId
from domain.novel.value_objects.chapter_id import ChapterId
from domain.novel.repositories.foreshadowing_repository import ForeshadowingRepository
from domain.novel.repositories.chapter_repository import ChapterRepository
from domain.bible.repositories.bible_repository import BibleRepository
from infrastructure.persistence.database.story_node_repository import StoryNodeRepository
from domain.ai.services.vector_store import VectorStore
from domain.ai.services.embedding_service import EmbeddingService
from application.ai.vector_retrieval_facade import VectorRetrievalFacade

logger = logging.getLogger(__name__)


class PriorityTier(str, Enum):
    """优先级层级（洋葱模型）"""
    T0_CRITICAL = "t0_critical"      # 绝对不删减
    T1_COMPRESSIBLE = "t1_compressible"  # 按比例压缩
    T2_DYNAMIC = "t2_dynamic"        # 动态水位线
    T3_SACRIFICIAL = "t3_sacrificial"  # 可牺牲泡沫


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
    T0_BUDGET_RATIO = 0.25   # 25% 给 T0（强制内容）
    T1_BUDGET_RATIO = 0.25   # 25% 给 T1（可压缩）
    T2_BUDGET_RATIO = 0.30   # 30% 给 T2（动态）
    T3_BUDGET_RATIO = 0.20   # 20% 给 T3（可牺牲）
    
    # 各槽位的默认上限
    MAX_FORESHADOWING_TOKENS = 2000
    MAX_CHARACTER_ANCHORS_TOKENS = 1500
    MAX_GRAPH_SUBNETWORK_TOKENS = 1000
    MAX_ACT_SUMMARIES_TOKENS = 1500
    MAX_RECENT_CHAPTERS_TOKENS = 5000
    MAX_VECTOR_RECALL_TOKENS = 5000
    
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
    ):
        self.foreshadowing_repo = foreshadowing_repository
        self.chapter_repo = chapter_repository
        self.bible_repo = bible_repository
        self.story_node_repo = story_node_repository
        self.chapter_element_repo = chapter_element_repository
        self.triple_repo = triple_repository
        
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
        scene_director: Optional[Dict[str, Any]] = None,
    ) -> BudgetAllocation:
        """执行预算分配
        
        Args:
            novel_id: 小说 ID
            chapter_number: 当前章节号
            outline: 章节大纲
            total_budget: 总 Token 预算
            scene_director: 场记分析结果（可选的角色/地点过滤）
        
        Returns:
            BudgetAllocation: 分配结果
        """
        allocation = BudgetAllocation(total_budget=total_budget)
        
        # ========== 第一步：收集所有内容 ==========
        slots = self._collect_all_slots(novel_id, chapter_number, outline, scene_director)
        
        # ========== 第二步：计算 T0 强制保留量 ==========
        t0_slots = {name: slot for name, slot in slots.items() if slot.tier == PriorityTier.T0_CRITICAL}
        t0_total = sum(slot.tokens for slot in t0_slots.values())
        
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
        t3_slots = {name: slot for name, slot in slots.items() if slot.tier == PriorityTier.T3_SACRIFICIAL}
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
    ) -> Dict[str, ContextSlot]:
        """收集所有上下文槽位"""
        slots = {}
        
        # ==================== T0: 强制内容 ====================
        
        # 1. 当前幕摘要
        act_summary = self._get_current_act_summary(novel_id, chapter_number)
        slots["current_act_summary"] = ContextSlot(
            name="当前幕摘要",
            tier=PriorityTier.T0_CRITICAL,
            content=act_summary,
            tokens=self.estimate_tokens(act_summary),
            priority=100,
        )
        
        # 2. 待回收伏笔（绝对优先级）
        foreshadowing_content = self._get_pending_foreshadowings(novel_id, chapter_number)
        slots["pending_foreshadowings"] = ContextSlot(
            name="待回收伏笔",
            tier=PriorityTier.T0_CRITICAL,
            content=foreshadowing_content,
            tokens=self.estimate_tokens(foreshadowing_content),
            max_tokens=self.MAX_FORESHADOWING_TOKENS,
            priority=90,
        )
        
        # 3. 本章角色锚点（传入大纲用于智能调度）
        character_anchors = self._get_character_anchors(novel_id, chapter_number, scene_director, outline)
        slots["character_anchors"] = ContextSlot(
            name="角色锚点",
            tier=PriorityTier.T0_CRITICAL,
            content=character_anchors,
            tokens=self.estimate_tokens(character_anchors),
            max_tokens=self.MAX_CHARACTER_ANCHORS_TOKENS,
            priority=80,
        )
        
        # 4. 宏观诊断断点（人设冲突提醒）
        diagnosis_breakpoints = self._get_diagnosis_breakpoints(novel_id, chapter_number)
        slots["diagnosis_breakpoints"] = ContextSlot(
            name="人设冲突提醒",
            tier=PriorityTier.T0_CRITICAL,
            content=diagnosis_breakpoints,
            tokens=self.estimate_tokens(diagnosis_breakpoints),
            max_tokens=1500,  # 最大 1500 tokens
            priority=85,  # 介于角色锚点和伏笔之间
        )
        
        # ==================== T1: 可压缩内容 ====================
        
        # 4. 图谱子网（一度关系）
        graph_content = self._get_graph_subnetwork(novel_id, chapter_number, outline)
        slots["graph_subnetwork"] = ContextSlot(
            name="图谱子网",
            tier=PriorityTier.T1_COMPRESSIBLE,
            content=graph_content,
            tokens=self.estimate_tokens(graph_content),
            max_tokens=self.MAX_GRAPH_SUBNETWORK_TOKENS,
            priority=70,
        )
        
        # 5. 近期幕摘要
        recent_acts = self._get_recent_act_summaries(novel_id, chapter_number, limit=3)
        slots["recent_act_summaries"] = ContextSlot(
            name="近期幕摘要",
            tier=PriorityTier.T1_COMPRESSIBLE,
            content=recent_acts,
            tokens=self.estimate_tokens(recent_acts),
            max_tokens=self.MAX_ACT_SUMMARIES_TOKENS,
            priority=60,
        )
        
        # ==================== T2: 动态内容 ====================
        
        # 6. 最近章节内容
        recent_chapters = self._get_recent_chapters(novel_id, chapter_number, limit=3)
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
    
    def _get_pending_foreshadowings(self, novel_id: str, chapter_number: int) -> str:
        """获取待回收伏笔（轨道二核心）- 按预期回收章节优先排序。"""
        if not self.foreshadowing_repo:
            return ""
        
        try:
            nid = NovelId(novel_id)
            registry = self.foreshadowing_repo.get_by_novel_id(nid)
            
            if not registry:
                return ""
            
            # 获取待回收伏笔 + 待消费的潜台词
            pending_foreshadows = registry.get_unresolved()
            pending_subtext = registry.get_pending_subtext_entries()
            
            lines = []
            
            # 对伏笔按预期回收章节排序
            def foreshadow_sort_key(f):
                if f.suggested_resolve_chapter:
                    if f.suggested_resolve_chapter <= chapter_number:
                        # 已到期，最高优先级
                        return (0, -f.importance.value, f.suggested_resolve_chapter)
                    else:
                        # 未到期，按距离排序
                        return (1, -f.importance.value, f.suggested_resolve_chapter)
                else:
                    # 无预期章节，放最后
                    return (2, -f.importance.value, 9999)
            
            sorted_foreshadows = sorted(pending_foreshadows, key=foreshadow_sort_key)
            
            if sorted_foreshadows:
                lines.append("【待回收伏笔】")
                for f in sorted_foreshadows[:10]:  # 最多 10 个
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
                lines.append("\n【潜台词账本】")
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
                        f"- Ch{entry.chapter} [{entry.character_id}] {status_mark}: {entry.hidden_clue}"
                    )
                    if entry.sensory_anchors:
                        anchors = ", ".join(f"{k}:{v}" for k, v in entry.sensory_anchors.items())
                        lines.append(f"  感官锚点: {anchors}")
            
            return "\n".join(lines)
            
        except Exception as e:
            logger.warning(f"获取待回收伏笔失败: {e}")
        
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
                
                # 刚登场标记
                if is_recently_appeared:
                    profile_parts.append("⚠️ 刚登场，需保持一致性")
                
                lines.append(f"\n- {char.name}: " + " | ".join(profile_parts))
            
            logger.info(
                f"[CharacterAnchors] 选中 {len(selected_characters)} 个角色, "
                f"包含 {sum(1 for _, r in selected_characters if r)} 个刚登场角色"
            )
            
            return "\n".join(lines)
        
        except Exception as e:
            logger.warning(f"获取角色锚点失败: {e}")
        
        return ""
    
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
    
    def _get_recent_chapters(
        self,
        novel_id: str,
        chapter_number: int,
        limit: int = 3,
    ) -> str:
        """获取最近章节内容"""
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
            
            if not recent:
                return ""
            
            lines = ["【最近章节】"]
            for chapter in reversed(recent):  # 按时间顺序
                lines.append(f"\n第 {chapter.number} 章：{chapter.title}")
                if chapter.content:
                    # 截取前 500 字作为预览
                    preview = chapter.content[:500]
                    if len(chapter.content) > 500:
                        preview += "..."
                    lines.append(preview)
            
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
        """获取宏观诊断断点（人设冲突提醒）
        
        从最新的未解决宏观诊断结果中提取冲突断点，注入到后续生成的提示词中，
        提醒 LLM 避免继续犯相同的人设错误。
        
        已解决的诊断结果不会被注入。
        
        Args:
            novel_id: 小说 ID
            chapter_number: 当前章节号
        
        Returns:
            格式化的人设冲突提醒文本
        """
        try:
            from infrastructure.persistence.database.connection import get_database
            
            db = get_database()
            
            # 获取最新未解决的诊断结果（关键：resolved = 0）
            sql = """
                SELECT breakpoints, trait, trigger_reason, created_at
                FROM macro_diagnosis_results
                WHERE novel_id = ? AND status = 'completed' AND resolved = 0
                ORDER BY created_at DESC
                LIMIT 1
            """
            row = db.fetch_one(sql, (novel_id,))
            
            if not row or not row["breakpoints"]:
                return ""
            
            import json
            breakpoints = json.loads(row["breakpoints"])
            
            if not breakpoints:
                return ""
            
            # 过滤：只保留当前章节之前的断点（已存在的冲突）
            relevant_breakpoints = [
                bp for bp in breakpoints
                if bp.get("chapter", 0) <= chapter_number
            ]
            
            if not relevant_breakpoints:
                return ""
            
            # 构建提醒文本
            lines = [
                "【⚠️ 人设冲突提醒 - 请在后续章节避免继续犯类似错误】",
                f"诊断时间：{row['created_at'][:16] if row['created_at'] else ''}",
                f"扫描人设：{row['trait']}",
                "",
                "已检测到以下人设冲突断点，请在写作时注意避免：",
            ]
            
            # 按章节分组
            by_chapter = {}
            for bp in relevant_breakpoints[:15]:  # 最多 15 个断点
                ch = bp.get("chapter", 0)
                if ch not in by_chapter:
                    by_chapter[ch] = []
                by_chapter[ch].append(bp)
            
            for ch in sorted(by_chapter.keys()):
                bps = by_chapter[ch]
                lines.append(f"\n第 {ch} 章：")
                for bp in bps:
                    reason = bp.get("reason", "")
                    tags = bp.get("tags", [])
                    tags_str = "、".join(tags)
                    lines.append(f"  • {reason}（冲突标签：{tags_str}）")
            
            lines.append("\n【注意】请确保后续章节的角色行为符合人设，避免上述冲突标签。")
            
            return "\n".join(lines)
            
        except Exception as e:
            logger.warning(f"获取宏观诊断断点失败: {e}")
        
        return ""
