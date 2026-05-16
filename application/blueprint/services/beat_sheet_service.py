"""节拍表生成服务

为章节大纲生成场景列表（Beat Sheet）
"""

import uuid
import json
import logging
from typing import Dict, List, Optional, TYPE_CHECKING
from datetime import datetime

from domain.novel.entities.beat_sheet import BeatSheet
from domain.novel.value_objects.scene import Scene
from domain.novel.repositories.beat_sheet_repository import BeatSheetRepository
from domain.novel.repositories.chapter_repository import ChapterRepository
from domain.novel.repositories.storyline_repository import StorylineRepository
from domain.ai.services.llm_service import LLMService, GenerationConfig
from domain.ai.value_objects.prompt import Prompt

if TYPE_CHECKING:
    from infrastructure.ai.chromadb_vector_store import ChromaDBVectorStore

logger = logging.getLogger(__name__)


class BeatSheetService:
    """节拍表生成服务

    为章节大纲生成 3-5 个场景，采用混合检索策略：
    1. 强制包含（Must-Have）：主要人物、活跃故事线、前置章节状态
    2. 向量检索（Nice-to-Have）：相关伏笔、地点、时间线
    """

    def __init__(
        self,
        beat_sheet_repo: BeatSheetRepository,
        chapter_repo: ChapterRepository,
        storyline_repo: StorylineRepository,
        llm_service: LLMService,
        vector_store: "ChromaDBVectorStore",
        bible_service=None,
    ):
        self.beat_sheet_repo = beat_sheet_repo
        self.chapter_repo = chapter_repo
        self.storyline_repo = storyline_repo
        self.llm_service = llm_service
        self.vector_store = vector_store
        self.bible_service = bible_service

    async def generate_beat_sheet(
        self,
        chapter_id: str,
        outline: str
    ) -> BeatSheet:
        """为章节生成节拍表

        Args:
            chapter_id: 章节 ID
            outline: 章节大纲

        Returns:
            生成的节拍表
        """
        logger.info(f"Generating beat sheet for chapter {chapter_id}")

        # 1. 混合检索：获取相关上下文
        context = await self._retrieve_relevant_context(chapter_id, outline)

        # 2. 构建提示词
        prompt = self._build_beat_sheet_prompt(outline, context)

        # 3. 调用 LLM 生成节拍表
        config = GenerationConfig(max_tokens=2048, temperature=0.7)
        response = await self.llm_service.generate(prompt, config)

        # 4. 解析响应
        scenes = self._parse_llm_response(response)

        # 5. 创建节拍表实体
        beat_sheet = BeatSheet(
            id=str(uuid.uuid4()),
            chapter_id=chapter_id,
            scenes=scenes
        )

        # 6. 保存到仓储
        await self.beat_sheet_repo.save(beat_sheet)

        logger.info(f"Beat sheet generated with {len(scenes)} scenes")
        return beat_sheet

    async def _retrieve_relevant_context(
        self,
        chapter_id: str,
        outline: str,
        max_tokens: int = 3000
    ) -> Dict:
        """混合检索策略：强制包含 + 向量检索 + 智能去重 + tokens 控制

        Phase 1.2 完整版：
        1. 强制包含：主要人物、活跃故事线、前置章节状态
        2. 向量检索：相关伏笔、地点、时间线事件
        3. 智能去重：避免重复信息
        4. Tokens 控制：限制上下文总长度

        Args:
            chapter_id: 章节 ID
            outline: 章节大纲
            max_tokens: 最大 tokens 数（粗略估算：1 token ≈ 1.5 字符）

        Returns:
            检索到的上下文字典
        """
        context = {
            "characters": [],
            "storylines": [],
            "previous_chapter": None,
            "foreshadowings": [],
            "locations": [],
            "timeline_events": []
        }

        # 获取章节信息
        from domain.novel.value_objects.chapter_id import ChapterId
        chapter = self.chapter_repo.get_by_id(ChapterId(chapter_id))
        if not chapter:
            logger.warning(f"Chapter {chapter_id} not found")
            return context

        novel_id = chapter.novel_id
        chapter_number = chapter.number

        # === 第一层：强制包含（Must-Have） ===

        # 1. 获取主要人物（从 Cast）
        try:
            from infrastructure.persistence.database.sqlite_cast_repository import SqliteCastRepository
            from infrastructure.persistence.database.connection import get_database

            cast_repo = SqliteCastRepository(get_database())
            cast = cast_repo.get_by_novel_id(novel_id)

            if cast and cast.characters:
                # 只包含主要角色（前 5 个）
                main_characters = cast.characters[:5]
                context["characters"] = [
                    {
                        "name": char.name,
                        "role": getattr(char, "role", "未知"),
                        "brief": getattr(char, "personality", "")[:100]  # 简短描述
                    }
                    for char in main_characters
                ]
                logger.info(f"Retrieved {len(context['characters'])} main characters")
        except Exception as e:
            logger.warning(f"Failed to retrieve characters: {e}")

        # 2. 获取活跃故事线
        try:
            all_storylines = self.storyline_repo.get_by_novel_id(novel_id)
            # 过滤活跃的故事线（有 last_active_chapter 且在当前章节附近）
            active_storylines = [
                sl for sl in all_storylines
                if hasattr(sl, 'last_active_chapter') and sl.last_active_chapter
                and abs(sl.last_active_chapter - chapter_number) <= 5
            ]
            if active_storylines:
                context["storylines"] = [
                    {
                        "name": sl.name,
                        "type": sl.storyline_type.value if hasattr(sl.storyline_type, 'value') else str(sl.storyline_type),
                        "progress": getattr(sl, "progress_summary", "")[:150]
                    }
                    for sl in active_storylines[:3]  # 最多 3 条
                ]
                logger.info(f"Retrieved {len(context['storylines'])} active storylines")
        except Exception as e:
            logger.warning(f"Failed to retrieve storylines: {e}")

        # 3. 获取前置章节状态（如果有）
        if chapter_number > 1:
            try:
                prev_chapter = self.chapter_repo.get_by_number(novel_id, chapter_number - 1)
                if prev_chapter and hasattr(prev_chapter, 'state') and prev_chapter.state:
                    context["previous_chapter"] = {
                        "number": prev_chapter.chapter_number,
                        "title": prev_chapter.title,
                        "summary": getattr(prev_chapter.state, "summary", "")[:200]
                    }
                    logger.info(f"Retrieved previous chapter state")
            except Exception as e:
                logger.warning(f"Failed to retrieve previous chapter: {e}")

        # === 第二层：向量检索（Nice-to-Have） ===

        # 4. 向量检索相关伏笔（暂时跳过，需要集成 embedding_service）
        if self.vector_store and outline:
            try:
                # 注意：当前 ChromaDBVectorStore 需要 embedding_service 来转换文本
                # 这里暂时跳过向量检索，等待后续集成 embedding_service
                logger.info("Vector search for foreshadowings skipped (needs embedding service integration)")
            except Exception as e:
                logger.warning(f"Failed to retrieve foreshadowings: {e}")

        # 5. 向量检索相关地点（暂时跳过）
        if self.bible_service and self.vector_store and outline:
            try:
                logger.info("Vector search for locations skipped (needs embedding service integration)")
            except Exception as e:
                logger.warning(f"Failed to retrieve locations: {e}")

        # 6. 获取相关时间线事件
        try:
            from infrastructure.persistence.database.sqlite_timeline_repository import SqliteTimelineRepository
            from infrastructure.persistence.database.connection import get_database

            timeline_repo = SqliteTimelineRepository(get_database())
            timeline_registry = timeline_repo.get_by_novel_id(novel_id)

            if timeline_registry and timeline_registry.events:
                # 获取当前章节之前的最近 5 个事件
                recent_events = [
                    e for e in timeline_registry.events
                    if e.chapter_number < chapter_number
                ][-5:]

                context["timeline_events"] = [
                    {
                        "description": event.description,
                        "time_type": event.time_type,
                        "chapter": event.chapter_number
                    }
                    for event in recent_events
                ]

                if context["timeline_events"]:
                    logger.info(f"Retrieved {len(context['timeline_events'])} timeline events")
        except Exception as e:
            logger.warning(f"Failed to retrieve timeline events: {e}")

        # === 第三层：智能去重和 Tokens 控制 ===
        context = self._deduplicate_and_limit_tokens(context, max_tokens)

        return context

    def _deduplicate_and_limit_tokens(self, context: Dict, max_tokens: int) -> Dict:
        """智能去重和 tokens 控制

        1. 去重：移除重复的信息
        2. 优先级排序：Must-Have > Nice-to-Have
        3. Tokens 控制：粗略估算并截断

        Args:
            context: 原始上下文
            max_tokens: 最大 tokens 数

        Returns:
            处理后的上下文
        """
        # 粗略估算：1 token ≈ 1.5 字符（中文）
        def estimate_tokens(text: str) -> int:
            return int(len(text) / 1.5)

        def estimate_context_tokens(ctx: Dict) -> int:
            """估算上下文的 tokens 数"""
            total = 0
            total += sum(estimate_tokens(json.dumps(c, ensure_ascii=False)) for c in ctx.get("characters", []))
            total += sum(estimate_tokens(json.dumps(s, ensure_ascii=False)) for s in ctx.get("storylines", []))
            if ctx.get("previous_chapter"):
                total += estimate_tokens(json.dumps(ctx["previous_chapter"], ensure_ascii=False))
            total += sum(estimate_tokens(json.dumps(f, ensure_ascii=False)) for f in ctx.get("foreshadowings", []))
            total += sum(estimate_tokens(json.dumps(l, ensure_ascii=False)) for l in ctx.get("locations", []))
            total += sum(estimate_tokens(json.dumps(e, ensure_ascii=False)) for e in ctx.get("timeline_events", []))
            return total

        # 去重：移除描述相同的项
        def deduplicate_list(items: List[Dict], key: str = "description") -> List[Dict]:
            seen = set()
            result = []
            for item in items:
                value = item.get(key, "")
                if value and value not in seen:
                    seen.add(value)
                    result.append(item)
            return result

        context["foreshadowings"] = deduplicate_list(context.get("foreshadowings", []), "description")
        context["locations"] = deduplicate_list(context.get("locations", []), "name")
        context["timeline_events"] = deduplicate_list(context.get("timeline_events", []), "description")

        # Tokens 控制：如果超出限制，按优先级截断
        current_tokens = estimate_context_tokens(context)

        if current_tokens > max_tokens:
            logger.warning(f"Context tokens ({current_tokens}) exceeds limit ({max_tokens}), truncating...")

            # 优先级：characters > storylines > previous_chapter > foreshadowings > timeline_events > locations
            # 逐步削减低优先级内容

            # 1. 削减地点（最低优先级）
            while current_tokens > max_tokens and context.get("locations"):
                context["locations"].pop()
                current_tokens = estimate_context_tokens(context)

            # 2. 削减时间线事件
            while current_tokens > max_tokens and context.get("timeline_events"):
                context["timeline_events"].pop()
                current_tokens = estimate_context_tokens(context)

            # 3. 削减伏笔
            while current_tokens > max_tokens and context.get("foreshadowings"):
                context["foreshadowings"].pop()
                current_tokens = estimate_context_tokens(context)

            # 4. 削减故事线
            while current_tokens > max_tokens and len(context.get("storylines", [])) > 1:
                context["storylines"].pop()
                current_tokens = estimate_context_tokens(context)

            # 5. 截断前置章节摘要
            if current_tokens > max_tokens and context.get("previous_chapter"):
                summary = context["previous_chapter"].get("summary", "")
                if len(summary) > 100:
                    context["previous_chapter"]["summary"] = summary[:100] + "..."
                    current_tokens = estimate_context_tokens(context)

            logger.info(f"Context truncated to {current_tokens} tokens")

        return context

    def _build_beat_sheet_prompt(
        self,
        outline: str,
        context: Dict
    ) -> Prompt:
        """构建节拍表生成提示词（使用增强的上下文）"""

        system_prompt = """你是一位专业的小说编剧，擅长将章节大纲拆解为具体的场景（Scene）。

你的任务是将章节大纲拆解为 3-5 个场景，每个场景应该：
1. 有明确的场景目标（Scene Goal）
2. 指定 POV 角色（从哪个角色的视角叙述）
3. 指定地点（可选）
4. 指定情绪基调（例如：紧张、温馨、悲伤、激烈）
5. 预估字数（每个场景 500-1000 字）

请以 JSON 格式返回场景列表，格式如下：
{
  "scenes": [
    {
      "title": "场景标题",
      "goal": "这个场景要达成什么目标",
      "pov_character": "POV 角色名称",
      "location": "地点（可选）",
      "tone": "情绪基调",
      "estimated_words": 800
    }
  ]
}

注意事项：
- 场景之间要有逻辑连贯性
- 每个场景聚焦一个明确目标，避免贪多
- POV 角色应该是章节中的主要角色
- 预估字数总和应该在 2000-4000 字之间
- 充分利用提供的上下文信息（人物、故事线、伏笔、地点、时间线）
"""

        # 构建用户提示词
        user_prompt = f"""章节大纲：
{outline}

"""

        # 添加主要人物信息
        if context.get("characters"):
            user_prompt += "\n=== 主要人物 ===\n"
            for char in context["characters"]:
                user_prompt += f"- {char['name']} ({char['role']}): {char['brief']}\n"

        # 添加活跃故事线
        if context.get("storylines"):
            user_prompt += "\n=== 活跃故事线 ===\n"
            for sl in context["storylines"]:
                user_prompt += f"- {sl['name']} ({sl['type']}): {sl['progress']}\n"

        # 添加前置章节状态
        if context.get("previous_chapter"):
            prev = context["previous_chapter"]
            user_prompt += f"\n=== 前一章节 ===\n"
            user_prompt += f"第 {prev['number']} 章《{prev['title']}》: {prev['summary']}\n"

        # 添加相关伏笔
        if context.get("foreshadowings"):
            user_prompt += "\n=== 相关伏笔（可以在场景中呼应） ===\n"
            for foreshadowing in context["foreshadowings"]:
                user_prompt += f"- {foreshadowing['description']} (第 {foreshadowing['chapter']} 章)\n"

        # 添加相关地点
        if context.get("locations"):
            user_prompt += "\n=== 可用地点 ===\n"
            for loc in context["locations"]:
                user_prompt += f"- {loc['name']}: {loc['description']}\n"

        # 添加时间线事件
        if context.get("timeline_events"):
            user_prompt += "\n=== 时间线（最近事件） ===\n"
            for event in context["timeline_events"]:
                user_prompt += f"- 第 {event['chapter']} 章: {event['description']} ({event['time_type']})\n"

        user_prompt += "\n请基于以上信息生成场景列表（JSON 格式）："

        return Prompt(
            system=system_prompt,
            user=user_prompt
        )

    def _parse_llm_response(self, response) -> List[Scene]:
        """解析 LLM 响应，提取场景列表"""
        try:
            # 提取响应文本（处理 GenerationResult 对象）
            if hasattr(response, 'content'):
                response_text = response.content
            elif hasattr(response, 'text'):
                response_text = response.text
            else:
                response_text = str(response)

            # 尝试提取 JSON（可能被包裹在 markdown 代码块中）
            response_text = response_text.strip()
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]
            response_text = response_text.strip()

            data = json.loads(response_text)
            scenes_data = data.get("scenes", [])

            scenes = []
            for i, scene_data in enumerate(scenes_data):
                scene = Scene(
                    title=scene_data.get("title", f"场景 {i+1}"),
                    goal=scene_data.get("goal", ""),
                    pov_character=scene_data.get("pov_character", "未知"),
                    location=scene_data.get("location"),
                    tone=scene_data.get("tone"),
                    estimated_words=scene_data.get("estimated_words", 800),
                    order_index=i,
                    transition_from_prev=scene_data.get("transition_from_prev"),
                )
                scenes.append(scene)

            if not scenes:
                raise ValueError("No scenes generated")

            return scenes

        except Exception as e:
            logger.error(f"Failed to parse LLM response: {e}")
            logger.error(f"Response: {response_text if 'response_text' in locals() else response}")
            raise ValueError(f"Failed to parse beat sheet response: {e}")

    async def get_beat_sheet(self, chapter_id: str) -> Optional[BeatSheet]:
        """获取章节的节拍表"""
        return await self.beat_sheet_repo.get_by_chapter_id(chapter_id)

    async def delete_beat_sheet(self, chapter_id: str) -> None:
        """删除章节的节拍表"""
        await self.beat_sheet_repo.delete_by_chapter_id(chapter_id)
