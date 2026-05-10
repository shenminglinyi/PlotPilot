"""三层记忆模型实现 — MemoryOrchestrator

三层记忆架构（复刻人类作家）：
- T0 语义记忆(20%)：世界观设定、角色关系、伏笔状态、Fact Lock
- T1 情景记忆(30%)：EmotionLedger（情绪账本替代摘要）
- T2 工作记忆(35%)：最近10-15章的完整内容
- T3 向量召回(15%)：早期原文片段（Echo Recall）

Token预算紧张时的挤压策略：
- T3 → T2 → T1 逐层挤压
- T0 绝对保护（不可挤压）
"""
from __future__ import annotations

import json
import logging
from typing import Dict, Any, List, Optional

from engine.core.services.memory_orchestrator import (
    MemoryOrchestrator, TokenBudget, ContextAssembly,
)
from engine.core.entities.story import StoryId
from engine.core.value_objects.emotion_ledger import EmotionLedger
from engine.infrastructure.memory.echo_recall import EchoRecall
from engine.infrastructure.memory.character_soul import CharacterSoulEngine

logger = logging.getLogger(__name__)


class MemoryOrchestratorImpl(MemoryOrchestrator):
    """三层记忆模型实现

    组装写作上下文，Token预算管理，EmotionLedger更新
    """

    def __init__(
        self,
        db_pool=None,
        character_soul: Optional[CharacterSoulEngine] = None,
        echo_recall: Optional[EchoRecall] = None,
    ):
        self._db_pool = db_pool
        self._character_soul = character_soul or CharacterSoulEngine(db_pool)
        self._echo_recall = echo_recall or EchoRecall(db_pool)

    async def assemble_context(
        self,
        story_id: StoryId,
        chapter_number: int,
        budget: TokenBudget,
    ) -> ContextAssembly:
        """组装写作上下文（三层记忆模型）"""
        assembly = ContextAssembly(budget=budget)

        try:
            # T0 语义记忆(20%)：世界观+角色面具+伏笔状态
            t0_parts = await self._assemble_t0(story_id.value, chapter_number)
            assembly.t0_content = "\n\n".join(t0_parts)

            # T1 情景记忆(30%)：EmotionLedger
            assembly.t1_content = await self._assemble_t1(story_id.value, chapter_number)

            # T2 工作记忆(35%)：最近章节内容
            assembly.t2_content = await self._assemble_t2(story_id.value, chapter_number)

            # T3 向量召回(15%)：早期原文
            assembly.t3_content = await self._assemble_t3(story_id.value, chapter_number)

            # Token预算挤压
            assembly = self._apply_budget_pressure(assembly, budget)

        except Exception as e:
            logger.error(f"组装上下文失败: {e}")

        return assembly

    async def _assemble_t0(self, story_id: str, chapter_number: int) -> List[str]:
        """T0 语义记忆：世界观+角色面具+伏笔状态"""
        parts = []

        # 角色Fact Lock
        try:
            if self._db_pool:
                with self._db_pool.get_connection() as conn:
                    # 获取故事中的角色列表
                    rows = conn.execute(
                        """SELECT character_id FROM story_characters
                           WHERE story_id = ?""",
                        (story_id,)
                    ).fetchall()

                    for row in rows:
                        fact_lock = await self._character_soul.generate_t0_fact_lock(
                            row["character_id"], chapter_number
                        )
                        if fact_lock:
                            parts.append(fact_lock)
        except Exception as e:
            logger.debug(f"T0角色FactLock组装失败: {e}")

        return parts

    async def _assemble_t1(self, story_id: str, chapter_number: int) -> str:
        """T1 情景记忆：EmotionLedger"""
        try:
            if self._db_pool:
                with self._db_pool.get_connection() as conn:
                    row = conn.execute(
                        """SELECT emotion_ledger FROM stories
                           WHERE id = ?""",
                        (story_id,)
                    ).fetchone()

                    if row and row["emotion_ledger"]:
                        ledger_data = json.loads(row["emotion_ledger"])
                        ledger = EmotionLedger.from_dict(ledger_data)
                        return ledger.to_t0_section()
        except Exception as e:
            logger.debug(f"T1情景记忆组装失败: {e}")

        return ""

    async def _assemble_t2(self, story_id: str, chapter_number: int) -> str:
        """T2 工作记忆：最近10-15章的完整内容"""
        try:
            if self._db_pool:
                with self._db_pool.get_connection() as conn:
                    rows = conn.execute(
                        """SELECT number, title, content
                           FROM chapters
                           WHERE novel_id = ? AND number < ?
                           ORDER BY number DESC
                           LIMIT 10""",
                        (story_id, chapter_number)
                    ).fetchall()

                    if rows:
                        parts = []
                        for row in reversed(rows):
                            header = f"第{row['number']}章 {row['title'] or ''}"
                            content = row["content"] or ""
                            # 截断过长章节
                            if len(content) > 2000:
                                content = content[:2000] + "...(截断)"
                            parts.append(f"{header}\n{content}")
                        return "\n\n---\n\n".join(parts)
        except Exception as e:
            logger.debug(f"T2工作记忆组装失败: {e}")

        return ""

    async def _assemble_t3(self, story_id: str, chapter_number: int) -> str:
        """T3 向量召回：早期原文片段"""
        parts = []

        try:
            if self._db_pool:
                with self._db_pool.get_connection() as conn:
                    # 获取故事中的角色
                    rows = conn.execute(
                        """SELECT character_id, character_name
                           FROM story_characters
                           WHERE story_id = ?""",
                        (story_id,)
                    ).fetchall()

                    for row in rows:
                        instruction = await self._echo_recall.generate_echo_instruction(
                            character_id=row["character_id"],
                            character_name=row["character_name"],
                            context=f"第{chapter_number}章",
                        )
                        if instruction:
                            parts.append(instruction)
        except Exception as e:
            logger.debug(f"T3向量召回组装失败: {e}")

        return "\n\n".join(parts)

    def _apply_budget_pressure(self, assembly: ContextAssembly, budget: TokenBudget) -> ContextAssembly:
        """Token预算挤压（T3→T2→T1，T0绝对保护）"""
        # 粗略估算Token数（中文约1.5字/token）
        def estimate_tokens(text: str) -> int:
            return len(text) // 2 if text else 0

        total = estimate_tokens(assembly.t0_content) + estimate_tokens(assembly.t1_content) + estimate_tokens(assembly.t2_content) + estimate_tokens(assembly.t3_content)
        assembly.total_tokens = total

        if total <= budget.total:
            return assembly  # 预算充足

        # 挤压T3
        t3_tokens = estimate_tokens(assembly.t3_content)
        if t3_tokens > budget.t3_max:
            # 截断T3
            max_chars = budget.t3_max * 2
            assembly.t3_content = assembly.t3_content[:max_chars]

        # 挤压T2
        t2_tokens = estimate_tokens(assembly.t2_content)
        if t2_tokens > budget.t2_max:
            max_chars = budget.t2_max * 2
            assembly.t2_content = assembly.t2_content[:max_chars] + "\n...(更多章节已截断)"

        # 挤压T1
        t1_tokens = estimate_tokens(assembly.t1_content)
        if t1_tokens > budget.t1_max:
            max_chars = budget.t1_max * 2
            assembly.t1_content = assembly.t1_content[:max_chars]

        # T0绝对保护（不挤压）

        # 重新估算
        assembly.total_tokens = (
            estimate_tokens(assembly.t0_content) +
            estimate_tokens(assembly.t1_content) +
            estimate_tokens(assembly.t2_content) +
            estimate_tokens(assembly.t3_content)
        )

        return assembly

    async def update_emotion_ledger(
        self,
        story_id: StoryId,
        chapter_number: int,
        chapter_content: str,
    ) -> EmotionLedger:
        """更新情绪账本（从章节内容中提取情感变化）"""
        # 读取当前账本
        current_ledger = EmotionLedger.create_empty()

        try:
            if self._db_pool:
                with self._db_pool.get_connection() as conn:
                    row = conn.execute(
                        "SELECT emotion_ledger FROM stories WHERE id = ?",
                        (story_id.value,)
                    ).fetchone()

                    if row and row["emotion_ledger"]:
                        current_ledger = EmotionLedger.from_dict(json.loads(row["emotion_ledger"]))
        except Exception as e:
            logger.debug(f"读取EmotionLedger失败: {e}")

        # TODO: 使用LLM提取情感变化，这里提供简化实现
        # 实际实现应调用LLM分析章节内容，提取Wounds/Boons/PowerShifts/OpenLoops

        return current_ledger

    async def manage_foreshadow(
        self,
        story_id: StoryId,
        foreshadow_id: str,
        action: str,
        chapter_number: int = 0,
    ) -> None:
        """管理伏笔生命周期"""
        if not self._db_pool:
            return

        try:
            with self._db_pool.get_connection() as conn:
                if action == "plant":
                    # 新伏笔在Foreshadow实体创建时已处理
                    pass
                elif action == "reference":
                    conn.execute(
                        """UPDATE foreshadows
                           SET reference_count = reference_count + 1
                           WHERE id = ?""",
                        (foreshadow_id,)
                    )
                elif action == "awaken":
                    conn.execute(
                        """UPDATE foreshadows SET status = 'awakening'
                           WHERE id = ? AND status IN ('planted', 'referenced')""",
                        (foreshadow_id,)
                    )
                elif action == "resolve":
                    conn.execute(
                        """UPDATE foreshadows
                           SET status = 'resolved', resolved_in_chapter = ?
                           WHERE id = ?""",
                        (chapter_number, foreshadow_id)
                    )
                elif action == "abandon":
                    conn.execute(
                        "UPDATE foreshadows SET status = 'abandoned' WHERE id = ?",
                        (foreshadow_id,)
                    )

                conn.commit()
        except Exception as e:
            logger.error(f"管理伏笔失败: {e}")
