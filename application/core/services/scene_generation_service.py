"""场景生成服务

为单个场景生成正文（500-1000 字）
"""

import logging
from typing import Dict, List, Optional, TYPE_CHECKING

from domain.novel.value_objects.scene import Scene
from domain.ai.services.llm_service import LLMService, GenerationConfig
from domain.ai.value_objects.prompt import Prompt
from application.engine.services.scene_director_service import SceneDirectorService

if TYPE_CHECKING:
    from infrastructure.ai.chromadb_vector_store import ChromaDBVectorStore

logger = logging.getLogger(__name__)


class SceneGenerationService:
    """场景生成服务

    为单个场景生成正文，集成：
    1. 场记分析（SceneDirectorAnalysis）
    2. 向量检索过滤上下文（POV 防火墙）
    3. 前置场景上下文（previous_scenes）
    4. LLM 生成正文
    """

    def __init__(
        self,
        llm_service: LLMService,
        scene_director: SceneDirectorService,
        vector_store: Optional["ChromaDBVectorStore"] = None,
        embedding_service=None,
    ):
        self.llm_service = llm_service
        self.scene_director = scene_director
        self.vector_store = vector_store
        self.embedding_service = embedding_service

    async def generate_scene(
        self,
        scene: Scene,
        chapter_number: int,
        previous_scenes: List[str],
        bible_context: Optional[Dict] = None
    ) -> str:
        """生成单个场景的正文

        Args:
            scene: 场景对象
            chapter_number: 章节号
            previous_scenes: 前置场景的正文列表
            bible_context: Bible 上下文（可选）

        Returns:
            生成的场景正文
        """
        logger.info(f"Generating scene: {scene.title} (POV: {scene.pov_character})")

        # 1. 场记分析
        scene_analysis = await self.scene_director.analyze(
            chapter_number=chapter_number,
            outline=f"{scene.title}\n{scene.goal}"
        )
        logger.debug(f"Scene analysis: characters={scene_analysis.characters}, "
                    f"locations={scene_analysis.locations}, pov={scene_analysis.pov}")

        # 2. 向量检索过滤上下文（POV 防火墙）
        relevant_context = await self._retrieve_relevant_context(
            scene=scene,
            scene_analysis=scene_analysis
        )

        # 3. 构建提示词
        prompt = self._build_scene_prompt(
            scene=scene,
            scene_analysis=scene_analysis,
            relevant_context=relevant_context,
            previous_scenes=previous_scenes,
            bible_context=bible_context
        )

        # 4. 生成正文
        config = GenerationConfig(max_tokens=2048, temperature=0.8)
        response = await self.llm_service.generate(prompt, config)

        # 提取响应文本
        if hasattr(response, 'content'):
            content = response.content
        elif hasattr(response, 'text'):
            content = response.text
        else:
            content = str(response)

        logger.info(f"Scene generated: {len(content)} characters")
        return content.strip()

    async def _retrieve_relevant_context(
        self,
        scene: Scene,
        scene_analysis
    ) -> Dict:
        """向量检索：获取与场景相关的上下文

        Phase 2.1 简化版：暂时返回空上下文
        """
        # TODO: 实现向量检索
        # - 检索相关人物信息（POV 防火墙）
        # - 检索相关地点信息
        # - 检索相关伏笔
        return {
            "characters": [],
            "locations": [],
            "foreshadowings": []
        }

    def _build_scene_prompt(
        self,
        scene: Scene,
        scene_analysis,
        relevant_context: Dict,
        previous_scenes: List[str],
        bible_context: Optional[Dict]
    ) -> Prompt:
        """构建场景生成提示词"""

        system_prompt = """你是一位专业的小说作家，擅长根据场景大纲生成生动的正文。

你的任务是根据场景信息生成 500-1000 字的正文，要求：
1. 严格遵循场景目标（Scene Goal）
2. 使用指定的 POV 角色视角叙述
3. 体现场景的情绪基调（Tone）
4. 与前置场景自然衔接
5. 文笔流畅，细节生动

注意事项：
- 不要偏离场景目标
- 不要引入场景大纲中未提及的重大情节
- 保持与前置场景的连贯性
- 字数控制在 500-1000 字之间
"""

        # 构建用户提示词
        user_prompt = f"""场景信息：
标题：{scene.title}
目标：{scene.goal}
POV 角色：{scene.pov_character}
地点：{scene.location or '未指定'}
情绪基调：{scene.tone or '未指定'}
预估字数：{scene.estimated_words}

"""

        # 添加场记分析结果
        if scene_analysis.characters:
            user_prompt += f"\n涉及角色：{', '.join(scene_analysis.characters)}"
        if scene_analysis.locations:
            user_prompt += f"\n涉及地点：{', '.join(scene_analysis.locations)}"
        if scene_analysis.emotional_state:
            user_prompt += f"\n情绪状态：{scene_analysis.emotional_state}"

        # 添加前置场景上下文
        if previous_scenes:
            user_prompt += "\n\n前置场景摘要：\n"
            for i, prev_scene in enumerate(previous_scenes[-2:], 1):  # 最多显示最近 2 个场景
                # 截取前 200 字作为摘要
                summary = prev_scene[:200] + "..." if len(prev_scene) > 200 else prev_scene
                user_prompt += f"\n场景 {i}：\n{summary}\n"

        # 添加相关上下文（如果有）
        if relevant_context.get("foreshadowings"):
            user_prompt += "\n\n相关伏笔（可以在场景中呼应）：\n"
            for foreshadowing in relevant_context["foreshadowings"][:3]:
                user_prompt += f"- {foreshadowing.get('description', 'N/A')}\n"

        user_prompt += "\n\n请生成场景正文："

        return Prompt(
            system=system_prompt,
            user=user_prompt
        )
