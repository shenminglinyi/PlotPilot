"""倒影召回机制 — 向量检索早期发言

核心设计：
- T3向量查询：从早期章节召回角色的发言片段
- T0追加指令："让林羽内心闪过自己当年的影子"
- 角色历史发言库：character_voice_samples表

示例：
第50章，林羽遇到天真少年
1. T3向量查询：召回林羽第1章的发言："我信每个人心底都有光。"
2. T0追加指令："林羽看着少年天真的脸，内心闪过自己当年的影子——那个也相信光的少年。"
"""
from __future__ import annotations

import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class EchoRecall:
    """倒影召回机制

    核心用途：
    - 在写作时召回角色早期的发言/行为
    - 让角色的成长有"回声"效果
    - 增强读者对角色变化的感知
    """

    def __init__(self, db_pool=None, vector_store=None):
        self._db_pool = db_pool
        self._vector_store = vector_store

    async def recall(
        self,
        character_id: str,
        context: str,
        max_results: int = 3,
    ) -> List[Dict[str, Any]]:
        """召回角色早期发言

        Args:
            character_id: 角色ID
            context: 当前场景上下文
            max_results: 最大返回数量

        Returns:
            早期发言列表 [{chapter, content, relevance_score}]
        """
        results = []

        # 1. 尝试向量检索
        if self._vector_store:
            try:
                vector_results = await self._vector_store.search(
                    collection_name="character_voice_samples",
                    query_text=context,
                    filter={"character_id": character_id},
                    limit=max_results,
                )
                results.extend(vector_results)
            except Exception as e:
                logger.warning(f"向量检索失败: {e}")

        # 2. 回退到DB检索
        if not results and self._db_pool:
            try:
                with self._db_pool.get_connection() as conn:
                    rows = conn.execute(
                        """SELECT chapter_number, content, embedding
                           FROM character_voice_samples
                           WHERE character_id = ?
                           ORDER BY chapter_number ASC
                           LIMIT ?""",
                        (character_id, max_results)
                    ).fetchall()

                    for row in rows:
                        results.append({
                            "chapter": row["chapter_number"],
                            "content": row["content"],
                            "relevance_score": 0.5,  # 无向量匹配时的默认分数
                        })
            except Exception as e:
                logger.warning(f"DB检索失败: {e}")

        return results

    async def store_sample(
        self,
        character_id: str,
        chapter_number: int,
        content: str,
    ) -> bool:
        """存储角色发言样本

        Args:
            character_id: 角色ID
            chapter_number: 章节号
            content: 发言内容

        Returns:
            是否成功
        """
        if not self._db_pool:
            return False

        try:
            with self._db_pool.get_connection() as conn:
                conn.execute(
                    """INSERT OR IGNORE INTO character_voice_samples
                       (character_id, chapter_number, content)
                       VALUES (?, ?, ?)""",
                    (character_id, chapter_number, content)
                )
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"存储发言样本失败: {e}")
            return False

    async def generate_echo_instruction(
        self,
        character_id: str,
        character_name: str,
        context: str,
    ) -> Optional[str]:
        """生成倒影召回的T0层注入指令

        Args:
            character_id: 角色ID
            character_name: 角色名
            context: 当前场景上下文

        Returns:
            注入指令（None表示无匹配）
        """
        results = await self.recall(character_id, context, max_results=1)

        if not results:
            return None

        sample = results[0]
        chapter = sample.get("chapter", "?")
        content = sample.get("content", "")

        if not content:
            return None

        return (
            f"[倒影召回] {character_name}看着眼前的场景，"
            f"内心闪过第{chapter}章的自己——"
            f"那时的TA说过：「{content[:50]}」"
        )
