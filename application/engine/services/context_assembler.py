"""上下文反哺管线（ContextAssembler - Feed-forward）

核心破局动作：反哺（Feed-forward）

把 ChapterAftermathPipeline 和 MacroDiagnosisService 产生的高质量资产
（知识图谱因果节点、人物可变状态标签、到期的伏笔债务），
通过统一的 ContextAssembler，高优先级地投喂给下一章的生成上下文。

宁可牺牲词藻的华丽，也必须保住因果图谱和动态状态的完整传入。

新增 T0 槽位：
  - STORY_ANCHOR (priority=125): 全书主线锚点 ≤300 字
  - SCARS_AND_MOTIVATIONS (priority=118): 角色伤疤与执念
  - ACTIVE_ENTITY_MEMORY (priority=112): 活跃实体记忆（因果图谱检索）
  - DEBT_DUE (priority=108): 叙事债务到期提醒
  - PREVIOUSLY_ON (priority=107): 卷级动态摘要

新增 T1 槽位：
  - CAUSAL_CHAINS: 未闭环因果链
  - COMPLETED_VOLUME_SUMMARIES: 已完结卷摘要
"""
import json
import logging
from typing import Dict, List, Optional, Any

from domain.novel.repositories.causal_edge_repository import CausalEdgeRepository
from domain.novel.repositories.character_state_repository import CharacterStateRepository
from domain.novel.repositories.narrative_debt_repository import NarrativeDebtRepository
from domain.novel.repositories.foreshadowing_repository import ForeshadowingRepository
from domain.novel.repositories.chapter_repository import ChapterRepository
from domain.novel.repositories.novel_repository import NovelRepository
from domain.bible.repositories.bible_repository import BibleRepository
from infrastructure.persistence.database.story_node_repository import StoryNodeRepository

logger = logging.getLogger(__name__)


class ContextAssembler:
    """上下文反哺管线（Feed-forward 核心入口）

    职责：
    1. 收集所有章后管线产生的资产
    2. 按优先级注入下一章的生成上下文
    3. 确保"该给的上下文就应该放"

    使用方式：
        assembler = ContextAssembler(
            causal_edge_repo=...,
            character_state_repo=...,
            debt_repo=...,
            ...
        )

        # 在 ContextBudgetAllocator._collect_all_slots 中调用
        anchor = assembler.build_story_anchor(novel_id)
        scars = assembler.build_scars_and_motivations(novel_id)
        active_entities = assembler.build_active_entity_memory(novel_id, chapter_number, outline)
        debt_due = assembler.build_debt_due_block(novel_id, chapter_number, outline)
        previously_on = assembler.build_previously_on(novel_id, chapter_number)
        causal_chains = assembler.build_causal_chains(novel_id)
    """

    def __init__(
        self,
        causal_edge_repo: Optional[CausalEdgeRepository] = None,
        character_state_repo: Optional[CharacterStateRepository] = None,
        debt_repo: Optional[NarrativeDebtRepository] = None,
        foreshadowing_repo: Optional[ForeshadowingRepository] = None,
        chapter_repo: Optional[ChapterRepository] = None,
        bible_repo: Optional[BibleRepository] = None,
        story_node_repo: Optional[StoryNodeRepository] = None,
        novel_repository: Optional[NovelRepository] = None,
    ):
        self.causal_edge_repo = causal_edge_repo
        self.character_state_repo = character_state_repo
        self.debt_repo = debt_repo
        self.foreshadowing_repo = foreshadowing_repo
        self.chapter_repo = chapter_repo
        self.bible_repo = bible_repo
        self.story_node_repo = story_node_repo
        self.novel_repository = novel_repository

    # ============================================================
    # T0 槽位构建方法
    # ============================================================

    def build_story_anchor(self, novel_id: str) -> str:
        """构建 T0: 全书主线锚点（≤300 字）

        格式：
        【📖 全书主线锚点（绝不可忘）】
        世界观：修仙世界，强者为尊
        主角目标：找到灭门仇人，为宗门复仇
        当前最大阻碍：仇人已是大陆第一强者
        """
        lines = ["【📖 全书主线锚点（绝不可忘）】"]

        if self.story_node_repo:
            try:
                nodes = self.story_node_repo.get_by_novel_sync(novel_id)

                root_nodes = [n for n in nodes if n.node_type.value == "root"]
                act_nodes = [n for n in nodes if n.node_type.value == "act"]

                if root_nodes:
                    root = root_nodes[0]
                    if root.description:
                        lines.append(f"世界观：{root.description[:100]}")
                    if root.narrative_arc:
                        lines.append(f"主线方向：{root.narrative_arc[:100]}")

                if act_nodes:
                    first_act = act_nodes[0]
                    if first_act.narrative_arc:
                        lines.append(f"起始目标：{first_act.narrative_arc[:80]}")
            except Exception as e:
                logger.warning("构建全书主线锚点（结构树）失败: %s", e)

        substantive = "\n".join(lines[1:]).strip()
        if len(substantive) < 36 and self.novel_repository:
            try:
                from domain.novel.value_objects.novel_id import NovelId

                novel = self.novel_repository.get_by_id(NovelId(novel_id))
                premise = (getattr(novel, "premise", None) or "").strip()
                premise_body = self._strip_internal_premise_prefix(premise)
                if premise_body:
                    lines.append(f"梗概主轴：{premise_body[:240]}")
            except Exception as e:
                logger.debug("ANCHOR 梗概兜底跳过: %s", e)

        result = "\n".join(lines)
        if len(result) > 300:
            result = result[:297] + "..."
        return result

    @staticmethod
    def _strip_internal_premise_prefix(premise: str) -> str:
        """去掉 create_novel 写入的系统内部体量前缀，保留作者梗概正文。"""
        if not premise:
            return ""
        if "【系统内部·叙事结构规划" in premise:
            idx = premise.find("\n\n")
            if idx != -1:
                premise = premise[idx + 2 :].strip()
        return premise.strip()

    def build_scars_and_motivations(self, novel_id: str) -> str:
        """构建 T0: 角色伤疤与执念

        从 CharacterStateRepository 获取有活跃伤疤的角色状态，
        调用 CharacterState.build_context_injection() 生成注入文本。
        """
        if not self.character_state_repo:
            return ""

        try:
            states = self.character_state_repo.get_characters_with_active_scars(novel_id)
            if not states:
                return ""

            id_to_name: Dict[str, str] = {}
            if self.bible_repo:
                try:
                    from domain.novel.value_objects.novel_id import NovelId

                    bible = self.bible_repo.get_by_novel_id(NovelId(novel_id))
                    if bible and getattr(bible, "characters", None):
                        for c in bible.characters:
                            cid = getattr(c, "character_id", None)
                            raw = cid.value if cid is not None and hasattr(cid, "value") else ""
                            nm = (getattr(c, "name", None) or "").strip()
                            if raw and nm:
                                id_to_name[str(raw)] = nm
                except Exception:
                    pass

            parts = []
            for state in states:
                dn = id_to_name.get(state.character_id, "").strip()
                injection = state.build_context_injection(display_name=dn or None)
                if injection:
                    parts.append(injection)

            return "\n\n".join(parts)

        except Exception as e:
            logger.warning(f"构建伤疤与执念注入失败: {e}")
            return ""

    def build_active_entity_memory(
        self,
        novel_id: str,
        chapter_number: int,
        outline: str,
    ) -> str:
        """构建 T0: 活跃实体记忆（因果图谱检索）

        核心逻辑：
        1. 从大纲中提取实体名称
        2. 在因果图谱中查出与主角的因果链
        3. 生成结构化的"前情提要"注入 T0
        """
        if not self.causal_edge_repo:
            return ""

        try:
            # 从大纲提取实体名称
            entity_names = self._extract_entities_from_outline(outline, novel_id)
            if not entity_names:
                return ""

            lines = ["【🧠 活跃实体记忆（写到此角色/势力时必须参考）】"]

            for entity_name in entity_names[:5]:  # 最多 5 个实体
                # 查因果链
                chains = self.causal_edge_repo.get_chains_involving(novel_id, entity_name)
                if not chains:
                    continue

                entity_lines = [f"\n  {entity_name}:"]
                for chain in chains[:3]:  # 每个实体最多 3 条因果链
                    entity_lines.append(
                        f"    [第{chain.source_chapter}章] {chain.source_event_summary} "
                        f"{chain.display_label} {chain.target_event_summary}"
                    )
                    if chain.state_change:
                        entity_lines.append(f"      状态变化: {chain.state_change}")

                lines.extend(entity_lines)

            if len(lines) <= 1:
                return ""

            return "\n".join(lines)

        except Exception as e:
            logger.warning(f"构建活跃实体记忆失败: {e}")
            return ""

    def build_debt_due_block(
        self,
        novel_id: str,
        chapter_number: int,
        outline: str = "",
    ) -> str:
        """构建 T0: 叙事债务到期提醒（MUST_RESOLVE）

        查出即将到期的伏笔、未闭环的因果边、未结算的故事线，
        放入 [MUST_RESOLVE] 块，强迫大模型在本章填坑。
        """
        if not self.debt_repo:
            return ""

        try:
            # 获取即将到期的债务
            due_soon = self.debt_repo.get_due_soon(novel_id, chapter_number, window=3)
            overdue = self.debt_repo.get_overdue(novel_id)

            # 合并去重
            all_debts = overdue + due_soon
            seen_ids = set()
            unique_debts = []
            for d in all_debts:
                if d.id not in seen_ids:
                    seen_ids.add(d.id)
                    unique_debts.append(d)

            if not unique_debts:
                return ""

            lines = ["【🚨 叙事债务到期提醒（MUST_RESOLVE）】"]

            for debt in unique_debts[:6]:  # 最多 6 条
                if debt.is_overdue:
                    marker = "🔴逾期"
                else:
                    due_info = f"Ch{debt.due_chapter}" if debt.due_chapter else "?"
                    marker = f"🟡Ch{due_info}到期"

                lines.append(
                    f"  {marker} [{debt.debt_type_label}] {debt.description} "
                    f"(埋于Ch{debt.planted_chapter})"
                )
                if debt.context:
                    lines.append(f"       ⚠️ {debt.context}")

            # 大纲冲突检测
            outline_conflicts = self._check_outline_debt_conflicts(outline, unique_debts)
            for conflict in outline_conflicts[:2]:
                lines.append(f"  ⚠️ 大纲冲突: {conflict}")

            lines.append("\n【如果你无视此指令，长篇小说的情节网将陷入崩溃】")

            return "\n".join(lines)

        except Exception as e:
            logger.warning(f"构建叙事债务到期提醒失败: {e}")
            return ""

    def build_previously_on(self, novel_id: str, chapter_number: int) -> str:
        """构建 T0: Previously On（卷级动态摘要）

        格式：
        【📺 Previously On】
        当前卷（第二卷·风云际会）: 林羽在青云门修行的第三年，
        比武大会筹备中，他已突破筑基期，但赵宇的死让他的心境出现裂痕...

        已完结卷:
        第一卷：林羽入青云门，获得古玉佩，与赵宇结为挚友
        """
        if not self.story_node_repo:
            return ""

        try:
            nodes = self.story_node_repo.get_by_novel_sync(novel_id)
            act_nodes = sorted(
                [n for n in nodes if n.node_type.value == "act"],
                key=lambda n: getattr(n, 'chapter_start', 0) or 0
            )

            if not act_nodes:
                return ""

            lines = ["【📺 Previously On】"]

            # 找当前卷
            current_act = None
            completed_acts = []
            for act in act_nodes:
                cs = getattr(act, 'chapter_start', None)
                ce = getattr(act, 'chapter_end', None)
                if cs and ce and cs <= chapter_number <= ce:
                    current_act = act
                elif ce and ce < chapter_number:
                    completed_acts.append(act)

            # 当前卷摘要（过程态，详细）
            if current_act:
                title = getattr(current_act, 'title', '当前卷')
                lines.append(f"\n当前卷（{title}）:")
                desc = getattr(current_act, 'description', '') or ''
                arc = getattr(current_act, 'narrative_arc', '') or ''
                if desc:
                    lines.append(f"  {desc[:400]}")
                if arc:
                    lines.append(f"  叙事弧线: {arc[:200]}")

            # 已完结卷摘要（结果态，极简）
            if completed_acts:
                lines.append("\n已完结卷:")
                for act in completed_acts[-3:]:  # 最多 3 个
                    title = getattr(act, 'title', '?')
                    desc = getattr(act, 'description', '') or ''
                    summary = desc[:100] if desc else "（无摘要）"
                    lines.append(f"  {title}: {summary}")

            return "\n".join(lines)

        except Exception as e:
            logger.warning(f"构建 Previously On 失败: {e}")
            return ""

    # ============================================================
    # T1 槽位构建方法
    # ============================================================

    def build_causal_chains(self, novel_id: str) -> str:
        """构建 T1: 未闭环因果链

        列出所有未闭环的高强度因果边，
        提醒 AI 这些"因果债务"尚未收束。
        """
        if not self.causal_edge_repo:
            return ""

        try:
            unresolved = self.causal_edge_repo.get_high_strength_unresolved(
                novel_id, min_strength=0.7
            )
            if not unresolved:
                return ""

            lines = ["【🔗 未闭环因果链（参考）】"]
            for edge in unresolved[:6]:
                lines.append(
                    f"  [Ch{edge.source_chapter}] {edge.source_event_summary} "
                    f"{edge.display_label} {edge.target_event_summary}"
                    f" (强度:{edge.strength:.1f})"
                )
                if edge.state_change:
                    lines.append(f"    → {edge.state_change}")

            return "\n".join(lines)

        except Exception as e:
            logger.warning(f"构建因果链摘要失败: {e}")
            return ""

    # ============================================================
    # 辅助方法
    # ============================================================

    def _extract_entities_from_outline(
        self,
        outline: str,
        novel_id: str,
    ) -> List[str]:
        """从大纲中提取实体名称

        策略：
        1. 从 Bible 中获取所有角色名
        2. 在大纲中匹配出现的角色名
        3. 返回出现的角色名列表
        """
        if not self.bible_repo or not outline:
            return []

        try:
            bible = self.bible_repo.get_by_novel_id(novel_id)
            if not bible or not bible.characters:
                return []

            # 在大纲中查找角色名出现
            found = []
            for char in bible.characters:
                if char.name in outline:
                    found.append(char.name)

            return found

        except Exception as e:
            logger.debug(f"从大纲提取实体失败: {e}")
            return []

    def _check_outline_debt_conflicts(
        self,
        outline: str,
        debts: List,
    ) -> List[str]:
        """检测大纲与未结算债务的冲突

        例：大纲试图"离开新手村"，但新手村的债务未清
        """
        if not outline:
            return []

        conflicts = []

        # 简单的关键词匹配检测
        leave_keywords = ["离开", "出发", "启程", "告别", "远离"]
        for debt in debts:
            if not debt.involved_entities:
                continue
            for entity in debt.involved_entities:
                if entity in outline:
                    # 大纲提到了与债务相关的实体
                    for kw in leave_keywords:
                        if kw in outline and debt.importance >= 3:
                            conflicts.append(
                                f"大纲试图'{kw}'，但'{entity}'相关的债务未结算: {debt.description}"
                            )
                            break

        return conflicts
